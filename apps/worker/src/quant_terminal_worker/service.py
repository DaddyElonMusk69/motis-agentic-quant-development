from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from quant_terminal_api.repositories.market_data import PostgresMarketDataRepository
from quant_terminal_api.repositories.runtime import RuntimeRepository
from quant_terminal_worker.jobs import run_claimed_job


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    repository = RuntimeRepository(database_url)
    market_data_repository = PostgresMarketDataRepository(database_url)
    worker_id = os.environ.get("MOTIS_WORKER_ID") or f"worker-{uuid4().hex[:12]}"
    workspace_root = Path(os.environ.get("MOTIS_WORKSPACE_ROOT") or Path.cwd())
    started_at = datetime.now(UTC)
    repository.record_worker_heartbeat(worker_id, status="idle", started_at=started_at)
    print(f"Motis worker ready: {worker_id}", flush=True)
    while True:
        job = repository.claim_next_job(worker_id=worker_id)
        if job is None:
            repository.record_worker_heartbeat(worker_id, status="idle", started_at=started_at)
            time.sleep(2)
            continue
        repository.record_worker_heartbeat(
            worker_id,
            status="running",
            current_job_id=job["job_id"],
            current_step=job.get("current_step"),
            started_at=started_at,
        )
        print(f"Running job {job['job_id']} ({job['job_type']})", flush=True)
        completed = run_claimed_job(
            repository=repository,
            job=job,
            workspace_root=workspace_root,
            market_data_repository=market_data_repository,
        )
        status = completed["status"] if completed else "unknown"
        repository.record_worker_heartbeat(worker_id, status="idle", started_at=started_at)
        print(f"Finished job {job['job_id']} with status {status}", flush=True)


if __name__ == "__main__":
    main()
