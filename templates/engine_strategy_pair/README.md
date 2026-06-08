# Engine/Strategy Pair Template

This folder is a minimal scaffold for a new contract-compliant signal engine and strategy pair.

Files:

- `engine_registry_entry.json`: canonical engine metadata.
- `signal_engine.py`: shared neutral packet construction logic.
- `generate_training_signals.py`: training signal generation result stub.
- `scan_live_signal.py`: latest-candle live scan result stub.
- `strategy.py`: base strategy module with `decide()` and `manage_position()`.

Use `docs/engine-strategy-contract.md` as the source of truth. The scaffold is deliberately small; production engines should replace the toy range logic with their own deterministic market-state logic while preserving the contract boundaries.
