from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from quant_terminal_worker.ingestion.raw_candle_fill import _read_dataset_rows, _write_dataset_rows


EMA_PERIODS = (36, 43, 144, 169, 576, 676)


class EMARefRepository(Protocol):
    def list_refs(self) -> list[dict[str, Any]]:
        ...

    def update_ref(self, registration: dict[str, Any]) -> None:
        ...


def enrich_derived_ema_datasets(
    *,
    repository: EMARefRepository,
    asset: str | None = None,
    timeframes: tuple[str, ...] = ("5m", "2h", "4h", "8h", "12h", "1d"),
    periods: tuple[int, ...] = EMA_PERIODS,
) -> dict[str, Any]:
    asset_filter = asset.upper() if asset else None
    refs = [
        ref
        for ref in repository.list_refs()
        if ref.get("data_type") == "candles"
        and ref.get("data_origin") == "derived"
        and ref.get("timeframe") in timeframes
        and (asset_filter is None or str(ref.get("asset", "")).upper() == asset_filter)
    ]
    enriched: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for ref in refs:
        result = enrich_derived_ema_dataset(registration=ref, repository=repository, periods=periods)
        if result["status"] == "enriched":
            enriched.append(result)
        else:
            skipped.append(result)
    return {
        "status": "enriched" if enriched else "noop",
        "asset": asset_filter,
        "dataset_count": len(refs),
        "enriched_count": len(enriched),
        "skipped_count": len(skipped),
        "enriched": enriched,
        "skipped": skipped,
    }


def enrich_derived_ema_dataset(
    *,
    registration: dict[str, Any],
    repository: Any,
    periods: tuple[int, ...] = EMA_PERIODS,
) -> dict[str, Any]:
    if registration.get("data_type") != "candles" or registration.get("data_origin") != "derived":
        return {
            "dataset_id": registration["dataset_id"],
            "status": "blocked",
            "reason": "ema_enrichment_supported_for_derived_candles_only",
        }
    rows = _read_dataset_rows(Path(registration["storage_uri"]))
    if not rows:
        return {
            "dataset_id": registration["dataset_id"],
            "status": "skipped",
            "reason": "empty_dataset",
        }
    enriched_rows = enrich_rows_with_ema(rows, periods=periods)
    _write_dataset_rows(Path(registration["storage_uri"]), enriched_rows)
    updated_registration = {
        **registration,
        "start_ts": enriched_rows[0]["timestamp"],
        "end_ts": enriched_rows[-1]["timestamp"],
        "row_count": len(enriched_rows),
        "quality_status": "ema_enriched",
        "schema_descriptor": _schema_with_ema(registration.get("schema_descriptor"), periods=periods),
    }
    repository.update_ref(updated_registration)
    return {
        "dataset_id": registration["dataset_id"],
        "status": "enriched",
        "asset": registration.get("asset"),
        "timeframe": registration.get("timeframe"),
        "row_count": len(enriched_rows),
        "start_ts": enriched_rows[0]["timestamp"],
        "end_ts": enriched_rows[-1]["timestamp"],
        "ema_columns": [f"ema_{period}" for period in periods],
    }


def enrich_rows_with_ema(rows: list[dict[str, Any]], *, periods: tuple[int, ...] = EMA_PERIODS) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda row: _coerce_datetime(row["timestamp"]))
    previous: dict[int, Decimal] = {}
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(sorted_rows, start=1):
        close = Decimal(str(row["close"]))
        next_row = dict(row)
        for period in periods:
            prior = previous.get(period)
            ema = close if prior is None else _recursive_ema(previous_ema=prior, period=period, close=close)
            previous[period] = ema
            next_row[f"ema_{period}"] = float(ema)
            next_row[f"ema_warmup_count_{period}"] = index
        enriched.append(next_row)
    return enriched


def _recursive_ema(*, previous_ema: Decimal, period: int, close: Decimal) -> Decimal:
    multiplier = Decimal("2") / Decimal(period + 1)
    return previous_ema + multiplier * (close - previous_ema)


def _schema_with_ema(schema: Any, *, periods: tuple[int, ...]) -> dict[str, Any]:
    base = dict(schema) if isinstance(schema, dict) else {}
    existing_columns = list(base.get("columns") or [])
    ema_columns = [f"ema_{period}" for period in periods]
    warmup_columns = [f"ema_warmup_count_{period}" for period in periods]
    for column in (*ema_columns, *warmup_columns):
        if column not in existing_columns:
            existing_columns.append(column)
    base["columns"] = existing_columns
    base["ema"] = {
        "method": "recursive",
        "source": "close",
        "periods": list(periods),
        "columns": ema_columns,
        "warmup_columns": warmup_columns,
    }
    return base


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
