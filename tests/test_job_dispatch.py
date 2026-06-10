import sys
from types import SimpleNamespace

from quant_terminal_api.job_dispatch import dispatch_runtime_job


def test_dispatch_runtime_job_uses_database_backend_by_default(monkeypatch):
    monkeypatch.delenv("MOTIS_JOB_BACKEND", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("MOTIS_CELERY_BROKER_URL", raising=False)

    dispatch = dispatch_runtime_job(
        {
            "job_id": "job-1",
            "job_type": "signal_pool_extend",
            "status": "queued",
            "payload": {"asset": "BTC"},
        }
    )

    assert dispatch == {
        "backend": "database",
        "dispatched": False,
        "reason": "polling_worker_backend",
    }


def test_dispatch_runtime_job_routes_celery_tasks(monkeypatch):
    calls = []

    class FakeTask:
        @staticmethod
        def apply_async(*, args, queue):
            calls.append({"args": args, "queue": queue})
            return SimpleNamespace(id="celery-task-1")

    monkeypatch.setenv("MOTIS_JOB_BACKEND", "celery")
    monkeypatch.setitem(
        sys.modules,
        "quant_terminal_worker.celery_tasks",
        SimpleNamespace(run_job_task=FakeTask()),
    )

    dispatch = dispatch_runtime_job(
        {
            "job_id": "job-1",
            "job_type": "signal_pool_extend",
            "status": "queued",
            "payload": {"asset": "BTC"},
        }
    )

    assert dispatch == {
        "backend": "celery",
        "dispatched": True,
        "queue": "signal_generation",
        "task_id": "celery-task-1",
    }
    assert calls == [{"args": ["job-1"], "queue": "signal_generation"}]


def test_dispatch_runtime_job_does_not_dispatch_running_jobs(monkeypatch):
    monkeypatch.setenv("MOTIS_JOB_BACKEND", "celery")

    dispatch = dispatch_runtime_job(
        {
            "job_id": "job-1",
            "job_type": "stage1_score",
            "status": "running",
            "payload": {},
        }
    )

    assert dispatch == {
        "backend": "celery",
        "dispatched": False,
        "reason": "job_status_running",
    }

