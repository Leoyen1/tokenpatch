from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mmdev.config import MMDevConfig  # noqa: E402
from mmdev.isolation import export_worktree_diff  # noqa: E402
from mmdev.models.base import CompletionResult  # noqa: E402
from mmdev.workflow import run_auto  # noqa: E402


class FakePlanner:
    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        return CompletionResult(
            text="""{
  "project_summary": "Small Python todo app.",
  "assumptions": [
    "The completed filter should be optional."
  ],
  "risks": [],
  "tasks": [{
    "task_id": "task-001",
    "title": "Add optional completed filter",
    "goal": "Allow list_todos to filter by completed status while preserving default behavior.",
    "context": "todo_app/todos.py exposes list_todos and tests/test_todos.py covers behavior.",
    "allowed_files": ["todo_app/todos.py", "tests/test_todos.py"],
    "forbidden_changes": ["Package metadata", "Persistent storage"],
    "acceptance_criteria": [
      "Calling list_todos(todos) returns all todos.",
      "Calling list_todos(todos, completed=true) returns only completed todos.",
      "Calling list_todos(todos, completed=false) returns only incomplete todos.",
      "python -m pytest passes."
    ],
    "validation_commands": ["python -m pytest"],
    "complexity": "low",
    "recommended_executor": "cheap",
    "max_attempts": 2
  }]
}""",
            input_tokens=500,
            output_tokens=300,
        )


class FakeExecutor:
    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        return CompletionResult(
            text="""{
  "patch": "diff --git a/tests/test_todos.py b/tests/test_todos.py\\nindex 09d4bee..7e77ac4 100644\\n--- a/tests/test_todos.py\\n+++ b/tests/test_todos.py\\n@@ -9,3 +9,20 @@ def test_list_todos_returns_all_items():\\n \\n     assert list_todos(todos) == todos\\n \\n+\\n+def test_list_todos_filters_completed_items():\\n+    todos = [\\n+        Todo(id=1, title=\\"Write spec\\", completed=True),\\n+        Todo(id=2, title=\\"Build CLI\\", completed=False),\\n+    ]\\n+\\n+    assert list_todos(todos, completed=True) == [todos[0]]\\n+\\n+\\n+def test_list_todos_filters_incomplete_items():\\n+    todos = [\\n+        Todo(id=1, title=\\"Write spec\\", completed=True),\\n+        Todo(id=2, title=\\"Build CLI\\", completed=False),\\n+    ]\\n+\\n+    assert list_todos(todos, completed=False) == [todos[1]]\\ndiff --git a/todo_app/todos.py b/todo_app/todos.py\\nindex c63cbab..785f1f4 100644\\n--- a/todo_app/todos.py\\n+++ b/todo_app/todos.py\\n@@ -10,6 +10,7 @@ class Todo:\\n     completed: bool = False\\n \\n \\n-def list_todos(todos: list[Todo]) -> list[Todo]:\\n-    return list(todos)\\n-\\n+def list_todos(todos: list[Todo], completed: bool | None = None) -> list[Todo]:\\n+    if completed is None:\\n+        return list(todos)\\n+    return [todo for todo in todos if todo.completed is completed]\\n",
  "changed_files": ["todo_app/todos.py", "tests/test_todos.py"],
  "summary": "Added optional completed filter and tests.",
  "risks": [],
  "verification_hint": "Run python -m pytest",
  "needs_human_input": false
}""",
            input_tokens=800,
            output_tokens=600,
        )


class FakeReviewer:
    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        return CompletionResult(
            text="""{
  "task_id": "task-001",
  "approved": true,
  "findings": [],
  "missing_acceptance_criteria": [],
  "recommended_next_action": "approve"
}""",
            input_tokens=700,
            output_tokens=120,
        )


def main() -> int:
    demo_root = REPO_ROOT / ".mmdev-demo" / "todo-app"
    if demo_root.exists():
        remove_demo_root(demo_root)
    shutil.copytree(
        EXAMPLE_ROOT,
        demo_root,
        ignore=shutil.ignore_patterns(".git", ".mmdev", ".pytest_cache", "__pycache__"),
    )
    run(["git", "init"], demo_root)
    run(["git", "config", "user.email", "demo@example.com"], demo_root)
    run(["git", "config", "user.name", "MMDev Demo"], demo_root)
    run(["git", "add", "."], demo_root)
    run(["git", "commit", "-m", "initial todo app"], demo_root)

    config = MMDevConfig(
        workdir=demo_root,
        openai_planner_model="fake-planner",
        openai_reviewer_model="fake-reviewer",
        deepseek_executor_model="fake-executor",
        command_timeout_seconds=60,
        planner_input_cost_per_million=10.0,
        planner_output_cost_per_million=20.0,
        reviewer_input_cost_per_million=10.0,
        reviewer_output_cost_per_million=20.0,
        executor_input_cost_per_million=1.0,
        executor_output_cost_per_million=2.0,
        baseline_strong_input_cost_per_million=10.0,
        baseline_strong_output_cost_per_million=20.0,
    )
    write_demo_config(config)
    result = run_auto(
        "为 todo 列表增加按 completed 状态筛选",
        config,
        FakePlanner(),
        FakeExecutor(),
        FakeReviewer(),
        isolation="worktree",
    )
    if not result.tasks or result.tasks[0].final_status != "approved":
        print(result.model_dump_json(indent=2))
        raise RuntimeError("demo workflow did not produce an approved task")
    patch_path = export_worktree_diff(config, "task-001")
    print(result.model_dump_json(indent=2))
    print(f"Demo root: {demo_root}")
    print(f"Approved patch: {patch_path}")
    print(f"Final report: {demo_root / '.mmdev' / 'reports' / 'final-report.md'}")
    return 0


def write_demo_config(config: MMDevConfig) -> None:
    init_dir = config.mmdev_dir
    init_dir.mkdir(parents=True, exist_ok=True)
    (init_dir / "config.toml").write_text(
        "\n".join(
            [
                'openai_planner_model = "fake-planner"',
                'openai_reviewer_model = "fake-reviewer"',
                'deepseek_executor_model = "fake-executor"',
                "planner_input_cost_per_million = 10.0",
                "planner_output_cost_per_million = 20.0",
                "reviewer_input_cost_per_million = 10.0",
                "reviewer_output_cost_per_million = 20.0",
                "executor_input_cost_per_million = 1.0",
                "executor_output_cost_per_million = 2.0",
                "baseline_strong_input_cost_per_million = 10.0",
                "baseline_strong_output_cost_per_million = 20.0",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run(args: list[str], cwd: Path) -> None:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"command failed: {args}")


def remove_demo_root(demo_root: Path) -> None:
    if (demo_root / ".git").exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(demo_root / ".mmdev" / "worktrees" / "task-001")],
            cwd=demo_root,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    shutil.rmtree(demo_root, onexc=make_writable)


def make_writable(function, path, excinfo) -> None:
    Path(path).chmod(0o700)
    function(path)


if __name__ == "__main__":
    raise SystemExit(main())
