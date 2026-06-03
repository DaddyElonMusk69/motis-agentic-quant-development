from datetime import UTC, datetime

from fastapi.testclient import TestClient

from quant_terminal_api.main import create_app


class FakeMarketDataRepository:
    def list_refs(self):
        return [
            {
                "dataset_id": "btc-raw-5m",
                "asset": "BTC",
                "instrument": "BTC-USDT-SWAP",
                "data_type": "candles",
                "timeframe": "5m",
                "data_origin": "raw",
                "start_ts": datetime(2026, 5, 1, tzinfo=UTC),
                "end_ts": datetime(2026, 5, 31, tzinfo=UTC),
                "row_count": 100,
                "storage_backend": "parquet",
                "storage_uri": ".data/market-data",
                "quality_status": "ingested",
                "ingestion_version": "legacy",
            }
        ]

    def get_ref(self, dataset_id: str):
        assert dataset_id == "btc-raw-5m"
        return self.list_refs()[0]


def test_market_data_catalog_endpoint_uses_repository():
    client = TestClient(create_app(market_data_repository=FakeMarketDataRepository()))

    response = client.get("/api/v1/market-data/catalog")

    assert response.status_code == 200
    assert response.json()["summary"] == {"assets": 1, "datasets": 1, "data_types": ["candles"]}


def test_market_data_refresh_endpoint_returns_plan_for_dataset():
    client = TestClient(create_app(market_data_repository=FakeMarketDataRepository()))

    response = client.post("/api/v1/market-data/btc-raw-5m/refresh")

    assert response.status_code == 200
    assert response.json()["dataset_id"] == "btc-raw-5m"
    assert response.json()["status"] == "planned"
