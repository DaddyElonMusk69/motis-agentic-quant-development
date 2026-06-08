from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_terminal_sdk.engine_contracts import (
    LiveSignalScanResult,
    SignalPacket,
    TrainingSignalGenerationResult,
    validate_signal_packet,
)
from quant_terminal_sdk.market_data_reader import MarketDataCandle
from quant_terminal_worker.signal_engines.runtime import (
    EngineLiveScanContext,
    EngineTrainingContext,
    EngineTrainingOutput,
)


DEFAULT_TIMEFRAMES = ("4h", "8h", "12h", "1d")
DEFAULT_CONTEXT_BARS = 80
DEFAULT_BB_PERIOD = 20
DEFAULT_BB_STDDEV = Decimal("2")
DEFAULT_PROXIMITY_THRESHOLD = Decimal("0.002")
DEFAULT_VOTE_THRESHOLD = 2
DEFAULT_DEDUPE_WINDOW_MINUTES = 120
DEFAULT_WATCHED_BANDS = ("upper", "lower")


def generate_training_signals(context: EngineTrainingContext) -> EngineTrainingOutput:
    raw_5m = context.market_data_reader.get_candles(asset=context.asset, timeframe="5m", origin="raw")
    timeframes = _timeframes(context.parameters)
    derived = {
        timeframe: context.market_data_reader.get_candles(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in timeframes
    }
    packets = generate_bollinger_packets(
        workspace_root=context.workspace_root,
        asset=context.asset,
        instrument=context.instrument,
        raw_5m=raw_5m,
        derived=derived,
        start=context.start,
        end=context.end,
        parameters=context.parameters,
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
    timeframes = _timeframes(context.parameters)
    derived = {
        timeframe: context.market_data_reader.get_candles(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in timeframes
    }
    packet = scan_bollinger_at(
        workspace_root=context.workspace_root,
        asset=context.asset,
        instrument=context.instrument,
        raw_5m=raw_5m,
        derived=derived,
        timestamp=raw_5m[-1].timestamp,
        parameters=context.parameters,
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


def generate_bollinger_packets(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    raw_5m: list[MarketDataCandle],
    derived: dict[str, list[MarketDataCandle]],
    start: datetime,
    end: datetime,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    window = timedelta(minutes=int(parameters.get("dedupe_window_minutes", DEFAULT_DEDUPE_WINDOW_MINUTES)))
    packets: list[dict[str, Any]] = []
    last_emitted_at: datetime | None = None

    for candle in raw_5m:
        if candle.timestamp < start:
            continue
        if candle.timestamp > end:
            break
        packet = scan_bollinger_at(
            workspace_root=workspace_root,
            asset=asset,
            instrument=instrument,
            raw_5m=raw_5m,
            derived=derived,
            timestamp=candle.timestamp,
            parameters=parameters,
        )
        if packet is None:
            continue
        if last_emitted_at is not None and (candle.timestamp - last_emitted_at) < window:
            continue
        last_emitted_at = candle.timestamp
        packets.append(packet)

    return packets


def scan_bollinger_at(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    raw_5m: list[MarketDataCandle],
    derived: dict[str, list[MarketDataCandle]],
    timestamp: datetime,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    _ensure_vegas_path(workspace_root)
    from vegas.bollinger_signal_engine import UniversalBollingerSignalEngine
    from vegas.replay_provider import ReplayMarketStateProvider

    timeframes = _timeframes(parameters)
    provider = ReplayMarketStateProvider(
        asset=asset,
        raw_5m=[_to_vegas_candle(candle) for candle in raw_5m],
        derived_candles={
            timeframe: [_to_vegas_candle(candle) for candle in derived[timeframe]]
            for timeframe in timeframes
        },
        timeframes=timeframes,
        context_bars=int(parameters.get("context_bars", DEFAULT_CONTEXT_BARS)),
    )
    try:
        snapshot = provider.snapshot_at(timestamp)
    except ValueError as error:
        if "Not enough completed" in str(error) or "No 5m candles" in str(error):
            return None
        raise
    engine = UniversalBollingerSignalEngine(
        bb_period=int(parameters.get("bb_period", DEFAULT_BB_PERIOD)),
        bb_stddev=Decimal(str(parameters.get("bb_stddev", DEFAULT_BB_STDDEV))),
        proximity_threshold=Decimal(str(parameters.get("proximity_threshold", DEFAULT_PROXIMITY_THRESHOLD))),
        vote_threshold=int(parameters.get("vote_threshold", DEFAULT_VOTE_THRESHOLD)),
        watched_bands=tuple(parameters.get("watched_bands", DEFAULT_WATCHED_BANDS)),
    )
    packet = engine.scan(snapshot)
    if packet is None:
        return None
    serialized = packet.to_dict()
    normalized = {
        "schema_version": "signal_packet.v2",
        "asset": serialized["asset"],
        "instrument": instrument,
        "timestamp": serialized["timestamp"],
        "active_timeframes": list(serialized.get("active_timeframes") or []),
        "evidence": {
            "pattern": "bollinger_band_proximity",
            "bb_period": int(parameters.get("bb_period", DEFAULT_BB_PERIOD)),
            "bb_stddev": str(parameters.get("bb_stddev", DEFAULT_BB_STDDEV)),
            "proximity_threshold": str(parameters.get("proximity_threshold", DEFAULT_PROXIMITY_THRESHOLD)),
            "vote_threshold": int(parameters.get("vote_threshold", DEFAULT_VOTE_THRESHOLD)),
            "active_timeframes": list(serialized.get("active_timeframes") or []),
            "interactions": list(serialized.get("interactions") or []),
        },
        "charts": serialized.get("charts") or {},
    }
    validate_signal_packet(normalized)
    return normalized


def _timeframes(parameters: dict[str, Any]) -> tuple[str, ...]:
    value = parameters.get("timeframes", DEFAULT_TIMEFRAMES)
    return tuple(str(item) for item in value)


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
        src = Path.cwd() / "artifacts" / "signal_engine" / "src"
    if not src.exists():
        raise ValueError(f"Signal engine source is missing: {src}")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
