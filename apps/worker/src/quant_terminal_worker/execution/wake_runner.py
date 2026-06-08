from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from quant_terminal_worker.execution.bundle_loader import load_execution_bundle
from quant_terminal_worker.execution.live_signal_scan import scan_latest_live_signal


DEFAULT_ENTRY_ORDER_TTL_MINUTES = 30


def run_route_wake(
    *,
    route_id: str,
    repository: Any,
    adapter: Any,
    workspace_root: Path | None = None,
    entry_order_ttl_minutes: int = DEFAULT_ENTRY_ORDER_TTL_MINUTES,
    allow_entry_scan: bool = True,
    live_signal_scanner: Callable[..., dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    workspace = workspace_root or Path.cwd()
    route = repository.get_deployment_route(route_id)
    if route is None:
        raise ValueError(f"deployment route not found: {route_id}")

    started_at = datetime.now(UTC)
    wake_id = f"wake-{route_id}-{started_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    blockers = _route_blockers(route)
    if blockers:
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": route.get("active_bundle_id"),
                "status": "blocked",
                "branch": "route_gate",
                "blockers": blockers,
                "exchange_snapshot": {},
                "signal_scan_result": {
                    "status": "not_run",
                    "reason": "route or adapter gates blocked wake",
                },
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": [],
                "error": {},
                "completed_at": datetime.now(UTC),
            },
        )

    adapter_blockers = list(adapter.readiness_blockers()) if hasattr(adapter, "readiness_blockers") else []
    if adapter_blockers:
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": route.get("active_bundle_id"),
                "status": "blocked",
                "branch": "route_gate",
                "blockers": adapter_blockers,
                "exchange_snapshot": {},
                "signal_scan_result": {
                    "status": "not_run",
                    "reason": "adapter gates blocked wake",
                },
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": [],
                "error": {},
                "completed_at": datetime.now(UTC),
            },
        )

    bundle = route.get("active_bundle")
    if bundle is None and route.get("active_bundle_id"):
        bundle = repository.get_execution_bundle(route["active_bundle_id"])
    if bundle is None:
        return _record_wake(
            repository,
            _error_wake(
                wake_id=wake_id,
                route=route,
                message="active execution bundle not found",
            ),
        )

    runtime = load_execution_bundle(bundle, workspace_root=workspace)
    try:
        snapshot = adapter.snapshot(route["instrument"])
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        return _record_wake(
            repository,
            _error_wake(
                wake_id=wake_id,
                route=route,
                message=str(exc),
                bundle_id=bundle["bundle_id"],
            ),
        )

    positions = _active_positions(snapshot)
    adapter_results = []
    working_entry_orders = _working_entry_orders(snapshot)
    if positions:
        fresh_working_entry_orders = [
            order
            for order in working_entry_orders
            if _order_age_minutes(order) < entry_order_ttl_minutes
        ]
        fresh_order_ids = {id(order) for order in fresh_working_entry_orders}
        for order in working_entry_orders:
            if id(order) in fresh_order_ids:
                continue
            order_id = str(order.get("ordId") or order.get("order_id") or "")
            client_order_id = str(order.get("clOrdId") or order.get("client_order_id") or "")
            if hasattr(adapter, "cancel_order") and (order_id or client_order_id):
                adapter_results.append(
                    adapter.cancel_order(
                        instrument=route["instrument"],
                        order_id=order_id or None,
                        client_order_id=client_order_id or None,
                    )
                )
        owner_state = repository.get_open_owner_state(route_id)
        owner_state = _reconcile_owner_state(
            repository=repository,
            owner_state=owner_state,
            position=positions[0],
            snapshot=snapshot,
        )
        decision = _run_position_management(
            runtime=runtime,
            route=route,
            snapshot=snapshot,
            owner_state=owner_state,
            position=positions[0],
            working_entry_orders=fresh_working_entry_orders,
            now=started_at,
        )
        position_intents = _normalize_strategy_order_intents(
            wake_id=wake_id,
            route=route,
            signal=None,
            decision=decision,
            execution_setup=runtime["execution_setup"],
            snapshot=snapshot,
        )
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": bundle["bundle_id"],
                "status": "completed",
                "branch": "position_management",
                "blockers": [],
                "exchange_snapshot": snapshot,
                "signal_scan_result": {"status": "skipped_position_open"},
                "strategy_decision": decision,
                "order_intents": position_intents,
                "adapter_results": adapter_results,
                "error": {},
                "completed_at": datetime.now(UTC),
            },
        )

    open_owner_state = repository.get_open_owner_state(route_id)
    if open_owner_state is not None and not working_entry_orders and hasattr(repository, "close_open_owner_state"):
        repository.close_open_owner_state(route_id, reason="exchange_position_flat")

    fresh_orders = [
        order
        for order in working_entry_orders
        if _order_age_minutes(order) < entry_order_ttl_minutes
    ]
    if fresh_orders:
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": bundle["bundle_id"],
                "status": "completed",
                "branch": "idle",
                "blockers": [],
                "exchange_snapshot": snapshot,
                "signal_scan_result": {
                    "status": "fresh_entry_order_exists",
                    "order_count": len(fresh_orders),
                },
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": [],
                "error": {},
                "completed_at": datetime.now(UTC),
            },
        )

    for order in working_entry_orders:
        order_id = str(order.get("ordId") or order.get("order_id") or "")
        client_order_id = str(order.get("clOrdId") or order.get("client_order_id") or "")
        if hasattr(adapter, "cancel_order") and (order_id or client_order_id):
            adapter_results.append(
                adapter.cancel_order(
                    instrument=route["instrument"],
                    order_id=order_id or None,
                    client_order_id=client_order_id or None,
                )
            )

    if not allow_entry_scan:
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": bundle["bundle_id"],
                "status": "blocked",
                "branch": "entry_scan",
                "blockers": ["signal_update_failed"],
                "exchange_snapshot": snapshot,
                "signal_scan_result": {"status": "blocked", "reason": "signal_update_failed"},
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": adapter_results,
                "error": {"message": "signal update failed before entry scan"},
                "completed_at": datetime.now(UTC),
            },
        )

    scanner = live_signal_scanner or scan_latest_live_signal
    try:
        signal = scanner(route=route, repository=repository, workspace_root=workspace)
    except ValueError as exc:
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": bundle["bundle_id"],
                "status": "blocked",
                "branch": "entry_scan",
                "blockers": ["live_signal_scan_failed"],
                "exchange_snapshot": snapshot,
                "signal_scan_result": {"status": "blocked", "reason": "live_signal_scan_failed"},
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": adapter_results,
                "error": {"message": str(exc)},
                "completed_at": datetime.now(UTC),
            },
        )
    if signal is None:
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": bundle["bundle_id"],
                "status": "completed",
                "branch": "idle",
                "blockers": [],
                "exchange_snapshot": snapshot,
                "signal_scan_result": {"status": "no_fresh_signal"},
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": adapter_results,
                "error": {},
                "completed_at": datetime.now(UTC),
            },
        )
    signal_scan_result = _fresh_signal_scan_result(signal)
    if _has_live_entry_for_signal(repository=repository, route_id=route_id, signal_id=signal["signal_id"]):
        return _record_wake(
            repository,
            {
                "wake_id": wake_id,
                "route_id": route_id,
                "bundle_id": bundle["bundle_id"],
                "status": "completed",
                "branch": "idle",
                "blockers": [],
                "exchange_snapshot": snapshot,
                "signal_scan_result": {**signal_scan_result, "status": "duplicate_live_signal"},
                "strategy_decision": {},
                "order_intents": [],
                "adapter_results": adapter_results,
                "error": {},
                "completed_at": datetime.now(UTC),
            },
        )

    decision = _run_entry_decision(runtime=runtime, route=route, signal=signal, snapshot=snapshot)
    order_intents = _normalize_strategy_order_intents(
        wake_id=wake_id,
        route=route,
        signal=signal,
        decision=decision,
        execution_setup=runtime["execution_setup"],
        snapshot=snapshot,
    )
    wake = {
        "wake_id": wake_id,
        "route_id": route_id,
        "bundle_id": bundle["bundle_id"],
        "status": "completed",
        "branch": "entry_scan",
        "blockers": [],
        "exchange_snapshot": snapshot,
        "signal_scan_result": signal_scan_result,
        "strategy_decision": decision,
        "order_intents": order_intents,
        "adapter_results": adapter_results,
        "error": {},
        "completed_at": datetime.now(UTC),
    }
    return _record_wake(repository, wake)


