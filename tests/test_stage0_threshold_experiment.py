from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path("dev/experiments/stage0/threshold_experiment.py").resolve()
SPEC = importlib.util.spec_from_file_location("stage0_threshold_experiment", SCRIPT_PATH)
assert SPEC is not None
experiment = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = experiment
SPEC.loader.exec_module(experiment)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


def _build_artifact_root(tmp_path: Path) -> Path:
    artifact_root = tmp_path / "artifact-root"
    packets_dir = artifact_root / "scores" / "_scoreable_signal_subset" / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    _write_text(
        artifact_root / "candles.csv",
        "\n".join(
            [
                "ts,open,high,low,close,volume,vol_ccy,vol_ccy_quote,confirm",
                "2025-12-01T00:05:00Z,100,101.5,99.5,101,1,1,101,1",
                "2025-12-01T00:10:00Z,101,103.0,100.5,102.5,1,1,102.5,1",
                "2025-12-01T01:05:00Z,100,100.2,98.8,99.0,1,1,99,1",
                "2025-12-01T01:10:00Z,99,101.5,98.9,101.2,1,1,101.2,1",
                "2025-12-01T02:05:00Z,100,100.4,99.7,100.1,1,1,100.1,1",
                "2025-12-01T02:10:00Z,100.1,100.3,99.8,100.0,1,1,100,1",
                "2025-12-01T02:30:00Z,100.0,100.2,99.9,100.0,1,1,100,1",
                "2025-12-01T03:00:00Z,100.0,100.1,99.9,100.0,1,1,100,1",
                "2025-12-01T03:10:00Z,100,100.1,99.9,100.0,1,1,100,1",
            ]
        )
        + "\n",
    )
    packet_payload = {
        "schema_version": "signal_packet.v2",
        "asset": "BTC",
        "interactions": [{"market_price": "100"}],
    }
    for stamp in ("20251201T000000Z", "20251201T010000Z", "20251201T020000Z"):
        _write_json(
            packets_dir / f"{stamp}.json",
            {
                **packet_payload,
                "timestamp": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z",
            },
        )
    return artifact_root


