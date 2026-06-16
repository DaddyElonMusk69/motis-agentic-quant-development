---
name: signal-engine-builder
description: Use when creating, registering, refactoring, or reviewing a Motis Quant Terminal signal engine, live scanner, training generator, neutral signal packet, engine registry entry, or paired base strategy template.
---

# Signal Engine Builder

## Purpose

Build Motis signal engines against the repo-owned contract, not by copying Vegas-specific runtime assumptions. A complete engine includes canonical metadata, training generation, latest-candle live scan, neutral packet output, required-data declarations, tests, and a paired base strategy template.

## Required References

Read these first:

- `docs/engine-strategy-contract.md`
- `templates/engine_strategy_pair/`
- `packages/strategy_sdk/src/quant_terminal_sdk/engine_contracts.py`
- `artifacts/signal_engine/engine_registry.json`

For current runtime examples, read:

- `apps/worker/src/quant_terminal_worker/signal_engines/runtime.py`
- `apps/worker/src/quant_terminal_worker/signal_engines/vegas_ema.py`
- `apps/worker/src/quant_terminal_worker/signal_engines/bollinger.py`
- `tests/test_signal_engine_runtime.py`
- `tests/test_api.py` signal-engine catalog tests

## Non-Negotiable Contract Rules

- Engine metadata must validate as `SignalEngineSpec`.
- Engine id must be stable and unique, e.g. `vegas_ema_vote1`.
- `required_data` must declare canonical Parquet needs, currently candle data by `origin` and `timeframe`.
- Training generator must consume canonical Parquet through `MarketDataReader` or the engine runtime context.
- Live scanner must scan the latest eligible canonical Parquet candle state, not historical DB signal backlog.
- Signal packets must be neutral market evidence only. Do not include direction, side, confidence, sizing, leverage, TP, SL, or order intent.
- Stage 1/runtime strategy invocation is the canonical interface boundary. Engines emit raw `signal_packet.v2` packets; every strategy caller must wrap those packets before calling `decide(context)`.
- Canonical `decide(context)` shape:
  - `context["signal"]["signal_id"]`
  - `context["signal"]["signal_set_key"]` when available
  - `context["signal"]["signal_engine_id"]` when available
  - `context["signal"]["asset"]`
  - `context["signal"]["instrument"]`
  - `context["signal"]["timestamp"]`
  - `context["signal"]["payload_schema"] == "signal_packet.v2"`
  - `context["signal"]["payload"] == <raw emitted packet>`
  - `context["runtime_mode"]` set to `stage1`, `backtest`, or `live`
  - `context["parameters"]` as a dict
  - `context["raw_data"]` as a dict
- Strategy direction belongs in the paired base strategy `decide(context)`, and strategies should read packet evidence through `context["signal"]["payload"]`, not by assuming the raw packet was passed directly as `context["signal"]`.
- The paired base strategy must match the engine's actual emitted packet shape. Do not copy legacy Vegas gates such as requiring two active timeframes unless the new engine really emits and requires that shape.
- Execution setup and live router own sizing, TP/SL price derivation, protection, pyramiding, and order submission.
- The engine registry entry should include `code_ref.base_strategy_path`, and that file must expose a valid strategy `decide()`.
- The engine must be visible through `GET /api/v1/signal-engines`, even before any DB signal pool exists. Repo registry entries must merge into the API catalog with zero counts when the DB has no row yet.

## Build Workflow

1. Pick the engine id, display name, version, default parameters, and required Parquet data.
2. Add or update the engine registry entry with canonical fields:
   - `signal_engine_id`
   - `version`
   - `name`
   - `required_data`
   - `output_envelope_version: "signal_packet.v2"`
   - `runtime_entrypoint`
   - `live_scanner_entrypoint`
   - `configuration_schema.default_parameters` when defaults differ from the adapter defaults
   - `code_ref.base_strategy_path`
3. Implement the engine adapter under `apps/worker/src/quant_terminal_worker/signal_engines/` unless an existing adapter can safely be parameterized.
4. Implement or point to the paired base strategy under `packages/strategy_modules/src/quant_terminal_strategies/`.
5. Add tests before implementation:
   - registry/spec validation
   - API engine catalog includes registry-only entries with `signal_set_count: 0` and `packet_count: 0`
   - training dispatch from Parquet
   - live scan from Parquet
   - packet neutrality
   - paired base strategy validates
   - canonical strategy context: wrap at least one real emitted training packet and one live-scan packet as `context["signal"]["payload"]` before calling `decide(context)`
   - engine/strategy compatibility: assert the paired strategy does not skip solely because of packet-shape assumptions such as active timeframe count, wrapper path, or missing legacy fields
   - Stage 1 scorer compatibility: exercise the actual Stage 1 scoring path with a representative raw emitted packet artifact and assert it produces scoreable `LONG`/`SHORT` decisions when the paired strategy has directional rules
   - Stage 0 signal-pool preparation still works where relevant
6. If catalog behavior changes, update `apps/api/src/quant_terminal_api/main.py` and tests so DB rows win but repo registry entries fill missing engines.
7. Run focused tests, then `pytest -q`. Run `npm --workspace apps/web-v2 run build` if frontend/API types were touched.
8. Restart the backend and verify the live endpoint includes the new engine:
   - `curl -sS http://127.0.0.1:8000/api/v1/signal-engines`

## Common Mistakes

- Adding a legacy script path without a contract runtime adapter.
- Assuming `engine_registry.json` alone makes the engine visible in the UI. The Engines page reads the API catalog, so registry-only engines must be merged into `GET /api/v1/signal-engines`.
- Letting a packet imply `LONG` or `SHORT`.
- Forgetting `code_ref.base_strategy_path`, which leaves Stage 1 to fall back to the generic starter.
- Reusing a paired base strategy that expects an older packet shape. Example: a 5m-only engine emitting `active_timeframes: ["5m"]` must not use a base strategy that requires two active timeframe votes before it can score.
- Testing `decide(context)` by passing the raw emitted packet as `context["signal"]`. This bypasses the canonical runtime wrapper and can hide Stage 1/live execution contract bugs.
- Making each strategy defensively support malformed scorer input instead of fixing the caller. Stage 1, backtests, promotion, and live execution must all call strategies with the same canonical signal wrapper.
- Using live exchange fetches inside the engine instead of canonical Parquet.
- Changing Vegas defaults while adding a variant. Add a separate engine id and spec defaults instead.

## Final Checklist

- `validate_signal_engine_spec(...)` passes.
- `validate_signal_packet(...)` passes for emitted packets.
- `validate_strategy_module(base_strategy_path)` passes.
- A representative emitted packet from the training generator and live scanner can be wrapped as `context["signal"]["payload"]` and passed to the paired `decide(context)` without being rejected for stale packet-shape reasons.
- The actual Stage 1 scorer path can consume a representative raw emitted packet artifact and call `decide(context)` with the canonical runtime signal wrapper.
- Strategy callers in Stage 1, backtests, promotion, and live execution use the same canonical wrapper shape.
- `GET /api/v1/signal-engines` returns the new engine after backend restart, even with zero signal sets.
- The v2 Engines tab can list/select the new engine.
- Existing engines keep their old behavior unless the user explicitly asked for a behavior change.
- New engine can be selected independently in research/trading flows by its engine id.
