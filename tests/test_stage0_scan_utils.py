from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


OPTIMIZATION_ROOT = Path("artifacts/skills/agentic-quant-trading-development/scripts/optimization").resolve()


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, OPTIMIZATION_ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_scan_index_finds_first_candle_after_signal_without_linear_prefix_scan() -> None:
    module = _load_script("significance_threshold_calibration")
    candles = [
        {"ts": _ts("2026-01-01T00:00:00Z"), "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0},
        {"ts": _ts("2026-01-01T00:05:00Z"), "open": 100.0, "high": 101.0, "low": 99.8, "close": 100.5},
        {"ts": _ts("2026-01-01T00:10:00Z"), "open": 100.5, "high": 102.0, "low": 100.3, "close": 101.5},
    ]

    index = module.build_candle_time_index(candles)

    assert module.first_candle_after(index, _ts("2026-01-01T00:00:00Z")) == 1
    assert module.first_candle_after(index, _ts("2026-01-01T00:04:00Z")) == 1
    assert module.first_candle_after(index, _ts("2026-01-01T00:10:00Z")) is None


def test_threshold_analysis_with_scan_index_preserves_direction_result() -> None:
    module = _load_script("significance_threshold_calibration")
    candles = [
        {"ts": _ts("2026-01-01T00:00:00Z"), "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        {"ts": _ts("2026-01-01T00:05:00Z"), "open": 100.0, "high": 101.5, "low": 99.9, "close": 101.0},
        {"ts": _ts("2026-01-01T00:10:00Z"), "open": 101.0, "high": 101.2, "low": 98.5, "close": 99.0},
    ]

    result = module.analyze_signal(
        candles,
        _ts("2026-01-01T00:00:00Z"),
        100.0,
        1,
        1.0,
        candle_time_index=module.build_candle_time_index(candles),
    )

    assert result["natural_direction"] == "LONG"
    assert result["reversed"] is True
    assert result["resolution_minutes"] == 5
