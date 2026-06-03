from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import create_engine, select
from sqlalchemy.sql.dml import Insert

from quant_terminal_api.db.models import data_sources, market_data_refs


def build_data_source_upsert(source_id: str, name: str, source_type: str) -> Insert:
    statement = insert(data_sources).values(
        source_id=source_id,
        name=name,
        source_type=source_type,
        config={},
    )
    return statement.on_conflict_do_update(
        index_elements=["source_id"],
        set_={"name": name, "source_type": source_type},
    )


def build_market_data_ref_upsert(registration: dict[str, Any]) -> Insert:
    statement = insert(market_data_refs).values(**registration)
    return statement.on_conflict_do_update(
        index_elements=["dataset_id"],
        set_={
            "start_ts": registration.get("start_ts"),
            "end_ts": registration.get("end_ts"),
            "row_count": registration.get("row_count"),
            "data_origin": registration.get("data_origin", "raw"),
            "storage_uri": registration.get("storage_uri"),
            "schema_descriptor": registration.get("schema_descriptor", {}),
            "quality_status": registration.get("quality_status", "unknown"),
            "ingestion_version": registration.get("ingestion_version"),
        },
    )


class PostgresMarketDataRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url)

    def list_refs(self) -> list[dict[str, Any]]:
        statement = select(market_data_refs).order_by(
            market_data_refs.c.asset,
            market_data_refs.c.data_type,
            market_data_refs.c.data_origin,
            market_data_refs.c.timeframe,
        )
        with self.engine.connect() as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]

    def get_ref(self, dataset_id: str) -> dict[str, Any] | None:
        statement = select(market_data_refs).where(market_data_refs.c.dataset_id == dataset_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
            return dict(row) if row else None
