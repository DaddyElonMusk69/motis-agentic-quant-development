from quant_terminal_sdk.execution import ExecutionSetup, PositionContext


def test_execution_setup_exposes_stage0_forward_hours_as_hard_exit_gate():
    setup = ExecutionSetup.from_mapping({"forward_hours": 36})

    assert setup.forward_hours == 36
    assert setup.hard_exit_after_hours == 36


def test_position_context_carries_live_position_age_and_hard_gate():
    context = PositionContext(
        instrument="AAVE-USDT-SWAP",
        direction="LONG",
        side="long",
        size="1.5",
        raw_size="1.5",
        entry_price="100",
        opened_at="2026-06-05T00:00:00Z",
        age_hours=37,
        hard_exit_after_hours=36,
    )

    assert context.is_hard_time_gate_expired() is True
