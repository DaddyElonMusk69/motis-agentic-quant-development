from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any

from quant_terminal_worker.adapters.exchange import ExchangeAdapterError, SwapOrderRequest, SwapProtectionRequest


class OKXCLIError(ExchangeAdapterError):
    pass


@dataclass(frozen=True, slots=True)
class OKXAdapter:
    config: dict[str, Any]
    adapter_id: str = "okx"

    def readiness_blockers(self) -> list[str]:
        backend = self.config.get("backend", "okx_cli")
        if backend == "okx_cli":
            blockers: list[str] = []
            if self._cli_path() is None:
                blockers.append("missing_okx_cli")
            if self.config.get("mode", "demo") not in {"demo", "live"}:
                blockers.append("invalid_okx_mode")
            return blockers

        required = {
            "api_key": "missing_okx_api_key",
            "api_secret": "missing_okx_api_secret",
            "passphrase": "missing_okx_passphrase",
        }
        return [
            blocker
            for key, blocker in required.items()
            if not self.config.get(key)
        ]

    def build_command(self, module: str, action: str, args: list[str] | None = None) -> list[str]:
        cli_path = self._cli_path()
        if cli_path is None:
            raise OKXCLIError("missing OKX CLI executable")

        command = [cli_path]
        profile = self.config.get("profile")
        if profile:
            command.extend(["--profile", str(profile)])

        mode = self.config.get("mode", "demo")
        if mode not in {"demo", "live"}:
            raise OKXCLIError(f"invalid OKX mode: {mode}")
        command.append(f"--{mode}")
        command.append("--json")
        command.extend([module, action])
        command.extend(args or [])
        return command

    def run_json_command(
        self,
        module: str,
        action: str,
        args: list[str] | None = None,
        timeout_seconds: int = 30,
    ) -> Any:
        command = self.build_command(module, action, args)
        run_command = command
        if self.config.get("use_login_shell", True):
            run_command = [
                str(self.config.get("login_shell") or "/bin/zsh"),
                "-lic",
                shlex.join(command),
            ]
        completed = subprocess.run(
            run_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            details = "\n".join(
                part.strip()
                for part in (completed.stderr, completed.stdout)
                if part.strip()
            )
            raise OKXCLIError(details or "OKX CLI command failed")

        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise OKXCLIError("OKX CLI returned non-JSON output") from exc

        return parsed

    def market_candles(
        self,
        inst_id: str,
        *,
        bar: str,
        limit: int,
        after: str | None = None,
    ) -> dict[str, Any]:
        args = [inst_id, "--bar", bar, "--limit", str(limit)]
        if after:
            args.extend(["--after", after])
        parsed = self.run_json_command(
            "market",
            "candles",
            args,
        )
        if isinstance(parsed, list):
            return {"code": "0", "data": parsed}
        if not isinstance(parsed, dict):
            raise OKXCLIError("OKX CLI returned unsupported candle JSON")
        return parsed

    def snapshot(self, instrument: str) -> dict[str, Any]:
        positions = self._extract_list(
            self.run_json_command(
                "account",
                "positions",
                [],
                timeout_seconds=int(self.config.get("position_query_timeout_seconds", 15)),
            ),
            keys=("data", "positions", "result"),
        )
        open_orders = self._extract_list(
            self.run_json_command(
                "swap",
                "orders",
                ["--instId", instrument],
                timeout_seconds=int(self.config.get("order_query_timeout_seconds", 15)),
            ),
            keys=("data", "orders", "result"),
        )
        protection_orders = self.list_swap_algo_orders(instrument, order_type="oco")
        balance = self._extract_object_or_list(
            self.run_json_command(
                "account",
                "balance",
                [],
                timeout_seconds=int(self.config.get("balance_query_timeout_seconds", 15)),
            )
        )
        recent_fills = self.list_swap_recent_fills(instrument)
        return {
            "instrument": instrument,
            "positions": self._filter_instrument_rows(positions, instrument),
            "open_orders": self._filter_instrument_rows(open_orders, instrument),
            "protection_orders": self._filter_instrument_rows(protection_orders, instrument),
            "balance": balance,
            "recent_fills": recent_fills,
        }

    def cancel_order(
        self,
        *,
        instrument: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        args = [instrument]
        if order_id:
            args.extend(["--ordId", order_id])
        elif client_order_id:
            args.extend(["--clOrdId", client_order_id])
        else:
            raise OKXCLIError("cancel_order requires order_id or client_order_id")
        parsed = self.run_json_command(
            "swap",
            "cancel",
            args,
            timeout_seconds=int(self.config.get("order_cancel_timeout_seconds", 15)),
        )
        if not isinstance(parsed, dict):
            return {"instrument": instrument, "order_id": order_id, "client_order_id": client_order_id, "result": parsed}
        return {
            "instrument": instrument,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "status": "cancel_requested",
            "result": parsed,
        }

    def list_swap_recent_fills(self, inst_id: str) -> list[dict[str, Any]]:
        try:
            parsed = self.run_json_command(
                "swap",
                "fills",
                ["--instId", inst_id],
                timeout_seconds=int(self.config.get("fill_query_timeout_seconds", 15)),
            )
        except OKXCLIError:
            return []
        return self._filter_instrument_rows(
            self._extract_list(parsed, keys=("data", "fills", "orders", "result")),
            inst_id,
        )

    def list_swap_algo_orders(self, inst_id: str, *, order_type: str | None = None) -> list[dict[str, Any]]:
        args = ["--instId", inst_id]
        if order_type:
            args.extend(["--ordType", order_type])
        parsed = self.run_json_command(
            "swap",
            "algo",
            ["orders", *args],
            timeout_seconds=int(self.config.get("algo_order_query_timeout_seconds", 15)),
        )
        return self._extract_list(parsed, keys=("data", "orders", "result"))

    def cancel_swap_algo_order(self, *, inst_id: str, algo_id: str) -> dict[str, Any]:
        parsed = self.run_json_command(
            "swap",
            "algo",
            ["cancel", "--instId", inst_id, "--algoId", algo_id],
            timeout_seconds=int(self.config.get("algo_order_cancel_timeout_seconds", 15)),
        )
        if isinstance(parsed, list):
            return {"data": parsed}
        if not isinstance(parsed, dict):
            raise OKXCLIError("OKX CLI returned JSON that was not an object")
        return parsed

    def cancel_swap_protection_orders(self, inst_id: str) -> dict[str, Any]:
        orders = self.list_swap_algo_orders(inst_id, order_type="oco")
        cancelled = []
        for order in orders:
            algo_id = str(order.get("algoId") or order.get("algo_id") or "")
            if algo_id:
                cancelled.append(self.cancel_swap_algo_order(inst_id=inst_id, algo_id=algo_id))
        return {
            "status": "cancelled" if cancelled else "noop",
            "instrument": inst_id,
            "cancelled_count": len(cancelled),
            "cancelled": cancelled,
        }

    def place_swap_protection_order(self, request: SwapProtectionRequest) -> dict[str, Any]:
        args = [
            "place",
            "--instId",
            request.inst_id,
            "--side",
            request.side,
            "--sz",
            request.size,
            "--ordType",
            "oco",
            "--tpTriggerPx",
            request.tp_trigger_price,
            "--tpOrdPx=-1",
            "--slTriggerPx",
            request.sl_trigger_price,
            "--slOrdPx=-1",
            "--tdMode",
            request.trade_mode,
            "--reduceOnly",
        ]
        if request.position_side:
            args.extend(["--posSide", request.position_side])
        parsed = self.run_json_command("swap", "algo", args)
        if isinstance(parsed, list):
            return {"data": parsed}
        if not isinstance(parsed, dict):
            raise OKXCLIError("OKX CLI returned JSON that was not an object")
        return parsed

    def amend_swap_protection_order(
        self,
        *,
        inst_id: str,
        algo_id: str,
        tp_trigger_price: str,
        sl_trigger_price: str,
        size: str | None = None,
    ) -> dict[str, Any]:
        args = [
            "amend",
            "--instId",
            inst_id,
            "--algoId",
            algo_id,
            "--newTpTriggerPx",
            tp_trigger_price,
            "--newTpOrdPx=-1",
            "--newSlTriggerPx",
            sl_trigger_price,
            "--newSlOrdPx=-1",
        ]
        if size:
            args.extend(["--newSz", size])
        parsed = self.run_json_command("swap", "algo", args)
        if isinstance(parsed, list):
            return {"data": parsed}
        if not isinstance(parsed, dict):
            raise OKXCLIError("OKX CLI returned JSON that was not an object")
        return parsed

    def ensure_swap_protection(self, request: SwapProtectionRequest) -> dict[str, Any]:
        orders = self.list_swap_algo_orders(request.inst_id, order_type="oco")
        live_orders = [order for order in orders if str(order.get("state") or "").lower() in {"", "live"}]
        if len(live_orders) == 1:
            order = live_orders[0]
            algo_id = str(order.get("algoId") or "")
            if algo_id and _protection_matches(order, request):
                return {"status": "noop", "reason": "protection_already_matches", "order": order}
            if algo_id:
                return {
                    "status": "amended",
                    "previous_order": order,
                    "result": self.amend_swap_protection_order(
                        inst_id=request.inst_id,
                        algo_id=algo_id,
                        tp_trigger_price=request.tp_trigger_price,
                        sl_trigger_price=request.sl_trigger_price,
                        size=request.size,
                    ),
                }

        cancelled = []
        for order in live_orders:
            algo_id = str(order.get("algoId") or "")
            if algo_id:
                cancelled.append(self.cancel_swap_algo_order(inst_id=request.inst_id, algo_id=algo_id))
        return {
            "status": "placed",
            "cancelled_count": len(cancelled),
            "cancelled": cancelled,
            "result": self.place_swap_protection_order(request),
        }

    def place_swap_order(self, request: SwapOrderRequest) -> dict[str, Any]:
        exchange_client_order_id = _okx_client_order_id(request.client_order_id)
        args = [
            "--instId",
            request.inst_id,
            "--side",
            request.side,
            "--ordType",
            request.order_type,
            "--sz",
            request.size,
            "--tdMode",
            request.trade_mode,
            "--clOrdId",
            exchange_client_order_id,
        ]
        if request.position_side:
            args.extend(["--posSide", request.position_side])
        if request.price:
            args.extend(["--px", request.price])
        if request.target_currency:
            args.extend(["--tgtCcy", request.target_currency])
        if request.tp_trigger_price:
            args.extend(["--tpTriggerPx", request.tp_trigger_price, "--tpOrdPx=-1"])
        if request.sl_trigger_price:
            args.extend(["--slTriggerPx", request.sl_trigger_price, "--slOrdPx=-1"])
        if request.reduce_only:
            args.append("--reduceOnly")
        parsed = self.run_json_command("swap", "place", args)
        if isinstance(parsed, list):
            return {
                "data": parsed,
                "client_order_id": request.client_order_id,
                "exchange_client_order_id": exchange_client_order_id,
            }
        if not isinstance(parsed, dict):
            raise OKXCLIError("OKX CLI returned JSON that was not an object")
        return {
            **parsed,
            "client_order_id": request.client_order_id,
            "exchange_client_order_id": exchange_client_order_id,
        }

    def set_swap_leverage(
        self,
        *,
        inst_id: str,
        leverage: str,
        margin_mode: str,
        position_side: str | None = None,
    ) -> dict[str, Any]:
        args = [
            "--instId",
            inst_id,
            "--lever",
            leverage,
            "--mgnMode",
            margin_mode,
        ]
        if position_side:
            args.extend(["--posSide", position_side])
        parsed = self.run_json_command("swap", "leverage", args)
        if isinstance(parsed, list):
            return {"data": parsed}
        if not isinstance(parsed, dict):
            raise OKXCLIError("OKX CLI returned JSON that was not an object")
        return parsed

    def _extract_list(self, payload: Any, *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in keys:
                data = payload.get(key)
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            if all(isinstance(value, (str, int, float, bool, type(None))) for value in payload.values()):
                return [payload]
        return []

    def _extract_object_or_list(self, payload: Any) -> dict[str, Any] | list[Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return payload
        return {}

    def _filter_instrument_rows(self, rows: list[dict[str, Any]], instrument: str) -> list[dict[str, Any]]:
        filtered = [
            row
            for row in rows
            if (row.get("instId") or row.get("instrument") or row.get("inst_id")) in {None, "", instrument}
        ]
        return filtered

    def _cli_path(self) -> str | None:
        configured = self.config.get("cli_path")
        if configured:
            path = Path(str(configured))
            if path.exists():
                return str(path)
            return shutil.which(str(configured))
        return shutil.which("okx")


def _okx_client_order_id(client_order_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", client_order_id)
    if cleaned == client_order_id and 1 <= len(cleaned) <= 32:
        return client_order_id
    digest = hashlib.sha1(client_order_id.encode("utf-8")).hexdigest()[:10]
    prefix = cleaned[: max(1, 32 - len(digest))]
    return f"{prefix}{digest}"[:32]


def _protection_matches(order: dict[str, Any], request: SwapProtectionRequest) -> bool:
    return (
        _same_decimal(order.get("tpTriggerPx"), request.tp_trigger_price)
        and _same_decimal(order.get("slTriggerPx"), request.sl_trigger_price)
        and _same_decimal(order.get("sz"), request.size)
        and str(order.get("side") or "").lower() == request.side
    )


def _same_decimal(left: Any, right: Any, *, tolerance: float = 1e-8) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return str(left) == str(right)
