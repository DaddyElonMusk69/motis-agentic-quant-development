from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from quant_terminal_api.repositories.market_data import (
    build_data_source_upsert,
    build_market_data_ref_upsert,
)
from quant_terminal_worker.ingestion.raw_candle_fill import _derive_candles, _write_dataset_rows


DEFAULT_DERIVED_TIMEFRAMES = ("5m", "2h", "4h", "8h", "12h", "1d")


def import_xauusd_csv_seed(
    *,
    csv_path: Path,
    target_root: Path,
    database_url: str,
    cutoff: datetime,
    source_id: str = "hybrid-xauusd-okx",
    ingestion_version: str = "xauusd-seed-pre-2025-06-01",
) -> dict[str, Any]:
    rows = list(_read_seed_rows(csv_path=csv_path, cutoff=cutoff))
    if not rows:
        raise ValueError(f"No rows before cutoff {cutoff.isoformat()} in {csv_path}")

    raw_storage_uri = target_root / "origin=raw" / f"source={source_id}" / "type=candles" / "asset=XAU" / "timeframe=5m"
    _write_dataset_rows(raw_storage_uri, rows)
    registrations = [
        _registration(
            source_id=source_id,
            ingestion_version=ingestion_version,
            timeframe="5m",
            origin="raw",
            storage_uri=raw_storage_uri,
            rows=rows,
        )
    ]

    derived_summaries: list[dict[str, Any]] = []
    for timeframe in DEFAULT_DERIVED_TIMEFRAMES:
        derived_rows = _derive_candles(
            raw_rows=rows,
            raw_timeframe="5m",
            derived_timeframe=timeframe,
        )
        if not derived_rows:
            continue
        derived_storage_uri = (
            target_root
            / "origin=derived"
            / f"source={source_id}"
            / "type=candles"
            / "asset=XAU"
            / f"timeframe={timeframe}"
        )
        _write_dataset_rows(derived_storage_uri, derived_rows)
        registrations.append(
            _registration(
                source_id=source_id,
                ingestion_version=ingestion_version,
                timeframe=timeframe,
                origin="derived",
                storage_uri=derived_storage_uri,
                rows=derived_rows,
                derived_from_dataset_id=registrations[0]["dataset_id"],
            )
        )
        derived_summaries.append(
            {
                "timeframe": timeframe,
                "row_count": len(derived_rows),
                "start_ts": derived_rows[0]["timestamp"],
                "end_ts": derived_rows[-1]["timestamp"],
            }
        )

    _upsert_registrations(
        database_url=database_url,
        source_id=source_id,
        registrations=registrations,
    )
    return {
        "source_file": str(csv_path),
        "asset": "XAU",
        "instrument": "XAU-USDT-SWAP",
        "cutoff": _to_iso(cutoff),
        "raw": {
            "dataset_id": registrations[0]["dataset_id"],
            "row_count": len(rows),
            "start_ts": rows[0]["timestamp"],
            "end_ts": rows[-1]["timestamp"],
            "storage_uri": str(raw_storage_uri),
        },
        "derived": derived_summaries,
        "registrations": registrations,
    }


def _read_seed_rows(*, csv_path: Path, cutoff: datetime) -> Iterable[dict[str, Any]]:
    cutoff_utc = _coerce_datetime(cutoff)
    with csv_path.open() as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 6:
                raise ValueError(f"Expected 6 tab-separated columns at line {line_no}, got {len(parts)}")
            timestamp = datetime.strptime(parts[0], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
            if timestamp >= cutoff_utc:
                continue
            open_, high, low, close = (float(value) for value in parts[1:5])
            yield {
                "timestamp": _to_iso(timestamp),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 0.0,
                "confirm": 1,
            }


def _registration(
    *,
    source_id: str,
    ingestion_version: str,
    timeframe: str,
    origin: str,
    storage_uri: Path,
    rows: list[dict[str, Any]],
    derived_from_dataset_id: str | None = None,
) -> dict[str, Any]:
    dataset_id = f"{source_id}-XAU-USDT-SWAP-candles-{timeframe}-{origin}-{ingestion_version}"
    schema_descriptor: dict[str, Any] = {
        "columns": ["timestamp", "open", "high", "low", "close", "volume", "confirm"],
        "format": "parquet",
        "origin": origin,
        "timestamp_assumption": "source timestamps treated as UTC",
        "volume_policy": "ignored_from_source_set_to_zero",
    }
    if derived_from_dataset_id:
        schema_descriptor["derived_from_dataset_id"] = derived_from_dataset_id
    return {
        "dataset_id": dataset_id,
        "source_id": source_id,
        "asset": "XAU",
        "instrument": "XAU-USDT-SWAP",
        "data_type": "candles",
        "timeframe": timeframe,
        "data_origin": origin,
        "start_ts": rows[0]["timestamp"],
        "end_ts": rows[-1]["timestamp"],
        "row_count": len(rows),
        "storage_backend": "parquet",
        "storage_uri": str(storage_uri),
        "schema_descriptor": schema_descriptor,
        "quality_status": "seeded",
        "ingestion_version": ingestion_version,
    }


def _upsert_registrations(
    *,
    database_url: str,
    source_id: str,
    registrations: list[dict[str, Any]],
) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            build_data_source_upsert(
                source_id=source_id,
                name="XAUUSD historical seed + OKX continuation",
                source_type="hybrid_market_data",
            )
        )
        for registration in registrations:
            connection.execute(build_market_data_ref_upsert(registration))


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import headerless XAUUSD 5m CSV as a Motis candle seed.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--target-root", default=Path(".data/market-data"), type=Path)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--cutoff", default="2025-06-01T00:00:00Z")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")
    result = import_xauusd_csv_seed(
        csv_path=args.csv,
        target_root=args.target_root,
        database_url=args.database_url,
        cutoff=_coerce_datetime(args.cutoff),
    )
    print(
        "Imported XAU seed: "
        f"{result['raw']['row_count']} raw rows, "
        f"{len(result['derived'])} derived refs, "
        f"{result['raw']['start_ts']} -> {result['raw']['end_ts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
