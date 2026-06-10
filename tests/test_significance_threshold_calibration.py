from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path("artifacts/skills/agentic-quant-trading-development/scripts/optimization/significance_threshold_calibration.py")
    .resolve()
)
SPEC = importlib.util.spec_from_file_location("significance_threshold_calibration", SCRIPT_PATH)
assert SPEC is not None
calibration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = calibration
SPEC.loader.exec_module(calibration)


def test_default_threshold_range_reaches_high_volatility_assets() -> None:
    parser = calibration.build_parser()

    args = parser.parse_args(["packets", "--candles", "candles.csv", "--out", "out.json"])

    assert args.threshold_range == [0.2, 3.0, 0.1]


def test_adaptive_selector_picks_meaningful_move_above_old_two_percent_ceiling() -> None:
    hype_curve = [
        (0.2, 501, 470, 93.8124, 5),
        (0.3, 501, 457, 91.2176, 10),
        (0.4, 501, 446, 89.022, 15),
        (0.5, 501, 425, 84.8303, 20),
        (0.6, 501, 411, 82.0359, 30),
        (0.7, 501, 387, 77.2455, 40),
        (0.8, 501, 372, 74.2515, 50),
        (0.9, 501, 348, 69.4611, 65),
        (1.0, 501, 327, 65.2695, 80),
        (1.1, 499, 313, 62.7255, 105),
        (1.2, 499, 302, 60.521, 110),
        (1.3, 499, 285, 57.1142, 120),
        (1.4, 498, 272, 54.6185, 142),
        (1.5, 497, 251, 50.503, 160),
        (1.6, 494, 237, 47.9757, 185),
        (1.7, 487, 227, 46.6119, 205),
        (1.8, 484, 215, 44.4215, 242),
        (1.9, 479, 198, 41.3361, 275),
        (2.0, 467, 182, 38.9722, 290),
        (2.1, 463, 167, 36.0691, 355),
        (2.2, 463, 159, 34.3413, 385),
        (2.3, 460, 149, 32.3913, 415),
        (2.4, 457, 141, 30.8534, 430),
        (2.5, 453, 133, 29.3598, 465),
        (2.6, 449, 115, 25.6125, 500),
        (2.7, 447, 108, 24.1611, 525),
        (2.8, 447, 104, 23.2662, 550),
        (2.9, 446, 98, 21.9731, 572),
        (3.0, 440, 87, 19.7727, 600),
    ]
    rows = [
        {
            "threshold_pct": threshold,
            "total_signals": 501,
            "total_valid": total_valid,
            "reversed_count": reversed_count,
            "reversal_rate_pct": reversal_rate_pct,
            "median_resolution_minutes": median_resolution_minutes,
        }
        for threshold, total_valid, reversed_count, reversal_rate_pct, median_resolution_minutes in hype_curve
    ]

    selection = calibration.select_adaptive_meaningful_move_threshold(rows)

    assert selection["chosen_threshold_pct"] == 2.9
    assert selection["selection_method"] == "adaptive_snapback_knee"
    assert selection["stable_range"] == [2.6, 3.0]
