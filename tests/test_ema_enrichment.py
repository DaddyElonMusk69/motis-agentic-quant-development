from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from quant_terminal_sdk.parquet_store import read_candles
from quant_terminal_worker.ingestion.ema_enrichment import (
    enrich_derived_ema_dataset,
    enrich_derived_ema_datasets,
    enrich_rows_with_ema,
)


class FakeRepository:
    def __init__(self) -> None:
        self.refs = []
        self.updated = []

    def list_refs(self):
        return self.refs

    def update_ref(self, registration):
        self.updated.append(registration)


def test_enrich_rows_with_ema_adds_recursive_ema_and_warmup_columns():
    rows = [
        _row("2026-06-01T00:00:00Z", close=100),
        _row("2026-06-01T02:00:00Z", close=110),
    ]

    enriched = enrich_rows_with_ema(rows, periods=(3,))

    assert enriched[0]["ema_3"] == 100.0
    assert enriched[0]["ema_warmup_count_3"] == 1
    assert enriched[1]["ema_3"] == 105.0
    assert enriched[1]["ema_warmup_count_3"] == 2


def test_enrich_derived_ema_dataset_rewrites_parquet_and_updates_ref(tmp_path: Path):
    storage_uri = tmp_path / "origin=derived/source=okx/type=candles/asset=BTC/timeframe=2h"
    path = storage_uri / "year=2026/month=06/data.parquet"
    path.parent.mkdir(parents=True)
    _write_parquet(path, [_row("2026-06-01T00:00:00Z", close=100), _row("2026-06-01T02:00:00Z", close=110)])
    registration = {
        "dataset_id": "btc-derived-2h",
        "source_id": "okx",
        "asset": "BTC",
        "instrument": "BTC-USDT-SWAP",
        "data_type": "candles",
        "timeframe": "2h",
        "data_origin": "derived",
        "row_count": 2,
        "storage_backend": "parquet",
        "storage_uri": str(storage_uri),
        "schema_descriptor": {"columns": ["timestamp", "open", "high", "low", "close", "volume"]},
        "quality_status": "rebuilt",
        "ingestion_version": "test",
    }
    repository = FakeRepository()

    result = enrich_derived_ema_dataset(registration=registration, repository=repository, periods=(3,))

    assert result["status"] == "enriched"
    assert result["ema_columns"] == ["ema_3"]
    rows = read_candles(path)
    assert rows[1]["ema_3"] == 105.0
    assert repository.updated[0]["quality_status"] == "ema_enriched"
    assert repository.updated[0]["schema_descriptor"]["ema"]["periods"] == [3]


def test_enrich_derived_ema_datasets_filters_by_asset_and_timeframe(tmp_path: Path):
    btc_storage = tmp_path / "origin=derived/source=okx/type=candles/asset=BTC/timeframe=2h"
    eth_storage = tmp_path / "origin=derived/source=okx/type=candles/asset=ETH/timeframe=2h"
    for storage_uri in (btc_storage, eth_storage):
        path = storage_uri / "year=2026/month=06/data.parquet"
        path.parent.mkdir(parents=True)
        _write_parquet(path, [_row("2026-06-01T00:00:00Z", close=100)])
    repository = FakeRepository()
    repository.refs = [
        _registration("btc-derived-2h", "BTC", btc_storage),
        _registration("eth-derived-2h", "ETH", eth_storage),
    ]

    result = enrich_derived_ema_datasets(repository=repository, asset="BTC", timeframes=("2h",), periods=(3,))

    assert result["status"] == "enriched"
    assert result["dataset_count"] == 1
    assert repository.updated[0]["dataset_id"] == "btc-derived-2h"


def test_enrich_derived_ema_datasets_default_includes_5m(tmp_path: Path):
    storage_uri = tmp_path / "origin=derived/source=okx/type=candles/asset=BTC/timeframe=5m"
    path = storage_uri / "year=2026/month=06/data.parquet"
    path.parent.mkdir(parents=True)
    _write_parquet(path, [_row("2026-06-01T00:00:00Z", close=100)])
    repository = FakeRepository()
    repository.refs = [_registration("btc-derived-5m", "BTC", storage_uri, timeframe="5m")]

    result = enrich_derived_ema_datasets(repository=repository, asset="BTC", periods=(3,))

    assert result["status"] == "enriched"
    assert result["dataset_count"] == 1
    assert repository.updated[0]["dataset_id"] == "btc-derived-5m"


def _registration(dataset_id: str, asset: str, storage_uri: Path, *, timeframe: str = "2h") -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "source_id": "okx",
        "asset": asset,
        "instrument": f"{asset}-USDT-SWAP",
        "data_type": "candles",
        "timeframe": timeframe,
        "data_origin": "derived",
        "row_count": 1,
        "storage_backend": "parquet",
        "storage_uri": str(storage_uri),
        "schema_descriptor": {},
        "quality_status": "rebuilt",
        "ingestion_version": "test",
    }


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path)


def _row(timestamp: str, *, close: float) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }
