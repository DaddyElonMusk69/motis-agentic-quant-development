from __future__ import annotations

from typing import Any


def decide(context: dict[str, Any]) -> dict[str, Any]:
    signal = context.get("signal") or {}
    payload = signal.get("payload") if isinstance(signal.get("payload"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    range_pct = float(evidence.get("range_pct") or 0)
    threshold_pct = float(evidence.get("threshold_pct") or 1)
    if range_pct < threshold_pct:
        return {
            "action": "SKIP",
            "direction": "FLAT",
            "reason_code": "range_below_threshold",
            "diagnostics": {"range_pct": range_pct, "threshold_pct": threshold_pct},
        }
    return {
        "action": "ENTER",
        "direction": "LONG",
        "reason_code": "example_breakout_accept",
        "diagnostics": {"range_pct": range_pct, "threshold_pct": threshold_pct},
    }


def manage_position(context: dict[str, Any]) -> dict[str, Any]:
    position_context = context.get("position_context") or {}
    if position_context.get("hard_exit_expired") is True:
        return {"action": "EXIT", "reason_code": "hard_exit_expired"}
    return {"action": "HOLD", "reason_code": "mechanical_policy"}
