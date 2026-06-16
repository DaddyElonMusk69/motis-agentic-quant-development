#!/usr/bin/env python3
"""Stage 0a: Calibrate the meaningful-move threshold for natural direction.

Scans a range of thresholds (e.g., 0.2% to 3.0%) and measures:
  - Direction split: LONG/SHORT ratio. Near 50/50 = random assignment.
  - Reversal rate: % of signals that reverse past threshold in opposite direction.
  - Clean resolution: % of signals that resolve without later crossing the opposite boundary.
  - Time to resolution.

The selected threshold is the first meaningful move boundary. It is not a
risk/SL model; downstream stages derive stop and exit policy separately.
"""

import csv
import json
import sys
import argparse
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC = WORKSPACE_ROOT / "artifacts" / "signal_engine" / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from vegas.workspace import find_workspace_root
from stage0_scan_utils import build_candle_time_index, first_candle_after


WORKSPACE_ROOT = find_workspace_root(WORKSPACE_ROOT)


def parse_ts(ts_str: str) -> datetime:
    ts_str = ts_str.strip()
    if ts_str.isdigit():
        return datetime.fromtimestamp(int(ts_str) / 1000, tz=timezone.utc)
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def load_candles(csv_path: str, start: datetime, end: datetime) -> list:
    start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
    end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
    candles = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = parse_ts(row["ts"])
            if ts < start:
                continue
            if ts > end:
                break
            candles.append({
                "ts": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    return candles


def get_reference_price(sig_data: dict) -> float | None:
    evidence = sig_data.get("evidence", {})
    if isinstance(evidence, dict):
        for key in ("trigger_candle_close", "trigger_price", "reference_price"):
            value = evidence.get(key)
            if value is not None:
                return float(value)

    interactions = sig_data.get("interactions", {})
    if isinstance(interactions, dict):
        for tf in interactions:
            entries = interactions[tf]
            if entries:
                mp = entries[0].get("market_price")
                if mp:
                    return float(mp)
    elif isinstance(interactions, list):
        for entry in interactions:
            if not isinstance(entry, dict):
                continue
            mp = entry.get("market_price")
            if mp:
                return float(mp)
    for tf in ["2h", "4h", "8h", "12h", "1d"]:
        lfc = sig_data.get("charts", {}).get(tf, {}).get("latest_forming_candle", {})
        if lfc and lfc.get("close"):
            return float(lfc["close"])
    return None


def analyze_signal(
    candles: list,
    signal_ts: datetime,
    ref_price: float,
    forward_hours: int,
    threshold_pct: float,
    candle_time_index: list[datetime] | None = None,
) -> dict:
    """
    For a given threshold, determine:
    - natural_direction: which side hit threshold first (or None if neither)
    - first_move_pct: how far it went before reversing past threshold the other way
    - reversed: did it reverse past threshold before window end?
    """
    cutoff = signal_ts + timedelta(hours=forward_hours)
    threshold_abs = threshold_pct / 100.0

    first_idx = first_candle_after(candle_time_index or build_candle_time_index(candles), signal_ts)
    if first_idx is None:
        return {"natural_direction": None, "first_move_pct": 0, "reversed": False,
                "status": "no_candles"}

    long_target = ref_price * (1 + threshold_abs)
    short_target = ref_price * (1 - threshold_abs)

    long_hit_ts = None
    short_hit_ts = None
    long_hit_idx = None
    short_hit_idx = None

    for i in range(first_idx, len(candles)):
        c = candles[i]
        if c["ts"] > cutoff:
            break
        if long_hit_ts is None and c["high"] >= long_target:
            long_hit_ts = c["ts"]
            long_hit_idx = i
        if short_hit_ts is None and c["low"] <= short_target:
            short_hit_ts = c["ts"]
            short_hit_idx = i
        if long_hit_ts is not None and short_hit_ts is not None:
            break

    # Neither hit
    if long_hit_ts is None and short_hit_ts is None:
        return {"natural_direction": None, "first_move_pct": 0, "reversed": False,
                "status": "no_trigger"}

    # Determine natural direction
    if long_hit_ts is not None and short_hit_ts is None:
        natural_direction = "LONG"
        first_hit_idx = long_hit_idx
    elif short_hit_ts is not None and long_hit_ts is None:
        natural_direction = "SHORT"
        first_hit_idx = short_hit_idx
    else:
        # Both hit in same candle — check which one was closer to ref
        # Or use the one that was hit first (closer to signal_ts)
        if long_hit_ts < short_hit_ts:
            natural_direction = "LONG"
            first_hit_idx = long_hit_idx
        else:
            natural_direction = "SHORT"
            first_hit_idx = short_hit_idx

    if first_hit_idx is None:
        return {"natural_direction": None, "first_move_pct": 0, "reversed": False,
                "status": "index_error"}
    resolution_minutes = int((candles[first_hit_idx]["ts"] - signal_ts).total_seconds() // 60)

    # Now compute first_move_pct: how far in natural direction before reversing
    # past threshold the other way
    if natural_direction == "LONG":
        peak = ref_price
        reversal_threshold = short_target
        reversed_ = False
        for i in range(first_hit_idx, len(candles)):
            c = candles[i]
            if c["ts"] > cutoff:
                break
            if c["high"] > peak:
                peak = c["high"]
            if c["low"] <= reversal_threshold:
                reversed_ = True
                break
        first_move_pct = (peak - ref_price) / ref_price * 100
    else:
        trough = ref_price
        reversal_threshold = long_target
        reversed_ = False
        for i in range(first_hit_idx, len(candles)):
            c = candles[i]
            if c["ts"] > cutoff:
                break
            if c["low"] < trough:
                trough = c["low"]
            if c["high"] >= reversal_threshold:
                reversed_ = True
                break
        first_move_pct = (ref_price - trough) / ref_price * 100

    return {
        "natural_direction": natural_direction,
        "first_move_pct": round(first_move_pct, 4),
        "reversed": reversed_,
        "resolution_minutes": resolution_minutes,
        "status": "ok"
    }


def percentiles(values: list, *pcts) -> dict:
    if not values:
        return {}
    vals = sorted(values)
    n = len(vals)
    result = {}
    for p in pcts:
        idx = int(n * p / 100)
        idx = min(idx, n - 1)
        result[f"p{p}"] = round(vals[idx], 4)
    return result


def _normalized(value: float, values: list[float], *, higher_is_better: bool = True) -> float:
    low = min(values)
    high = max(values)
    if high == low:
        return 1.0
    normalized = (value - low) / (high - low)
    if not higher_is_better:
        normalized = 1.0 - normalized
    return round(normalized, 6)


def _clean_resolution_rate(row: dict) -> float:
    total_signals = float(row.get("total_signals") or 0)
    if total_signals <= 0:
        total_signals = float(row.get("total_valid", 0)) + float(row.get("no_trigger", 0))
    if total_signals <= 0:
        return 0.0
    clean_count = float(row.get("clean_resolution_count", row.get("total_valid", 0) - row.get("reversed_count", 0)))
    return clean_count / total_signals


def _snapback_rate(row: dict) -> float:
    if "snapback_rate" in row:
        return float(row["snapback_rate"])
    if row.get("reversal_rate_pct") is not None:
        return float(row["reversal_rate_pct"]) / 100.0
    total_valid = float(row.get("total_valid", 0))
    if total_valid <= 0:
        return 0.0
    return float(row.get("reversed_count", 0)) / total_valid


def rank_adaptive_threshold_rows(rows: list[dict]) -> list[dict]:
    clean_values = [_clean_resolution_rate(row) for row in rows]
    snapback_values = [_snapback_rate(row) for row in rows]
    time_values = [
        float(row["median_resolution_minutes"] if row.get("median_resolution_minutes") is not None else 10**9)
        for row in rows
    ]
    annotated = []
    for row in rows:
        clean_rate = _clean_resolution_rate(row)
        snapback_rate = _snapback_rate(row)
        median_resolution = float(row["median_resolution_minutes"] if row.get("median_resolution_minutes") is not None else 10**9)
        clean_component = _normalized(clean_rate, clean_values)
        snapback_component = _normalized(snapback_rate, snapback_values, higher_is_better=False)
        time_component = _normalized(median_resolution, time_values, higher_is_better=False)
        adaptive_score = round(
            clean_component * 0.50
            + snapback_component * 0.35
            + time_component * 0.15,
            6,
        )
        annotated.append({
            **row,
            "clean_resolution_rate": round(clean_rate, 6),
            "snapback_rate": round(snapback_rate, 6),
            "adaptive_score": adaptive_score,
            "score_components": {
                "clean_resolution": clean_component,
                "snapback": snapback_component,
                "time_to_resolution": time_component,
            },
            "score_weights": {
                "clean_resolution": 0.50,
                "snapback": 0.35,
                "time_to_resolution": 0.15,
            },
        })

    ranked = sorted(
        annotated,
        key=lambda row: (
            -float(row["adaptive_score"]),
            float(row["snapback_rate"]),
            float(row["median_resolution_minutes"] if row.get("median_resolution_minutes") is not None else 10**9),
            float(row["threshold_pct"]),
        ),
    )
    if not ranked:
        return []
    stable_floor = float(ranked[0]["adaptive_score"]) * 0.95
    return [
        {
            **row,
            "stable_band_member": float(row["adaptive_score"]) >= stable_floor,
            "stable_band_score_floor": round(stable_floor, 6),
        }
        for row in ranked
    ]


def select_snapback_knee_threshold(rows: list[dict]) -> float:
    stable_rows = sorted(
        [row for row in rows if row.get("stable_band_member")],
        key=lambda row: float(row["threshold_pct"]),
    )
    if len(stable_rows) < 2:
        return float((stable_rows or rows)[0]["threshold_pct"])
    start_snapback = float(stable_rows[0]["snapback_rate"])
    end_snapback = float(stable_rows[-1]["snapback_rate"])
    total_improvement = start_snapback - end_snapback
    if total_improvement <= 0:
        return float(max(stable_rows, key=lambda row: float(row["adaptive_score"]))["threshold_pct"])
    target_snapback = start_snapback - (total_improvement * 0.5)
    for row in stable_rows:
        if float(row["snapback_rate"]) <= target_snapback:
            return float(row["threshold_pct"])
    return float(stable_rows[-1]["threshold_pct"])


def select_adaptive_meaningful_move_threshold(rows: list[dict]) -> dict:
    ranked = rank_adaptive_threshold_rows(rows)
    if not ranked:
        raise ValueError("cannot select threshold from empty scan results")
    chosen = select_snapback_knee_threshold(ranked)
    stable_members = [row for row in ranked if row["stable_band_member"]]
    stable_thresholds = [float(row["threshold_pct"]) for row in stable_members]
    ordered = sorted(
        [
            {
                **row,
                "selection_method": "adaptive_snapback_knee"
                if float(row["threshold_pct"]) == chosen
                else "adaptive_score_rank",
            }
            for row in ranked
        ],
        key=lambda row: (
            0 if float(row["threshold_pct"]) == chosen else 1,
            -float(row["adaptive_score"]),
            float(row["snapback_rate"]),
            float(row["threshold_pct"]),
        ),
    )
    return {
        "chosen_threshold_pct": chosen,
        "stable_range": [
            min(stable_thresholds) if stable_thresholds else chosen,
            max(stable_thresholds) if stable_thresholds else chosen,
        ],
        "selection_method": "adaptive_snapback_knee",
        "ranked_thresholds": ordered,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 0a: significance threshold calibration")
    parser.add_argument("signal_dir", help="Directory of signal JSON files")
    parser.add_argument("--candles", required=True, help="Path to 5m candles CSV")
    parser.add_argument("--forward-hours", type=int, default=36)
    parser.add_argument("--threshold-range", nargs=3, type=float,
                        default=[0.2, 3.0, 0.1],
                        help="Start, end, step for threshold scan (pct)")
    parser.add_argument("--out", required=True, help="Canonical output JSON path")
    parser.add_argument("--asset", default="UNKNOWN")
    parser.add_argument("--vote-threshold", type=int, default=0)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    threshold_start, threshold_end, threshold_step = args.threshold_range
    signal_dir = Path(args.signal_dir)
    candles_path = Path(args.candles)
    forward_hours = args.forward_hours

    # Discover signal files
    signal_files = sorted(signal_dir.glob("*.json"))
    signal_files = [f for f in signal_files if f.name not in ("index.json", "summary.json")]
    total = len(signal_files)
    print(f"Found {total} signal files")

    if total == 0:
        print("No signal files found.")
        sys.exit(1)

    # Parse all signal timestamps
    signal_records = []
    for sf in signal_files:
        dt_str = sf.stem.replace("Z", "")
        try:
            ts = datetime.strptime(dt_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            signal_records.append((sf, ts))
        except ValueError:
            continue

    earliest = min(ts for _, ts in signal_records)
    latest = max(ts for _, ts in signal_records) + timedelta(hours=forward_hours)

    print(f"Loading candles...")
    candles = load_candles(str(candles_path), earliest, latest)
    candle_time_index = build_candle_time_index(candles)
    print(f"Loaded {len(candles):,} candles. Signal range: {earliest} → {latest}")

    # Pre-load all signal data
    print(f"Loading {len(signal_records)} signal packets...")
    signal_data = []
    for sf, sig_ts in signal_records:
        try:
            with open(sf) as f:
                sd = json.load(f)
            ref_price = get_reference_price(sd)
            if ref_price is None:
                continue
            signal_data.append({
                "signal_id": sf.stem,
                "signal_ts": sig_ts,
                "ref_price": ref_price,
            })
        except Exception:
            continue
    print(f"Loaded {len(signal_data)} signals with valid reference prices")

    # Generate thresholds
    thresholds = []
    t = threshold_start
    while t <= threshold_end + 1e-9:
        thresholds.append(round(t, 2))
        t += threshold_step

    print(f"\nScanning {len(thresholds)} thresholds ({threshold_start}% → {threshold_end}%)...")
    print(f"{'Threshold':>10s}  {'Split(L/S)':>12s}  {'Rev%':>6s}  {'TravelP25':>10s}  {'TravelP50':>10s}  {'NoTrig%':>8s}")
    print("-" * 72)

    results = []
    for thresh_idx, threshold in enumerate(thresholds):
        longs = 0
        shorts = 0
        reversed_count = 0
        no_trigger = 0
        travel_pcts = []
        resolution_minutes = []

        for sd in signal_data:
            r = analyze_signal(
                candles,
                sd["signal_ts"],
                sd["ref_price"],
                forward_hours,
                threshold,
                candle_time_index,
            )

            if r["status"] == "no_trigger":
                no_trigger += 1
                continue

            if r["natural_direction"] == "LONG":
                longs += 1
            elif r["natural_direction"] == "SHORT":
                shorts += 1
            else:
                no_trigger += 1
                continue

            if r["reversed"]:
                reversed_count += 1
            travel_pcts.append(r["first_move_pct"])
            if r.get("resolution_minutes") is not None:
                resolution_minutes.append(int(r["resolution_minutes"]))

        total_valid = longs + shorts
        if total_valid == 0:
            continue

        split_str = f"{longs}/{shorts}" if total_valid > 0 else "N/A"
        rev_pct = reversed_count / total_valid * 100 if total_valid > 0 else 0
        no_trig_pct = no_trigger / len(signal_data) * 100
        pcts = percentiles(travel_pcts, 25, 50, 75)
        median_resolution_minutes = int(statistics.median(resolution_minutes)) if resolution_minutes else None

        travel_p25 = pcts.get("p25", 0)
        travel_p50 = pcts.get("p50", 0)

        # Stability markers
        flags = []
        if rev_pct < 15:
            flags.append("✓rev")
        else:
            flags.append(" ✗rev")
        if travel_p25 >= 1.0:
            flags.append("✓travel")
        else:
            flags.append(" ✗travel")
        if 35 <= (longs / total_valid * 100) <= 65:
            flags.append("~split")
        else:
            flags.append("✓split")

        flag_str = " ".join(flags)
        print(f"{threshold:>8.1f}%  {split_str:>12s}  {rev_pct:>5.1f}%  {travel_p25:>8.2f}%  {travel_p50:>8.2f}%  {no_trig_pct:>7.1f}%  {flag_str}")

        results.append({
            "threshold_pct": threshold,
            "total_signals": len(signal_data),
            "long_count": longs,
            "short_count": shorts,
            "total_valid": total_valid,
            "no_trigger": no_trigger,
            "no_trigger_pct": round(no_trig_pct, 1),
            "reversed_count": reversed_count,
            "reversal_rate_pct": round(rev_pct, 1),
            "clean_resolution_count": total_valid - reversed_count,
            "clean_resolution_rate": round((total_valid - reversed_count) / len(signal_data), 6),
            "median_resolution_minutes": median_resolution_minutes,
            "travel_p25": round(travel_p25, 2),
            "travel_p50": round(travel_p50, 2),
            "reversal_ok": rev_pct < 15,
            "travel_ok": travel_p25 >= 1.0,
            "split_ok": not (35 <= (longs / total_valid * 100) <= 65 if total_valid > 0 else True),
        })

    # ── Select meaningful-move threshold ─────────────────────────────
    print(f"\n{'='*70}")
    print(f"MEANINGFUL-MOVE THRESHOLD SELECTION")
    print(f"{'='*70}")

    selection = select_adaptive_meaningful_move_threshold(results)
    chosen = selection["chosen_threshold_pct"]
    low, high = selection["stable_range"]
    print("\nAdaptive meaningful-move top thresholds:")
    for r in selection["ranked_thresholds"][:5]:
        print(
            f"  {r['threshold_pct']:.1f}%  score={r['adaptive_score']:.6f}  "
            f"clean={r['clean_resolution_rate'] * 100:.1f}%  "
            f"snapback={r['snapback_rate'] * 100:.1f}%  "
            f"median_resolution={r['median_resolution_minutes']}m"
        )
    print(f"\n  Stable range: {low:.1f}% – {high:.1f}%")
    print(f"  Chosen threshold ({selection['selection_method']}): {chosen:.1f}%")

    # ── Save ──────────────────────────────────────────────────────────
    out_path = args.out

    out = {
        "asset": args.asset,
        "vote_threshold": args.vote_threshold,
        "total_signals": len(signal_data),
        "forward_hours": forward_hours,
        "threshold_range": [threshold_start, threshold_end, threshold_step],
        "stable_range": [low, high],
        "chosen_threshold_pct": chosen,
        "threshold_semantics": "first_meaningful_move",
        "selection_method": selection["selection_method"],
        "adaptive_stable_range": selection["stable_range"],
        "adaptive_top_thresholds": selection["ranked_thresholds"][:5],
        "scan_results": results,
    }

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
