from __future__ import annotations

from typing import Any


STRATEGY_ID = "liquidity_sweep_v1_base"
STRATEGY_VERSION = "v0.1"


def decide(context: dict[str, Any]) -> dict[str, Any]:
    signal = context.get("signal") if isinstance(context.get("signal"), dict) else {}
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    signal_id = str(signal.get("signal_id", "unknown"))
    event_type = str(evidence.get("event_type") or "").upper()

    if event_type == "HIGH_SWEEP":
        return _decision(
            signal_id=signal_id,
            action="ENTER",
            direction="SHORT",
            confidence=0.45,
            reason_code="high_sweep_reversal_seed_short",
            diagnostics=_diagnostics(payload=payload, signal=signal, evidence=evidence, directional_prior="reversal"),
        )
    if event_type == "LOW_SWEEP":
        return _decision(
            signal_id=signal_id,
            action="ENTER",
            direction="LONG",
            confidence=0.45,
            reason_code="low_sweep_reversal_seed_long",
            diagnostics=_diagnostics(payload=payload, signal=signal, evidence=evidence, directional_prior="reversal"),
        )

    return _decision(
        signal_id=signal_id,
        action="SKIP",
        direction="FLAT",
        confidence=0.2,
        reason_code="missing_liquidity_sweep_event_type",
        diagnostics=_diagnostics(payload=payload, signal=signal, evidence=evidence, directional_prior=None),
    )


def manage_position(context: dict[str, Any]) -> dict[str, Any]:
    position_context = context.get("position_context") if isinstance(context.get("position_context"), dict) else {}
    if position_context.get("hard_exit_expired") is True:
        return {"action": "EXIT", "reason_code": "hard_exit_expired"}
    return {"action": "HOLD", "reason_code": "mechanical_policy"}


def _diagnostics(
    *,
    payload: dict[str, Any],
    signal: dict[str, Any],
    evidence: dict[str, Any],
    directional_prior: str | None,
) -> dict[str, Any]:
    return {
        "pattern": evidence.get("pattern"),
        "event_type": evidence.get("event_type"),
        "directional_prior": directional_prior,
        "reference_window_hours": evidence.get("reference_window_hours"),
        "reference_level": evidence.get("reference_level"),
        "trigger_price": evidence.get("trigger_price"),
        "sweep_distance_atr": evidence.get("sweep_distance_atr"),
        "cooldown_hours": evidence.get("cooldown_hours"),
        "close_location_pct": evidence.get("close_location_pct"),
        "active_timeframes": payload.get("active_timeframes") or signal.get("active_timeframes") or [],
    }


def _decision(
    *,
    signal_id: str,
    action: str,
    direction: str,
    confidence: float,
    reason_code: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_id": f"{STRATEGY_ID}-{STRATEGY_VERSION}-{signal_id}",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "signal_id": signal_id,
        "action": action,
        "trade_action": action,
        "direction": direction,
        "confidence": confidence,
        "reason_code": reason_code,
        "execution_profile": {},
        "diagnostics": diagnostics,
    }
