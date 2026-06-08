import pytest

from quant_terminal_worker.adapters.exchange import ExchangeAdapterError, build_exchange_adapter
from quant_terminal_worker.adapters.okx import OKXAdapter


def test_exchange_factory_builds_okx_cli_adapter_with_profile():
    adapter = build_exchange_adapter(
        {
            "execution_adapter": "okx",
            "account_mode": "live",
            "exchange_account": "main-live-01",
        }
    )

    assert isinstance(adapter, OKXAdapter)
    assert adapter.adapter_id == "okx"
    assert adapter.config["backend"] == "okx_cli"
    assert adapter.config["mode"] == "live"
    assert adapter.config["profile"] == "main-live-01"


def test_exchange_factory_omits_default_profile():
    adapter = build_exchange_adapter(
        {
            "execution_adapter": "okx",
            "account_mode": "demo",
            "exchange_account": "default",
        }
    )

    assert isinstance(adapter, OKXAdapter)
    assert adapter.config["mode"] == "demo"
    assert adapter.config["profile"] is None


def test_exchange_factory_rejects_unsupported_exchange_tag():
    with pytest.raises(ExchangeAdapterError, match="unsupported execution adapter: binance"):
        build_exchange_adapter(
            {
                "execution_adapter": "binance",
                "account_mode": "live",
                "exchange_account": "default",
            }
        )