def _route_blockers(route: dict[str, Any]) -> list[str]:
    blockers = list(route.get("blockers") or [])
    if blockers:
        return blockers
    if not route.get("enabled"):
        blockers.append("route_disabled")
    if not route.get("active_bundle_id"):
        blockers.append("missing_active_bundle")
    if not route.get("promoted"):
        blockers.append("route_not_promoted")
    if not route.get("data_warmed"):
        blockers.append("data_not_warmed")
    if route.get("account_mode") == "live" and not route.get("manually_armed"):
        blockers.append("route_not_manually_armed")
    return blockers


def _record_wake(repository: Any, wake: dict[str, Any]) -> dict[str, Any]:
    return repository.record_wake_run(wake)


def _error_wake(
    *,
    wake_id: str,
    route: dict[str, Any],
    message: str,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    return {
        "wake_id": wake_id,
        "route_id": route["route_id"],
        "bundle_id": bundle_id or route.get("active_bundle_id"),
        "status": "error",
        "branch": "error",
        "blockers": [],
        "exchange_snapshot": {},
        "signal_scan_result": {},
        "strategy_decision": {},
        "order_intents": [],
        "adapter_results": [],
        "error": {"message": message},
        "completed_at": datetime.now(UTC),
    }


def _active_positions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    positions = snapshot.get("positions") or []
    return [position for position in positions if _numeric(position.get("pos") or position.get("size") or position.get("sz")) != 0]


def _working_entry_orders(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    orders = snapshot.get("open_orders") or []
    return [order for order in orders if not _truthy(order.get("reduceOnly") or order.get("reduce_only"))]


def _order_age_minutes(order: dict[str, Any]) -> float:
    if order.get("age_minutes") is not None:
        return float(order["age_minutes"])
    created = order.get("created_at") or order.get("cTime")
    if created is None:
        return 0.0
    try:
        if isinstance(created, (int, float)) or str(created).isdigit():
            created_at = datetime.fromtimestamp(float(created) / 1000, tz=UTC)
        else:
            created_at = datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(UTC) - created_at).total_seconds() / 60)


