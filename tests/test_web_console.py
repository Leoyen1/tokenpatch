import subprocess

from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse

from mmdev.config import init_state_dir
from mmdev.models.base import CompletionResult
from mmdev.web_console import create_web_app


class FakeStrongClient:
    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        return CompletionResult(
            text="""{
  "project_summary": "demo",
  "assumptions": [],
  "risks": [],
  "tasks": [{
    "task_id": "task-001",
    "title": "Update app file",
    "goal": "Update file",
    "context": "",
    "allowed_files": ["src/app.py"],
    "forbidden_changes": [],
    "acceptance_criteria": ["file updated"],
    "validation_commands": [],
    "complexity": "low",
    "recommended_executor": "cheap",
    "max_attempts": 2
  }]
}"""
        )


class FakeExecutorClient:
    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        return CompletionResult(
            text="""{
  "patch": "diff --git a/src/app.py b/src/app.py\\n--- a/src/app.py\\n+++ b/src/app.py\\n@@ -1 +1 @@\\n-old\\n+new\\n",
  "changed_files": ["src/app.py"],
  "summary": "updated",
  "risks": [],
  "verification_hint": "",
  "needs_human_input": false
}"""
        )


def setup_demo_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    init_state_dir(tmp_path)
    config = tmp_path / ".mmdev" / "config.toml"
    config.write_text(
        """strong_model_provider = "openai"
openai_api_key = "fake-openai-key"
openai_planner_model = "fake-plan"
openai_reviewer_model = "fake-review"
executor_provider = "deepseek_byok"
deepseek_api_key = "fake-deepseek-key"
deepseek_base_url = "https://example.test/v1"
deepseek_executor_model = "fake-executor"
""",
        encoding="utf-8",
    )


def patch_templates(monkeypatch):
    class FakeTemplates:
        def __init__(self, directory):  # pragma: no cover - shape-only stub
            self.directory = directory

        def TemplateResponse(self, name, context):
            if name == "settings.html":
                html = "<html><body>Doctor Checks</body></html>"
            elif name == "onboarding.html":
                html = "<html><body>First-run checklist</body></html>"
            elif name == "setup.html":
                html = "<html><body>One-time setup</body></html>"
            else:
                html = "<html><body>tokenpatch Web Console</body></html>"
            return HTMLResponse(content=html)

    monkeypatch.setattr("mmdev.web_console.Jinja2Templates", FakeTemplates)


def test_web_home_and_settings_render(monkeypatch, tmp_path):
    setup_demo_repo(tmp_path)
    patch_templates(monkeypatch)
    app = create_web_app(tmp_path, strong_client_builder=lambda config: FakeStrongClient(), executor_client_builder=lambda config: FakeExecutorClient())
    client = TestClient(app)

    home = client.get("/")
    assert home.status_code == 200
    assert "tokenpatch Web Console" in home.text

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "Doctor Checks" in settings.text

    onboarding = client.get("/onboarding")
    assert onboarding.status_code == 200
    assert "First-run checklist" in onboarding.text

    setup = client.get("/setup")
    assert setup.status_code == 200
    assert "One-time setup" in setup.text

    state = client.get("/api/onboarding")
    assert state.status_code == 200
    payload = state.json()
    assert payload["ready_to_plan"] is True
    assert payload["steps"][0]["title"] == "Initialize local state"


def test_web_plan_run_report_flow(monkeypatch, tmp_path):
    setup_demo_repo(tmp_path)
    patch_templates(monkeypatch)
    app = create_web_app(tmp_path, strong_client_builder=lambda config: FakeStrongClient(), executor_client_builder=lambda config: FakeExecutorClient())
    client = TestClient(app)

    plan = client.post("/api/plan", json={"requirement": "update app"})
    assert plan.status_code == 200
    assert plan.json()["ok"] is True
    assert plan.json()["plan"]["tasks"][0]["task_id"] == "task-001"

    run = client.post("/api/run/task-001")
    assert run.status_code == 200
    assert run.json()["ok"] is True
    assert run.json()["checkpoint"]["source"] == "web-run"
    assert run.json()["execution"]["changed_files"] == ["src/app.py"]

    checkpoints = client.get("/api/checkpoints")
    assert checkpoints.status_code == 200
    assert checkpoints.json()["checkpoints"]

    memory = client.post("/api/memory/refresh")
    assert memory.status_code == 200
    assert memory.json()["memory"]["key_files"]

    report = client.post("/api/report")
    assert report.status_code == 200
    payload = report.json()
    assert payload["ok"] is True
    assert "tokenpatch Final Report" in payload["report_text"]
    assert payload["metrics_summary"]["model_calls"] >= 2
    assert payload["patch_economics"]["generated_patches"] == 1
    assert payload["patch_economics"]["applied_patches"] == 1
    assert payload["patch_economics"]["accepted_patches"] == 0
    assert payload["patch_economics"]["estimated_savings_ratio"] > 0
    assert payload["patch_economics"]["savings_ratio_per_applied_patch"] > 0


def test_web_error_mapping_for_missing_tasks(monkeypatch, tmp_path):
    setup_demo_repo(tmp_path)
    patch_templates(monkeypatch)
    app = create_web_app(tmp_path, strong_client_builder=lambda config: FakeStrongClient(), executor_client_builder=lambda config: FakeExecutorClient())
    client = TestClient(app)

    response = client.post("/api/run/task-001")
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert "No task plan exists yet" in payload["error"]


def test_web_onboarding_reports_missing_config(monkeypatch, tmp_path):
    patch_templates(monkeypatch)
    app = create_web_app(tmp_path, strong_client_builder=lambda config: FakeStrongClient(), executor_client_builder=lambda config: FakeExecutorClient())
    client = TestClient(app)

    response = client.get("/api/onboarding")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready_to_plan"] is False
    assert payload["next_action"]["title"] == "Initialize local state"
    assert any(step["title"] == "Configure strong model" for step in payload["steps"])


def test_web_setup_saves_global_executor_config(monkeypatch, tmp_path):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    patch_templates(monkeypatch)
    app = create_web_app(tmp_path, strong_client_builder=lambda config: FakeStrongClient(), executor_client_builder=lambda config: FakeExecutorClient())
    client = TestClient(app)

    response = client.post(
        "/api/setup",
        json={
            "executor_provider": "deepseek_byok",
            "deepseek_api_key": "deepseek-key",
            "deepseek_base_url": "https://api.deepseek.com/v1",
            "deepseek_executor_model": "deepseek-chat",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert global_path.exists()
    text = global_path.read_text(encoding="utf-8")
    assert 'deepseek_api_key = "deepseek-key"' in text
    assert not (tmp_path / ".mmdev" / "config.toml").exists()
