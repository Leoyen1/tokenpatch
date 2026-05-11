import subprocess

from mmdev.config import MMDevConfig
from mmdev.models.base import CompletionResult
from mmdev.workflow import run_auto


class FakePlanner:
    def complete(self, *, prompt, model, timeout_seconds):
        return CompletionResult(
            text="""{
  "project_summary": "sample",
  "assumptions": [],
  "risks": [],
  "tasks": [{
    "task_id": "task-001",
    "title": "Update todos",
    "goal": "Update todo file",
    "context": "",
    "allowed_files": ["src/todos.py"],
    "forbidden_changes": [],
    "acceptance_criteria": ["File is updated"],
    "validation_commands": ["python -c \\"import pathlib; assert pathlib.Path('src/todos.py').read_text() == 'new\\\\n'\\""],
    "complexity": "low",
    "recommended_executor": "cheap",
    "max_attempts": 2
  }]
}"""
        )


class FakeExecutor:
    def complete(self, *, prompt, model, timeout_seconds):
        return CompletionResult(
            text="""{
  "patch": "diff --git a/src/todos.py b/src/todos.py\\n--- a/src/todos.py\\n+++ b/src/todos.py\\n@@ -1 +1 @@\\n-old\\n+new\\n",
  "changed_files": ["src/todos.py"],
  "summary": "Updated todo file",
  "risks": [],
  "verification_hint": "Run validation",
  "needs_human_input": false
}"""
        )


class FakeReviewer:
    def complete(self, *, prompt, model, timeout_seconds):
        return CompletionResult(
            text="""{
  "task_id": "task-001",
  "approved": true,
  "findings": [],
  "missing_acceptance_criteria": [],
  "recommended_next_action": "approve"
}"""
        )


def test_run_auto_executes_full_local_workflow(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "todos.py").write_text("old\n", encoding="utf-8")
    config = MMDevConfig(
        workdir=tmp_path,
        openai_planner_model="planner",
        openai_reviewer_model="reviewer",
        deepseek_executor_model="executor",
        command_timeout_seconds=30,
    )

    result = run_auto("update todo file", config, FakePlanner(), FakeExecutor(), FakeReviewer())

    assert len(result.tasks) == 1
    assert result.tasks[0].validation.passed is True
    assert result.tasks[0].review.approved is True
    assert (tmp_path / ".mmdev" / "tasks.json").exists()
    assert (tmp_path / ".mmdev" / "reports" / "task-001-validation.json").exists()
    assert (tmp_path / ".mmdev" / "reports" / "task-001-review.json").exists()
    assert (tmp_path / ".mmdev" / "reports" / "final-report.md").exists()


class RetryPlanner(FakePlanner):
    pass


class RetryExecutor:
    def __init__(self):
        self.calls = 0

    def complete(self, *, prompt, model, timeout_seconds):
        self.calls += 1
        if self.calls == 1:
            patch = "diff --git a/src/todos.py b/src/todos.py\\n--- a/src/todos.py\\n+++ b/src/todos.py\\n@@ -1 +1 @@\\n-old\\n+bad\\n"
        else:
            patch = "diff --git a/src/todos.py b/src/todos.py\\n--- a/src/todos.py\\n+++ b/src/todos.py\\n@@ -1 +1 @@\\n-bad\\n+new\\n"
        return CompletionResult(
            text=f"""{{
  "patch": "{patch}",
  "changed_files": ["src/todos.py"],
  "summary": "Updated todo file",
  "risks": [],
  "verification_hint": "Run validation",
  "needs_human_input": false
}}"""
        )


class RetryReviewer:
    def __init__(self):
        self.calls = 0

    def complete(self, *, prompt, model, timeout_seconds):
        self.calls += 1
        action = "retry-cheap" if self.calls == 1 else "approve"
        approved = "false" if self.calls == 1 else "true"
        return CompletionResult(
            text=f"""{{
  "task_id": "task-001",
  "approved": {approved},
  "findings": [],
  "missing_acceptance_criteria": [],
  "recommended_next_action": "{action}"
}}"""
        )


def test_run_auto_retries_when_review_recommends_retry_cheap(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "todos.py").write_text("old\n", encoding="utf-8")
    config = MMDevConfig(
        workdir=tmp_path,
        openai_planner_model="planner",
        openai_reviewer_model="reviewer",
        deepseek_executor_model="executor",
        command_timeout_seconds=30,
    )
    executor = RetryExecutor()
    reviewer = RetryReviewer()

    result = run_auto("update todo file", config, RetryPlanner(), executor, reviewer)

    assert result.tasks[0].attempts == 2
    assert result.tasks[0].final_status == "approved"
    assert result.tasks[0].next_action == "approve"
    assert executor.calls == 2
    assert reviewer.calls == 2
    assert (src / "todos.py").read_text(encoding="utf-8") == "new\n"


def test_run_auto_worktree_isolation_keeps_main_worktree_unchanged(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "todos.py").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, text=True, capture_output=True, timeout=10, check=True)
    config = MMDevConfig(
        workdir=tmp_path,
        openai_planner_model="planner",
        openai_reviewer_model="reviewer",
        deepseek_executor_model="executor",
        command_timeout_seconds=30,
    )

    result = run_auto("update todo file", config, FakePlanner(), FakeExecutor(), FakeReviewer(), isolation="worktree")

    assert result.tasks[0].final_status == "approved"
    assert (src / "todos.py").read_text(encoding="utf-8") == "old\n"
    worktree_file = tmp_path / ".mmdev" / "worktrees" / "task-001" / "src" / "todos.py"
    assert worktree_file.read_text(encoding="utf-8") == "new\n"
