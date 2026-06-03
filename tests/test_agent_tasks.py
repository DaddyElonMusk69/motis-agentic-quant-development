from pathlib import Path

from quant_terminal_sdk.agent_tasks import AgentTaskBundle


def test_agent_task_bundle_rejects_locked_oos_files_in_allowed_context(tmp_path: Path):
    task = AgentTaskBundle(
        task_id="agent-stage1a-iter003",
        cycle_id="2026-06-btc-vegas",
        stage="stage1a",
        strategy_id="vegas_reclaim",
        strategy_version="0.1.0",
        allowed_context_paths=[
            "agent_tasks/agent-stage1a-iter003/score_summary.json",
            "agent_tasks/agent-stage1a-iter003/failure_clusters.json",
        ],
        forbidden_context_paths=[
            "data/walk_forward/2026-06/locked_oos.jsonl",
            "data/walk_forward/2026-06/validation_ground_truth.jsonl",
        ],
    )

    prompt = task.render_prompt(repo_root=tmp_path)

    assert "locked_oos.jsonl" not in prompt
    assert "validation_ground_truth.jsonl" not in prompt
    assert "failure_clusters.json" in prompt
    assert "Do not inspect forbidden validation or locked OOS data" in prompt