def _fresh_signal_scan_result(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "fresh_signal",
        "signal_id": signal["signal_id"],
        "signal_timestamp": _iso_timestamp(signal.get("timestamp")),
        "signal_engine_id": signal.get("signal_engine_id"),
        "asset": signal.get("asset"),
        "source": "live_parquet_snapshot",
    }


def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        timestamp = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return timestamp.isoformat().replace("+00:00", "Z")
    return str(value)


def _has_live_entry_for_signal(*, repository: Any, route_id: str, signal_id: str) -> bool:
    if hasattr(repository, "has_live_entry_for_signal"):
        return bool(repository.has_live_entry_for_signal(route_id=route_id, signal_id=signal_id))
    wakes = repository.list_wake_runs(route_id, limit=25) if hasattr(repository, "list_wake_runs") else []
    for wake in wakes:
        scan = wake.get("signal_scan_result") if isinstance(wake.get("signal_scan_result"), dict) else {}
        if scan.get("signal_id") != signal_id:
            continue
        for intent in wake.get("order_intents") or []:
            if _canonical_action(intent.get("action")) in {"ENTER", "ENTER_LONG", "ENTER_SHORT"}:
                return True
    return False


def _run_entry_decision(
    *,
    runtime: dict[str, Any],
    route: dict[str, Any],
    signal: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    module = runtime["strategy_module"]
    if not hasattr(module, "decide"):
        return {
            "action": "SKIP",
            "trade_action": "SKIP",
            "direction": "FLAT",
            "reason_code": "strategy_missing_decide",
            "signal_id": signal["signal_id"],
            "order_intents": [],
        }
    raw = module.decide(
        {
            "signal": signal,
            "runtime_mode": route.get("account_mode", "live"),
            "execution_setup": runtime["execution_setup"],
            "exchange_snapshot": snapshot,
            "portfolio_state": snapshot,
        }
    )
    action = _canonical_action(raw.get("action") or raw.get("trade_action") or "SKIP")
    direction = raw.get("direction") or _direction_from_action(action) or "FLAT"
    return {
        **raw,
        "action": action,
        "trade_action": raw.get("trade_action", action),
        "direction": str(direction).upper(),
        "signal_id": raw.get("signal_id", signal["signal_id"]),
        "decision_id": raw.get("decision_id") or f"{route['route_id']}:{signal['signal_id']}",
    }


def _run_position_management(
    *,
    runtime: dict[str, Any],
    route: dict[str, Any],
    snapshot: dict[str, Any],
    owner_state: dict[str, Any] | None,
    position: dict[str, Any],
    working_entry_orders: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    module = runtime["strategy_module"]
    position_context = _position_context(
        position=position,
        execution_setup=runtime["execution_setup"],
        now=now,
        owner_state=owner_state,
    )
    if not hasattr(module, "manage_position"):
        decision = _default_protection_decision(
            route=route,
            position_context=position_context,
            snapshot=snapshot,
            execution_setup=runtime["execution_setup"],
            owner_state=owner_state,
        ) or {
            "decision_id": f"{route['route_id']}:position-management",
            "action": "HOLD",
            "reason_code": "strategy_missing_manage_position",
            "order_intents": [],
            "diagnostics": {"position_context": position_context},
        }
        gated = _apply_hard_time_gate(route=route, decision=decision, position_context=position_context)
        return _apply_pyramid_management(
            route=route,
            decision=gated,
            position_context=position_context,
            owner_state=owner_state,
            execution_setup=runtime["execution_setup"],
            working_entry_orders=working_entry_orders,
        )
    raw = module.manage_position(
        {
            "runtime_mode": route.get("account_mode", "live"),
            "execution_setup": runtime["execution_setup"],
            "exchange_snapshot": snapshot,
            "owner_state": owner_state or {},
            "position_context": position_context,
            "portfolio_state": snapshot,
        }
    )
    action = _canonical_action(raw.get("action", "HOLD"))
    decision = {
        "decision_id": raw.get("decision_id") or f"{route['route_id']}:position-management",
        "action": action,
        "reason_code": raw.get("reason_code", "position_management"),
        "order_intents": raw.get("order_intents", []),
        "quantity": raw.get("quantity"),
        "notional_usd": raw.get("notional_usd"),
        "side": raw.get("side"),
        "direction": raw.get("direction"),
        "order_type": raw.get("order_type"),
        "price": raw.get("price"),
        "tp": raw.get("tp"),
        "sl": raw.get("sl"),
        "tp_pct": raw.get("tp_pct"),
        "sl_pct": raw.get("sl_pct"),
        "reduce_only": raw.get("reduce_only"),
        "diagnostics": raw.get("diagnostics", {}),
    }
    if _canonical_action(decision.get("action")) == "HOLD":
        decision = _default_protection_decision(
            route=route,
            position_context=position_context,
            snapshot=snapshot,
            execution_setup=runtime["execution_setup"],
            owner_state=owner_state,
        ) or decision
    gated = _apply_hard_time_gate(route=route, decision=decision, position_context=position_context)
    return _apply_pyramid_management(
        route=route,
        decision=gated,
        position_context=position_context,
        owner_state=owner_state,
        execution_setup=runtime["execution_setup"],
        working_entry_orders=working_entry_orders,
    )


def _default_protection_decision(
    *,
    route: dict[str, Any],
    position_context: dict[str, Any],
    snapshot: dict[str, Any],
    execution_setup: dict[str, Any],
    owner_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    setup = execution_setup.get("setup") if isinstance(execution_setup.get("setup"), dict) else execution_setup
    tp_pct = _numeric(setup.get("tp_pct"))
    sl_pct = _numeric(setup.get("sl_pct"))
    entry_price = _numeric(position_context.get("entry_price"))
    size = _numeric(position_context.get("size"))
    if tp_pct <= 0 or sl_pct <= 0 or entry_price <= 0 or size <= 0:
        return None

    direction = str(position_context.get("direction") or "LONG").upper()
    tp, sl = _protection_prices(entry_price=entry_price, direction=direction, tp_pct=tp_pct, sl_pct=sl_pct)
    expected_side = "sell" if direction == "LONG" else "buy"
    protection_state = _protection_state(snapshot=snapshot, instrument=route["instrument"])
    position_state = dict(owner_state.get("position_state") or {}) if owner_state else {}
    refresh_required = _truthy(position_state.get("protection_refresh_required"))
    if not refresh_required and protection_state["has_single_live"] and _protection_matches(
        protection_state["orders"][0],
        side=expected_side,
        size=_format_decimal(size),
        tp=tp,
        sl=sl,
    ):
        return None

    return {
        "decision_id": f"{route['route_id']}:bundle-protection",
        "action": "UPDATE_PROTECTION",
        "reason_code": "bundle_protection_refresh",
        "order_intents": [],
        "quantity": _format_decimal(size),
        "notional_usd": None,
        "side": expected_side,
        "direction": direction,
        "order_type": "market",
        "price": None,
        "tp": tp,
        "sl": sl,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "reduce_only": True,
        "diagnostics": {
            "entry_price": _format_decimal(entry_price),
            "protection_refresh_required": refresh_required,
            "live_protection_count": protection_state["live_count"],
        },
    }


def _apply_hard_time_gate(
    *,
    route: dict[str, Any],
    decision: dict[str, Any],
    position_context: dict[str, Any],
) -> dict[str, Any]:
    hard_exit_after_hours = _numeric(position_context.get("hard_exit_after_hours"))
    age_hours = _numeric(position_context.get("age_hours"))
    action = _canonical_action(decision.get("action"))
    if hard_exit_after_hours <= 0 or age_hours < hard_exit_after_hours or action in {"EXIT", "REDUCE"}:
        return decision
    direction = str(position_context.get("direction") or "LONG").upper()
    diagnostics = dict(decision.get("diagnostics") or {})
    diagnostics.update(
        {
            "position_age_hours": age_hours,
            "hard_exit_after_hours": hard_exit_after_hours,
            "strategy_decision_before_gate": decision,
        }
    )
    return {
        **decision,
        "decision_id": decision.get("decision_id") or f"{route['route_id']}:position-management",
        "action": "EXIT",
        "reason_code": "hard_time_gate_expired",
        "order_intents": [],
        "quantity": position_context["size"],
        "notional_usd": None,
        "side": "sell" if direction == "LONG" else "buy",
        "direction": direction,
        "order_type": "market",
        "price": None,
        "reduce_only": True,
        "diagnostics": diagnostics,
    }


def _position_context(
    *,
    position: dict[str, Any],
    execution_setup: dict[str, Any],
    now: datetime,
    owner_state: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_size = _numeric(position.get("pos") or position.get("size") or position.get("sz"))
    direction = _position_direction(position, raw_size=raw_size)
    opened_at = _position_opened_at(position, owner_state=owner_state)
    age_hours = None
    if opened_at is not None:
        age_hours = max(0.0, (now - opened_at).total_seconds() / 3600)
    return {
        "instrument": position.get("instId") or position.get("instrument"),
        "direction": direction,
        "side": "long" if direction == "LONG" else "short",
        "size": _format_decimal(abs(raw_size)),
        "raw_size": _format_decimal(raw_size),
        "entry_price": _first_present(position, "avgPx", "avg_price", "entry_price", "openAvgPx"),
        "mark_price": _first_present(position, "markPx", "mark_price"),
        "last_price": _first_present(position, "last", "lastPx", "last_price"),
        "opened_at": opened_at.isoformat().replace("+00:00", "Z") if opened_at else None,
        "age_hours": age_hours,
        "hard_exit_after_hours": _hard_exit_after_hours(execution_setup),
        "pyramid": _pyramid_context(
            execution_setup=execution_setup,
            owner_state=owner_state,
            position=position,
            position_context_base={
                "direction": direction,
                "entry_price": _first_present(position, "avgPx", "avg_price", "entry_price", "openAvgPx"),
            },
            route=None,
            working_entry_orders=[],
        ),
    }


def _reconcile_owner_state(
    *,
    repository: Any,
    owner_state: dict[str, Any] | None,
    position: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    if owner_state is None:
        return None
    position_state = dict(owner_state.get("position_state") or {})
    legs = [dict(leg) for leg in position_state.get("legs") or []]
    if not legs:
        return owner_state
    open_orders = snapshot.get("open_orders") or []
    recent_fills = snapshot.get("recent_fills") or []
    changed = False
    for index, leg in enumerate(legs):
        status = str(leg.get("status") or "submitted").lower()
        if status in {"filled", "cancelled", "canceled", "failed", "rejected"}:
            continue
        fill = _matching_exchange_row(leg, recent_fills)
        if fill is not None:
            changed = _apply_fill_or_terminal_row(leg, fill) or changed
            continue
        open_order = _matching_exchange_row(leg, open_orders)
        if open_order is not None:
            before = dict(leg)
            if status != "working":
                leg["status"] = "working"
            _copy_exchange_ids(leg, open_order)
            changed = (leg != before) or changed
            continue
        if index == 0:
            entry_price = _first_present(position, "avgPx", "avg_price", "entry_price", "openAvgPx")
            if entry_price not in (None, ""):
                leg["status"] = "filled"
                leg["entry_price"] = str(entry_price)
                leg["fill_source"] = "live_position"
                changed = True
    if not changed:
        return owner_state
    position_state["legs"] = legs
    if hasattr(repository, "update_owner_state"):
        return repository.update_owner_state(owner_state["owner_state_id"], position_state=position_state)
    return {**owner_state, "position_state": position_state}


def _matching_exchange_row(leg: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    leg_ids = _exchange_identifiers(leg)
    if not leg_ids:
        return None
    for row in rows:
        if leg_ids.intersection(_exchange_identifiers(row)):
            return row
    return None


def _exchange_identifiers(row: dict[str, Any]) -> set[str]:
    identifiers = set()
    for key in (
        "client_order_id",
        "exchange_client_order_id",
        "clOrdId",
        "cl_order_id",
        "ordId",
        "order_id",
        "orderId",
        "exchange_order_id",
    ):
        value = row.get(key)
        if value not in (None, ""):
            identifiers.add(str(value))
    return identifiers


def _apply_fill_or_terminal_row(leg: dict[str, Any], row: dict[str, Any]) -> bool:
    status = _exchange_row_status(row)
    before = dict(leg)
    _copy_exchange_ids(leg, row)
    if status in {"cancelled", "canceled"}:
        leg["status"] = "cancelled"
        leg["cancelled_at"] = _exchange_time(row)
        return leg != before
    if status in {"failed", "rejected"}:
        leg["status"] = "failed"
        leg["failed_at"] = _exchange_time(row)
        return leg != before
    fill_price = _first_present(row, "fillPx", "fill_px", "avgPx", "avg_price", "px", "price")
    if fill_price not in (None, "") or status in {"filled", "partially_filled", "partially-filled"}:
        leg["status"] = "filled"
        if fill_price not in (None, ""):
            leg["entry_price"] = str(fill_price)
        fill_size = _first_present(row, "fillSz", "fill_size", "accFillSz", "acc_fill_sz", "sz", "size")
        if fill_size not in (None, ""):
            leg["filled_size"] = str(fill_size)
        fill_time = _exchange_time(row)
        if fill_time is not None:
            leg["filled_at"] = fill_time
        leg["fill_source"] = "exchange_fill"
    return leg != before


def _copy_exchange_ids(leg: dict[str, Any], row: dict[str, Any]) -> None:
    order_id = _first_present(row, "ordId", "order_id", "orderId", "exchange_order_id")
    client_order_id = _first_present(row, "clOrdId", "exchange_client_order_id", "client_order_id", "cl_order_id")
    if order_id not in (None, ""):
        leg["exchange_order_id"] = str(order_id)
    if client_order_id not in (None, ""):
        leg["exchange_client_order_id"] = str(client_order_id)


def _exchange_row_status(row: dict[str, Any]) -> str:
    return str(_first_present(row, "state", "status", "order_state") or "").lower()


def _exchange_time(row: dict[str, Any]) -> str | None:
    value = _first_present(row, "fillTime", "fill_time", "uTime", "updated_at", "cTime", "created_at")
    parsed = _parse_datetime(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else str(value) if value not in (None, "") else None


def _apply_pyramid_management(
    *,
    route: dict[str, Any],
    decision: dict[str, Any],
    position_context: dict[str, Any],
    owner_state: dict[str, Any] | None,
    execution_setup: dict[str, Any],
    working_entry_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    pyramid_context = _pyramid_context(
        execution_setup=execution_setup,
        owner_state=owner_state,
        position={},
        position_context_base=position_context,
        route=route,
        working_entry_orders=working_entry_orders,
    )
    diagnostics = dict(decision.get("diagnostics") or {})
    diagnostics["pyramid"] = pyramid_context
    action = _canonical_action(decision.get("action"))
    if action in {"EXIT", "REDUCE", "PYRAMID", "UPDATE_PROTECTION", "BLOCKED"}:
        return {**decision, "diagnostics": diagnostics}
    if not pyramid_context["eligible"] or not pyramid_context["trigger_reached"]:
        return {**decision, "diagnostics": diagnostics}
    direction = str(position_context.get("direction") or pyramid_context.get("direction") or "LONG").upper()
    return {
        **decision,
        "action": "PYRAMID",
        "reason_code": "pyramid_trigger_reached",
        "order_intents": [],
        "quantity": None,
        "notional_usd": None,
        "side": "buy" if direction == "LONG" else "sell",
        "direction": direction,
        "order_type": "market",
        "price": None,
        "reduce_only": False,
        "position_instance_id": pyramid_context["position_instance_id"],
        "pyramid_leg": pyramid_context["next_leg"],
        "trigger_price": pyramid_context["trigger_price"],
        "last_leg_entry": pyramid_context["last_leg_entry"],
        "diagnostics": diagnostics,
    }


def _pyramid_context(
    *,
    execution_setup: dict[str, Any],
    owner_state: dict[str, Any] | None,
    position: dict[str, Any],
    position_context_base: dict[str, Any],
    route: dict[str, Any] | None,
    working_entry_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    setup = execution_setup.get("setup") if isinstance(execution_setup.get("setup"), dict) else execution_setup
    pyramid_setup = setup.get("pyramid") if isinstance(setup.get("pyramid"), dict) else {}
    step_pct = _numeric(pyramid_setup.get("step_pct") or setup.get("pyramid_step_pct"))
    max_legs = _pyramid_max_legs(execution_setup)
    sl_breakeven = _truthy(pyramid_setup.get("sl_breakeven") or setup.get("sl_breakeven"))
    position_state = dict(owner_state.get("position_state") or {}) if owner_state else {}
    direction = str(position_state.get("direction") or position_context_base.get("direction") or "LONG").upper()
    all_legs = [dict(leg) for leg in position_state.get("legs") or []]
    filled_leg_rows = [
        dict(leg)
        for leg in all_legs
        if str(leg.get("status") or "submitted").lower() == "filled"
    ]
    pending_leg_rows = [
        dict(leg)
        for leg in all_legs
        if str(leg.get("status") or "submitted").lower() in {"submitted", "working", "open", "partially_filled", "partially-filled"}
    ]
    filled_legs = len(filled_leg_rows)
    pending_legs = len(pending_leg_rows)
    active_leg_count = filled_legs + pending_legs
    last_leg = filled_leg_rows[-1] if filled_leg_rows else {}
    last_leg_entry = _numeric(
        last_leg.get("entry_price")
        or last_leg.get("entry")
        or last_leg.get("last_leg_entry")
        or position_context_base.get("entry_price")
    )
    trigger_source = "mark"
    trigger_price = _numeric(position_context_base.get("mark_price") or _first_present(position, "markPx", "mark_price"))
    if trigger_price <= 0:
        trigger_source = "last"
        trigger_price = _numeric(position_context_base.get("last_price") or _first_present(position, "last", "lastPx", "last_price"))
    next_trigger_price = None
    if last_leg_entry > 0 and step_pct > 0:
        if direction == "SHORT":
            next_trigger_price = last_leg_entry * (1 - step_pct / 100)
        else:
            next_trigger_price = last_leg_entry * (1 + step_pct / 100)
        next_trigger_price = _rounded_number(next_trigger_price)
    blockers: list[str] = []
    if owner_state is None:
        blockers.append("missing_owner_state")
    elif route is not None and owner_state.get("bundle_id") != route.get("active_bundle_id"):
        blockers.append("bundle_mismatch")
    if step_pct <= 0:
        blockers.append("missing_pyramid_step_pct")
    if active_leg_count >= max_legs:
        blockers.append("max_legs_reached")
    if pending_legs > 0:
        blockers.append("pending_pyramid_leg_exists")
    if last_leg_entry <= 0:
        blockers.append("missing_last_leg_entry")
    if trigger_price <= 0:
        blockers.append("missing_trigger_price")
    if working_entry_orders:
        blockers.append("working_add_order_exists")
    trigger_reached = False
    if not blockers and next_trigger_price is not None:
        trigger_reached = trigger_price <= next_trigger_price if direction == "SHORT" else trigger_price >= next_trigger_price
    return {
        "step_pct": _rounded_number(step_pct) if step_pct > 0 else None,
        "max_legs": max_legs,
        "sl_breakeven": sl_breakeven,
        "filled_legs": filled_legs,
        "pending_legs": pending_legs,
        "active_legs": active_leg_count,
        "next_leg": filled_legs + 1,
        "last_leg_entry": _rounded_number(last_leg_entry) if last_leg_entry > 0 else None,
        "next_trigger_price": next_trigger_price,
        "trigger_price": _rounded_number(trigger_price) if trigger_price > 0 else None,
        "trigger_source": trigger_source if trigger_price > 0 else None,
        "trigger_reached": trigger_reached,
        "eligible": not blockers,
        "blockers": blockers,
        "position_instance_id": owner_state.get("position_instance_id") if owner_state else None,
        "direction": direction,
    }


def _position_direction(position: dict[str, Any], *, raw_size: float) -> str:
    side = str(position.get("posSide") or position.get("position_side") or position.get("side") or "").lower()
    if side in {"short", "sell"}:
        return "SHORT"
    if side in {"long", "buy"}:
        return "LONG"
    return "SHORT" if raw_size < 0 else "LONG"


def _position_opened_at(position: dict[str, Any], *, owner_state: dict[str, Any] | None) -> datetime | None:
    value = _first_present(position, "opened_at", "open_time", "cTime", "created_at", "uTime")
    if value is None and owner_state:
        value = _first_present(owner_state, "opened_at", "created_at")
    return _parse_datetime(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _hard_exit_after_hours(execution_setup: dict[str, Any]) -> float | None:
    setup = execution_setup.get("setup") if isinstance(execution_setup.get("setup"), dict) else {}
    value = (
        execution_setup.get("hard_exit_after_hours")
        or execution_setup.get("forward_hours")
        or execution_setup.get("max_hold_hours")
        or setup.get("hard_exit_after_hours")
        or setup.get("forward_hours")
        or setup.get("max_hold_hours")
    )
    if value is None:
        return None
    return _numeric(value)


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping[key]
    return None


def _normalize_strategy_order_intents(
    *,
    wake_id: str,
    route: dict[str, Any],
    signal: dict[str, Any] | None,
    decision: dict[str, Any],
    execution_setup: dict[str, Any],
    snapshot: dict[str, Any],
 ) -> list[dict[str, Any]]:
    explicit_intents = decision.get("order_intents")
    if isinstance(explicit_intents, list) and explicit_intents:
        return [
            _coerce_order_intent(
                wake_id=wake_id,
                route=route,
                signal=signal,
                decision=decision,
                execution_setup=execution_setup,
                snapshot=snapshot,
                intent=intent,
                index=index,
            )
            for index, intent in enumerate(explicit_intents)
        ]
    action = _canonical_action(decision.get("action") or decision.get("trade_action") or "SKIP")
    if action not in {"ENTER", "ENTER_LONG", "ENTER_SHORT", "EXIT", "REDUCE", "PYRAMID", "UPDATE_PROTECTION"}:
        return []
    return [
        _coerce_order_intent(
            wake_id=wake_id,
            route=route,
            signal=signal,
            decision=decision,
            execution_setup=execution_setup,
            snapshot=snapshot,
            intent={},
            index=0,
        )
    ]


def _coerce_order_intent(
    *,
    wake_id: str,
    route: dict[str, Any],
    signal: dict[str, Any] | None,
    decision: dict[str, Any],
    execution_setup: dict[str, Any],
    snapshot: dict[str, Any],
    intent: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    setup = execution_setup.get("setup") if isinstance(execution_setup.get("setup"), dict) else execution_setup
    action = _canonical_action(intent.get("action") or decision.get("action") or decision.get("trade_action") or "SKIP")
    direction = str(intent.get("direction") or decision.get("direction") or _direction_from_action(action) or "LONG").upper()
    side = str(intent.get("side") or decision.get("side") or _side_for_action(action=action, direction=direction)).lower()
    client_order_id = f"motis-{route['route_id']}-{wake_id}-{index}"
    quantity = (
        intent.get("quantity")
        or intent.get("order_quantity")
        or decision.get("quantity")
        or decision.get("order_quantity")
        or setup.get("position_quantity")
        or setup.get("quantity")
        or "0"
    )
    notional_usd = (
        intent.get("notional_usd")
        or intent.get("position_notional_usd")
        or decision.get("notional_usd")
        or decision.get("position_notional_usd")
        or setup.get("position_notional_usd")
        or setup.get("notional_usd")
    )
    route_sizing = _route_margin_sizing(route=route, execution_setup=execution_setup, snapshot=snapshot, action=action)
    if route_sizing is not None:
        quantity = route_sizing["margin_usd"]
        notional_usd = route_sizing["notional_usd"]
    target_currency = (
        intent.get("target_currency")
        or intent.get("tgt_ccy")
        or decision.get("target_currency")
        or decision.get("tgt_ccy")
        or setup.get("target_currency")
        or setup.get("tgt_ccy")
    )
    leverage = intent.get("leverage") or decision.get("leverage") or setup.get("leverage")
    if route_sizing is not None:
        target_currency = "margin"
        leverage = route_sizing["leverage"]
    order_intent = {
        "intent_id": f"{wake_id}:{index}",
        "route_id": route["route_id"],
        "asset": route["asset"],
        "instrument": route["instrument"],
        "signal_id": signal["signal_id"] if signal else None,
        "action": action,
        "side": side,
        "direction": direction,
        "order_type": intent.get("order_type") or decision.get("order_type") or setup.get("entry_model", "market"),
        "quantity": str(quantity),
        "notional_usd": notional_usd,
        "trade_mode": intent.get("trade_mode") or decision.get("trade_mode") or setup.get("trade_mode", "isolated"),
        "target_currency": target_currency,
        "leverage": leverage,
        "price": intent.get("price") or decision.get("price"),
        "tp": intent.get("tp") or decision.get("tp"),
        "sl": intent.get("sl") or decision.get("sl"),
        "tp_pct": intent.get("tp_pct") or decision.get("tp_pct") or setup.get("tp_pct"),
        "sl_pct": intent.get("sl_pct") or decision.get("sl_pct") or setup.get("sl_pct"),
        "reduce_only": _truthy(intent.get("reduce_only") if "reduce_only" in intent else _default_reduce_only(action)),
        "client_order_id": str(intent.get("client_order_id") or client_order_id)[:64],
        "status": intent.get("status") or "intent_only",
    }
    for key in ("position_instance_id", "pyramid_leg", "trigger_price", "last_leg_entry"):
        value = intent.get(key) if key in intent else decision.get(key)
        if value not in (None, ""):
            order_intent[key] = value
    if route_sizing is not None:
        order_intent.update(
            {
                "sizing_source": "route_margin_allocation",
                "account_equity_usd": route_sizing["account_equity_usd"],
                "margin_allocation_pct": route_sizing["margin_allocation_pct"],
                "pyramid_max_legs": route_sizing["pyramid_max_legs"],
                "margin_usd": route_sizing["margin_usd"],
            }
        )
    return order_intent


def _route_margin_sizing(
    *,
    route: dict[str, Any],
    execution_setup: dict[str, Any],
    snapshot: dict[str, Any],
    action: str,
) -> dict[str, Any] | None:
    if action not in {"ENTER", "ENTER_LONG", "ENTER_SHORT", "PYRAMID"}:
        return None
    margin_allocation_pct = _numeric(route.get("margin_allocation_pct"))
    leverage = _numeric(route.get("leverage"))
    account_equity = _account_equity_usd(snapshot)
    if margin_allocation_pct <= 0 or leverage <= 0 or account_equity <= 0:
        return None
    max_legs = _pyramid_max_legs(execution_setup)
    margin_usd = account_equity * margin_allocation_pct / 100 / max_legs
    return {
        "account_equity_usd": _rounded_number(account_equity),
        "margin_allocation_pct": _rounded_number(margin_allocation_pct),
        "leverage": _rounded_number(leverage),
        "pyramid_max_legs": max_legs,
        "margin_usd": _rounded_number(margin_usd),
        "notional_usd": _rounded_number(margin_usd * leverage),
    }


def _pyramid_max_legs(execution_setup: dict[str, Any]) -> int:
    setup = execution_setup.get("setup") if isinstance(execution_setup.get("setup"), dict) else execution_setup
    pyramid = setup.get("pyramid") if isinstance(setup.get("pyramid"), dict) else {}
    value = pyramid.get("max_legs") or setup.get("max_legs") or 1
    try:
        max_legs = int(value)
    except (TypeError, ValueError):
        max_legs = 1
    return max(1, max_legs)


def _account_equity_usd(snapshot: dict[str, Any]) -> float:
    balance = snapshot.get("balance") if isinstance(snapshot, dict) else None
    candidates: list[Any] = []
    balance_rows: list[dict[str, Any]] = []
    if isinstance(balance, dict):
        candidates.extend([balance.get("totalEq"), balance.get("eq"), balance.get("availEq"), balance.get("availBal")])
        data = balance.get("data")
        if isinstance(data, list):
            balance_rows.extend([row for row in data if isinstance(row, dict)])
    elif isinstance(balance, list):
        balance_rows.extend([row for row in balance if isinstance(row, dict)])
    for row in balance_rows:
        if row.get("ccy") in {None, "", "USDT", "USD"}:
            candidates.extend([row.get("totalEq"), row.get("eq"), row.get("availEq"), row.get("availBal")])
        details = row.get("details")
        if isinstance(details, list):
            for detail in details:
                if isinstance(detail, dict) and detail.get("ccy") in {None, "", "USDT", "USD"}:
                    candidates.extend([detail.get("eqUsd"), detail.get("eq"), detail.get("availEq"), detail.get("availBal")])
    for candidate in candidates:
        value = _numeric(candidate)
        if value > 0:
            return value
    return 0.0


def _protection_prices(*, entry_price: float, direction: str, tp_pct: float, sl_pct: float) -> tuple[str, str]:
    if direction == "SHORT":
        tp = entry_price * (1 - tp_pct / 100)
        sl = entry_price * (1 + sl_pct / 100)
    else:
        tp = entry_price * (1 + tp_pct / 100)
        sl = entry_price * (1 - sl_pct / 100)
    return _format_decimal(tp), _format_decimal(sl)


def _protection_state(*, snapshot: dict[str, Any], instrument: str) -> dict[str, Any]:
    orders = [
        order
        for order in snapshot.get("protection_orders") or []
        if str(order.get("instId") or order.get("instrument") or "") == instrument
        and str(order.get("state") or "").lower() in {"", "live"}
    ]
    return {"orders": orders, "live_count": len(orders), "has_single_live": len(orders) == 1}


def _protection_matches(order: dict[str, Any], *, side: str, size: str, tp: str, sl: str) -> bool:
    return (
        str(order.get("side") or "").lower() == side
        and _same_decimal(order.get("sz") or order.get("size"), size)
        and _same_decimal(order.get("tpTriggerPx") or order.get("tp"), tp)
        and _same_decimal(order.get("slTriggerPx") or order.get("sl"), sl)
    )


def _same_decimal(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 1e-8
    except (TypeError, ValueError):
        return str(left) == str(right)


def _rounded_number(value: float) -> float | int:
    rounded = round(float(value), 8)
    return int(rounded) if rounded.is_integer() else rounded


def _canonical_action(value: Any) -> str:
    action = str(value or "SKIP").upper()
    aliases = {
        "LONG": "ENTER_LONG",
        "SHORT": "ENTER_SHORT",
        "ENTER": "ENTER",
        "BUY": "ENTER_LONG",
        "SELL": "ENTER_SHORT",
        "NO_TRADE": "SKIP",
        "WAIT": "SKIP",
    }
    return aliases.get(action, action)


def _direction_from_action(action: str) -> str | None:
    if action in {"ENTER_LONG", "PYRAMID"}:
        return "LONG"
    if action == "ENTER_SHORT":
        return "SHORT"
    return None


def _side_for_action(*, action: str, direction: str) -> str:
    if action in {"EXIT", "REDUCE", "UPDATE_PROTECTION"}:
        return "sell" if direction == "LONG" else "buy"
    return "buy" if direction == "LONG" else "sell"


def _default_reduce_only(action: str) -> bool:
    return action in {"EXIT", "REDUCE", "UPDATE_PROTECTION"}


def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_decimal(value: Any) -> str:
    numeric = _numeric(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.12f}".rstrip("0").rstrip(".")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"true", "1", "yes"}
