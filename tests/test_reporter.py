import json

from mmdev.config import init_state_dir
from mmdev.reporter import generate_report, write_final_report
from mmdev.schemas import ModelUsage, ProjectPlan, ReviewResult, ValidationResult
from mmdev.usage import append_usage


def test_generate_report_summarizes_tasks_results_and_usage(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    (mmdev_dir / "config.toml").write_text(
        "baseline_strong_input_cost_per_million = 10.0\nbaseline_strong_output_cost_per_million = 20.0\n",
        encoding="utf-8",
    )
    plan = ProjectPlan.model_validate(
        {
            "project_summary": "sample",
            "assumptions": [],
            "risks": [],
            "tasks": [
                {
                    "task_id": "task-001",
                    "title": "Add filter",
                    "goal": "Add a filter",
                    "context": "",
                    "allowed_files": ["src/todos.py"],
                    "forbidden_changes": [],
                    "acceptance_criteria": ["Works"],
                    "validation_commands": ["pytest"],
                    "complexity": "low",
                    "recommended_executor": "cheap",
                    "max_attempts": 2,
                }
            ],
        }
    )
    (mmdev_dir / "tasks.json").write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )
    validation = ValidationResult(task_id="task-001", command_results=[], passed=True)
    review = ReviewResult(
        task_id="task-001",
        approved=True,
        findings=[],
        missing_acceptance_criteria=[],
        recommended_next_action="approve",
    )
    (mmdev_dir / "reports" / "task-001-validation.json").write_text(validation.model_dump_json(), encoding="utf-8")
    (mmdev_dir / "reports" / "task-001-review.json").write_text(review.model_dump_json(), encoding="utf-8")
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=100_000,
            output_tokens=100_000,
            estimated_cost=1.0,
            duration_ms=1,
            purpose="plan",
            charged_credits=2.5,
            provider_cost=0.5,
        ),
    )
    (mmdev_dir / "logs" / "run-events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:00Z",
                        "event": "cli.plan.finish",
                        "outcome": "success",
                        "strong_provider": "claude",
                        "strong_model": "claude-plan",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "ts": "2026-01-01T00:01:00Z",
                        "event": "cli.review.finish",
                        "outcome": "error",
                        "strong_provider": "claude",
                        "strong_model": "claude-review",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "ts": "2026-01-01T00:02:00Z",
                        "event": "cli.auto.finish",
                        "outcome": "success",
                        "strong_provider": "claude",
                        "planner_model": "claude-plan",
                        "reviewer_model": "claude-review",
                        "executor_provider": "mmdev_gateway",
                        "executor_model": "gateway-v1",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = generate_report(mmdev_dir)
    assert "Total tasks: 1" in report
    assert "Validation: passed" in report
    assert "Review: approved" in report
    assert "Estimated total cost: 1.000000" in report
    assert "Gateway credits charged: 2.500000" in report
    assert "Gateway provider cost: 0.500000" in report
    assert "Estimated strong-model cost: 1.000000" in report
    assert "Estimated cheap-executor cost: 0.000000" in report
    assert "Estimated all-strong baseline cost: 3.000000" in report
    assert "Estimated savings vs all-strong: 2.000000" in report
    assert "Estimated savings ratio: 66.67%" in report
    assert "## Cost by Provider/Model" in report
    assert "- plan / planner: calls=1, input=100000, output=100000, cost=1.000000" in report
    assert "## Routing Success (from run-events.jsonl)" in report
    assert "- Logged run events: 3" in report
    assert "plan / claude / claude-plan: runs=1, success=1, error=0, success_rate=100.00%" in report
    assert "review / claude / claude-review: runs=1, success=0, error=1, success_rate=0.00%" in report
    assert "executor=mmdev_gateway (gateway-v1): runs=1, success=1, error=0, success_rate=100.00%" in report
    path = write_final_report(mmdev_dir)
    assert path.name == "final-report.md"
    assert path.exists()
