import json
from pathlib import Path

import pytest

from quant_terminal_worker.adapters.okx import OKXAdapter, OKXCLIError, SwapOrderRequest, SwapProtectionRequest


def test_okx_adapter_reports_missing_live_credentials():
    adapter = OKXAdapter(config={"backend": "env_credentials"})

    assert adapter.adapter_id == "okx"
    assert adapter.readiness_blockers() == [
        "missing_okx_api_key",
        "missing_okx_api_secret",
        "missing_okx_passphrase",
    ]


def test_okx_adapter_is_ready_with_required_credentials():
    adapter = OKXAdapter(
        config={
            "backend": "env_credentials",
            "api_key": "key",
            "api_secret": "secret",
            "passphrase": "passphrase",
        }
    )

    assert adapter.readiness_blockers() == []


def test_okx_cli_adapter_builds_market_candles_command():
    adapter = OKXAdapter(
        config={
            "backend": "okx_cli",
            "cli_path": "/opt/homebrew/bin/okx",
            "profile": "motis",
            "mode": "live",
        }
    )

    command = adapter.build_command("market", "candles", ["BTC-USDT-SWAP", "--bar", "5m"])

    assert command == [
        "/opt/homebrew/bin/okx",
        "--profile",
        "motis",
        "--live",
        "--json",
        "market",
        "candles",
        "BTC-USDT-SWAP",
        "--bar",
        "5m",
    ]


