import csv
import json
import sqlite3
from datetime import datetime, timezone

from typer.testing import CliRunner

from mmdev.cli import app
from mmdev.config import init_state_dir
from mmdev.run_events import append_run_event
from mmdev.schemas import ModelUsage, ProjectPlan, ValidationResult
from mmdev.state import record_plan, record_validation, state_path
from mmdev.usage import append_usage


runner = CliRunner()


def test_metrics_command_outputs_grouped_json(tmp_path):
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
                    "title": "Change title",
                    "goal": "Change title",
                    "context": "",
                    "allowed_files": ["index.html"],
                    "forbidden_changes": [],
                    "acceptance_criteria": ["Title changed"],
                    "validation_commands": [],
                    "complexity": "low",
                    "recommended_executor": "cheap",
                    "max_attempts": 2,
                }
            ],
        }
    )
    record_plan(mmdev_dir, plan)
    validation = ValidationResult(task_id="task-001", command_results=[], passed=True)
    record_validation(mmdev_dir, validation)
    (mmdev_dir / "reports" / "task-001-validation.json").write_text(validation.model_dump_json(), encoding="utf-8")
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="claude-plan",
            input_tokens=120,
            output_tokens=30,
            estimated_cost=0.12,
            duration_ms=5,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="gateway-executor-v1",
            input_tokens=90,
            output_tokens=40,
            estimated_cost=0.05,
            duration_ms=4,
            purpose="execute",
            charged_credits=0.08,
            provider_cost=0.03,
        ),
    )
    append_run_event(
        mmdev_dir,
        {
            "event": "cli.plan.finish",
            "outcome": "success",
            "strong_provider": "claude",
            "strong_model": "claude-plan",
        },
    )
    append_run_event(
        mmdev_dir,
        {
            "event": "cli.auto.finish",
            "outcome": "success",
            "strong_provider": "claude",
            "planner_model": "claude-plan",
            "reviewer_model": "claude-review",
            "executor_provider": "mmdev_gateway",
            "executor_model": "gateway-executor-v1",
        },
    )

    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["model_calls"] == 2
    assert payload["summary"]["run_events"] == 2
    assert payload["summary"]["calls_by_purpose"]["plan"] == 1
    assert payload["summary"]["calls_by_purpose"]["execute"] == 1
    assert abs(payload["summary"]["baseline_cost"] - 0.0035) < 0.000001
    assert abs(payload["summary"]["estimated_savings"] - (-0.1665)) < 0.000001
    assert payload["summary"]["baseline_uses_default"] is False
    assert payload["patch_economics"]["accepted_patches"] == 1
    assert payload["patch_economics"]["applied_patches"] == 1
    assert payload["patch_economics"]["generated_patches"] == 1
    assert abs(payload["patch_economics"]["cost_per_accepted_patch"] - 0.17) < 0.000001
    assert abs(payload["patch_economics"]["cost_per_applied_patch"] - 0.17) < 0.000001
    assert abs(payload["patch_economics"]["baseline_cost_per_accepted_patch"] - 0.0035) < 0.000001
    assert abs(payload["patch_economics"]["baseline_cost_per_applied_patch"] - 0.0035) < 0.000001
    assert payload["usage_by_model_purpose"][0]["purpose"] == "execute"
    assert payload["usage_by_model_purpose"][1]["purpose"] == "plan"
    assert payload["strong_route_stats"][0]["provider"] == "claude"
    assert payload["auto_route_stats"][0]["executor_provider"] == "mmdev_gateway"


