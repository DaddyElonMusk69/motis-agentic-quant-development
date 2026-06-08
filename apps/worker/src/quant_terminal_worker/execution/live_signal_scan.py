from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_terminal_sdk.market_data_reader import MarketDataCandle, MarketDataReader


DEFAULT_TIMEFRAMES = ("2h", "4h", "8h", "12h", "1d")
DEFAULT_CONTEXT_BARS = 80
DEFAULT_PROXIMITY_THRESHOLD = Decimal("0.002")
DEFAULT_VOTE_THRESHOLD = 2
SIGNAL_ENGINE_VERSION = "0.1"


def scan_latest_live_signal(
    *,
    route: dict[str, Any],
    repository: Any,
    workspace_root: Path,
) -> dict[str, Any] | None:
    signal_engine_id = route["signal_engine_id"]
    if signal_engine_id != "vegas_ema":
        raise ValueError(f"live signal scan is not implemented for {signal_engine_id}")

    _ensure_vegas_path(workspace_root)
    from vegas.replay_provider import ReplayMarketStateProvider
    from vegas.signal_engine import UniversalVegasSignalEngine

    asset = route["asset"].upper()
    reader = MarketDataReader(repository=repository, workspace_root=workspace_root)
    raw_5m = reader.get_candles(asset=asset, timeframe="5m", origin="raw")
    if not raw_5m:
        raise ValueError(f"Raw candle data is empty for {asset}. Update local candle data first.")
    derived = {
        timeframe: reader.get_candles(asset=asset, timeframe=timeframe, origin="derived")
        for timeframe in DEFAULT_TIMEFRAMES
    }
    latest = raw_5m[-1]
    provider = ReplayMarketStateProvider(
        asset=asset,
        raw_5m=[_to_vegas_candle(candle) for candle in raw_5m],
        derived_candles={
            timeframe: [_to_vegas_candle(candle) for candle in candles]
            for timeframe, candles in derived.items()
        },
        context_bars=DEFAULT_CONTEXT_BARS,
    )
    snapshot = provider.snapshot_at(latest.timestamp)
    engine = UniversalVegasSignalEngine(
        proximity_threshold=DEFAULT_PROXIMITY_THRESHOLD,
        vote_threshold=DEFAULT_VOTE_THRESHOLD,
    )
    packet = engine.scan(snapshot)
    if packet is None:
        return None
    payload = packet.to_dict()
    timestamp = _parse_timestamp(str(payload["timestamp"]))
    return {
        "signal_id": _build_live_signal_id(route=route, timestamp=timestamp),
        "signal_set_key": None,
        "signal_engine_id": signal_engine_id,
        "signal_engine_version": route.get("signal_engine_version") or SIGNAL_ENGINE_VERSION,
        "asset": asset,
        "instrument": route.get("instrument") or f"{asset}-USDT-SWAP",
        "timestamp": _iso_z(timestamp),
        "data_refs": [],
        "payload_schema": payload.get("schema_version", "signal_packet.v2"),
        "payload": payload,
    }


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


def _build_live_signal_id(*, route: dict[str, Any], timestamp: datetime) -> str:
    return f"{route['signal_engine_id']}:{route['asset'].upper()}:live:{timestamp.strftime('%Y%m%dT%H%M%SZ')}"


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
