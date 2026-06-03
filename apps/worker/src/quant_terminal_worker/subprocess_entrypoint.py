from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Callable
from typing import Any


def _load_entrypoint(entrypoint: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    module_name, separator, function_name = entrypoint.partition(":")
    if separator != ":" or not module_name or not function_name:
        raise ValueError("Entrypoint must use 'module:function' format")

    module = importlib.import_module(module_name)
    function = getattr(module, function_name)
    if not callable(function):
        raise TypeError(f"Entrypoint {entrypoint!r} is not callable")
    return function


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("Expected exactly one entrypoint argument")
        entrypoint = sys.argv[1]
        payload = json.loads(sys.stdin.read() or "{}")
        result = _load_entrypoint(entrypoint)(payload)
        sys.stdout.write(json.dumps(result))
        return 0
    except Exception as exc:
        sys.stderr.write(f"{exc.__class__.__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
