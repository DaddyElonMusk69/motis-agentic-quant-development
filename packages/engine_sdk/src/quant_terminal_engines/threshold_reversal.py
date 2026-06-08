from __future__ import annotations

from datetime import datetime
from typing import Any

from quant_terminal_sdk.engine_contracts import (
    LiveSignalScanResult,
    SignalPacket,
    TrainingSignalGenerationResult,
    validate_signal_packet,
)


ENGINE_ID = "threshold_reversal"
ENGINE_VERSION = "0.1.0"
PAYLOAD_SCHEMA = "signal_packet.v2"


def generate_signals(payload: dict[str, Any]) -> dict[str, Any]:
    rows = sorted(payload.get("rows", []), key=lambda row: row["timestamp"])
    parameters = payload.get("parameters", {})
    min_move_pct = float(parameters.get("min_move_pct", 1.0))
    asset = payload["asset"]
    instrument = payload["instrument"]
    dataset_refs = list(payload.get("dataset_refs", []))

    signals: list[dict[str, Any]] = []
    if len(rows) < 2:
        return {"signals": signals}

    anchor_open = float(rows[0]["open"])
    for row in rows[1:]:
        close = float(row["close"])
        move_pct = round(((close - anchor_open) / anchor_open) * 100, 6)
        if abs(move_pct) < min_move_pct:
            continue
        timestamp = row["timestamp"]
        signals.append(
            {
                "signal_id": f"{ENGINE_ID}-{asset}-{_compact_timestamp(timestamp)}",
                "signal_engine_id": ENGINE_ID,
                "signal_engine_version": ENGINE_VERSION,
                "asset": asset,
                "instrument": instrument,
                "timestamp": timestamp,
                "data_refs": dataset_refs,
                "payload_schema": PAYLOAD_SCHEMA,
                "payload": {
                    "schema_version": PAYLOAD_SCHEMA,
                    "asset": asset,
                    "instrument": instrument,
                    "timestamp": timestamp,
                    "active_timeframes": ["5m"],
                    "evidence": {
                        "move_pct": move_pct,
                        "lookback_open": anchor_open,
                        "current_close": close,
                        "neutral_trigger": "lookback_move_exceeded",
                    },
                },
            }
        )
    return {"signals": signals}


def generate_training_signals(context: Any) -> dict[str, Any]:
    rows = [
        _row_from_candle(candle)
        for candle in context.market_data_reader.get_candles(
            asset=context.asset,
            timeframe="5m",
            origin="raw",
            start=context.start,
            end=context.end,
        )
    ]
    generated = generate_signals(
        {
            "asset": context.asset,
            "instrument": context.instrument,
            "dataset_refs": [],
            "rows": rows,
            "parameters": context.parameters,
        }
    )["signals"]
    packets = [signal["payload"] for signal in generated]
    for packet in packets:
        validate_signal_packet(packet)
    return {
        "result": TrainingSignalGenerationResult(
            status="appended" if packets else "noop",
            generated_packet_count=len(packets),
            appended_packet_count=0,
            raw_candle_end_ts=context.raw_candle_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            scan_coverage_end_ts=context.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            packet_refs=[],
        ),
        "packets": packets,
    }


def scan_live_signal(context: Any) -> LiveSignalScanResult:
    rows = [
        _row_from_candle(candle)
        for candle in context.market_data_reader.get_candles(asset=context.asset, timeframe="5m", origin="raw")
    ]
    generated = generate_signals(
        {
            "asset": context.asset,
            "instrument": context.instrument,
            "dataset_refs": [],
            "rows": rows,
            "parameters": context.parameters,
        }
    )["signals"]
    if not generated:
        return LiveSignalScanResult(
            status="no_fresh_signal",
            source="live_parquet_snapshot",
            reason="latest_confirmed_candle_did_not_trigger",
        )
    latest_ts = rows[-1]["timestamp"] if rows else None
    latest_signal = generated[-1]
    if latest_signal["timestamp"] != latest_ts:
        return LiveSignalScanResult(
            status="no_fresh_signal",
            source="live_parquet_snapshot",
            reason="latest_confirmed_candle_did_not_trigger",
        )
    packet = latest_signal["payload"]
    validate_signal_packet(packet)
    return LiveSignalScanResult(
        status="fresh_signal",
        source="live_parquet_snapshot",
        signal=SignalPacket.from_mapping(packet),
    )


def _row_from_candle(candle: Any) -> dict[str, Any]:
    return {
        "timestamp": candle.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
    }


def _compact_timestamp(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%SZ")
