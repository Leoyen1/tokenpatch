import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from mmdev.cli import app
from mmdev.cli import build_strong_client
from mmdev.cli import format_savings_snapshot
from mmdev.config import MMDevConfig
from mmdev.models.openai_client import OpenAIChatCompletionsClient, OpenAIResponsesClient
from mmdev.schemas import ReviewResult


runner = CliRunner()


def test_build_strong_client_supports_openai_base_url_and_api_modes(tmp_path):
    responses = build_strong_client(
        MMDevConfig(
            workdir=tmp_path,
            openai_api_key="key",
            openai_base_url="https://cc-switch.example/v1",
            openai_api_mode="responses",
        )
    )
    assert isinstance(responses, OpenAIResponsesClient)
    assert responses.base_url == "https://cc-switch.example/v1"

    chat = build_strong_client(
        MMDevConfig(
            workdir=tmp_path,
            openai_api_key="key",
            openai_base_url="https://cc-switch.example/v1",
            openai_api_mode="chat_completions",
        )
    )
    assert isinstance(chat, OpenAIChatCompletionsClient)
    assert chat.base_url == "https://cc-switch.example/v1"


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

    result = runner.invoke(app, ["auto", "implement feature", "--no-checkpoint"])
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


def test_init_global_command_writes_template(monkeypatch, tmp_path):
    global_path = tmp_path / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))

    result = runner.invoke(app, ["init-global"])

    assert result.exit_code == 0
    assert str(global_path) in result.stdout
    assert global_path.exists()
    assert "deepseek_executor_model" in global_path.read_text(encoding="utf-8")


def test_auto_creates_checkpoint_by_default(monkeypatch, tmp_path):
    config = MMDevConfig(
        workdir=tmp_path,
        strong_model_provider="openai",
        openai_api_key="x",
        openai_planner_model="plan",
        openai_reviewer_model="review",
        deepseek_api_key="x",
        deepseek_base_url="https://example.test/v1",
        deepseek_executor_model="executor",
    )

    class DummyAutoResult:
        def model_dump_json(self, indent=2):
            return "{}"

    class DummyCheckpoint:
        id = "checkpoint-001"

    captured = {}
    def fake_create_checkpoint(cfg, label, source):
        captured["args"] = (label, source)
        return DummyCheckpoint()

    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    monkeypatch.setattr("mmdev.cli.build_strong_client", lambda cfg: object())
    monkeypatch.setattr("mmdev.cli.build_executor_client", lambda cfg: object())
    monkeypatch.setattr("mmdev.cli.run_auto", lambda *args, **kwargs: DummyAutoResult())
    monkeypatch.setattr("mmdev.cli.create_checkpoint", fake_create_checkpoint)

    result = runner.invoke(app, ["auto", "implement feature"])

    assert result.exit_code == 0
    assert "Checkpoint: checkpoint-001" in result.stdout
    assert captured["args"] == ("before-auto", "auto")


