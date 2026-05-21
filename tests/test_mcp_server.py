import io
import json
import subprocess

from typer.testing import CliRunner

from mmdev.config import init_state_dir
from mmdev.cli import app
from mmdev.mcp_server import MCP_PROTOCOL_VERSION, handle_message, read_message, write_message
from mmdev.schemas import ProjectPlan
from mmdev.state import record_plan


runner = CliRunner()


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result


def setup_repo(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "app.py").write_text("base\n", encoding="utf-8")
    run(["git", "add", "."], tmp_path)
    run(["git", "commit", "-m", "initial"], tmp_path)


def test_mcp_initialize_and_tools_list():
    init = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert init["result"]["serverInfo"]["name"] == "tokenpatch"
    assert init["result"]["capabilities"]["tools"]["listChanged"] is False

    listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "tokenpatch" in names
    assert "tokenpatch_auto" in names
    assert "tokenpatch_checkpoint_create" in names
    assert "tokenpatch_memory_refresh" in names
    assert "tokenpatch_run_task" in names
    descriptions = {tool["name"]: tool["description"] for tool in listed["result"]["tools"]}
    assert "tp:" in descriptions["tokenpatch"]
    assert "tp:" in descriptions["tokenpatch_auto"]

    resources = handle_message({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}})
    assert resources["result"] == {"resources": []}

    templates = handle_message({"jsonrpc": "2.0", "id": 4, "method": "resources/templates/list", "params": {}})
    assert templates["result"] == {"resourceTemplates": []}


def test_mcp_checkpoint_and_memory_tools(tmp_path):
    setup_repo(tmp_path)

    init = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "tokenpatch_init", "arguments": {"workdir": str(tmp_path)}},
        }
    )
    assert ".mmdev" in init["result"]["content"][0]["text"]

    checkpoint = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "tokenpatch_checkpoint_create", "arguments": {"workdir": str(tmp_path), "label": "mcp test"}},
        }
    )
    checkpoint_payload = json.loads(checkpoint["result"]["content"][0]["text"])
    assert checkpoint_payload["source"] == "mcp"

    memory = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "tokenpatch_memory_refresh", "arguments": {"workdir": str(tmp_path)}},
        }
    )
    memory_payload = json.loads(memory["result"]["content"][0]["text"])
    assert memory_payload["generated_at"]


def test_mcp_framing_roundtrip():
    out = io.BytesIO()
    write_message(out, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    out.seek(0)
    message = read_message(out)
    assert message["result"]["ok"] is True


def test_mcp_command_is_registered():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mcp" in result.stdout


def test_mcp_run_task_returns_structured_failure(monkeypatch, tmp_path):
    setup_repo(tmp_path)
    mmdev_dir = init_state_dir(tmp_path)
    plan = ProjectPlan.model_validate(
        {
            "project_summary": "",
            "assumptions": [],
            "risks": [],
            "tasks": [
                {
                    "task_id": "task-001",
                    "title": "Edit app",
                    "goal": "Edit app",
                    "context": "",
                    "allowed_files": ["app.py"],
                    "forbidden_changes": [],
                    "acceptance_criteria": ["File updated"],
                    "validation_commands": [],
                    "complexity": "low",
                    "recommended_executor": "cheap",
                    "max_attempts": 2,
                }
            ],
        }
    )
    (mmdev_dir / "tasks.json").write_text(plan.model_dump_json(), encoding="utf-8")
    (mmdev_dir / "config.toml").write_text(
        'deepseek_api_key = "key"\n'
        'deepseek_base_url = "https://example.test/v1"\n'
        'deepseek_executor_model = "executor"\n',
        encoding="utf-8",
    )
    record_plan(mmdev_dir, plan)

    class BadClient:
        def complete(self, *, prompt, model, timeout_seconds):
            from mmdev.models.base import CompletionResult

            return CompletionResult(text="not json")

    monkeypatch.setattr("mmdev.mcp_server.build_executor_client", lambda config: BadClient())

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "tokenpatch_run_task",
                "arguments": {"workdir": str(tmp_path), "task_id": "task-001", "checkpoint": False},
            },
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is False
    assert payload["status"] == "execution-failed"
    assert payload["task_statuses"][0]["status"] == "execution-failed"


def test_mcp_auto_runs_host_planned_task_without_strong_model_key(monkeypatch, tmp_path):
    setup_repo(tmp_path)
    mmdev_dir = init_state_dir(tmp_path)
    (mmdev_dir / "config.toml").write_text(
        'executor_provider = "deepseek_byok"\n'
        'deepseek_api_key = "key"\n'
        'deepseek_base_url = "https://example.test/v1"\n'
        'deepseek_executor_model = "executor"\n',
        encoding="utf-8",
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

    monkeypatch.setattr("mmdev.mcp_server.build_executor_client", lambda config: GoodClient())

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "tokenpatch_auto",
                "arguments": {
                    "workdir": str(tmp_path),
                    "requirement": "update app with tokenpatch",
                    "title": "Update app",
                    "goal": "Change app.py from base to updated.",
                    "allowed_files": ["app.py"],
                    "acceptance_criteria": ["app.py says updated"],
                },
            },
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["status"] == "executed"
    assert payload["checkpoint"]["source"] == "mcp-auto"
    assert payload["execution"]["changed_files"] == ["app.py"]
    assert payload["task_statuses"][0]["status"] == "executed"
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "updated\n"


def test_mcp_tokenpatch_requires_file_scope_before_execution(tmp_path):
    setup_repo(tmp_path)

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "tokenpatch",
                "arguments": {"workdir": str(tmp_path), "requirement": "update app"},
            },
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is False
    assert payload["status"] == "needs-file-scope"
    assert payload["example_arguments"]["allowed_files"] == ["relative/path/to/file.ext"]


def test_mcp_tokenpatch_runs_with_minimal_arguments(monkeypatch, tmp_path):
    setup_repo(tmp_path)
    mmdev_dir = init_state_dir(tmp_path)
    (mmdev_dir / "config.toml").write_text(
        'executor_provider = "deepseek_byok"\n'
        'deepseek_api_key = "key"\n'
        'deepseek_base_url = "https://example.test/v1"\n'
        'deepseek_executor_model = "executor"\n',
        encoding="utf-8",
    )

    class GoodClient:
        def complete(self, *, prompt, model, timeout_seconds):
            from mmdev.models.base import CompletionResult

            return CompletionResult(
                text="""{
  "patch": "diff --git a/app.py b/app.py\\n--- a/app.py\\n+++ b/app.py\\n@@ -1 +1 @@\\n-base\\n+tokenpatch updated\\n",
  "changed_files": ["app.py"],
  "summary": "updated through tokenpatch",
  "risks": [],
  "verification_hint": "",
  "needs_human_input": false
}""",
                input_tokens=10,
                output_tokens=5,
            )

    monkeypatch.setattr("mmdev.mcp_server.build_executor_client", lambda config: GoodClient())

    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "tokenpatch",
                "arguments": {
                    "workdir": str(tmp_path),
                    "requirement": "update app",
                    "allowed_files": ["app.py"],
                },
            },
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["ok"] is True
    assert payload["status"] == "executed"
    assert payload["execution"]["changed_files"] == ["app.py"]
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "tokenpatch updated\n"
