from __future__ import annotations

from typing import Any

from quant_terminal_sdk.engine_contracts import LiveSignalScanResult, SignalPacket

try:
    from .signal_engine import scan_candles_for_packet
except ImportError:
    from signal_engine import scan_candles_for_packet


def scan_live_signal(
    *,
    asset: str,
    instrument: str | None,
    latest_confirmed_candles: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> LiveSignalScanResult:
    """Scan the latest eligible canonical Parquet candle state."""
    config = config or {}
    packet = scan_candles_for_packet(
        asset=asset,
        instrument=instrument,
        candles=latest_confirmed_candles,
        range_threshold_pct=float(config.get("range_threshold_pct", 1.0)),
    )
    if packet is None:
        return LiveSignalScanResult(
            status="no_fresh_signal",
            source="live_parquet_snapshot",
            reason="latest_confirmed_candle_did_not_trigger",
        )
    return LiveSignalScanResult(
        status="fresh_signal",
        source="live_parquet_snapshot",
        signal=SignalPacket.from_mapping(packet),
    )
