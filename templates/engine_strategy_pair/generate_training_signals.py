from __future__ import annotations

from typing import Any

from quant_terminal_sdk.engine_contracts import TrainingSignalGenerationResult

try:
    from .signal_engine import scan_candles_for_packet
except ImportError:
    from signal_engine import scan_candles_for_packet


def generate_training_signals(
    *,
    asset: str,
    instrument: str | None,
    candles: list[dict[str, Any]],
    packet_ref_prefix: str = "packets",
    config: dict[str, Any] | None = None,
) -> TrainingSignalGenerationResult:
    """Minimal training generator stub.

    Real engines should iterate the requested historical window from canonical
    Parquet and append packet refs through the application's signal-pool import
    flow. This scaffold only demonstrates the contract shape.
    """
    config = config or {}
    packet = scan_candles_for_packet(
        asset=asset,
        instrument=instrument,
        candles=candles,
        range_threshold_pct=float(config.get("range_threshold_pct", 1.0)),
    )
    raw_end = str(candles[-1]["ts"]) if candles else None
    packet_refs = [f"{packet_ref_prefix}/{asset.lower()}-{packet['timestamp']}.json"] if packet else []
    return TrainingSignalGenerationResult(
        status="appended" if packet else "noop",
        generated_packet_count=1 if packet else 0,
        appended_packet_count=1 if packet else 0,
        raw_candle_end_ts=raw_end,
        scan_coverage_end_ts=raw_end,
        final_signal_end_ts=packet["timestamp"] if packet else None,
        packet_refs=packet_refs,
    )
