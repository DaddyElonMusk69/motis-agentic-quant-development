# Canonical Engine and Strategy Contract

This document is the repo-owned source of truth for building new signal engine and strategy pairs. It defines the contracts that future builders must target. It does not refactor the current runtime dispatch layer; any Vegas-specific runtime paths that still exist are compatibility behavior to remove in a later phase.

## Ownership Boundaries

- Market data is canonical in Parquet and discovered through `market_data_refs`.
- Signal engines own market-state scanning and emit neutral evidence packets only.
- Strategies own entry direction and entry/skip judgment through `decide(context)`.
- Strategies may own discretionary position judgment through `manage_position(context)`.
- Live execution owns sizing, exchange routing, TP/SL prices, protection updates, pyramiding submissions, hard time exits, and idempotent order submission.
- Postgres remains canonical for promoted bundle metadata, routes, wake audit, and queryable research signal pools.

## Signal Engine Spec

New engines declare a `SignalEngineSpec` compatible registry entry:

```json
{
  "signal_engine_id": "example_breakout",
  "version": "0.1.0",
  "name": "Example Breakout",
  "required_data": [
    {
      "data_type": "candles",
      "origin": "raw",
      "timeframe": "5m",
      "lookback_bars": 500
    }
  ],
  "output_envelope_version": "signal_packet.v2",
  "runtime_entrypoint": "engines/example_breakout/generate_training_signals.py",
  "live_scanner_entrypoint": "engines/example_breakout/scan_live_signal.py"
}
```

Required fields:

- `signal_engine_id`: stable id used by API, research sessions, routes, and bundles.
- `version`: engine implementation version.
- `required_data`: canonical market-data needs.
- `output_envelope_version`: currently `signal_packet.v2`.
- `runtime_entrypoint`: training/research signal generation entrypoint.
- `live_scanner_entrypoint`: live latest-candle scan entrypoint.

Legacy fields such as `replay_generator_path` and `live_scanner_path` may be parsed by validators for existing metadata, but new engines should use the canonical names.

## Required Market Data

Supported v1 data declarations:

```json
{
  "data_type": "candles",
  "origin": "raw",
  "timeframe": "5m",
  "lookback_bars": 20000,
  "freshness_tolerance_seconds": 300
}
```

Derived candles may declare a source:

```json
{
  "data_type": "candles",
  "origin": "derived",
  "timeframe": "2h",
  "source": {"data_type": "candles", "origin": "raw", "timeframe": "5m"}
}
```

The data reader must resolve `market_data_refs` for the asset, `data_type`, `origin`, and `timeframe`, then read partitioned Parquet from `storage_uri`. Returned rows must be UTC, sorted, deduped, and confirmed-only where the source supports confirmation.

## Signal Packet

Signal packets are neutral market evidence. They must not contain strategy direction, order intent, sizing, leverage, TP, SL, or confidence scoring.

Canonical packet shape:

```json
{
  "schema_version": "signal_packet.v2",
  "asset": "SOL",
  "instrument": "SOL-USDT-SWAP",
  "timestamp": "2026-06-08T00:00:00Z",
  "active_timeframes": ["5m", "2h"],
  "evidence": {
    "pattern": "breakout",
    "trigger_price": "150.25",
    "features": {"range_pct": 1.2}
  }
}
```

Forbidden packet fields include `direction`, `side`, `action`, `trade_action`, `confidence`, `entry_price`, `size`, `notional_usd`, `margin`, `leverage`, `tp`, `tp_pct`, `sl`, and `sl_pct`.

## Training Signal Generation

Training generation scans historical canonical Parquet and appends research packets to the signal pool. It does not create a live order queue.

Result contract:

```json
{
  "status": "appended",
  "generated_packet_count": 12,
  "appended_packet_count": 10,
  "raw_candle_end_ts": "2026-06-08T00:00:00Z",
  "previous_signal_end_ts": "2026-06-07T00:00:00Z",
  "scan_coverage_end_ts": "2026-06-08T00:00:00Z",
  "final_signal_end_ts": "2026-06-08T00:00:00Z",
  "packet_refs": ["packets/sol-20260608T000000Z.json"]
}
```

Training dedupe belongs to research signal generation only. Live execution must not drain historical packets as a backlog.

## Live Signal Scan

Live scanning uses freshly warmed canonical Parquet, builds the latest eligible candle state, and scans the latest confirmed candle only.