def test_run_stage0_threshold_experiment_writes_current_and_experimental_outputs(tmp_path: Path) -> None:
    artifact_root = _build_artifact_root(tmp_path)
    executed: list[list[str]] = []

    def fake_runner(command: list[str]) -> None:
        executed.append(command)
        if command[1].endswith("significance_threshold_calibration.py"):
            out_path = Path(command[command.index("--out") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(
                    {
                        "chosen_threshold_pct": 0.8,
                        "stable_range": [0.8, 1.2],
                    }
                )
            )
        elif command[1].endswith("signal_ground_truth.py"):
            out_dir = Path(command[command.index("--out") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir.parent / "ground_truth_summary.json").write_text(
                json.dumps(
                    {
                        "metrics": {
                            "total_records": 3,
                            "status_counts": {"triggered": 2, "no_trigger": 1},
                            "trigger_rate_pct": 66.67,
                            "significance_threshold_pct": 0.8,
                            "reversed_count": 1,
                            "reversal_rate_pct": 50.0,
                        }
                    }
                )
            )

    result = experiment.run_stage0_threshold_experiment(
        workspace_root=tmp_path,
        artifact_root=artifact_root,
        asset="BTC",
        signal_engine_id="vegas_ema",
        signal_set_id="BTC-vegas_ema-canonical",
        window_start="2025-12-01T00:00:00Z",
        window_end="2025-12-01T02:00:00Z",
        forward_hours=1,
        threshold_start=1.0,
        threshold_end=2.0,
        threshold_step=1.0,
        out_dir=tmp_path / "out",
        command_runner=fake_runner,
    )

    assert [Path(command[1]).name for command in executed] == [
        "max_travel_distribution.py",
        "significance_threshold_calibration.py",
        "signal_ground_truth.py",
    ]
    assert result["current"]["chosen_threshold_pct"] == 0.8
    assert result["experimental"]["chosen_threshold_pct"] == 2.0
    assert result["experimental"]["signal_count"] == 3

    current_threshold = json.loads((tmp_path / "out" / "current" / "threshold_calibration.json").read_text())
    current_summary = json.loads((tmp_path / "out" / "current" / "ground_truth_summary.json").read_text())
    threshold_scan = json.loads((tmp_path / "out" / "experimental" / "threshold_scan.json").read_text())
    top_thresholds = json.loads((tmp_path / "out" / "experimental" / "top_thresholds.json").read_text())
    comparison_summary = (tmp_path / "out" / "comparison_summary.md").read_text()

    assert current_threshold["chosen_threshold_pct"] == 0.8
    assert current_summary["metrics"]["trigger_rate_pct"] == 66.67
    assert len(threshold_scan["rows"]) == 2
    assert top_thresholds["top_thresholds"][0]["threshold_pct"] == 2.0
    assert "Current chosen threshold: 0.8%" in comparison_summary
    assert "Experimental chosen threshold: 2.0%" in comparison_summary


def test_run_stage0_threshold_experiment_rejects_empty_packet_window(tmp_path: Path) -> None:
    artifact_root = _build_artifact_root(tmp_path)

    with pytest.raises(experiment.Stage0ThresholdExperimentError, match="no packets found in requested window"):
        experiment.run_stage0_threshold_experiment(
            workspace_root=tmp_path,
            artifact_root=artifact_root,
            asset="BTC",
            signal_engine_id="vegas_ema",
            signal_set_id="BTC-vegas_ema-canonical",
            window_start="2025-12-02T00:00:00Z",
            window_end="2025-12-02T23:59:59Z",
            forward_hours=1,
            out_dir=tmp_path / "out",
        )


def test_run_stage0_threshold_experiment_rejects_packet_without_reference_price(tmp_path: Path) -> None:
    artifact_root = _build_artifact_root(tmp_path)
    bad_packet = artifact_root / "scores" / "_scoreable_signal_subset" / "packets" / "20251201T000000Z.json"
    _write_json(
        bad_packet,
        {
            "schema_version": "signal_packet.v2",
            "asset": "BTC",
            "timestamp": "2025-12-01T00:00:00Z",
            "interactions": [],
        },
    )

    with pytest.raises(experiment.Stage0ThresholdExperimentError, match="missing reference price"):
        experiment.run_stage0_threshold_experiment(
            workspace_root=tmp_path,
            artifact_root=artifact_root,
            asset="BTC",
            signal_engine_id="vegas_ema",
            signal_set_id="BTC-vegas_ema-canonical",
            window_start="2025-12-01T00:00:00Z",
            window_end="2025-12-01T02:00:00Z",
            forward_hours=1,
            out_dir=tmp_path / "out",
        )


def test_validate_candle_coverage_accepts_last_complete_5m_candle() -> None:
    candles = [
        {"ts": experiment.parse_ts("2026-06-02T11:55:00Z")},
    ]

    experiment.validate_candle_coverage(
        candles,
        required_end=experiment.parse_ts("2026-06-02T11:59:59Z"),
    )


def test_experimental_scan_uses_adaptive_curve_score_without_fixed_eligibility() -> None:
    rows = [
        {
            "threshold_pct": 0.3,
            "resolution_rate": 1.0,
            "snapback_rate": 0.78,
            "clean_resolution_rate": 0.22,
            "median_resolution_minutes": 45,
            "p25_clean_first_leg_pct": 2.35,
            "stage0_score": 1.7,
        },
        {
            "threshold_pct": 1.7,
            "resolution_rate": 0.8,
            "snapback_rate": 0.11,
            "clean_resolution_rate": 0.71,
            "median_resolution_minutes": 390,
            "p25_clean_first_leg_pct": 2.2,
            "stage0_score": 1.2,
        },
    ]

    ranked = experiment.rank_threshold_rows(rows)

    assert ranked[0]["threshold_pct"] == 1.7
    assert "eligible" not in ranked[0]
    assert ranked[0]["adaptive_score"] > ranked[1]["adaptive_score"]
    assert ranked[0]["score_weights"]["clean_resolution"] == 0.50


def test_knee_selector_moves_past_early_high_snapback_adaptive_peak() -> None:
    rows = [
        {
            "threshold_pct": 0.2,
            "resolution_rate": 1.0,
            "snapback_rate": 0.854352,
            "clean_resolution_rate": 0.145648,
            "median_resolution_minutes": 20,
            "p25_clean_first_leg_pct": 2.235375,
            "stage0_score": 1.627893,
        },
        {
            "threshold_pct": 0.3,
            "resolution_rate": 1.0,
            "snapback_rate": 0.777975,
            "clean_resolution_rate": 0.222025,
            "median_resolution_minutes": 45,
            "p25_clean_first_leg_pct": 2.354274,
            "stage0_score": 1.742358,
        },
        {
            "threshold_pct": 0.4,
            "resolution_rate": 0.996448,
            "snapback_rate": 0.695187,
            "clean_resolution_rate": 0.30373,
            "median_resolution_minutes": 75,
            "p25_clean_first_leg_pct": 2.202274,
            "stage0_score": 1.672242,
        },
        {
            "threshold_pct": 0.5,
            "resolution_rate": 0.98579,
            "snapback_rate": 0.627027,
            "clean_resolution_rate": 0.367673,
            "median_resolution_minutes": 110,
            "p25_clean_first_leg_pct": 2.167316,
            "stage0_score": 1.593728,
        },
        {
            "threshold_pct": 0.6,
            "resolution_rate": 0.982238,
            "snapback_rate": 0.555154,
            "clean_resolution_rate": 0.436945,
            "median_resolution_minutes": 150,
            "p25_clean_first_leg_pct": 2.186241,
            "stage0_score": 1.592112,
        },
        {
            "threshold_pct": 0.7,
            "resolution_rate": 0.978686,
            "snapback_rate": 0.492196,
            "clean_resolution_rate": 0.497336,
            "median_resolution_minutes": 180,
            "p25_clean_first_leg_pct": 2.181772,
            "stage0_score": 1.550443,
        },
        {
            "threshold_pct": 0.8,
            "resolution_rate": 0.973357,
            "snapback_rate": 0.430657,
            "clean_resolution_rate": 0.554174,
            "median_resolution_minutes": 215,
            "p25_clean_first_leg_pct": 2.174633,
            "stage0_score": 1.506511,
        },
        {
            "threshold_pct": 0.9,
            "resolution_rate": 0.973357,
            "snapback_rate": 0.35219,
            "clean_resolution_rate": 0.630551,
            "median_resolution_minutes": 270,
            "p25_clean_first_leg_pct": 2.223588,
            "stage0_score": 1.546121,
        },
        {
            "threshold_pct": 1.0,
            "resolution_rate": 0.960924,
            "snapback_rate": 0.314233,
            "clean_resolution_rate": 0.659147,
            "median_resolution_minutes": 330,
            "p25_clean_first_leg_pct": 2.250217,
            "stage0_score": 1.483472,
        },
        {
            "threshold_pct": 1.1,
            "resolution_rate": 0.936057,
            "snapback_rate": 0.278937,
            "clean_resolution_rate": 0.674956,
            "median_resolution_minutes": 375,
            "p25_clean_first_leg_pct": 2.019545,
            "stage0_score": 1.239185,
        },
        {
            "threshold_pct": 1.2,
            "resolution_rate": 0.912966,
            "snapback_rate": 0.233463,
            "clean_resolution_rate": 0.699822,
            "median_resolution_minutes": 440,
            "p25_clean_first_leg_pct": 2.061208,
            "stage0_score": 1.202066,
        },
        {
            "threshold_pct": 1.3,
            "resolution_rate": 0.895204,
            "snapback_rate": 0.202381,
            "clean_resolution_rate": 0.714032,
            "median_resolution_minutes": 510,
            "p25_clean_first_leg_pct": 2.156816,
            "stage0_score": 1.184643,
        },
        {
            "threshold_pct": 1.4,
            "resolution_rate": 0.880995,
            "snapback_rate": 0.175403,
            "clean_resolution_rate": 0.726465,
            "median_resolution_minutes": 562,
            "p25_clean_first_leg_pct": 2.186241,
            "stage0_score": 1.134449,
        },
        {
            "threshold_pct": 1.5,
            "resolution_rate": 0.856128,
            "snapback_rate": 0.155602,
            "clean_resolution_rate": 0.722913,
            "median_resolution_minutes": 640,
            "p25_clean_first_leg_pct": 2.246597,
            "stage0_score": 1.082729,
        },
        {
            "threshold_pct": 1.6,
            "resolution_rate": 0.834813,
            "snapback_rate": 0.138298,
            "clean_resolution_rate": 0.719361,
            "median_resolution_minutes": 697,
            "p25_clean_first_leg_pct": 2.320846,
            "stage0_score": 1.043453,
        },
        {
            "threshold_pct": 1.7,
            "resolution_rate": 0.79929,
            "snapback_rate": 0.113333,
            "clean_resolution_rate": 0.708703,
            "median_resolution_minutes": 730,
            "p25_clean_first_leg_pct": 2.439451,
            "stage0_score": 1.016969,
        },
        {
            "threshold_pct": 1.8,
            "resolution_rate": 0.77087,
            "snapback_rate": 0.085253,
            "clean_resolution_rate": 0.705151,
            "median_resolution_minutes": 825,
            "p25_clean_first_leg_pct": 2.560425,
            "stage0_score": 1.003048,
        },
        {
            "threshold_pct": 1.9,
            "resolution_rate": 0.738899,
            "snapback_rate": 0.069712,
            "clean_resolution_rate": 0.687389,
            "median_resolution_minutes": 860,
            "p25_clean_first_leg_pct": 2.6246,
            "stage0_score": 0.949537,
        },
        {
            "threshold_pct": 2.0,
            "resolution_rate": 0.722913,
            "snapback_rate": 0.044226,
            "clean_resolution_rate": 0.690941,
            "median_resolution_minutes": 890,
            "p25_clean_first_leg_pct": 2.646139,
            "stage0_score": 0.914164,
        },
        {
            "threshold_pct": 2.1,
            "resolution_rate": 0.699822,
            "snapback_rate": 0.027919,
            "clean_resolution_rate": 0.680284,
            "median_resolution_minutes": 927,
            "p25_clean_first_leg_pct": 2.675988,
            "stage0_score": 0.866873,
        },
    ]

    ranked = experiment.rank_threshold_rows(rows)

    assert ranked[0]["threshold_pct"] == 1.7
    assert ranked[0]["selection_method"] == "adaptive_snapback_knee"
