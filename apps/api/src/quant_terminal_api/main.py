from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from quant_terminal_api.repositories.market_data import PostgresMarketDataRepository
from quant_terminal_api.services.market_data_catalog import (
    build_catalog,
    build_refresh_plan,
    read_parquet_candles,
)
from quant_terminal_sdk.agent_tasks import AgentTaskBundle


class AgentTaskPreviewRequest(BaseModel):
    task_id: str
    cycle_id: str
    stage: str
    strategy_id: str
    strategy_version: str
    allowed_context_paths: list[str] = Field(default_factory=list)
    forbidden_context_paths: list[str] = Field(default_factory=list)


DEFAULT_WALK_FORWARD_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_id": "rolling_90d_14d_14d_weekly",
        "anchor": "rolling",
        "retrain_cadence": "7d",
        "train_range": "90d",
        "validation_range": "14d",
        "oos_range": "14d",
        "embargo": "0d",
    }
]


def create_app(market_data_repository: Any | None = None) -> FastAPI:
    app = FastAPI(title="Motis Deterministic Quant Terminal", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):51[0-9]{2}$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    repository = market_data_repository

    def get_market_data_repository() -> Any:
        nonlocal repository
        if repository is None:
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
            repository = PostgresMarketDataRepository(database_url)
        return repository

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "services": {
                "api": "ready",
                "database": "configured",
                "worker": "configured",
            },
        }

    @app.get("/api/v1/walk-forward/templates")
    def list_walk_forward_templates() -> dict[str, Any]:
        return {"templates": DEFAULT_WALK_FORWARD_TEMPLATES}

    @app.post("/api/v1/agent-tasks/preview")
    def preview_agent_task(request: AgentTaskPreviewRequest) -> dict[str, str]:
        bundle = AgentTaskBundle(
            task_id=request.task_id,
            cycle_id=request.cycle_id,
            stage=request.stage,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            allowed_context_paths=request.allowed_context_paths,
            forbidden_context_paths=request.forbidden_context_paths,
        )
        return {"prompt": bundle.render_prompt(repo_root=Path.cwd())}

    @app.get("/api/v1/market-data/catalog")
    def market_data_catalog() -> dict[str, Any]:
        return build_catalog(get_market_data_repository().list_refs())

    @app.get("/api/v1/market-data/{dataset_id}/candles")
    def read_market_data_candles(dataset_id: str, limit: int = 200) -> dict[str, Any]:
        registration = get_market_data_repository().get_ref(dataset_id)
        if registration is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        if registration["data_type"] != "candles":
            raise HTTPException(status_code=400, detail="dataset is not candles")
        return {
            "dataset_id": dataset_id,
            "rows": read_parquet_candles(Path(registration["storage_uri"]), limit=limit),
        }

    @app.post("/api/v1/market-data/{dataset_id}/refresh")
    def refresh_market_data(dataset_id: str) -> dict[str, Any]:
        registration = get_market_data_repository().get_ref(dataset_id)
        if registration is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        return build_refresh_plan(registration)

    return app


app = create_app()
