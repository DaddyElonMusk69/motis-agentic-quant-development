import json
from pathlib import Path

from quant_terminal_sdk.parquet_store import read_candles
from quant_terminal_worker.ingestion.legacy_dev_data import (
    import_legacy_dev_data,
    normalize_legacy_csv_row,
)


def _write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "ts,open,high,low,close,volume,vol_ccy,vol_ccy_quote,confirm",
                "2026-06-01T00:00:00Z,100,105,99,101,12.5,1.25,1262.5,1",
                "2026-06-01T00:05:00Z,101,106,100,104,8.75,0.875,910,1",
            ]
        )
        + "\n"
    )


def test_normalize_legacy_csv_row_preserves_candle_and_volume_fields():
    row = normalize_legacy_csv_row(
        {
            "ts": "2026-06-01T00:00:00Z",
            "open": "100",
            "high": "105",
            "low": "99",
            "close": "101",
            "volume": "12.5",
            "vol_ccy": "1.25",
            "vol_ccy_quote": "1262.5",
            "confirm": "1",
        }
    )

    assert row == {
        "timestamp": "2026-06-01T00:00:00Z",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 12.5,
        "vol_ccy": 1.25,
        "vol_ccy_quote": 1262.5,
        "confirm": 1,
    }


def test_import_legacy_dev_data_writes_parquet_and_registration_rows(tmp_path: Path):
    source_root = tmp_path / "legacy" / "dev" / "data"
    target_root = tmp_path / "new-data"
    manifest_dir = source_root / "manifests"
    manifest_dir.mkdir(parents=True)

    _write_csv(source_root / "raw" / "BTC" / "5m" / "candles.csv")
    _write_csv(source_root / "derived" / "BTC" / "2h" / "candles.csv")
    (manifest_dir / "BTC.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "asset": "BTC",
                "raw": {
                    "5m": {
                        "path": "dev/data/raw/BTC/5m/candles.csv",
                        "rows": 2,
                        "start_ts": "2026-06-01T00:00:00Z",
                        "end_ts": "2026-06-01T00:05:00Z",
                    }
                },
                "derived": {
                    "2h": {
                        "path": "dev/data/derived/BTC/2h/candles.csv",
                        "rows": 2,
                        "start_ts": "2026-06-01T00:00:00Z",
                        "end_ts": "2026-06-01T00:05:00Z",
                        "rule": "aggregated from canonical raw 5m",
                    }
                },
            }
        )
    )

    result = import_legacy_dev_data(
        source_root=source_root,
        target_root=target_root,
        assets=["BTC"],
        timeframes=["5m", "2h"],
        ingestion_version="legacy-dev-data-test",
    )

    assert len(result.registrations) == 2
    raw_registration = result.registrations[0]
    assert raw_registration["dataset_id"] == "legacy-okx-BTC-USDT-SWAP-candles-5m-raw-legacy-dev-data-test"
    assert raw_registration["storage_backend"] == "parquet"
    assert raw_registration["data_origin"] == "raw"
    assert raw_registration["schema_descriptor"]["origin"] == "raw"
    assert raw_registration["row_count"] == 2
    assert len(result.parquet_paths) == 2
    assert read_candles(result.parquet_paths[0])[0]["timestamp"] == "2026-06-01T00:00:00Z"
