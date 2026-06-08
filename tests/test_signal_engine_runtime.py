from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import create_engine, insert

from quant_terminal_api.db.models import data_sources, market_data_refs, metadata
from quant_terminal_api.repositories.runtime import RuntimeRepository
from quant_terminal_sdk.engine_contracts import (
    ContractValidationError,
    validate_signal_engine_spec,
    validate_signal_packet,
    validate_strategy_module,
)
from quant_terminal_worker.execution.live_signal_scan import scan_latest_live_signal
from quant_terminal_worker.execution.wake_runner import run_route_wake
from quant_terminal_worker.ingestion.legacy_signals import build_signal_set_key
from quant_terminal_worker.ingestion.signal_pool_extension import extend_signal_pool_from_local_candles
from quant_terminal_worker.signal_engines import vegas_ema
from quant_terminal_worker.signal_engines.runtime import resolve_signal_engine


def test_resolve_signal_engine_prefers_canonical_db_spec(tmp_path: Path):
    repository = _repository()
    _register_threshold_engine(repository)

    resolved = resolve_signal_engine(
        "threshold_reversal",
        version="0.1.0",
        repository=repository,
        workspace_root=tmp_path,
    )

    assert resolved.spec.signal_engine_id == "threshold_reversal"
    assert resolved.spec.runtime_entrypoint == "quant_terminal_engines.threshold_reversal:generate_training_signals"
    assert resolved.spec.live_scanner_entrypoint == "quant_terminal_engines.threshold_reversal:scan_live_signal"


def test_resolve_signal_engine_rejects_invalid_required_data(tmp_path: Path):
    repository = _repository()
    repository.register_signal_engine(
        {
            "signal_engine_id": "bad_engine",
            "name": "Bad Engine",
            "description": "",
            "version": "0.1.0",
            "code_ref": {},
            "supported_input_data_types": ["orderbook"],
            "required_data": [{"data_type": "orderbook", "origin": "raw", "timeframe": "5m"}],
            "output_envelope_version": "signal_packet.v2",
            "runtime_entrypoint": "quant_terminal_engines.threshold_reversal:generate_training_signals",
            "live_scanner_entrypoint": "quant_terminal_engines.threshold_reversal:scan_live_signal",
            "configuration_schema": {},
        }
    )

    with pytest.raises(ContractValidationError, match="unsupported required data type: orderbook"):
        resolve_signal_engine("bad_engine", repository=repository, workspace_root=tmp_path)


