import json
from pathlib import Path

from typer.testing import CliRunner

from mmdev.cli import app
from mmdev.config import MMDevConfig
from mmdev.schemas import ReviewResult


runner = CliRunner()


def test_plan_prints_strong_model_provider_and_model(monkeypatch, tmp_path):
    config = MMDevConfig(
        workdir=tmp_path,
        strong_model_provider="claude",
        claude_api_key="x",
        claude_planner_model="claude-plan",
    )

    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    monkeypatch.setattr("mmdev.cli.build_strong_client", lambda cfg: object())
    monkeypatch.setattr("mmdev.cli.create_plan", lambda requirement, cfg, client: object())
    monkeypatch.setattr("mmdev.cli.write_plan", lambda mmdev_dir, plan: Path(mmdev_dir) / "tasks.json")

    result = runner.invoke(app, ["plan", "add filter"])
    assert result.exit_code == 0
    assert "Strong model (plan): provider=claude, model=claude-plan" in result.stdout
    run_events = config.mmdev_dir / "logs" / "run-events.jsonl"
    assert run_events.exists()
    events = [json.loads(line) for line in run_events.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events[0]["event"] == "cli.plan.start"
    assert events[0]["strong_provider"] == "claude"
    assert events[0]["strong_model"] == "claude-plan"
    assert events[-1]["event"] == "cli.plan.finish"
    assert events[-1]["outcome"] == "success"


def test_review_prints_strong_model_provider_and_model(monkeypatch, tmp_path):
    config = MMDevConfig(
        workdir=tmp_path,
        strong_model_provider="openai",
        openai_api_key="x",
        openai_reviewer_model="gpt-review",
    )

    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    monkeypatch.setattr("mmdev.cli.load_plan", lambda mmdev_dir: {})
    monkeypatch.setattr("mmdev.cli.find_task", lambda plan_data, task_id: object())
    monkeypatch.setattr("mmdev.cli.read_validation_result", lambda mmdev_dir, task_id: object())
    monkeypatch.setattr("mmdev.cli.build_strong_client", lambda cfg: object())
    monkeypatch.setattr(
        "mmdev.cli.review_task",
        lambda task, validation, cfg, client: ReviewResult(
            task_id="task-001",
            approved=True,
            findings=[],
            missing_acceptance_criteria=[],
            recommended_next_action="approve",
        ),
    )
    monkeypatch.setattr("mmdev.cli.write_review_result", lambda mmdev_dir, review: Path(mmdev_dir) / "task-001-review.json")

    result = runner.invoke(app, ["review", "task-001"])
    assert result.exit_code == 0
    assert "Strong model (review): provider=openai, model=gpt-review" in result.stdout
    run_events = config.mmdev_dir / "logs" / "run-events.jsonl"
    events = [json.loads(line) for line in run_events.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events[0]["event"] == "cli.review.start"
    assert events[0]["task_id"] == "task-001"
    assert events[0]["strong_provider"] == "openai"
    assert events[0]["strong_model"] == "gpt-review"
    assert events[-1]["event"] == "cli.review.finish"
    assert events[-1]["outcome"] == "success"


def test_auto_prints_strong_and_executor_model_labels(monkeypatch, tmp_path):
    config = MMDevConfig(
        workdir=tmp_path,
        strong_model_provider="claude",
        claude_api_key="x",
        claude_planner_model="claude-plan",
        claude_reviewer_model="claude-review",
        executor_provider="mmdev_gateway",
        mmdev_gateway_url="https://gateway.example.test",
        mmdev_gateway_token="token",
        mmdev_gateway_executor_model="gateway-executor-v1",
    )

    class DummyAutoResult:
        def model_dump_json(self, indent=2):  # pragma: no cover - shape-only stub
            return "{}"

    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    monkeypatch.setattr("mmdev.cli.build_strong_client", lambda cfg: object())
    monkeypatch.setattr("mmdev.cli.build_executor_client", lambda cfg: object())
    monkeypatch.setattr("mmdev.cli.run_auto", lambda *args, **kwargs: DummyAutoResult())

    result = runner.invoke(app, ["auto", "implement feature"])
    assert result.exit_code == 0
    assert "Strong model (plan): provider=claude, model=claude-plan" in result.stdout
    assert "Strong model (review): provider=claude, model=claude-review" in result.stdout
    assert "Executor model: provider=mmdev_gateway, model=gateway-executor-v1" in result.stdout
    run_events = config.mmdev_dir / "logs" / "run-events.jsonl"
    events = [json.loads(line) for line in run_events.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events[0]["event"] == "cli.auto.start"
    assert events[0]["strong_provider"] == "claude"
    assert events[0]["planner_model"] == "claude-plan"
    assert events[0]["reviewer_model"] == "claude-review"
    assert events[0]["executor_provider"] == "mmdev_gateway"
    assert events[0]["executor_model"] == "gateway-executor-v1"
    assert events[-1]["event"] == "cli.auto.finish"
    assert events[-1]["outcome"] == "success"
