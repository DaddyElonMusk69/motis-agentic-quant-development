from __future__ import annotations

import os
from typing import Any

from quant_terminal_worker.job_routing import queue_for_job


def runtime_job_backend() -> str:
    configured = os.environ.get("MOTIS_JOB_BACKEND")
    if configured:
        return configured.strip().lower()
    if os.environ.get("CELERY_BROKER_URL") or os.environ.get("MOTIS_CELERY_BROKER_URL"):
        return "celery"
    return "database"


def dispatch_runtime_job(job: dict[str, Any]) -> dict[str, Any]:
    backend = runtime_job_backend()
    if backend in {"database", "db", "polling", "legacy"}:
        return {"backend": "database", "dispatched": False, "reason": "polling_worker_backend"}
    if backend != "celery":
        raise RuntimeError(f"unsupported job backend: {backend}")
    if job.get("status") != "queued":
        return {"backend": "celery", "dispatched": False, "reason": f"job_status_{job.get('status')}"}

    from quant_terminal_worker.celery_tasks import run_job_task

    queue = queue_for_job(str(job["job_type"]), job.get("payload") or {})
    try:
        async_result = run_job_task.apply_async(args=[job["job_id"]], queue=queue)
    except Exception as exc:
        raise RuntimeError(f"failed to dispatch job {job['job_id']} to Celery: {exc}") from exc
    return {
        "backend": "celery",
        "dispatched": True,
        "queue": queue,
        "task_id": async_result.id,
    }
