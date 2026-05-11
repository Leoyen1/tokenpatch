import subprocess

from mmdev.config import MMDevConfig
from mmdev.models.base import CompletionResult
from mmdev.reviewer import review_task
from mmdev.schemas import DevTask, ValidationResult


class FakeClient:
    def complete(self, *, prompt, model, timeout_seconds):
        assert "Git diff:" in prompt
        return CompletionResult(
            text="""{
  "task_id": "task-001",
  "approved": true,
  "findings": [],
  "missing_acceptance_criteria": [],
  "recommended_next_action": "approve"
}"""
        )


def make_task():
    return DevTask.model_validate(
        {
            "task_id": "task-001",
            "title": "Review",
            "goal": "Review change",
            "context": "",
            "allowed_files": ["src/todos.py"],
            "forbidden_changes": [],
            "acceptance_criteria": ["Works"],
            "validation_commands": ["pytest"],
            "complexity": "low",
            "recommended_executor": "cheap",
            "max_attempts": 2,
        }
    )


def test_review_task_uses_validation_and_git_diff(tmp_path, monkeypatch):
    config = MMDevConfig(workdir=tmp_path, openai_reviewer_model="reviewer")
    validation = ValidationResult(task_id="task-001", command_results=[], passed=True)

    def fake_run(args, cwd, text, capture_output, timeout, check):
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        if args[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(args, 0, "diff --git a/src/todos.py b/src/todos.py\n", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = review_task(make_task(), validation, config, FakeClient())
    assert result.approved is True
    assert result.recommended_next_action == "approve"

