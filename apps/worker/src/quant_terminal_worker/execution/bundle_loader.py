from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


def load_execution_bundle(bundle: dict[str, Any], *, workspace_root: Path) -> dict[str, Any]:
    bundle_root = Path(bundle["bundle_uri"])
    if not bundle_root.is_absolute():
        bundle_root = workspace_root / bundle_root
    strategy_path = Path(bundle["strategy_module_ref"])
    if not strategy_path.is_absolute():
        strategy_path = workspace_root / strategy_path
    setup_path = bundle_root / "execution_setup.json"
    execution_setup = bundle.get("execution_setup") or {}
    if setup_path.is_file():
        execution_setup = json.loads(setup_path.read_text())
    return {
        "bundle": bundle,
        "bundle_root": bundle_root,
        "strategy_path": strategy_path,
        "strategy_module": load_strategy_module(strategy_path),
        "execution_setup": execution_setup,
    }


def load_strategy_module(strategy_path: Path) -> ModuleType:
    if not strategy_path.is_file():
        raise FileNotFoundError(f"strategy module not found: {strategy_path}")
    module_name = f"motis_execution_strategy_{abs(hash(str(strategy_path)))}"
    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load strategy module: {strategy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
