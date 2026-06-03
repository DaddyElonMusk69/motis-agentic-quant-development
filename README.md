# Motis Deterministic Quant Terminal

Locally runnable web app scaffold for deterministic, agent-assisted quant strategy research
and execution.

## Architecture

- `apps/web`: React/Vite operator terminal.
- `apps/api`: FastAPI API and SQLAlchemy schema metadata.
- `apps/worker`: Python worker subprocess runner and execution adapter boundaries.
- `packages/strategy_sdk`: shared signal, strategy, walk-forward, market-data, and deployment contracts.
- `ops`: Docker Compose and container packaging.

## Local Development

```bash
cp .env.example .env
python3 -m pytest tests -q
make dev-api
make dev-worker
npm install
make dev-web
```

Docker Compose packaging:

```bash
cp .env.example .env
make compose-up
```

If you use an existing local Postgres instead of the Compose Postgres container, create the
default app role/database before running migrations:

```bash
bash ops/scripts/bootstrap_local_postgres.sh
```

The v1 live-route path uses an OKX adapter boundary. The default local backend is the
installed OKX CLI with JSON output:

```bash
okx --profile <name> --demo --json market candles BTC-USDT-SWAP --bar 5m --limit 2
okx --profile <name> --live --json swap place --instId BTC-USDT-SWAP --side buy --ordType market --sz 1 --tdMode cross --clOrdId <id>
```

Strategies never call the CLI directly. Worker adapters own exchange access, parse JSON,
record command outputs, and enforce idempotent client order ids. Routes must still be
promoted, warmed, manually armed, and enabled before live execution is allowed by the SDK.

## OKX Candle Ingestion

The worker ingestion path fetches candles through the OKX adapter, normalizes OKX candle
arrays, writes partitioned Parquet, and returns a registration payload matching
`market_data_refs`.

Core module:

```text
apps/worker/src/quant_terminal_worker/ingestion/okx_candles.py
```

The API repository layer exposes a matching insert builder:

```text
apps/api/src/quant_terminal_api/repositories/market_data.py
```