def test_vegas_vote1_resolves_as_separate_engine_with_vote_threshold_one(tmp_path: Path, monkeypatch):
    root, repository = _workspace_with_vegas_pool(
        tmp_path,
        signal_engine_id="vegas_ema_vote1",
        vote_threshold=1,
        include_manifest_vote_threshold=False,
    )
    _register_default_vegas_refs(
        repository,
        root=root,
        asset="AAVE",
        rows=[
            _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
            _candle_row("2026-06-01T00:05:00Z", open_=100, close=101),
        ],
    )
    calls = []

    def fake_generate_vegas_packets(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(vegas_ema, "generate_vegas_packets", fake_generate_vegas_packets)

    result = extend_signal_pool_from_local_candles(
        workspace_root=root,
        repository=repository,
        signal_engine_id="vegas_ema_vote1",
        asset="AAVE",
        target_end="2026-06-01T00:05:00Z",
    )

    resolved = resolve_signal_engine("vegas_ema_vote1", repository=repository, workspace_root=root)
    assert resolved.spec.signal_engine_id == "vegas_ema_vote1"
    assert result["status"] == "no_new_signals"
    assert calls[0]["vote_threshold"] == 1


def test_vegas_vote1_resolves_from_artifact_registry(tmp_path: Path):
    repository = _repository()

    resolved = resolve_signal_engine("vegas_ema_vote1", repository=repository, workspace_root=Path.cwd())

    assert resolved.spec.signal_engine_id == "vegas_ema_vote1"
    assert resolved.spec.name == "Vegas 1 Vote"
    assert resolved.spec.configuration_schema["default_parameters"]["vote_threshold"] == 1
    assert resolved.spec.runtime_entrypoint == "quant_terminal_worker.signal_engines.vegas_ema:generate_training_signals"


def test_existing_vegas_engine_remains_vote_threshold_two(tmp_path: Path, monkeypatch):
    root, repository = _workspace_with_vegas_pool(tmp_path, signal_engine_id="vegas_ema", vote_threshold=2)
    _register_default_vegas_refs(
        repository,
        root=root,
        asset="AAVE",
        rows=[
            _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
            _candle_row("2026-06-01T00:05:00Z", open_=100, close=101),
        ],
    )
    calls = []

    monkeypatch.setattr(vegas_ema, "generate_vegas_packets", lambda **kwargs: calls.append(kwargs) or [])

    extend_signal_pool_from_local_candles(
        workspace_root=root,
        repository=repository,
        signal_engine_id="vegas_ema",
        asset="AAVE",
        target_end="2026-06-01T00:05:00Z",
    )

    assert calls[0]["vote_threshold"] == 2


def test_generic_training_dispatch_extends_non_vegas_signal_pool_from_parquet(tmp_path: Path):
    root, repository = _workspace_with_threshold_pool(tmp_path)
    _register_candle_ref(
        repository,
        root=root,
        asset="SOL",
        timeframe="5m",
        origin="raw",
        rows=[
            _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
            _candle_row("2026-06-01T00:05:00Z", open_=100, close=103),
        ],
    )

    result = extend_signal_pool_from_local_candles(
        workspace_root=root,
        repository=repository,
        signal_engine_id="threshold_reversal",
        asset="SOL",
        target_end="2026-06-01T00:05:00Z",
    )

    assert result["status"] == "extended"
    assert result["signal_engine_id"] == "threshold_reversal"
    assert result["appended_packet_count"] == 1
    signals = repository.list_signals(signal_set_key=build_signal_set_key("threshold_reversal", "SOL", "SOL-threshold_reversal-canonical"))
    assert signals[0]["payload"]["evidence"]["neutral_trigger"] == "lookback_move_exceeded"
    assert "direction" not in signals[0]["payload"]


def test_bollinger_registry_entry_is_contract_compliant():
    validate_signal_engine_spec("bollinger")
    validate_strategy_module("packages/strategy_modules/src/quant_terminal_strategies/bollinger_base.py")


def test_bollinger_training_dispatch_extends_signal_pool_from_parquet(tmp_path: Path):
    root, repository = _workspace_with_bollinger_pool(tmp_path)
    _register_bollinger_refs(repository, root=root, asset="AAVE")

    result = extend_signal_pool_from_local_candles(
        workspace_root=root,
        repository=repository,
        signal_engine_id="bollinger",
        asset="AAVE",
        target_end="2026-06-01T04:05:00Z",
    )

    assert result["status"] == "extended"
    assert result["signal_engine_id"] == "bollinger"
    assert result["appended_packet_count"] == 2
    signals = repository.list_signals(signal_set_key=build_signal_set_key("bollinger", "AAVE", "AAVE-bollinger-canonical"))
    packet = signals[0]["payload"]
    validate_signal_packet(packet)
    assert packet["evidence"]["pattern"] == "bollinger_band_proximity"
    assert packet["evidence"]["vote_threshold"] == 1
    assert packet["evidence"]["bb_period"] == 2
    assert packet["evidence"]["interactions"][0]["band"] == "upper"
    assert "direction" not in packet
    assert "direction" not in packet["evidence"]


def test_bollinger_live_scan_scans_latest_parquet_candle_only(tmp_path: Path):
    root, repository = _workspace_with_bollinger_pool(tmp_path)
    _register_bollinger_refs(repository, root=root, asset="AAVE")
    route = {
        **_route(root),
        "route_id": "aave-live",
        "signal_engine_id": "bollinger",
        "signal_engine_version": "0.1",
        "asset": "AAVE",
        "instrument": "AAVE-USDT-SWAP",
    }

    signal = scan_latest_live_signal(route=route, repository=repository, workspace_root=root)

    assert signal is not None
    assert signal["signal_engine_id"] == "bollinger"
    assert signal["payload_schema"] == "signal_packet.v2"
    assert signal["payload"]["evidence"]["pattern"] == "bollinger_band_proximity"
    assert signal["payload"]["evidence"]["active_timeframes"] == ["4h"]


def test_generic_live_scan_returns_non_vegas_packet_from_latest_parquet(tmp_path: Path):
    root, repository = _workspace_with_threshold_pool(tmp_path)
    _register_candle_ref(
        repository,
        root=root,
        asset="SOL",
        timeframe="5m",
        origin="raw",
        rows=[
            _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
            _candle_row("2026-06-01T00:05:00Z", open_=100, close=103),
        ],
    )
    route = _route(root)

    signal = scan_latest_live_signal(route=route, repository=repository, workspace_root=root)

    assert signal is not None
    assert signal["signal_engine_id"] == "threshold_reversal"
    assert signal["payload_schema"] == "signal_packet.v2"
    assert signal["payload"]["evidence"]["move_pct"] == 3.0


def test_non_vegas_live_wake_uses_generic_scanner_and_strategy_decide(tmp_path: Path):
    root, repository = _workspace_with_threshold_pool(tmp_path)
    _register_candle_ref(
        repository,
        root=root,
        asset="SOL",
        timeframe="5m",
        origin="raw",
        rows=[
            _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
            _candle_row("2026-06-01T00:05:00Z", open_=100, close=103),
        ],
    )
    bundle = _bundle(root)
    route = {
        **_route(root),
        "active_bundle_id": bundle["bundle_id"],
        "active_bundle": bundle,
        "enabled": True,
        "promoted": True,
        "data_warmed": True,
        "manually_armed": True,
        "blockers": [],
    }

    wake = run_route_wake(
        route_id="sol-live",
        repository=FakeWakeRepository(repository=repository, route=route, bundle=bundle),
        adapter=FakeAdapter(),
        workspace_root=root,
    )

    assert wake["branch"] == "entry_scan"
    assert wake["signal_scan_result"]["source"] == "live_parquet_snapshot"
    assert wake["signal_scan_result"]["signal_engine_id"] == "threshold_reversal"
    assert wake["strategy_decision"]["direction"] == "LONG"
    assert wake["order_intents"][0]["action"] == "ENTER"


class FakeAdapter:
    def readiness_blockers(self):
        return []

    def snapshot(self, instrument):
        return {
            "instrument": instrument,
            "positions": [],
            "open_orders": [],
            "protection_orders": [],
            "balance": {"total_equity_usd": 1000},
            "recent_fills": [],
        }


class FakeWakeRepository:
    def __init__(self, *, repository: RuntimeRepository, route: dict[str, object], bundle: dict[str, object]) -> None:
        self.repository = repository
        self.route = route
        self.bundle = bundle
        self.wakes: list[dict[str, object]] = []

    def __getattr__(self, name: str):
        return getattr(self.repository, name)

    def get_deployment_route(self, route_id):
        if route_id != self.route["route_id"]:
            return None
        return {**self.route, "active_bundle": self.bundle}

    def get_execution_bundle(self, bundle_id):
        if bundle_id == self.bundle["bundle_id"]:
            return self.bundle
        return None

    def get_open_owner_state(self, route_id):
        return None

    def close_open_owner_states(self, route_id, *, instrument=None, reason):
        return []

    def record_wake_run(self, wake):
        self.wakes.append(wake)
        return wake

    def list_wake_runs(self, route_id, limit=25):
        return list(reversed(self.wakes))[:limit]


def _repository() -> RuntimeRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    repository = RuntimeRepository(engine)
    with engine.begin() as connection:
        connection.execute(insert(data_sources).values(source_id="okx", name="OKX", source_type="exchange", config={}))
    return repository


def _workspace_with_threshold_pool(tmp_path: Path) -> tuple[Path, RuntimeRepository]:
    root = tmp_path / "workspace"
    root.mkdir()
    repository = _repository()
    _register_threshold_engine(repository)
    repository.upsert_signal_set(
        {
            "signal_set_key": build_signal_set_key("threshold_reversal", "SOL", "SOL-threshold_reversal-canonical"),
            "signal_set_id": "SOL-threshold_reversal-canonical",
            "signal_engine_id": "threshold_reversal",
            "signal_engine_version": "0.1.0",
            "asset": "SOL",
            "instrument": "SOL-USDT-SWAP",
            "start_ts": None,
            "end_ts": None,
            "packet_count": 0,
            "payload_schema": "signal_packet.v2",
            "source_path": "canonicalized:signals",
            "manifest": {"parameters": {"min_move_pct": 1.0}},
        }
    )
    return root, repository


def _workspace_with_bollinger_pool(tmp_path: Path) -> tuple[Path, RuntimeRepository]:
    root = tmp_path / "workspace-bollinger"
    root.mkdir()
    repository = _repository()
    _register_bollinger_engine(repository)
    asset = "AAVE"
    repository.upsert_signal_set(
        {
            "signal_set_key": build_signal_set_key("bollinger", asset, f"{asset}-bollinger-canonical"),
            "signal_set_id": f"{asset}-bollinger-canonical",
            "signal_engine_id": "bollinger",
            "signal_engine_version": "0.1",
            "asset": asset,
            "instrument": f"{asset}-USDT-SWAP",
            "start_ts": None,
            "end_ts": None,
            "packet_count": 0,
            "payload_schema": "signal_packet.v2",
            "source_path": "canonicalized:signals",
            "manifest": {
                "parameters": {
                    "timeframes": ["4h"],
                    "context_bars": 2,
                    "bb_period": 2,
                    "bb_stddev": "2",
                    "proximity_threshold": "0.03",
                    "vote_threshold": 1,
                    "dedupe_window_minutes": 120,
                }
            },
        }
    )
    return root, repository


def _register_threshold_engine(repository: RuntimeRepository) -> None:
    repository.register_signal_engine(
        {
            "signal_engine_id": "threshold_reversal",
            "name": "Threshold Reversal",
            "description": "Contract proof engine",
            "version": "0.1.0",
            "code_ref": {},
            "supported_input_data_types": ["candles"],
            "required_data": [{"data_type": "candles", "origin": "raw", "timeframe": "5m"}],
            "output_envelope_version": "signal_packet.v2",
            "runtime_entrypoint": "quant_terminal_engines.threshold_reversal:generate_training_signals",
            "live_scanner_entrypoint": "quant_terminal_engines.threshold_reversal:scan_live_signal",
            "configuration_schema": {},
        }
    )


def _register_bollinger_engine(repository: RuntimeRepository) -> None:
    repository.register_signal_engine(
        {
            "signal_engine_id": "bollinger",
            "name": "Bollinger Bands",
            "description": "Bollinger band proximity signal engine.",
            "version": "0.1",
            "code_ref": {
                "path": "apps/worker/src/quant_terminal_worker/signal_engines/bollinger.py",
                "base_strategy_path": "packages/strategy_modules/src/quant_terminal_strategies/bollinger_base.py",
            },
            "supported_input_data_types": ["candles"],
            "required_data": [
                {"data_type": "candles", "origin": "raw", "timeframe": "5m"},
                {
                    "data_type": "candles",
                    "origin": "derived",
                    "timeframe": "4h",
                    "source": {"data_type": "candles", "origin": "raw", "timeframe": "5m"},
                },
            ],
            "output_envelope_version": "signal_packet.v2",
            "runtime_entrypoint": "quant_terminal_worker.signal_engines.bollinger:generate_training_signals",
            "live_scanner_entrypoint": "quant_terminal_worker.signal_engines.bollinger:scan_live_signal",
            "configuration_schema": {
                "default_parameters": {
                    "timeframes": ["4h"],
                    "context_bars": 2,
                    "bb_period": 2,
                    "vote_threshold": 1,
                    "proximity_threshold": "0.03",
                }
            },
        }
    )


def _workspace_with_vegas_pool(
    tmp_path: Path,
    *,
    signal_engine_id: str,
    vote_threshold: int,
    include_manifest_vote_threshold: bool = True,
) -> tuple[Path, RuntimeRepository]:
    root = tmp_path / f"workspace-{signal_engine_id}"
    root.mkdir()
    repository = _repository()
    _register_vegas_engine(repository, signal_engine_id=signal_engine_id, vote_threshold=vote_threshold)
    asset = "AAVE"
    signal_set_id = f"{asset}-{signal_engine_id}-canonical"
    repository.upsert_signal_set(
        {
            "signal_set_key": build_signal_set_key(signal_engine_id, asset, signal_set_id),
            "signal_set_id": signal_set_id,
            "signal_engine_id": signal_engine_id,
            "signal_engine_version": "0.1",
            "asset": asset,
            "instrument": f"{asset}-USDT-SWAP",
            "start_ts": None,
            "end_ts": None,
            "packet_count": 0,
            "payload_schema": "signal_packet.v2",
            "source_path": "canonicalized:signals",
            "manifest": {"parameters": {"vote_threshold": vote_threshold} if include_manifest_vote_threshold else {}},
        }
    )
    return root, repository


def _register_vegas_engine(repository: RuntimeRepository, *, signal_engine_id: str, vote_threshold: int) -> None:
    repository.register_signal_engine(
        {
            "signal_engine_id": signal_engine_id,
            "name": f"Vegas EMA vote {vote_threshold}",
            "description": "",
            "version": "0.1",
            "code_ref": {},
            "supported_input_data_types": ["candles"],
            "required_data": [
                {"data_type": "candles", "origin": "raw", "timeframe": "5m"},
                {
                    "data_type": "candles",
                    "origin": "derived",
                    "timeframe": "2h",
                    "source": {"data_type": "candles", "origin": "raw", "timeframe": "5m"},
                },
            ],
            "output_envelope_version": "signal_packet.v2",
            "runtime_entrypoint": "quant_terminal_worker.signal_engines.vegas_ema:generate_training_signals",
            "live_scanner_entrypoint": "quant_terminal_worker.signal_engines.vegas_ema:scan_live_signal",
            "configuration_schema": {"default_parameters": {"vote_threshold": vote_threshold}},
        }
    )


def _register_default_vegas_refs(
    repository: RuntimeRepository,
    *,
    root: Path,
    asset: str,
    rows: list[dict[str, object]],
) -> None:
    _register_candle_ref(repository, root=root, asset=asset, timeframe="5m", origin="raw", rows=rows)
    for timeframe in ("2h", "4h", "8h", "12h", "1d"):
        _register_candle_ref(repository, root=root, asset=asset, timeframe=timeframe, origin="derived", rows=rows)


def _register_bollinger_refs(
    repository: RuntimeRepository,
    *,
    root: Path,
    asset: str,
) -> None:
    raw_rows = [
        _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
        _candle_row("2026-06-01T04:00:00Z", open_=100, close=104),
        _candle_row("2026-06-01T04:05:00Z", open_=104, close=105),
    ]
    derived_rows = [
        _candle_row("2026-05-31T16:00:00Z", open_=100, close=100),
        _candle_row("2026-05-31T20:00:00Z", open_=100, close=100),
        _candle_row("2026-06-01T00:00:00Z", open_=100, close=100),
    ]
    _register_candle_ref(repository, root=root, asset=asset, timeframe="5m", origin="raw", rows=raw_rows)
    _register_candle_ref(repository, root=root, asset=asset, timeframe="4h", origin="derived", rows=derived_rows)


def _register_candle_ref(
    repository: RuntimeRepository,
    *,
    root: Path,
    asset: str,
    timeframe: str,
    origin: str,
    rows: list[dict[str, object]],
) -> None:
    storage_uri = root / ".data" / "market-data" / f"origin={origin}" / "source=okx" / "type=candles" / f"asset={asset}" / f"timeframe={timeframe}"
    path = storage_uri / "year=2026" / "month=06" / "data.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
    with repository.engine.begin() as connection:
        connection.execute(
            insert(market_data_refs).values(
                dataset_id=f"{asset}-{origin}-{timeframe}",
                source_id="okx",
                asset=asset,
                instrument=f"{asset}-USDT-SWAP",
                data_type="candles",
                timeframe=timeframe,
                data_origin=origin,
                start_ts=datetime.fromisoformat(str(rows[0]["timestamp"]).replace("Z", "+00:00")),
                end_ts=datetime.fromisoformat(str(rows[-1]["timestamp"]).replace("Z", "+00:00")),
                row_count=len(rows),
                storage_backend="parquet",
                storage_uri=str(storage_uri),
                schema_descriptor={},
                quality_status="ingested",
                ingestion_version="test",
            )
        )


def _candle_row(timestamp: str, *, open_: float, close: float) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": open_,
        "high": max(open_, close),
        "low": min(open_, close),
        "close": close,
        "volume": 1.0,
        "vol_ccy": 1.0,
        "vol_ccy_quote": 1.0,
        "confirm": 1,
    }


