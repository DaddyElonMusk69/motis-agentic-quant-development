from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_terminal_sdk.engine_contracts import LiveSignalScanResult, SignalPacket, TrainingSignalGenerationResult
from quant_terminal_sdk.market_data_reader import MarketDataCandle
from quant_terminal_worker.signal_engines.runtime import (
    EngineLiveScanContext,
    EngineTrainingContext,
    EngineTrainingOutput,
)


DEFAULT_TIMEFRAMES = ("2h", "4h", "8h", "12h", "1d")
DEFAULT_CONTEXT_BARS = 80
DEFAULT_PROXIMITY_THRESHOLD = Decimal("0.002")
DEFAULT_VOTE_THRESHOLD = 2
DEFAULT_DEDUPE_WINDOW_MINUTES = 120


def generate_training_signals(context: EngineTrainingContext) -> EngineTrainingOutput:
    raw_5m = context.market_data_reader.get_candles(asset=context.asset, timeframe="5m", origin="raw")
    derived = {
        timeframe: context.market_data_reader.get_candles(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in DEFAULT_TIMEFRAMES
    }
    packets = generate_vegas_packets(
        workspace_root=context.workspace_root,
        asset=context.asset,
        raw_5m=raw_5m,
        derived=derived,
        start=context.start,
        end=context.end,
        context_bars=int(context.parameters.get("context_bars", DEFAULT_CONTEXT_BARS)),
        proximity_threshold=Decimal(str(context.parameters.get("proximity_threshold", DEFAULT_PROXIMITY_THRESHOLD))),
        vote_threshold=int(context.parameters.get("vote_threshold", DEFAULT_VOTE_THRESHOLD)),
        window_minutes=int(context.parameters.get("dedupe_window_minutes", DEFAULT_DEDUPE_WINDOW_MINUTES)),
    )
    return EngineTrainingOutput(
        result=TrainingSignalGenerationResult(
            status="appended" if packets else "noop",
            generated_packet_count=len(packets),
            appended_packet_count=0,
            raw_candle_end_ts=_iso_z(context.raw_candle_end),
            scan_coverage_end_ts=_iso_z(context.end),
            packet_refs=[],
        ),
        packets=packets,
    )


def scan_live_signal(context: EngineLiveScanContext) -> LiveSignalScanResult:
    raw_5m = context.market_data_reader.get_candles(asset=context.asset, timeframe="5m", origin="raw")
    if not raw_5m:
        raise ValueError(f"Raw candle data is empty for {context.asset}. Update local candle data first.")
    derived = {
        timeframe: context.market_data_reader.get_candles(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in DEFAULT_TIMEFRAMES
    }
    latest = raw_5m[-1]
    _ensure_vegas_path(context.workspace_root)
    from vegas.replay_provider import ReplayMarketStateProvider
    from vegas.signal_engine import UniversalVegasSignalEngine

    provider = ReplayMarketStateProvider(
        asset=context.asset,
        raw_5m=[_to_vegas_candle(candle) for candle in raw_5m],
        derived_candles={
            timeframe: [_to_vegas_candle(candle) for candle in candles]
            for timeframe, candles in derived.items()
        },
        context_bars=int(context.parameters.get("context_bars", DEFAULT_CONTEXT_BARS)),
    )
    snapshot = provider.snapshot_at(latest.timestamp)
    engine = UniversalVegasSignalEngine(
        proximity_threshold=Decimal(str(context.parameters.get("proximity_threshold", DEFAULT_PROXIMITY_THRESHOLD))),
        vote_threshold=int(context.parameters.get("vote_threshold", DEFAULT_VOTE_THRESHOLD)),
    )
    packet = engine.scan(snapshot)
    if packet is None:
        return LiveSignalScanResult(
            status="no_fresh_signal",
            source="live_parquet_snapshot",
            reason="latest_confirmed_candle_did_not_trigger",
        )
    return LiveSignalScanResult(
        status="fresh_signal",
        source="live_parquet_snapshot",
        signal=SignalPacket.from_mapping(packet.to_dict()),
    )


def generate_vegas_packets(
    *,
    workspace_root: Path,
    asset: str,
    raw_5m: list[MarketDataCandle],
    derived: dict[str, list[MarketDataCandle]],
    start: datetime,
    end: datetime,
    context_bars: int,
    proximity_threshold: Decimal,
    vote_threshold: int,
    window_minutes: int,
) -> list[dict[str, Any]]:
    _ensure_vegas_path(workspace_root)
    from vegas.replay_provider import ReplayMarketStateProvider
    from vegas.signal_engine import UniversalVegasSignalEngine

    provider = ReplayMarketStateProvider(
        asset=asset,
        raw_5m=[_to_vegas_candle(candle) for candle in raw_5m],
        derived_candles={
            timeframe: [_to_vegas_candle(candle) for candle in candles]
            for timeframe, candles in derived.items()
        },
        context_bars=context_bars,
    )
    engine = UniversalVegasSignalEngine(
        proximity_threshold=proximity_threshold,
        vote_threshold=vote_threshold,
    )
    window = timedelta(minutes=window_minutes)
    packets: list[dict[str, Any]] = []
    last_emitted_at: datetime | None = None

    for candle in provider.raw_5m:
        if candle.ts < start:
            continue
        if candle.ts > end:
            break
        try:
            snapshot = provider.snapshot_at(candle.ts)
        except ValueError as error:
            if "Not enough completed" not in str(error):
                raise
            continue
        packet = engine.scan(snapshot)
        if packet is None:
            continue
        if last_emitted_at is not None and (candle.ts - last_emitted_at) < window:
            continue
        last_emitted_at = candle.ts
        packets.append(packet.to_dict())

    return packets


def _to_vegas_candle(candle: MarketDataCandle) -> Any:
    from vegas.schemas import Candle

    return Candle(
        ts=candle.timestamp,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        vol_ccy=candle.vol_ccy,
        vol_ccy_quote=candle.vol_ccy_quote,
        confirm=candle.confirm,
    )


def _ensure_vegas_path(root: Path) -> None:
    src = root / "artifacts" / "signal_engine" / "src"
    if not src.exists():
        raise ValueError(f"Vegas signal engine source is missing: {src}")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
