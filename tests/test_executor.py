import subprocess

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.executor import execute_task
from mmdev.models.base import CompletionResult
from mmdev.schemas import DevTask


class FakeClient:
    def complete(self, *, prompt, model, timeout_seconds):
        return CompletionResult(
            text="""{
  "patch": "diff --git a/src/todos.py b/src/todos.py\\n--- a/src/todos.py\\n+++ b/src/todos.py\\n@@ -1 +1 @@\\n-old\\n+new\\n",
  "changed_files": ["src/todos.py"],
  "summary": "Updated todo file",
  "risks": [],
  "verification_hint": "Run pytest",
  "needs_human_input": false
}"""
        )


def test_execute_task_saves_patch_and_invokes_git_apply(tmp_path, monkeypatch):
    init_state_dir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "todos.py").write_text("old\n", encoding="utf-8")
    config = MMDevConfig(workdir=tmp_path, deepseek_executor_model="executor")
    task = DevTask.model_validate(
        {
            "task_id": "task-001",
            "title": "Edit todos",
            "goal": "Change old to new",
            "context": "",
            "allowed_files": ["src/todos.py"],
            "forbidden_changes": [],
            "acceptance_criteria": ["File updated"],
            "validation_commands": [],
            "complexity": "low",
            "recommended_executor": "cheap",
            "max_attempts": 2,
        }
    )
    calls = []

    def fake_run(args, cwd, text, capture_output, timeout, check):
        calls.append(args)
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[:2] == ["git", "apply"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = execute_task(task, config, FakeClient())
    assert result.changed_files == ["src/todos.py"]
    assert (tmp_path / ".mmdev" / "patches" / "task-001.patch").exists()
    assert any(call[:2] == ["git", "apply"] for call in calls)

