from pathlib import Path

from quant_terminal_worker.ingestion.okx_candles import ingest_okx_candles, normalize_okx_candle


class FakeOKXAdapter:
    def market_candles(self, inst_id: str, *, bar: str, limit: int):
        assert inst_id == "BTC-USDT-SWAP"
        assert bar == "5m"
        assert limit == 2
        return {
            "code": "0",
            "data": [
                ["1780272000000", "100", "105", "99", "101", "12.5"],
                ["1780272300000", "101", "106", "100", "104", "8.75"],
            ],
        }


def test_normalize_okx_candle_array_payload():
    row = normalize_okx_candle(["1780272000000", "100", "105", "99", "101", "12.5"])

    assert row == {
        "timestamp": "2026-06-01T00:00:00Z",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 12.5,
    }


def test_ingest_okx_candles_writes_parquet_and_builds_registration(tmp_path: Path):
    result = ingest_okx_candles(
        adapter=FakeOKXAdapter(),
        root=tmp_path,
        inst_id="BTC-USDT-SWAP",
        asset="BTC",
        timeframe="5m",
        year=2026,
        month=6,
        limit=2,
        ingestion_version="okx-cli-test",
    )

    assert result.path.exists()
    assert result.row_count == 2
    assert result.registration == {
        "dataset_id": "okx-BTC-USDT-SWAP-candles-5m-2026-06-okx-cli-test",
        "source_id": "okx",
        "asset": "BTC",
        "instrument": "BTC-USDT-SWAP",
        "data_type": "candles",
        "timeframe": "5m",
        "data_origin": "raw",
        "start_ts": "2026-06-01T00:00:00Z",
        "end_ts": "2026-06-01T00:05:00Z",
        "storage_backend": "parquet",
        "storage_uri": str(result.path),
        "schema_descriptor": {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "format": "parquet",
        },
        "quality_status": "ingested",
        "ingestion_version": "okx-cli-test",
    }
