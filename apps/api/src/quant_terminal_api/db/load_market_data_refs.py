from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from quant_terminal_api.repositories.market_data import (
    build_data_source_upsert,
    build_market_data_ref_upsert,
)


def load_market_data_refs(database_url: str, registrations: list[dict[str, Any]]) -> int:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            build_data_source_upsert(source_id="okx", name="OKX", source_type="exchange")
        )
        for registration in registrations:
            connection.execute(build_market_data_ref_upsert(registration))
    return len(registrations)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load market_data_refs registrations into Postgres.")
    parser.add_argument("--registrations", required=True, type=Path)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    registrations = json.loads(args.registrations.read_text())
    count = load_market_data_refs(args.database_url, registrations)
    print(f"Loaded {count} market_data_refs rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
