from __future__ import annotations

from datetime import UTC, datetime, timedelta

from quant_terminal_worker.execution.scheduler import RouteLifecycleScheduler, _resume_delay_seconds


def test_scheduler_resume_running_routes_schedules_existing_running_routes_only():
    routes = {
        "running-route": {
            "route_id": "running-route",
            "scheduler_status": "running",
            "cron_interval_minutes": 5,
        },
        "stopped-route": {
            "route_id": "stopped-route",
            "scheduler_status": "stopped",
            "cron_interval_minutes": 5,
        },
    }
    updates = []
    cycles = []

    scheduler = RouteLifecycleScheduler(
        load_route=lambda route_id: routes.get(route_id),
        list_routes=lambda: list(routes.values()),
        update_route=lambda route_id, update: updates.append((route_id, update)) or {**routes[route_id], **update},
        run_cycle=lambda route_id: cycles.append(route_id) or {},
    )

    try:
        resumed = scheduler.resume_running()

        assert resumed == ["running-route"]
        assert scheduler.is_scheduled("running-route") is True
        assert scheduler.is_scheduled("stopped-route") is False
        assert cycles == []
        assert updates == []
    finally:
        scheduler.stop("running-route")


def test_scheduler_resume_delay_uses_persisted_next_wake_at():
    now = datetime(2026, 6, 6, 4, 0, tzinfo=UTC)

    assert _resume_delay_seconds(
        {"next_wake_at": now + timedelta(seconds=30), "cron_interval_minutes": 5},
        now=now,
    ) == 30
    assert _resume_delay_seconds(
        {"next_wake_at": now - timedelta(seconds=30), "cron_interval_minutes": 5},
        now=now,
    ) == 0
