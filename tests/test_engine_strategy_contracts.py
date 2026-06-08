import json
from pathlib import Path

import pytest

from quant_terminal_sdk.engine_contracts import (
    ContractValidationError,
    LiveSignalScanResult,
    SignalEngineSpec,
    SignalPacket,
    TrainingSignalGenerationResult,
    validate_engine_registry_entry,
    validate_execution_bundle,
    validate_execution_bundle_contract,
    validate_signal_engine_spec,
    validate_signal_packet,
    validate_strategy_module,
)


def test_valid_signal_engine_spec_accepts_required_parquet_candles():
    spec = SignalEngineSpec.from_mapping(
        {
            "signal_engine_id": "breakout",
            "version": "0.1",
            "required_data": [{"data_type": "candles", "origin": "raw", "timeframe": "5m"}],
            "output_envelope_version": "signal_packet.v2",
            "runtime_entrypoint": "engines/breakout/generate.py",
            "live_scanner_entrypoint": "engines/breakout/live_scan.py",
        }
    )

    assert spec.signal_engine_id == "breakout"
    assert spec.required_data[0]["timeframe"] == "5m"
    assert validate_engine_registry_entry(spec.to_mapping()) == []


def test_engine_spec_requires_live_scanner():
    with pytest.raises(ContractValidationError, match="live_scanner_entrypoint is required"):
        SignalEngineSpec.from_mapping(
            {
                "signal_engine_id": "breakout",
                "version": "0.1",
                "required_data": [{"data_type": "candles", "origin": "raw", "timeframe": "5m"}],
                "output_envelope_version": "signal_packet.v2",
                "runtime_entrypoint": "engines/breakout/generate.py",
            }
        )


def test_required_data_rejects_unsupported_type():
    with pytest.raises(ContractValidationError, match="unsupported required data type: orderbook"):
        SignalEngineSpec.from_mapping(
            {
                "signal_engine_id": "breakout",
                "version": "0.1",
                "required_data": [{"data_type": "orderbook", "origin": "raw", "timeframe": "5m"}],
                "output_envelope_version": "signal_packet.v2",
                "runtime_entrypoint": "engines/breakout/generate.py",
                "live_scanner_entrypoint": "engines/breakout/live_scan.py",
            }
        )


def test_signal_packet_rejects_directional_or_execution_fields():
    packet = {
        "schema_version": "signal_packet.v2",
        "asset": "SOL",
        "timestamp": "2026-06-08T00:00:00Z",
        "direction": "LONG",
        "votes": [{"timeframe": "2h", "kind": "breakout"}],
    }

    with pytest.raises(ContractValidationError, match="forbidden signal packet field: direction"):
        validate_signal_packet(packet)


def test_signal_packet_rejects_directional_fields_inside_evidence():
    packet = {
        "schema_version": "signal_packet.v2",
        "asset": "SOL",
        "timestamp": "2026-06-08T00:00:00Z",
        "evidence": {"pattern": "breakout", "direction": "LONG"},
    }

    with pytest.raises(ContractValidationError, match="forbidden signal packet field: evidence.direction"):
        validate_signal_packet(packet)


def test_signal_packet_accepts_neutral_evidence():
    packet = SignalPacket.from_mapping(
        {
            "schema_version": "signal_packet.v2",
            "asset": "SOL",
            "timestamp": "2026-06-08T00:00:00Z",
            "instrument": "SOL-USDT-SWAP",
            "active_timeframes": ["5m", "2h"],
            "evidence": {"breakout": True},
        }
    )

    assert packet.asset == "SOL"
    assert validate_signal_packet(packet.to_mapping()) == []


def test_strategy_module_requires_decide(tmp_path: Path):
    strategy_path = tmp_path / "strategy.py"
    strategy_path.write_text("def helper():\n    return None\n")

    with pytest.raises(ContractValidationError, match="strategy module must expose callable decide"):
        validate_strategy_module(strategy_path)


