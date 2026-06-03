from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant_terminal_sdk.market_data import MarketDataReference
from quant_terminal_sdk.parquet_store import write_candles


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    registrations: list[dict[str, Any]]
    parquet_paths: list[Path]


def normalize_legacy_csv_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "timestamp": row["ts"],
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
        "vol_ccy": float(row["vol_ccy"]),
        "vol_ccy_quote": float(row["vol_ccy_quote"]),
        "confirm": int(row["confirm"]),
    }


def import_legacy_dev_data(
    *,
    source_root: Path,
    target_root: Path,
    assets: list[str] | None = None,
    timeframes: list[str] | None = None,
    ingestion_version: str = "legacy-dev-data",
) -> LegacyImportResult:
    manifest_paths = sorted((source_root / "manifests").glob("*.json"))
    requested_assets = set(assets or [])
    requested_timeframes = set(timeframes or [])
    registrations: list[dict[str, Any]] = []
    parquet_paths: list[Path] = []

    for manifest_path in manifest_paths:
        manifest = json.loads(manifest_path.read_text())
        asset = manifest["asset"]
        if requested_assets and asset not in requested_assets:
            continue

        for origin, entries in (("raw", manifest.get("raw", {})), ("derived", manifest.get("derived", {}))):
            for timeframe, descriptor in sorted(entries.items()):
                if requested_timeframes and timeframe not in requested_timeframes:
                    continue

                csv_path = _resolve_legacy_path(source_root, descriptor["path"])
                if not csv_path.exists():
                    raise FileNotFoundError(csv_path)

                rows = _read_legacy_rows(csv_path)
                if not rows:
                    continue

                instrument = f"{asset}-USDT-SWAP"
                reference = MarketDataReference(
                    dataset_id=(
                        f"legacy-okx-{instrument}-candles-{timeframe}-{origin}-"
                        f"{ingestion_version}"
                    ),
                    source_id="okx",
                    asset=asset,
                    instrument=instrument,
                    data_type="candles",
                    timeframe=timeframe,
                    storage_backend="parquet",
                )
                written = _write_monthly_partitions(
                    root=target_root / f"origin={origin}",
                    reference=reference,
                    rows=rows,
                )
                parquet_paths.extend(written)
                registrations.append(
                    _build_registration(
                        reference=reference,
                        target_root=target_root / f"origin={origin}",
                        rows=rows,
                        origin=origin,
                        descriptor=descriptor,
                        ingestion_version=ingestion_version,
                    )
                )

    return LegacyImportResult(registrations=registrations, parquet_paths=parquet_paths)


def _read_legacy_rows(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open(newline="") as handle:
        return [normalize_legacy_csv_row(row) for row in csv.DictReader(handle)]


def _write_monthly_partitions(
    *,
    root: Path,
    reference: MarketDataReference,
    rows: list[dict[str, Any]],
) -> list[Path]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        year = int(row["timestamp"][0:4])
        month = int(row["timestamp"][5:7])
        grouped[(year, month)].append(row)

    paths: list[Path] = []
    for (year, month), month_rows in sorted(grouped.items()):
        paths.append(
            write_candles(
                root=root,
                reference=reference,
                year=year,
                month=month,
                rows=month_rows,
            )
        )
    return paths


def _build_registration(
    *,
    reference: MarketDataReference,
    target_root: Path,
    rows: list[dict[str, Any]],
    origin: str,
    descriptor: dict[str, Any],
    ingestion_version: str,
) -> dict[str, Any]:
    storage_uri = (
        target_root
        / f"source={reference.source_id}"
        / f"type={reference.data_type}"
        / f"asset={reference.asset}"
        / f"timeframe={reference.timeframe}"
    )
    return {
        "dataset_id": reference.dataset_id,
        "source_id": reference.source_id,
        "asset": reference.asset,
        "instrument": reference.instrument,
        "data_type": reference.data_type,
        "timeframe": reference.timeframe,
        "data_origin": origin,
        "start_ts": rows[0]["timestamp"],
        "end_ts": rows[-1]["timestamp"],
        "row_count": len(rows),
        "storage_backend": reference.storage_backend,
        "storage_uri": str(storage_uri),
        "schema_descriptor": {
            "columns": [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "vol_ccy",
                "vol_ccy_quote",
                "confirm",
            ],
            "format": "parquet",
            "origin": origin,
            "legacy_rule": descriptor.get("rule"),
        },
        "quality_status": "ingested",
        "ingestion_version": ingestion_version,
    }


def _resolve_legacy_path(source_root: Path, manifest_path: str) -> Path:
    path = Path(manifest_path)
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "dev" and parts[1] == "data":
        return source_root.joinpath(*parts[2:])
    return source_root / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy dev/data candles to Parquet.")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--target-root", required=True, type=Path)
    parser.add_argument("--registrations-out", required=True, type=Path)
    parser.add_argument("--asset", action="append", dest="assets")
    parser.add_argument("--timeframe", action="append", dest="timeframes")
    parser.add_argument("--ingestion-version", default="legacy-dev-data")
    args = parser.parse_args()

    result = import_legacy_dev_data(
        source_root=args.source_root,
        target_root=args.target_root,
        assets=args.assets,
        timeframes=args.timeframes,
        ingestion_version=args.ingestion_version,
    )
    args.registrations_out.parent.mkdir(parents=True, exist_ok=True)
    args.registrations_out.write_text(json.dumps(result.registrations, indent=2))
    print(
        f"Imported {len(result.registrations)} datasets and wrote "
        f"{len(result.parquet_paths)} parquet partitions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