def test_metrics_command_can_write_output_file(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=10,
            output_tokens=5,
            estimated_cost=0.01,
            duration_ms=1,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    out = tmp_path / "exports" / "metrics.json"

    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--compact", "--out", str(out)])
    assert result.exit_code == 0
    assert f"Wrote {out}" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["model_calls"] == 1
    assert payload["summary"]["calls_by_purpose"]["plan"] == 1


def test_metrics_command_window_filters_usage_and_events(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="old-plan",
            input_tokens=10,
            output_tokens=5,
            estimated_cost=0.01,
            duration_ms=1,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="new-exec",
            input_tokens=20,
            output_tokens=10,
            estimated_cost=0.02,
            duration_ms=1,
            purpose="execute",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    with sqlite3.connect(state_path(mmdev_dir)) as conn:
        conn.execute("update model_usage set created_at='2000-01-01 00:00:00' where id=1")
        conn.commit()
    run_events = mmdev_dir / "logs" / "run-events.jsonl"
    run_events.write_text(
        "\n".join(
            [
                json.dumps({"ts": "2000-01-01T00:00:00Z", "event": "cli.plan.finish", "outcome": "success"}),
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "cli.auto.finish",
                        "outcome": "success",
                        "strong_provider": "claude",
                        "planner_model": "claude-plan",
                        "reviewer_model": "claude-review",
                        "executor_provider": "mmdev_gateway",
                        "executor_model": "gateway-v1",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--window", "24h"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["window"]["spec"] == "24h"
    assert payload["summary"]["model_calls"] == 1
    assert payload["summary"]["run_events"] == 1
    assert payload["summary"]["calls_by_purpose"]["plan"] == 0
    assert payload["summary"]["calls_by_purpose"]["execute"] == 1


def test_metrics_command_rejects_invalid_window(tmp_path):
    init_state_dir(tmp_path)
    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--window", "bad"])
    assert result.exit_code != 0
    assert "window must be 'all' or <N>h/<N>d" in result.output


def test_metrics_command_can_write_grouped_csv_files(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=11,
            output_tokens=7,
            estimated_cost=0.02,
            duration_ms=1,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    append_run_event(
        mmdev_dir,
        {
            "event": "cli.plan.finish",
            "outcome": "success",
            "strong_provider": "openai",
            "strong_model": "gpt-planner",
        },
    )
    csv_dir = tmp_path / "exports" / "csv"
    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--csv-dir", str(csv_dir), "--compact"])
    assert result.exit_code == 0

    usage_csv = csv_dir / "usage_by_model_purpose.csv"
    strong_csv = csv_dir / "strong_route_stats.csv"
    auto_csv = csv_dir / "auto_route_stats.csv"
    assert usage_csv.exists()
    assert strong_csv.exists()
    assert auto_csv.exists()

    with usage_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["purpose"] == "plan"
    assert rows[0]["model"] == "planner"

    with strong_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["provider"] == "openai"
    assert rows[0]["model"] == "gpt-planner"

    with auto_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == []


def test_metrics_command_csv_prefix_changes_output_filenames(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=1,
            output_tokens=1,
            estimated_cost=0.0,
            duration_ms=1,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    csv_dir = tmp_path / "exports" / "csv"
    result = runner.invoke(
        app,
        ["metrics", "--workdir", str(tmp_path), "--csv-dir", str(csv_dir), "--csv-prefix", "daily-2026-05-11", "--compact"],
    )
    assert result.exit_code == 0
    assert (csv_dir / "daily-2026-05-11-usage_by_model_purpose.csv").exists()
    assert (csv_dir / "daily-2026-05-11-strong_route_stats.csv").exists()
    assert (csv_dir / "daily-2026-05-11-auto_route_stats.csv").exists()


def test_metrics_command_rejects_csv_prefix_without_csv_dir(tmp_path):
    init_state_dir(tmp_path)
    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--csv-prefix", "daily"])
    assert result.exit_code != 0
    assert "--csv-prefix requires --csv-dir" in result.output


def test_metrics_command_can_write_meta_csv(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=3,
            output_tokens=2,
            estimated_cost=0.01,
            duration_ms=1,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    csv_dir = tmp_path / "exports" / "csv"
    result = runner.invoke(
        app,
        ["metrics", "--workdir", str(tmp_path), "--csv-dir", str(csv_dir), "--csv-prefix", "daily", "--csv-meta", "--compact"],
    )
    assert result.exit_code == 0
    meta_csv = csv_dir / "daily-meta.csv"
    assert meta_csv.exists()
    with meta_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["window_spec"] == "all"
    assert rows[0]["model_calls"] == "1"
    assert rows[0]["calls_plan"] == "1"
    assert rows[0]["accepted_patches"] == "0"
    assert rows[0]["applied_patches"] == "0"
    assert rows[0]["generated_patches"] == "0"
    assert rows[0]["cost_per_accepted_patch"] == "0.0"
    assert rows[0]["cost_per_applied_patch"] == "0.0"
    assert rows[0]["savings_ratio_per_applied_patch"] == "0.0"


def test_metrics_command_rejects_csv_meta_without_csv_dir(tmp_path):
    init_state_dir(tmp_path)
    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--csv-meta"])
    assert result.exit_code != 0
    assert "--csv-meta requires --csv-dir" in result.output


def test_metrics_command_can_push_payload(monkeypatch, tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    append_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=4,
            output_tokens=2,
            estimated_cost=0.01,
            duration_ms=1,
            purpose="plan",
            charged_credits=0.0,
            provider_cost=0.0,
        ),
    )
    captured: dict = {}

    def fake_push(metrics, url, *, token=None, timeout_seconds=20):
        captured["url"] = url
        captured["token"] = token
        captured["timeout_seconds"] = timeout_seconds
        captured["model_calls"] = metrics["summary"]["model_calls"]
        return 202

    monkeypatch.setattr("mmdev.cli.push_metrics", fake_push)
    result = runner.invoke(
        app,
        [
            "metrics",
            "--workdir",
            str(tmp_path),
            "--push",
            "https://collector.example.test/ingest",
            "--push-token",
            "secret-token",
            "--push-timeout-seconds",
            "15",
            "--compact",
        ],
    )
    assert result.exit_code == 0
    assert "Pushed metrics to https://collector.example.test/ingest (status 202)" in result.output
    assert captured["url"] == "https://collector.example.test/ingest"
    assert captured["token"] == "secret-token"
    assert captured["timeout_seconds"] == 15
    assert captured["model_calls"] == 1


def test_metrics_command_push_failure_returns_exit_1(monkeypatch, tmp_path):
    init_state_dir(tmp_path)

    def fake_push(metrics, url, *, token=None, timeout_seconds=20):
        raise RuntimeError("network down")

    monkeypatch.setattr("mmdev.cli.push_metrics", fake_push)
    result = runner.invoke(app, ["metrics", "--workdir", str(tmp_path), "--push", "https://collector.example.test/ingest"])
    assert result.exit_code == 1
    assert "Failed to push metrics: network down" in result.output