def _route(root: Path) -> dict[str, object]:
    return {
        "route_id": "sol-live",
        "active_bundle_id": "bundle-1",
        "signal_engine_id": "threshold_reversal",
        "signal_engine_version": "0.1.0",
        "asset": "SOL",
        "instrument": "SOL-USDT-SWAP",
        "account_mode": "live",
        "execution_adapter": "okx",
        "bundle_uri": str(root / "bundle"),
    }


def _bundle(root: Path) -> dict[str, object]:
    bundle_root = root / "bundle"
    bundle_root.mkdir()
    strategy_path = bundle_root / "strategy.py"
    strategy_path.write_text(
        "def decide(context):\n"
        "    return {'action': 'ENTER', 'direction': 'LONG', 'reason_code': 'threshold_accept'}\n"
    )
    execution_setup = {
        "schema_version": "0.1",
        "forward_hours": 24,
        "hard_exit_after_hours": 24,
        "setup": {
            "final_tp_pct": 1.0,
            "initial_sl_pct": 0.5,
            "protection_enabled": False,
        },
    }
    (bundle_root / "execution_setup.json").write_text(json.dumps(execution_setup))
    return {
        "bundle_id": "bundle-1",
        "bundle_uri": str(bundle_root),
        "strategy_module_ref": str(strategy_path),
        "strategy_id": "threshold-strategy",
        "strategy_version": "v0.1",
        "signal_engine_id": "threshold_reversal",
        "signal_engine_version": "0.1.0",
        "asset": "SOL",
        "instrument": "SOL-USDT-SWAP",
        "source_stage1_session_id": "session-1",
        "execution_setup": execution_setup,
        "risk_limits": {"max_notional_usd": 1000, "max_daily_loss_usd": 100},
        "evidence_refs": {},
        "content_hash": "hash",
        "status": "promoted",
    }
