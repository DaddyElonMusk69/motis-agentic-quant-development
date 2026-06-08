from __future__ import annotations

from typing import Any

from quant_terminal_sdk.engine_contracts import SUPPORTED_PACKET_SCHEMA, validate_signal_packet


def scan_candles_for_packet(
    *,
    asset: str,
    instrument: str | None,
    candles: list[dict[str, Any]],
    range_threshold_pct: float = 1.0,
) -> dict[str, Any] | None:
    """Return a neutral evidence packet for the latest candle, or None."""
    if not candles:
        return None
    latest = candles[-1]
    high = float(latest["high"])
    low = float(latest["low"])
    close = float(latest["close"])
    if close <= 0:
        return None
    range_pct = (high - low) / close * 100
    if range_pct < range_threshold_pct:
        return None

    packet = {
        "schema_version": SUPPORTED_PACKET_SCHEMA,
        "asset": asset,
        "instrument": instrument,
        "timestamp": str(latest["ts"]),
        "active_timeframes": ["5m"],
        "evidence": {
            "engine": "example_breakout",
            "range_pct": range_pct,
            "close": close,
            "threshold_pct": range_threshold_pct,
        },
    }
    validate_signal_packet(packet)
    return packet