def test_do_command_runs_bounded_executor_without_strong_model_key(monkeypatch, tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    (tmp_path / "app.py").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    config = MMDevConfig(
        workdir=tmp_path,
        executor_provider="deepseek_byok",
        deepseek_api_key="key",
        deepseek_base_url="https://example.test",
        deepseek_executor_model="executor",
    )

    class GoodClient:
        def complete(self, *, prompt, model, timeout_seconds):
            from mmdev.models.base import CompletionResult

            return CompletionResult(
                text="""{
  "patch": "diff --git a/app.py b/app.py\\n--- a/app.py\\n+++ b/app.py\\n@@ -1 +1 @@\\n-base\\n+updated\\n",
  "changed_files": ["app.py"],
  "summary": "updated app",
  "risks": [],
  "verification_hint": "",
  "needs_human_input": false
}""",
                input_tokens=10,
                output_tokens=5,
            )

    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    monkeypatch.setattr("mmdev.cli.build_executor_client", lambda cfg: GoodClient())

    result = runner.invoke(
        app,
        [
            "do",
            "update app",
            "--allowed-file",
            "app.py",
            "--acceptance",
            "app.py says updated",
            "--no-checkpoint",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout[result.stdout.find('{\n  "ok"'):])
    assert payload["ok"] is True
    assert payload["execution"]["changed_files"] == ["app.py"]
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "updated\n"


def test_do_command_requires_allowed_file(tmp_path):
    result = runner.invoke(app, ["do", "update app", "--workdir", str(tmp_path)])

    assert result.exit_code != 0
    assert "at least one --allowed-file is required" in result.output


def test_checkpoint_and_memory_cli_commands(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    (tmp_path / "app.py").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)

    create = runner.invoke(app, ["checkpoint", "create", "before edit", "--workdir", str(tmp_path)])
    assert create.exit_code == 0
    checkpoint_id = json.loads(create.stdout)["id"]

    listed = runner.invoke(app, ["checkpoint", "list", "--workdir", str(tmp_path)])
    assert listed.exit_code == 0
    assert checkpoint_id in listed.stdout

    memory = runner.invoke(app, ["memory", "refresh", "--workdir", str(tmp_path)])
    assert memory.exit_code == 0
    assert "Project Memory Pack" not in memory.stdout

    shown = runner.invoke(app, ["memory", "show", "--workdir", str(tmp_path)])
    assert shown.exit_code == 0
    assert "Project Memory Pack" in shown.stdout


def test_web_command_starts_local_console(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path)
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)

    captured = {}

    def fake_create_web_app(workdir):
        captured["workdir"] = workdir
        return object()

    class FakeUvicorn:
        @staticmethod
        def run(app_instance, host, port):
            captured["app"] = app_instance
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setitem(__import__("sys").modules, "uvicorn", FakeUvicorn)
    monkeypatch.setattr("mmdev.web_console.create_web_app", fake_create_web_app)

    result = runner.invoke(app, ["web", "--host", "127.0.0.1", "--port", "8787"])
    assert result.exit_code == 0
    assert "Starting tokenpatch web console at http://127.0.0.1:8787" in result.stdout
    assert captured["workdir"] == tmp_path
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8787


def test_setup_command_starts_setup_page(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path)
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)

    captured = {}

    def fake_create_web_app(workdir):
        captured["workdir"] = workdir
        return object()

    class FakeUvicorn:
        @staticmethod
        def run(app_instance, host, port):
            captured["app"] = app_instance
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setitem(__import__("sys").modules, "uvicorn", FakeUvicorn)
    monkeypatch.setattr("mmdev.web_console.create_web_app", fake_create_web_app)

    result = runner.invoke(app, ["setup", "--host", "127.0.0.1", "--port", "8788"])

    assert result.exit_code == 0
    assert "Starting tokenpatch setup at http://127.0.0.1:8788/setup" in result.stdout
    assert captured["workdir"] == tmp_path
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8788