Result contract:

```json
{
  "status": "fresh_signal",
  "source": "live_parquet_snapshot",
  "signal": {
    "schema_version": "signal_packet.v2",
    "asset": "SOL",
    "timestamp": "2026-06-08T00:00:00Z",
    "evidence": {"pattern": "breakout"}
  }
}
```

No-signal result:

```json
{
  "status": "no_fresh_signal",
  "source": "live_parquet_snapshot",
  "reason": "latest_confirmed_candle_did_not_trigger"
}
```

## Strategy Module

A strategy module must expose:

```python
def decide(context: dict) -> dict:
    ...
```

It may also expose:

```python
def manage_position(context: dict) -> dict:
    ...
```

`decide(context)` returns one of:

```json
{"action": "ENTER", "direction": "LONG", "reason_code": "accepted"}
{"action": "ENTER_LONG", "direction": "LONG", "reason_code": "accepted"}
{"action": "ENTER_SHORT", "direction": "SHORT", "reason_code": "accepted"}
{"action": "SKIP", "direction": "FLAT", "reason_code": "filtered"}
{"action": "BLOCKED", "direction": "FLAT", "reason_code": "missing_context"}
```

`manage_position(context)` returns one of:

```json
{"action": "HOLD", "reason_code": "policy_ok"}
{"action": "EXIT", "reason_code": "strategy_exit"}
{"action": "REDUCE", "reason_code": "risk_reduction"}
{"action": "PYRAMID", "reason_code": "strategy_add"}
{"action": "UPDATE_PROTECTION", "reason_code": "strategy_protection"}
{"action": "BLOCKED", "reason_code": "missing_context"}
```

Strategies should not hardcode live sizing, leverage, TP/SL prices, or exchange account behavior. They can read `execution_setup` percentages and diagnostics to explain their decisions, but mechanical execution derives order prices from exchange truth.

## Execution Setup

Promotion produces an execution setup consumed by live execution:

```json
{
  "schema_version": "0.1",
  "source": "stage4_realized_expectancy",
  "account_mode": "live",
  "execution_adapter": "okx",
  "forward_hours": 24,
  "hard_exit_after_hours": 24,
  "stage4_candidate_id": "candidate-001",
  "setup": {
    "candidate_id": "candidate-001",
    "final_tp_pct": 1.2,
    "initial_sl_pct": 0.6,
    "protection_enabled": true,
    "protect_trigger_pct": 0.5,
    "trail_sl_pct": 0.1,
    "pyramid": {"max_legs": 3, "step_pct": 0.3}
  }
}
```

For fixed-SL candidates:

```json
{
  "final_tp_pct": 1.2,
  "initial_sl_pct": 0.6,
  "protection_enabled": false
}
```

Live execution derives actual TP/SL prices from OKX average entry, side, size, mark price, and this percentage policy. It must not treat derived local prices as exchange truth.

## Promotion Handoff

Stage handoff responsibilities:

- Stage 0 defines asset universe, training/walk-forward windows, significant-move threshold, and hard forward-hours gate.
- Stage 1 produces the strategy module and directional evidence.
- Stage 2 selects an exit policy from the training travel profile.
- Stage 3 tests fixed SL, exact protection, local variants, and pyramiding candidates using candle walk-forward semantics.
- Stage 4 runs sequential account simulation with user capital, margin allocation, leverage, fees, hard exit, protection, and pyramiding.
- Promotion freezes the latest completed Stage 4 candidate into an execution bundle with `strategy.py`, `execution_setup.json`, `manifest.json`, `evidence_refs.json`, and risk limits.

## Validation Entrypoints

Use the SDK validators before accepting new builds:

```python
from quant_terminal_sdk.engine_contracts import (
    validate_execution_bundle,
    validate_execution_bundle_contract,
    validate_signal_engine_spec,
    validate_signal_packet,
    validate_strategy_module,
)

validate_signal_engine_spec("example_breakout")
validate_signal_engine_spec("templates/engine_strategy_pair/engine_registry_entry.json")
validate_signal_packet(packet)
validate_strategy_module("strategy.py")
validate_execution_bundle_contract(bundle)
validate_execution_bundle("aave-vegas_ema-aave-vegas_ema-strategy-v01-3bee1a88652e")
```

These validators are intentionally strict for new contracts and include limited legacy parsing only so current Vegas metadata remains readable during the phase-2 runtime refactor.
