from __future__ import annotations

from bisect import bisect_right
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
from quant_terminal_worker.signal_engines.runtime import (
    EngineLiveScanContext,
    EngineTrainingContext,
    EngineTrainingOutput,
)


EMA_PERIODS = (36, 43, 144, 169, 576, 676)
EMA_TUNNELS: dict[str, tuple[int, int]] = {
    "fast": (36, 43),
    "mid": (144, 169),
    "slow": (576, 676),
}
CANDLE_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "vol_ccy", "vol_ccy_quote", "confirm"]
DEFAULT_CONTEXT_BARS = 80
DEFAULT_PROXIMITY_THRESHOLD = Decimal("0.002")
DEFAULT_VOTE_THRESHOLD = 3
DEFAULT_DEDUPE_WINDOW_MINUTES = 120
DEFAULT_CONTEXT_TIMEFRAMES = ("2h", "1d")


def generate_training_signals(context: EngineTrainingContext) -> EngineTrainingOutput:
    raw_5m = context.market_data_reader.get_candles(asset=context.asset, timeframe="5m", origin="raw")
    if not raw_5m:
        raise ValueError(f"Raw candle data is empty for {context.asset}. Update local candle data first.")
    derived_rows = context.market_data_reader.get_rows(asset=context.asset, timeframe="5m", origin="derived")
    context_rows = {
        timeframe: context.market_data_reader.get_rows(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in _context_timeframes(context.parameters)
    }
    packets, generated_packet_count = generate_5m_cluster_packets(
        workspace_root=context.workspace_root,
        asset=context.asset,
        instrument=context.instrument,
        derived_rows=derived_rows,
        start=context.start,
        end=context.end,
        parameters=context.parameters,
        context_rows=context_rows,
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
    derived_rows = context.market_data_reader.get_rows(asset=context.asset, timeframe="5m", origin="derived")
    context_rows = {
        timeframe: context.market_data_reader.get_rows(asset=context.asset, timeframe=timeframe, origin="derived")
        for timeframe in _context_timeframes(context.parameters)
    }
    packet = scan_5m_cluster_latest(
        workspace_root=context.workspace_root,
        asset=context.asset,
        instrument=context.instrument,
        derived_rows=derived_rows,
        context_rows=context_rows,
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


def generate_5m_cluster_packets(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    derived_rows: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    parameters: dict[str, Any],
    context_rows: dict[str, list[dict[str, Any]]] | None = None,
    packet_sink: Any | None = None,
    packet_chunk_size: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    del workspace_root
    rows = _prepare_rows(derived_rows)
    if not rows:
        raise ValueError(f"Vegas 5m EMA Cluster requires derived EMA candle rows for {asset} 5m.")
    prepared_context_rows = _prepare_context_rows(asset=asset, context_rows=context_rows, parameters=parameters)
    window = timedelta(minutes=int(parameters.get("dedupe_window_minutes", DEFAULT_DEDUPE_WINDOW_MINUTES)))
    packets: list[dict[str, Any]] = []
    buffered_packets: list[dict[str, Any]] = []
    generated_packet_count = 0
    last_emitted_at: datetime | None = None

    for index, row in enumerate(rows):
        timestamp = row["timestamp"]
        if timestamp < start:
            continue
        if timestamp > end:
            break
        packet = _scan_row(
            asset=asset,
            instrument=instrument,
            rows=rows,
            context_rows=prepared_context_rows,
            index=index,
            parameters=parameters,
        )
        if packet is None:
            continue
        if last_emitted_at is not None and (timestamp - last_emitted_at) < window:
            continue
        last_emitted_at = timestamp
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


def scan_5m_cluster_latest(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    derived_rows: list[dict[str, Any]],
    context_rows: dict[str, list[dict[str, Any]]] | None = None,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    del workspace_root
    rows = _prepare_rows(derived_rows)
    if not rows:
        raise ValueError(f"Vegas 5m EMA Cluster requires derived EMA candle rows for {asset} 5m.")
    prepared_context_rows = _prepare_context_rows(asset=asset, context_rows=context_rows, parameters=parameters)
    return _scan_row(asset=asset, instrument=instrument, rows=rows, context_rows=prepared_context_rows, index=len(rows) - 1, parameters=parameters)


def scan_5m_cluster_at(
    *,
    workspace_root: Path,
    asset: str,
    instrument: str,
    derived_rows: list[dict[str, Any]],
    context_rows: dict[str, list[dict[str, Any]]] | None = None,
    timestamp: datetime,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    del workspace_root
    rows = _prepare_rows(derived_rows)
    if not rows:
        raise ValueError(f"Vegas 5m EMA Cluster requires derived EMA candle rows for {asset} 5m.")
    timestamps = [row["timestamp"] for row in rows]
    index = bisect_right(timestamps, _utc(timestamp)) - 1
    if index < 0:
        return None
    prepared_context_rows = _prepare_context_rows(asset=asset, context_rows=context_rows, parameters=parameters)
    return _scan_row(asset=asset, instrument=instrument, rows=rows, context_rows=prepared_context_rows, index=index, parameters=parameters)


def _scan_row(
    *,
    asset: str,
    instrument: str,
    rows: list[dict[str, Any]],
    context_rows: dict[str, list[dict[str, Any]]],
    index: int,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    row = rows[index]
    timestamp = row["timestamp"]
    close = _decimal(row.get("close"))
    if close == 0:
        raise ValueError("Cannot scan Vegas 5m EMA distance with zero close.")

    proximity_threshold = Decimal(str(parameters.get("proximity_threshold", DEFAULT_PROXIMITY_THRESHOLD)))
    vote_threshold = int(parameters.get("cluster_vote_threshold", parameters.get("vote_threshold", DEFAULT_VOTE_THRESHOLD)))
    ema_values: dict[int, Decimal] = {}
    ema_distances: dict[int, Decimal] = {}
    ema_validity: dict[int, bool] = {}
    interactions: list[dict[str, Any]] = []
    matched_periods: list[int] = []

    for tunnel, periods in EMA_TUNNELS.items():
        for period in periods:
            ema_value = _ema_value(row, period)
            distance_pct = abs(close - ema_value) / close
            is_valid = _ema_is_valid(row, period)
            ema_values[period] = ema_value
            ema_distances[period] = distance_pct
            ema_validity[period] = is_valid
            if not is_valid or distance_pct > proximity_threshold:
                continue
            matched_periods.append(period)
            interactions.append(
                {
                    "timeframe": "5m",
                    "tunnel": tunnel,
                    "period": period,
                    "ema_value": str(ema_value),
                    "market_price": str(close),
                    "distance_pct": str(distance_pct),
                }
            )

    if len(matched_periods) < vote_threshold:
        return None

    context_bars = int(parameters.get("context_bars", DEFAULT_CONTEXT_BARS))
    trigger_context_rows = rows[max(0, index - context_bars + 1) : index + 1]
    context_timeframes = list(_context_timeframes(parameters))
    charts = {
        "5m": {
            "role": "trigger",
            "timeframe": "5m",
            "columns": CANDLE_COLUMNS,
            "completed_candles": [_row_to_packet_row(context_row) for context_row in trigger_context_rows],
            "ema_mode": "precomputed_5m_ema_cluster",
            "ema_values": {str(period): str(value) for period, value in ema_values.items()},
            "ema_distances": {str(period): str(value) for period, value in ema_distances.items()},
            "ema_validity": {str(period): valid for period, valid in ema_validity.items()},
        }
    }
    charts.update(
        _context_charts(
            rows_by_timeframe=context_rows,
            signal_timestamp=timestamp,
            context_bars=context_bars,
            context_timeframes=context_timeframes,
        )
    )
    packet = {
        "schema_version": "signal_packet.v2",
        "asset": asset,
        "instrument": instrument,
        "timestamp": _iso_z(timestamp),
        "active_timeframes": ["5m"],
        "interactions": interactions,
        "charts": charts,
        "evidence": {
            "pattern": "vegas_ema_5m_cluster_proximity",
            "ema_mode": "precomputed_5m_ema_cluster",
            "timeframe": "5m",
            "trigger_timeframe": "5m",
            "context_timeframes": context_timeframes,
            "proximity_threshold": str(proximity_threshold),
            "vote_threshold": vote_threshold,
            "matched_ema_count": len(matched_periods),
            "matched_periods": matched_periods,
            "active_timeframes": ["5m"],
            "interactions": interactions,
            "charts": charts,
        },
    }
    validate_signal_packet(packet)
    return packet


def _ema_value(row: dict[str, Any], period: int) -> Decimal:
    for key in (f"ema_{period}", f"ema{period}"):
        if row.get(key) not in (None, ""):
            return _decimal(row[key])
    raise ValueError(
        f"Vegas 5m EMA Cluster requires derived candle column ema_{period}. "
        "Prepare EMA-enriched 5m data before using vegas_ema_5m_cluster."
    )


def _ema_is_valid(row: dict[str, Any], period: int) -> bool:
    for key in (f"ema_warmup_count_{period}", f"ema_{period}_warmup_count", "ema_warmup_count"):
        if row.get(key) not in (None, ""):
            return int(row[key]) >= period
    return True


def _prepare_context_rows(
    *,
    asset: str,
    context_rows: dict[str, list[dict[str, Any]]] | None,
    parameters: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    rows_by_timeframe: dict[str, list[dict[str, Any]]] = {}
    source = context_rows or {}
    for timeframe in _context_timeframes(parameters):
        rows = _prepare_rows(source.get(timeframe) or [])
        if not rows:
            raise ValueError(f"Vegas 5m EMA Cluster requires derived EMA context rows for {asset} {timeframe}.")
        rows_by_timeframe[timeframe] = rows
    return rows_by_timeframe


def _context_charts(
    *,
    rows_by_timeframe: dict[str, list[dict[str, Any]]],
    signal_timestamp: datetime,
    context_bars: int,
    context_timeframes: list[str],
) -> dict[str, dict[str, Any]]:
    charts: dict[str, dict[str, Any]] = {}
    for timeframe in context_timeframes:
        rows = rows_by_timeframe.get(timeframe) or []
        timestamps = [row["timestamp"] for row in rows]
        index = bisect_right(timestamps, _utc(signal_timestamp)) - 1
        if index < 0:
            continue
        context_rows = rows[max(0, index - context_bars + 1) : index + 1]
        latest_row = rows[index]
        ema_values, ema_distances, ema_validity = _ema_snapshot(latest_row)
        charts[timeframe] = {
            "role": "context",
            "timeframe": timeframe,
            "columns": CANDLE_COLUMNS,
            "completed_candles": [_row_to_packet_row(context_row) for context_row in context_rows],
            "ema_mode": "precomputed_context_ema",
            "ema_values": {str(period): str(value) for period, value in ema_values.items()},
            "ema_distances": {str(period): str(value) for period, value in ema_distances.items()},
            "ema_validity": {str(period): valid for period, valid in ema_validity.items()},
        }
    return charts


def _ema_snapshot(row: dict[str, Any]) -> tuple[dict[int, Decimal], dict[int, Decimal], dict[int, bool]]:
    close = _decimal(row.get("close"))
    if close == 0:
        raise ValueError("Cannot scan Vegas EMA context distance with zero close.")
    ema_values: dict[int, Decimal] = {}
    ema_distances: dict[int, Decimal] = {}
    ema_validity: dict[int, bool] = {}
    for period in EMA_PERIODS:
        ema_value = _ema_value(row, period)
        ema_values[period] = ema_value
        ema_distances[period] = abs(close - ema_value) / close
        ema_validity[period] = _ema_is_valid(row, period)
    return ema_values, ema_distances, ema_validity


def _context_timeframes(parameters: dict[str, Any]) -> tuple[str, ...]:
    value = parameters.get("context_timeframes", DEFAULT_CONTEXT_TIMEFRAMES)
    return tuple(str(item) for item in value)


def _prepare_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for row in rows:
        prepared.append({**row, "timestamp": _utc(row.get("timestamp") or row.get("ts"))})
    return sorted(prepared, key=lambda row: row["timestamp"])


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


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso_z(value: datetime) -> str:
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")
