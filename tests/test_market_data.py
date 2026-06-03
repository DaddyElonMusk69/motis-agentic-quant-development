from pathlib import Path

from quant_terminal_sdk.market_data import MarketDataReference


def test_market_data_reference_builds_partitioned_parquet_path(tmp_path: Path):
    reference = MarketDataReference(
        dataset_id="okx-btc-5m",
        source_id="okx",
        asset="BTC",
        instrument="BTC-USDT-SWAP",
        data_type="candles",
        timeframe="5m",
        storage_backend="parquet",
    )

    path = reference.parquet_path(root=tmp_path, year=2026, month=6)

    assert path == tmp_path / "source=okx" / "type=candles" / "asset=BTC" / "timeframe=5m" / "year=2026" / "month=06" / "data.parquet"
