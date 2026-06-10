from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quant_terminal_api.repositories.market_data import PostgresMarketDataRepository
from quant_terminal_api.repositories.runtime import RuntimeRepository
from quant_terminal_worker.celery_app import celery_app
from quant_terminal_worker.jobs import run_claimed_job


@celery_app.task(name="quant_terminal_worker.run_job", bind=True)
def run_job_task(self: Any, job_id: str) -> dict[str, Any] | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    repository = RuntimeRepository(database_url)
    worker_id = f"celery-{self.request.hostname or 'worker'}-{self.request.id}"
    started_at = datetime.now(UTC)
    repository.record_worker_heartbeat(worker_id, status="idle", started_at=started_at)
    job = repository.claim_job(job_id=job_id, worker_id=worker_id)
    if job is None:
        return {"status": "skipped", "reason": "job_not_claimable", "job_id": job_id}

    repository.record_worker_heartbeat(
        worker_id,
        status="running",
        current_job_id=job["job_id"],
        current_step=job.get("current_step"),
        started_at=started_at,
    )
    workspace_root = Path(os.environ.get("MOTIS_WORKSPACE_ROOT") or Path.cwd())
    market_data_repository = PostgresMarketDataRepository(database_url)
    completed = run_claimed_job(
        repository=repository,
        job=job,
        workspace_root=workspace_root,
        market_data_repository=market_data_repository,
    )
    repository.record_worker_heartbeat(worker_id, status="idle", started_at=started_at)
    return completed