def test_mcp_config_outputs_json_and_markdown(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path)
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)

    json_result = runner.invoke(app, ["mcp-config"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["mcpServers"]["tokenpatch"]["command"]
    assert payload["mcpServers"]["tokenpatch"]["args"][0].endswith("tokenpatch_mcp_launcher.py")

    md_result = runner.invoke(app, ["mcp-config", "--format", "markdown"])
    assert md_result.exit_code == 0
    assert "Recommended agent instruction" in md_result.stdout
    assert "tokenpatch_auto" in md_result.stdout
    assert "tp:" in md_result.stdout


def test_format_savings_snapshot_prioritizes_savings_fields():
    text = format_savings_snapshot(
        {
            "summary": {
                "savings_ratio": 88.5,
                "estimated_savings": 1.25,
                "estimated_cost": 0.15,
                "baseline_cost": 1.4,
                "baseline_uses_default": True,
            },
            "patch_economics": {
                "applied_patches": 2,
                "cost_per_applied_patch": 0.075,
                "savings_per_applied_patch": 0.625,
                "savings_ratio_per_applied_patch": 88.5,
            },
        }
    )
    assert "Savings Snapshot:" in text
    assert "Savings ratio: 88.50%" in text
    assert "Estimated savings: 1.250000" in text
    assert "Applied patches: 2" in text
    assert "Cost per applied patch: 0.075000" in text
    assert "default frontier baseline" in text


def test_install_codex_cli_dry_run(monkeypatch, tmp_path):
    codex_config = tmp_path / "codex-config.toml"
    codex_config.write_text("[mcp_servers]\n", encoding="utf-8")

    result = runner.invoke(app, ["install-codex", "--config-path", str(codex_config), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run; no files were modified." in result.stdout
    assert "[mcp_servers.tokenpatch]" in result.stdout
    assert "tokenpatch_mcp_launcher.py" in result.stdout
    assert "Launcher mode is enabled" in result.stdout
    assert "Instructions:" in result.stdout
    assert "Settings -> MCP Servers -> tokenpatch -> Environment variables" in result.stdout
    assert "DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro" in result.stdout
    assert "tp: implement" in result.stdout
    assert "[mcp_servers.tokenpatch]" not in codex_config.read_text(encoding="utf-8")


def test_install_codex_cli_fixed_workdir(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path)
    codex_config = tmp_path / "codex-config.toml"
    codex_config.write_text("[mcp_servers]\n", encoding="utf-8")
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)

    result = runner.invoke(app, ["install-codex", "--config-path", str(codex_config), "--dry-run", "--fixed-workdir", "--script-command"])

    assert result.exit_code == 0
    assert str(tmp_path) in result.stdout
    assert "--workdir" in result.stdout


def test_install_cursor_cli_dry_run(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path)
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)

    result = runner.invoke(app, ["install-cursor", "--dry-run", "--python-command", "python"])

    assert result.exit_code == 0
    assert "Dry run; no files were modified." in result.stdout
    assert ".cursor" in result.stdout
    assert "python -m mmdev.cli do" in result.stdout
    assert "report --workdir ." in result.stdout
    assert "Savings ratio" in result.stdout
    assert "tp: implement" in result.stdout
    assert not (tmp_path / ".cursor" / "rules" / "tokenpatch.mdc").exists()


def test_install_claude_code_cli_dry_run(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path)
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)

    result = runner.invoke(app, ["install-claude-code", "--dry-run", "--python-command", "python"])

    assert result.exit_code == 0
    assert "Claude Code MCP config:" in result.stdout
    assert "Claude Code memory:" in result.stdout
    assert "Dry run; no files were modified." in result.stdout
    assert "tp: implement" in result.stdout
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


def test_bootstrap_cli_dry_run_does_not_write(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path, deepseek_api_key="sk-test")
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    codex_config = tmp_path / "codex" / "config.toml"
    cursor_rule = tmp_path / ".cursor" / "rules" / "tokenpatch.mdc"
    claude_mcp = tmp_path / ".mcp.json"
    claude_memory = tmp_path / ".claude" / "CLAUDE.md"

    result = runner.invoke(
        app,
        [
            "bootstrap",
            "--dry-run",
            "--codex-config-path",
            str(codex_config),
            "--cursor-rules-path",
            str(cursor_rule),
            "--claude-mcp-path",
            str(claude_mcp),
            "--claude-memory-path",
            str(claude_memory),
            "--python-command",
            "python",
        ],
    )

    assert result.exit_code == 0
    assert "tokenpatch bootstrap for" in result.stdout
    assert "deepseek_byok configured (deepseek-v4-pro)" in result.stdout
    assert "Would initialize:" in result.stdout
    assert "Codex config:" in result.stdout
    assert "Cursor rule:" in result.stdout
    assert "Claude Code MCP config:" in result.stdout
    assert "Dry run; no files were modified." in result.stdout
    assert "TokenPatch Bootstrap Test" in result.stdout
    assert "tp: modify" in result.stdout
    assert not codex_config.exists()
    assert not cursor_rule.exists()
    assert not claude_mcp.exists()
    assert not claude_memory.exists()
    assert not (tmp_path / ".mmdev").exists()


def test_bootstrap_cli_writes_project_integrations(monkeypatch, tmp_path):
    config = MMDevConfig(workdir=tmp_path, deepseek_api_key="sk-test")
    monkeypatch.setattr("mmdev.cli.load_config", lambda workdir=None: config)
    codex_config = tmp_path / "codex" / "config.toml"
    cursor_rule = tmp_path / ".cursor" / "rules" / "tokenpatch.mdc"
    claude_mcp = tmp_path / ".mcp.json"
    claude_memory = tmp_path / ".claude" / "CLAUDE.md"

    result = runner.invoke(
        app,
        [
            "bootstrap",
            "--codex-config-path",
            str(codex_config),
            "--cursor-rules-path",
            str(cursor_rule),
            "--claude-mcp-path",
            str(claude_mcp),
            "--claude-memory-path",
            str(claude_memory),
            "--python-command",
            "python",
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".mmdev" / "config.toml").exists()
    assert codex_config.exists()
    assert (tmp_path / "codex" / "tokenpatch_mcp_launcher.py").exists()
    assert cursor_rule.exists()
    assert claude_mcp.exists()
    assert claude_memory.exists()
    assert (tmp_path / ".claude" / "tokenpatch_mcp_launcher.py").exists()
    assert "python -m mmdev.cli do" in cursor_rule.read_text(encoding="utf-8")
    assert "tokenpatch" in claude_memory.read_text(encoding="utf-8")
