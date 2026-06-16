from __future__ import annotations

import importlib.util
from pathlib import Path


OPTIMIZATION_ROOT = Path("artifacts/skills/agentic-quant-trading-development/scripts/optimization").resolve()


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, OPTIMIZATION_ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage0_reference_price_extractors_accept_liquidity_sweep_packets() -> None:
    packet = {
        "schema_version": "signal_packet.v2",
        "active_timeframes": ["5m"],
        "evidence": {
            "pattern": "liquidity_sweep_event",
            "event_type": "HIGH_SWEEP",
            "trigger_candle_close": "52.92",
            "trigger_price": "52.95",
        },
    }

    for script_name in ("max_travel_distribution", "significance_threshold_calibration", "signal_ground_truth"):
        module = _load_script(script_name)

        assert module.get_reference_price(packet) == 52.92


def test_stage0_reference_price_extractors_fall_back_to_liquidity_sweep_trigger_price() -> None:
    packet = {
        "schema_version": "signal_packet.v2",
        "active_timeframes": ["5m"],
        "evidence": {
            "pattern": "liquidity_sweep_event",
            "event_type": "LOW_SWEEP",
            "trigger_price": "48.12",
        },
    }

    for script_name in ("max_travel_distribution", "significance_threshold_calibration", "signal_ground_truth"):
        module = _load_script(script_name)

        assert module.get_reference_price(packet) == 48.12
