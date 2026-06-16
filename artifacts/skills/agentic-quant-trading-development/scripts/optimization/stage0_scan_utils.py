from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from typing import Any


def build_candle_time_index(candles: list[dict[str, Any]]) -> list[datetime]:
    return [candle["ts"] for candle in candles]


def first_candle_after(candle_time_index: list[datetime], signal_ts: datetime) -> int | None:
    index = bisect_right(candle_time_index, signal_ts)
    return index if index < len(candle_time_index) else None
