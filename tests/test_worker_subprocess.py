from pathlib import Path

from quant_terminal_worker.subprocess_runner import run_entrypoint_subprocess


def test_worker_runs_strategy_entrypoint_in_subprocess(tmp_path: Path):
    strategy_file = tmp_path / "sample_strategy.py"
    strategy_file.write_text(
        "\n".join(
            [
                "def decide(context):",
                "    return {",
                "        'decision_id': 'decision-1',",
                "        'strategy_id': 'sample',",
                "        'strategy_version': '0.1.0',",
                "        'signal_id': context['signal']['signal_id'],",
                "        'action': 'ENTER',",
                "        'direction': 'LONG',",
                "        'confidence': 0.72,",
                "        'reason_code': 'unit_test',",
                "        'execution_profile': {},",
                "        'diagnostics': {'runtime': 'subprocess'},",
                "    }",
            ]
        )
    )

    result = run_entrypoint_subprocess(
        entrypoint="sample_strategy:decide",
        payload={"signal": {"signal_id": "signal-1"}},
        extra_python_paths=[tmp_path],
        timeout_seconds=5,
    )

    assert result["signal_id"] == "signal-1"
    assert result["diagnostics"] == {"runtime": "subprocess"}
