from fastapi.testclient import TestClient

from quant_terminal_api.main import create_app


def test_health_endpoint_reports_local_services():
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "services": {
            "api": "ready",
            "database": "configured",
            "worker": "configured",
        },
    }


def test_api_allows_local_vite_origin_for_browser_fetches():
    client = TestClient(create_app())

    response = client.options(
        "/api/v1/market-data/catalog",
        headers={
            "Origin": "http://127.0.0.1:5177",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5177"


def test_default_walk_forward_templates_are_exposed():
    client = TestClient(create_app())

    response = client.get("/api/v1/walk-forward/templates")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert templates[0]["template_id"] == "rolling_90d_14d_14d_weekly"
    assert templates[0]["retrain_cadence"] == "7d"
    assert templates[0]["train_range"] == "90d"


def test_agent_task_preview_scopes_prompt_context():
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/agent-tasks/preview",
        json={
            "task_id": "agent-stage1a-iter003",
            "cycle_id": "2026-06-btc-vegas",
            "stage": "stage1a",
            "strategy_id": "vegas_reclaim",
            "strategy_version": "0.1.0",
            "allowed_context_paths": ["agent_tasks/example/failure_clusters.json"],
            "forbidden_context_paths": ["agent_tasks/example/locked_oos.jsonl"],
        },
    )

    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert "failure_clusters.json" in prompt
    assert "locked_oos.jsonl" not in prompt