def test_strategy_decide_return_shape_is_validated(tmp_path: Path):
    strategy_path = tmp_path / "strategy.py"
    strategy_path.write_text(
        "def decide(context):\n"
        "    return {'action': 'ENTER', 'direction': 'FLAT', 'reason_code': 'bad'}\n"
    )

    with pytest.raises(ContractValidationError, match="entry decisions require LONG or SHORT direction"):
        validate_strategy_module(strategy_path)


def test_manage_position_return_shape_is_validated(tmp_path: Path):
    strategy_path = tmp_path / "strategy.py"
    strategy_path.write_text(
        "def decide(context):\n"
        "    return {'action': 'SKIP', 'direction': 'FLAT', 'reason_code': 'idle'}\n"
        "def manage_position(context):\n"
        "    return {'action': 'ENTER', 'reason_code': 'bad'}\n"
    )

    with pytest.raises(ContractValidationError, match="invalid manage_position action: ENTER"):
        validate_strategy_module(strategy_path)


def test_execution_bundle_requires_live_exit_policy_fields():
    bundle = {
        "bundle_id": "bundle-1",
        "execution_setup": {
            "schema_version": "0.1",
            "forward_hours": 24,
            "hard_exit_after_hours": 24,
            "setup": {"final_tp_pct": 2.0},
        },
    }

    with pytest.raises(ContractValidationError, match="execution setup missing initial_sl_pct"):
        validate_execution_bundle_contract(bundle)


def test_training_and_live_scan_result_contracts():
    training = TrainingSignalGenerationResult(
        status="appended",
        generated_packet_count=4,
        appended_packet_count=3,
        raw_candle_end_ts="2026-06-08T00:00:00Z",
        scan_coverage_end_ts="2026-06-08T00:00:00Z",
        packet_refs=["packets/a.json"],
    )
    live = LiveSignalScanResult(
        status="fresh_signal",
        source="live_parquet_snapshot",
        signal=SignalPacket(
            schema_version="signal_packet.v2",
            asset="SOL",
            timestamp="2026-06-08T00:00:00Z",
            evidence={"kind": "breakout"},
        ),
    )

    assert training.appended_packet_count == 3
    assert live.signal is not None


def test_engine_contracts_export_from_sdk_root():
    import quant_terminal_sdk as sdk

    assert sdk.SignalEngineSpec is SignalEngineSpec
    assert sdk.SignalPacket is SignalPacket
    assert sdk.validate_execution_bundle is validate_execution_bundle
    assert sdk.validate_execution_bundle_contract is validate_execution_bundle_contract
    assert sdk.validate_signal_engine_spec is validate_signal_engine_spec


def test_vegas_registry_metadata_is_canonical_and_readable():
    registry = json.loads(Path("artifacts/signal_engine/engine_registry.json").read_text())
    vegas_spec = SignalEngineSpec.from_mapping(registry["vegas_ema"])

    assert vegas_spec.signal_engine_id == "vegas_ema"
    assert vegas_spec.output_envelope_version == "signal_packet.v2"
    assert vegas_spec.runtime_entrypoint == "quant_terminal_worker.signal_engines.vegas_ema:generate_training_signals"
    assert vegas_spec.live_scanner_entrypoint == "quant_terminal_worker.signal_engines.vegas_ema:scan_live_signal"
    assert validate_signal_engine_spec("vegas_ema") == []


def test_engine_strategy_template_pair_validates():
    template_root = Path("templates/engine_strategy_pair")
    registry_entry = json.loads((template_root / "engine_registry_entry.json").read_text())

    assert validate_engine_registry_entry(registry_entry) == []
    assert validate_signal_engine_spec(template_root / "engine_registry_entry.json") == []
    assert validate_strategy_module(template_root / "strategy.py") == []


def test_current_aave_execution_bundle_validates_with_legacy_aliases():
    bundle_id = "aave-vegas_ema-aave-vegas_ema-strategy-v01-3bee1a88652e"

    assert validate_execution_bundle(bundle_id) == []
