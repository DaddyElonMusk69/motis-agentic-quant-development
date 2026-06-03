from pathlib import Path

from quant_terminal_sdk.market_data import MarketDataReference
from quant_terminal_sdk.parquet_store import read_candles, write_candles


def test_write_and_read_candles_from_partitioned_parquet(tmp_path: Path):
    reference = MarketDataReference(
        dataset_id="okx-btc-5m",
        source_id="okx",
        asset="BTC",
        instrument="BTC-USDT-SWAP",
        data_type="candles",
        timeframe="5m",
        storage_backend="parquet",
    )
    rows = [
        {
            "timestamp": "2026-06-01T00:00:00Z",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 12.5,
        }
    ]

    path = write_candles(root=tmp_path, reference=reference, year=2026, month=6, rows=rows)

    assert path.exists()
    assert read_candles(path) == rows