def test_okx_cli_adapter_runs_json_command(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "print(json.dumps({'argv': __import__('sys').argv[1:], 'data': [{'close': '100'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "demo"})

    result = adapter.market_candles("BTC-USDT-SWAP", bar="5m", limit=2)

    assert result["data"] == [{"close": "100"}]
    assert result["argv"] == [
        "--demo",
        "--json",
        "market",
        "candles",
        "BTC-USDT-SWAP",
        "--bar",
        "5m",
        "--limit",
        "2",
    ]


def test_okx_cli_adapter_wraps_market_candle_array_output(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "print(json.dumps([['1780272000000', '100', '105', '99', '101', '12.5']]))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "demo"})

    result = adapter.market_candles("BTC-USDT-SWAP", bar="5m", limit=2)

    assert result == {
        "code": "0",
        "data": [["1780272000000", "100", "105", "99", "101", "12.5"]],
    }


def test_okx_cli_adapter_raises_on_nonzero_exit(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "sys.stderr.write('order rejected')",
                "raise SystemExit(2)",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    with pytest.raises(OKXCLIError, match="order rejected"):
        adapter.place_swap_order(
            SwapOrderRequest(
                inst_id="BTC-USDT-SWAP",
                side="buy",
                order_type="market",
                size="1",
                trade_mode="cross",
                client_order_id="route-decision-1",
            )
        )


def test_okx_cli_adapter_includes_stdout_when_nonzero_exit(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "sys.stdout.write('{\"code\":\"51000\",\"msg\":\"bad attached order\"}')",
                "sys.stderr.write('update notice')",
                "raise SystemExit(1)",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    with pytest.raises(OKXCLIError, match="bad attached order"):
        adapter.place_swap_order(
            SwapOrderRequest(
                inst_id="ETH-USDT-SWAP",
                side="buy",
                order_type="market",
                size="2",
                trade_mode="isolated",
                client_order_id="route-decision-1",
            )
        )


def test_okx_cli_adapter_places_swap_order_with_client_order_id(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'ordId': '123'}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.place_swap_order(
        SwapOrderRequest(
            inst_id="BTC-USDT-SWAP",
            side="buy",
            order_type="market",
            size="1",
            trade_mode="cross",
            client_order_id="route-decision-1",
            position_side="long",
        )
    )

    assert result["ordId"] == "123"
    expected_argv = [
        "--live",
        "--json",
        "swap",
        "place",
        "--instId",
        "BTC-USDT-SWAP",
        "--side",
        "buy",
        "--ordType",
        "market",
        "--sz",
        "1",
        "--tdMode",
        "cross",
        "--clOrdId",
        result["exchange_client_order_id"],
        "--posSide",
        "long",
    ]
    assert result["argv"] == expected_argv
    assert result["client_order_id"] == "route-decision-1"
    assert result["exchange_client_order_id"].isalnum()


def test_okx_cli_adapter_sanitizes_exchange_client_order_id(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'ordId': '123'}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.place_swap_order(
        SwapOrderRequest(
            inst_id="ETH-USDT-SWAP",
            side="buy",
            order_type="market",
            size="2",
            trade_mode="isolated",
            client_order_id="motis-eth-live-test-004",
            target_currency="margin",
        )
    )

    exchange_client_order_id = result["argv"][result["argv"].index("--clOrdId") + 1]
    assert exchange_client_order_id.isalnum()
    assert len(exchange_client_order_id) <= 32
    assert exchange_client_order_id != "motis-eth-live-test-004"
    assert result["client_order_id"] == "motis-eth-live-test-004"
    assert result["exchange_client_order_id"] == exchange_client_order_id


def test_okx_cli_adapter_places_margin_sized_swap_order(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'ordId': '123'}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.place_swap_order(
        SwapOrderRequest(
            inst_id="ETH-USDT-SWAP",
            side="buy",
            order_type="market",
            size="2",
            trade_mode="isolated",
            client_order_id="route-decision-eth",
            target_currency="margin",
        )
    )

    expected_argv = [
        "--live",
        "--json",
        "swap",
        "place",
        "--instId",
        "ETH-USDT-SWAP",
        "--side",
        "buy",
        "--ordType",
        "market",
        "--sz",
        "2",
        "--tdMode",
        "isolated",
        "--clOrdId",
        result["exchange_client_order_id"],
        "--tgtCcy",
        "margin",
    ]
    assert result["argv"] == expected_argv
    assert result["client_order_id"] == "route-decision-eth"
    assert result["exchange_client_order_id"].isalnum()


def test_okx_cli_adapter_places_swap_order_with_attached_tp_sl(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'ordId': '123'}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.place_swap_order(
        SwapOrderRequest(
            inst_id="ETH-USDT-SWAP",
            side="buy",
            order_type="market",
            size="2",
            trade_mode="isolated",
            client_order_id="route-decision-eth",
            target_currency="margin",
            tp_trigger_price="1620",
            sl_trigger_price="1560",
        )
    )

    expected_argv = [
        "--live",
        "--json",
        "swap",
        "place",
        "--instId",
        "ETH-USDT-SWAP",
        "--side",
        "buy",
        "--ordType",
        "market",
        "--sz",
        "2",
        "--tdMode",
        "isolated",
        "--clOrdId",
        result["exchange_client_order_id"],
        "--tgtCcy",
        "margin",
        "--tpTriggerPx",
        "1620",
        "--tpOrdPx=-1",
        "--slTriggerPx",
        "1560",
        "--slOrdPx=-1",
    ]
    assert result["argv"] == expected_argv
    assert result["client_order_id"] == "route-decision-eth"
    assert result["exchange_client_order_id"].isalnum()


def test_okx_cli_adapter_wraps_list_swap_order_response(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps([{'clOrdId': 'route-decision-eth', 'sCode': '0'}]))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.place_swap_order(
        SwapOrderRequest(
            inst_id="ETH-USDT-SWAP",
            side="buy",
            order_type="market",
            size="2",
            trade_mode="isolated",
            client_order_id="route-decision-eth",
        )
    )

    assert result["data"] == [{"clOrdId": "route-decision-eth", "sCode": "0"}]
    assert result["client_order_id"] == "route-decision-eth"
    assert result["exchange_client_order_id"].isalnum()


def test_okx_cli_adapter_sets_swap_leverage(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'sCode': '0'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.set_swap_leverage(
        inst_id="ETH-USDT-SWAP",
        leverage="5",
        margin_mode="isolated",
    )

    assert result["argv"] == [
        "--live",
        "--json",
        "swap",
        "leverage",
        "--instId",
        "ETH-USDT-SWAP",
        "--lever",
        "5",
        "--mgnMode",
        "isolated",
    ]


def test_okx_cli_adapter_wraps_list_leverage_response(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps([{'instId': 'ETH-USDT-SWAP', 'lever': '5'}]))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.set_swap_leverage(
        inst_id="ETH-USDT-SWAP",
        leverage="5",
        margin_mode="isolated",
    )

    assert result == {"data": [{"instId": "ETH-USDT-SWAP", "lever": "5"}]}


def test_okx_cli_adapter_lists_swap_protection_orders(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'instId': 'ETH-USDT-SWAP', 'algoId': 'algo-1'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.list_swap_algo_orders("ETH-USDT-SWAP", order_type="oco")

    assert result == [{"instId": "ETH-USDT-SWAP", "algoId": "algo-1"}]


def test_okx_cli_adapter_cancels_swap_protection_order(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'sCode': '0'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.cancel_swap_algo_order(inst_id="ETH-USDT-SWAP", algo_id="algo-1")

    assert result["argv"] == [
        "--live",
        "--json",
        "swap",
        "algo",
        "cancel",
        "--instId",
        "ETH-USDT-SWAP",
        "--algoId",
        "algo-1",
    ]


def test_okx_cli_adapter_places_swap_protection_order(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'sCode': '0'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.place_swap_protection_order(
        SwapProtectionRequest(
            inst_id="ETH-USDT-SWAP",
            side="sell",
            size="0.06",
            trade_mode="isolated",
            tp_trigger_price="1700",
            sl_trigger_price="1400",
            position_side="net",
        )
    )

    assert result["argv"] == [
        "--live",
        "--json",
        "swap",
        "algo",
        "place",
        "--instId",
        "ETH-USDT-SWAP",
        "--side",
        "sell",
        "--sz",
        "0.06",
        "--ordType",
        "oco",
        "--tpTriggerPx",
        "1700",
        "--tpOrdPx=-1",
        "--slTriggerPx",
        "1400",
        "--slOrdPx=-1",
        "--tdMode",
        "isolated",
        "--reduceOnly",
        "--posSide",
        "net",
    ]


def test_okx_cli_adapter_amends_swap_protection_order(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'sCode': '0'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.amend_swap_protection_order(
        inst_id="ETH-USDT-SWAP",
        algo_id="algo-1",
        tp_trigger_price="1710",
        sl_trigger_price="1410",
        size="0.06",
    )

    assert result["argv"] == [
        "--live",
        "--json",
        "swap",
        "algo",
        "amend",
        "--instId",
        "ETH-USDT-SWAP",
        "--algoId",
        "algo-1",
        "--newTpTriggerPx",
        "1710",
        "--newTpOrdPx=-1",
        "--newSlTriggerPx",
        "1410",
        "--newSlOrdPx=-1",
        "--newSz",
        "0.06",
    ]


def test_okx_cli_adapter_builds_execution_snapshot(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "argv = sys.argv[1:]",
                "if 'positions' in argv:",
                "    print(json.dumps({'data': [{'instId': 'AAVE-USDT-SWAP', 'pos': '1'}, {'instId': 'BTC-USDT-SWAP', 'pos': '2'}]}))",
                "elif 'fills' in argv:",
                "    print(json.dumps({'data': [{'instId': 'AAVE-USDT-SWAP', 'clOrdId': 'motis-1', 'ordId': 'fill-1', 'fillPx': '100'}, {'instId': 'ETH-USDT-SWAP', 'ordId': 'fill-2'}]}))",
                "elif 'orders' in argv:",
                "    print(json.dumps({'data': [{'instId': 'AAVE-USDT-SWAP', 'ordId': '123'}, {'instId': 'ETH-USDT-SWAP', 'ordId': '456'}]}))",
                "elif 'balance' in argv:",
                "    print(json.dumps({'data': [{'ccy': 'USDT', 'availBal': '100'}]}))",
                "else:",
                "    print(json.dumps({'data': []}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "demo"})

    snapshot = adapter.snapshot("AAVE-USDT-SWAP")

    assert snapshot["instrument"] == "AAVE-USDT-SWAP"
    assert snapshot["positions"] == [{"instId": "AAVE-USDT-SWAP", "pos": "1"}]
    assert snapshot["open_orders"] == [{"instId": "AAVE-USDT-SWAP", "ordId": "123"}]
    assert snapshot["recent_fills"] == [{"instId": "AAVE-USDT-SWAP", "clOrdId": "motis-1", "ordId": "fill-1", "fillPx": "100"}]
    assert snapshot["balance"]["data"] == [{"ccy": "USDT", "availBal": "100"}]


def test_okx_cli_adapter_snapshot_tolerates_missing_recent_fills_command(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "argv = sys.argv[1:]",
                "if 'fills' in argv:",
                "    sys.exit(2)",
                "if 'positions' in argv or 'orders' in argv or 'balance' in argv:",
                "    print(json.dumps({'data': []}))",
                "else:",
                "    print(json.dumps({'data': []}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "demo"})

    snapshot = adapter.snapshot("AAVE-USDT-SWAP")

    assert snapshot["recent_fills"] == []


def test_okx_cli_adapter_cancels_order_by_order_id(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'sCode': '0'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "demo"})

    result = adapter.cancel_order(instrument="AAVE-USDT-SWAP", order_id="123")

    assert result["status"] == "cancel_requested"
    assert result["result"]["argv"] == [
        "--demo",
        "--json",
        "swap",
        "cancel",
        "AAVE-USDT-SWAP",
        "--ordId",
        "123",
    ]


def test_okx_cli_adapter_cancels_order_by_client_order_id(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "print(json.dumps({'argv': sys.argv[1:], 'data': [{'sCode': '0'}]}))",
            ]
        )
    )
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "live"})

    result = adapter.cancel_order(instrument="AAVE-USDT-SWAP", client_order_id="motis-1")

    assert result["status"] == "cancel_requested"
    assert result["result"]["argv"] == [
        "--live",
        "--json",
        "swap",
        "cancel",
        "AAVE-USDT-SWAP",
        "--clOrdId",
        "motis-1",
    ]


def test_okx_cli_adapter_rejects_non_json_output(tmp_path: Path):
    cli = tmp_path / "okx"
    cli.write_text("#!/usr/bin/env python3\nprint('not json')\n")
    cli.chmod(0o755)
    adapter = OKXAdapter(config={"backend": "okx_cli", "cli_path": str(cli), "mode": "demo"})

    with pytest.raises(OKXCLIError, match="non-JSON"):
        adapter.market_candles("BTC-USDT-SWAP", bar="5m", limit=2)
