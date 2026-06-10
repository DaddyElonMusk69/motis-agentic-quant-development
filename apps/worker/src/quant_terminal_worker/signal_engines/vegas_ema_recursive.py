from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
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


DEFAULT_TIMEFRAMES = ("2h", "4h", "8h", "12h", "1d")
DEFAULT_CONTEXT_BARS = 80
DEFAULT_PROXIMITY_THRESHOLD = Decimal("0.002")
DEFAULT_VOTE_THRESHOLD = 2
DEFAULT_DEDUPE_WINDOW_MINUTES = 120
DEFAULT_REQUIRED_CONTEXT_TIMEFRAMES = ("2h", "1d")
EMA_TUNNELS: dict[str, tuple[int, int]] = {
    "fast": (36, 43),
    "mid": (144, 169),
    "slow": (576, 676),
}
TIMEFRAME_DELTAS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
}
CANDLE_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "vol_ccy", "vol_ccy_quote", "confirm"]


@dataclass(frozen=True, slots=True)
class ActiveCandle:
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vol_ccy: Decimal
    vol_ccy_quote: Decimal
    confirm: int = 0


def generate_training_signals(context: EngineTrainingContext) -> EngineTrainingOutput:
    raw_5m = context.market_data_reader.get_candles(asset=context.asset, timeframe="5m", origin="raw")
    timeframes = _timeframes(context.parameters)
    derived_rows = {
        timeframe: context.market_data_reader.get_rows(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in timeframes
    }
    packets, generated_packet_count = generate_recursive_vegas_packets(
        workspace_root=context.workspace_root,
        asset=context.asset,
        instrument=context.instrument,
        raw_5m=raw_5m,
        derived_rows=derived_rows,
        start=context.start,
        end=context.end,
        parameters=context.parameters,
        packet_sink=context.packet_sink,
        packet_chunk_size=context.packet_chunk_size,
    )
    return EngineTrainingOutput(
        result=TrainingSignalGenerationResult(
            status="appended" if generated_packet_count else "noop",
            generated_packet_count=generated_packet_count,
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
    derived_rows = {
        timeframe: context.market_data_reader.get_rows(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in timeframes
    }
    packet = scan_recursive_vegas_at(
        workspace_root=context.workspace_root,
        asset=context.asset,
        instrument=context.instrument,
        raw_5m=raw_5m,
        derived_rows=derived_rows,
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


def generate_recursive_vegas_packets(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    raw_5m: list[MarketDataCandle],
    derived_rows: dict[str, list[dict[str, Any]]],
    start: datetime,
    end: datetime,
    parameters: dict[str, Any],
    packet_sink: Any | None = None,
    packet_chunk_size: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    window = timedelta(minutes=int(parameters.get("dedupe_window_minutes", DEFAULT_DEDUPE_WINDOW_MINUTES)))
    packets: list[dict[str, Any]] = []
    buffered_packets: list[dict[str, Any]] = []
    generated_packet_count = 0
    last_emitted_at: datetime | None = None
    prepared_indexes = {
        timeframe: _prepare_row_index(rows)
        for timeframe, rows in derived_rows.items()
    }
    raw_timestamps = [_utc(candle.timestamp) for candle in raw_5m]

    for candle in raw_5m:
        if candle.timestamp < start:
            continue
        if candle.timestamp > end:
            break
        packet = _scan_recursive_vegas_at_prepared(
            asset=asset,
            instrument=instrument,
            raw_5m=raw_5m,
            raw_timestamps=raw_timestamps,
            prepared_indexes=prepared_indexes,
            timestamp=candle.timestamp,
            parameters=parameters,
        )
        if packet is None:
            continue
        if last_emitted_at is not None and (candle.timestamp - last_emitted_at) < window:
            continue
        last_emitted_at = candle.timestamp
        generated_packet_count += 1
        if callable(packet_sink):
            buffered_packets.append(packet)
            if len(buffered_packets) >= max(1, int(packet_chunk_size)):
                packet_sink(buffered_packets)
                buffered_packets = []
        else:
            packets.append(packet)

    if callable(packet_sink) and buffered_packets:
        packet_sink(buffered_packets)

    return packets, generated_packet_count


def scan_recursive_vegas_at(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    raw_5m: list[MarketDataCandle],
    derived_rows: dict[str, list[dict[str, Any]]],
    timestamp: datetime,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    del workspace_root
    prepared_indexes = {
        timeframe: _prepare_row_index(rows)
        for timeframe, rows in derived_rows.items()
    }
    raw_timestamps = [_utc(candle.timestamp) for candle in raw_5m]
    return _scan_recursive_vegas_at_prepared(
        asset=asset,
        instrument=instrument,
        raw_5m=raw_5m,
        raw_timestamps=raw_timestamps,
        prepared_indexes=prepared_indexes,
        timestamp=timestamp,
        parameters=parameters,
    )


def _scan_recursive_vegas_at_prepared(
    *,
    asset: str,
    instrument: str,
    raw_5m: list[MarketDataCandle],
    raw_timestamps: list[datetime],
    prepared_indexes: dict[str, tuple[list[dict[str, Any]], list[datetime]]],
    timestamp: datetime,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    timestamp = _utc(timestamp)
    interactions: list[dict[str, Any]] = []
    charts: dict[str, Any] = {}
    voting_timeframes: list[str] = []
    proximity_threshold = Decimal(str(parameters.get("proximity_threshold", DEFAULT_PROXIMITY_THRESHOLD)))

    for timeframe in _timeframes(parameters):
        rows, row_timestamps = prepared_indexes.get(timeframe) or ([], [])
        if not rows:
            raise ValueError(f"Recursive Vegas EMA requires derived EMA candle rows for {asset} {timeframe}.")
        bucket_start = floor_timestamp(timestamp, timeframe)
        completed_end = bisect_left(row_timestamps, bucket_start)
        if completed_end <= 0:
            continue
        active_path = _active_5m_path(raw_5m=raw_5m, raw_timestamps=raw_timestamps, bucket_start=bucket_start, timestamp=timestamp)
        if not active_path:
            continue
        active_candle = _active_candle(bucket_start=bucket_start, path=active_path)
        context_bars = int(parameters.get("context_bars", DEFAULT_CONTEXT_BARS))
        completed_context = rows[max(0, completed_end - context_bars) : completed_end]
        chart_interactions, ema_values, ema_distances, ema_validity = _scan_timeframe(
            asset=asset,
            timeframe=timeframe,
            previous_row=rows[completed_end - 1],
            active_candle=active_candle,
            proximity_threshold=proximity_threshold,
        )
        charts[timeframe] = _chart_packet(
            timeframe=timeframe,
            completed_context=completed_context,
            active_candle=active_candle,
            ema_values=ema_values,
            ema_distances=ema_distances,
            ema_validity=ema_validity,
        )
        if chart_interactions:
            voting_timeframes.append(timeframe)
            interactions.extend(chart_interactions)

    vote_threshold = int(parameters.get("vote_threshold", DEFAULT_VOTE_THRESHOLD))
    if len(voting_timeframes) < vote_threshold:
        return None

    chart_timeframes = _packet_chart_timeframes(voting_timeframes, charts)
    packet = {
        "schema_version": "signal_packet.v2",
        "asset": asset,
        "instrument": instrument,
        "timestamp": _iso_z(timestamp),
        "active_timeframes": voting_timeframes,
        "interactions": interactions,
        "charts": {timeframe: charts[timeframe] for timeframe in chart_timeframes},
        "evidence": {
            "pattern": "vegas_ema_tunnel_proximity",
            "ema_mode": "recursive_precomputed_completed_htf_plus_active_candle",
            "proximity_threshold": str(proximity_threshold),
            "vote_threshold": vote_threshold,
            "active_timeframes": voting_timeframes,
            "interactions": interactions,
            "charts": {timeframe: charts[timeframe] for timeframe in chart_timeframes},
        },
    }
    validate_signal_packet(packet)
    return packet


def recursive_ema_update(previous_ema: Decimal | str | int | float, period: int, active_close: Decimal | str | int | float) -> Decimal:
    if period <= 0:
        raise ValueError("EMA period must be positive")
    previous = Decimal(str(previous_ema))
    close = Decimal(str(active_close))
    multiplier = Decimal("2") / Decimal(period + 1)
    return previous + multiplier * (close - previous)


def floor_timestamp(value: datetime, timeframe: str) -> datetime:
    value = _utc(value)
    delta = TIMEFRAME_DELTAS[timeframe]
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    seconds = int((value - epoch).total_seconds())
    bucket_seconds = int(delta.total_seconds())
    return epoch + timedelta(seconds=seconds - seconds % bucket_seconds)


def _scan_timeframe(
    *,
    asset: str,
    timeframe: str,
    previous_row: dict[str, Any],
    active_candle: ActiveCandle,
    proximity_threshold: Decimal,
) -> tuple[list[dict[str, Any]], dict[int, Decimal], dict[int, Decimal], dict[int, bool]]:
    del asset
    ema_values: dict[int, Decimal] = {}
    ema_distances: dict[int, Decimal] = {}
    ema_validity: dict[int, bool] = {}
    interactions: list[dict[str, Any]] = []

    for tunnel, periods in EMA_TUNNELS.items():
        period_values: list[Decimal] = []
        period_distances: list[Decimal] = []
        periods_are_valid = True
        for period in periods:
            previous_ema = _ema_value(previous_row, period)
            ema_value = recursive_ema_update(previous_ema, period, active_candle.close)
            if active_candle.close == 0:
                raise ValueError("Cannot scan Vegas EMA distance with zero active close.")
            distance_pct = abs(active_candle.close - ema_value) / active_candle.close
            is_valid = _ema_is_valid(previous_row, period)
            ema_values[period] = ema_value
            ema_distances[period] = distance_pct
            ema_validity[period] = is_valid
            periods_are_valid = periods_are_valid and is_valid
            period_values.append(ema_value)
            period_distances.append(distance_pct)

        nearest_distance = min(period_distances)
        if periods_are_valid and nearest_distance <= proximity_threshold:
            interactions.append(
                {
                    "timeframe": timeframe,
                    "tunnel": tunnel,
                    "tunnel_upper_limit": str(max(period_values)),
                    "tunnel_lower_limit": str(min(period_values)),
                    "market_price": str(active_candle.close),
                    "distance_pct": str(nearest_distance),
                }
            )

    return interactions, ema_values, ema_distances, ema_validity


def _ema_value(row: dict[str, Any], period: int) -> Decimal:
    for key in (f"ema_{period}", f"ema{period}"):
        if row.get(key) not in (None, ""):
            return Decimal(str(row[key]))
    raise ValueError(
        f"Recursive Vegas EMA requires derived candle column ema_{period}. "
        "Prepare EMA-enriched HTF data before using vegas_ema_recursive."
    )


def _ema_is_valid(row: dict[str, Any], period: int) -> bool:
    for key in (f"ema_warmup_count_{period}", f"ema_{period}_warmup_count", "ema_warmup_count"):
        if row.get(key) not in (None, ""):
            return int(row[key]) >= period
    return True


def _active_5m_path(
    *,
    raw_5m: list[MarketDataCandle],
    raw_timestamps: list[datetime],
    bucket_start: datetime,
    timestamp: datetime,
) -> list[MarketDataCandle]:
    start = bisect_left(raw_timestamps, bucket_start)
    end = bisect_right(raw_timestamps, timestamp)
    return raw_5m[start:end]


def _active_candle(*, bucket_start: datetime, path: list[MarketDataCandle]) -> ActiveCandle:
    return ActiveCandle(
        ts=bucket_start,
        open=path[0].open,
        high=max(candle.high for candle in path),
        low=min(candle.low for candle in path),
        close=path[-1].close,
        volume=sum((candle.volume for candle in path), start=Decimal("0")),
        vol_ccy=sum((candle.vol_ccy for candle in path), start=Decimal("0")),
        vol_ccy_quote=sum((candle.vol_ccy_quote for candle in path), start=Decimal("0")),
        confirm=0,
    )


def _chart_packet(
    *,
    timeframe: str,
    completed_context: list[dict[str, Any]],
    active_candle: ActiveCandle,
    ema_values: dict[int, Decimal],
    ema_distances: dict[int, Decimal],
    ema_validity: dict[int, bool],
) -> dict[str, Any]:
    return {
        "timeframe": timeframe,
        "columns": CANDLE_COLUMNS,
        "completed_candles": [_row_to_packet_row(row) for row in completed_context],
        "latest_forming_candle": _active_to_packet_row(active_candle),
        "ema_mode": "recursive_precomputed_completed_htf_plus_active_candle",
        "ema_values": {str(period): str(value) for period, value in ema_values.items()},
        "ema_distances": {str(period): str(value) for period, value in ema_distances.items()},
        "ema_validity": {str(period): valid for period, valid in ema_validity.items()},
    }


def _row_to_packet_row(row: dict[str, Any]) -> list[Any]:
    timestamp = _utc(row["timestamp"]).isoformat().replace("+00:00", "Z")
    return [
        timestamp,
        str(_decimal(row.get("open", 0))),
        str(_decimal(row.get("high", 0))),
        str(_decimal(row.get("low", 0))),
        str(_decimal(row.get("close", 0))),
        str(_decimal(row.get("volume", 0))),
        str(_decimal(row.get("vol_ccy", row.get("volCcy", 0)))),
        str(_decimal(row.get("vol_ccy_quote", row.get("volCcyQuote", 0)))),
        int(row.get("confirm", 1)),
    ]


def _active_to_packet_row(candle: ActiveCandle) -> list[Any]:
    return [
        candle.ts.isoformat().replace("+00:00", "Z"),
        str(candle.open),
        str(candle.high),
        str(candle.low),
        str(candle.close),
        str(candle.volume),
        str(candle.vol_ccy),
        str(candle.vol_ccy_quote),
        candle.confirm,
    ]


def _packet_chart_timeframes(voting_timeframes: list[str], charts: dict[str, Any]) -> list[str]:
    selected: list[str] = []
    for timeframe in (*voting_timeframes, *DEFAULT_REQUIRED_CONTEXT_TIMEFRAMES):
        if timeframe in charts and timeframe not in selected:
            selected.append(timeframe)
    return selected


def _prepare_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for row in rows:
        prepared.append({**row, "timestamp": _utc(row.get("timestamp") or row.get("ts"))})
    return sorted(prepared, key=lambda row: row["timestamp"])


def _prepare_row_index(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[datetime]]:
    prepared = _prepare_rows(rows)
    return prepared, [row["timestamp"] for row in prepared]


def _timeframes(parameters: dict[str, Any]) -> tuple[str, ...]:
    value = parameters.get("timeframes", DEFAULT_TIMEFRAMES)
    return tuple(str(item) for item in value)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso_z(value: datetime) -> str:
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")
