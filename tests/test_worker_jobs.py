import json

from sqlalchemy import create_engine

from quant_terminal_api.db.models import metadata
from quant_terminal_api.repositories.runtime import RuntimeRepository
from quant_terminal_worker.jobs import run_claimed_job


def test_worker_runs_stage1_score_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    repository = RuntimeRepository(engine)
    artifact_root = tmp_path / "dev/training_sessions/aave-vegas-tunnel-v01/stage1-aave"
    iteration_root = artifact_root / "iterations" / "iter_001_v0.1"
    strategy_root = artifact_root / "strategy_module"
    packets_root = tmp_path / "packets"
    for path in (
        iteration_root / "decisions",
        iteration_root / "scores",
        iteration_root / "summaries",
        strategy_root,
        packets_root,
    ):
        path.mkdir(parents=True)
    (strategy_root / "strategy.py").write_text(
        """
def decide(context):
    return {
        "strategy_id": "aave-vegas-tunnel-v01",
        "strategy_version": "v0.1",
        "signal_id": context["signal"]["signal_id"],
        "trade_action": "ENTER",
        "action": "ENTER",
        "direction": "LONG",
        "confidence": 0.7,
        "reason_code": "api_test",
        "diagnostics": {},
    }
"""
    )
    (packets_root / "sig-1.json").write_text('{"signal_id":"sig-1","payload":{}}')
    (iteration_root / "signal_sample.json").write_text(
        json.dumps({"signals": [{"signal_id": "sig-1", "packet_path": str(packets_root / "sig-1.json")}]})
    )
    (iteration_root / "builder_training_sample.json").write_text(
        json.dumps({"signals": [{"signal_id": "sig-1", "ground_truth": {"natural_direction": "LONG"}}]})
    )
    repository.create_stage1_research_session(
        {
            "session_id": "stage1-aave",
            "artifact_root": str(artifact_root),
            "source_candidate_id": "candidate-aave",
            "source_universe_run_id": "universe-aave",
            "signal_set_key": "vegas_ema:AAVE:2026-AAVE-2h-dedupe-vote2",
            "signal_engine_id": "vegas_ema",
            "signal_engine_version": "0.1",
            "asset": "AAVE",
            "signal_set_id": "2026-AAVE-2h-dedupe-vote2",
            "strategy_id": "aave-vegas-tunnel-v01",
            "strategy_version": "v0.1",
            "train_start": "2026-03-01",
            "train_end": "2026-04-30",
            "walk_forward_start": "2026-05-25",
            "walk_forward_end": "2026-05-31",
            "status": "draft",
            "manifest": {"session_id": "stage1-aave"},
        }
    )
    repository.enqueue_job(
        job_type="stage1_score",
        scope_key="stage1_session:stage1-aave",
        payload={"session_id": "stage1-aave", "iteration_id": "iter_001_v0.1", "sample_role": "training"},
    )
    job = repository.claim_next_job(worker_id="worker-1")

    completed = run_claimed_job(repository=repository, job=job, workspace_root=tmp_path)

    assert completed["status"] == "completed"
    assert completed["result"]["score"]["metrics"]["directional_agreement"] == 1
    assert (iteration_root / "scores" / "stage1a_directional_scores.json").exists()


def test_worker_runs_market_data_ema_refresh_job(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    repository = RuntimeRepository(engine)
    storage_uri = tmp_path / "origin=derived/source=okx/type=candles/asset=BTC/timeframe=2h"
    path = storage_uri / "year=2026/month=06/data.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"timestamp": "2026-06-01T00:00:00Z", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
                {"timestamp": "2026-06-01T02:00:00Z", "open": 110, "high": 110, "low": 110, "close": 110, "volume": 1},
            ]
        ),
        path,
    )
    market_repository = FakeMarketDataRepository(
        {
            "dataset_id": "btc-derived-2h",
            "source_id": "okx",
            "asset": "BTC",
            "instrument": "BTC-USDT-SWAP",
            "data_type": "candles",
            "timeframe": "2h",
            "data_origin": "derived",
            "start_ts": "2026-06-01T00:00:00Z",
            "end_ts": "2026-06-01T02:00:00Z",
            "row_count": 2,
            "storage_backend": "parquet",
            "storage_uri": str(storage_uri),
            "schema_descriptor": {},
            "quality_status": "rebuilt",
            "ingestion_version": "test",
        }
    )
    repository.enqueue_job(
        job_type="market_data_ema_refresh",
        scope_key="asset:BTC:ema",
        payload={"asset": "BTC"},
    )
    job = repository.claim_next_job(worker_id="worker-1")

    completed = run_claimed_job(repository=repository, job=job, workspace_root=tmp_path, market_data_repository=market_repository)

    assert completed["status"] == "completed"
    assert completed["result"]["enriched_count"] == 1
    refreshed = market_repository.get_ref("btc-derived-2h")
    assert refreshed["quality_status"] == "ema_enriched"
    assert refreshed["schema_descriptor"]["ema"]["periods"] == [36, 43, 144, 169, 576, 676]


class FakeMarketDataRepository:
    def __init__(self, ref):
        self.ref = ref

    def list_refs(self):
        return [self.ref]

    def update_ref(self, registration):
        self.ref = registration

    def get_ref(self, dataset_id):
        return self.ref if self.ref["dataset_id"] == dataset_id else None
