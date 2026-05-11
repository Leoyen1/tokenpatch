import pytest

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.json_utils import ModelJSONError
from mmdev.models.base import CompletionResult
from mmdev.planner import create_plan, write_plan


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, *, prompt, model, timeout_seconds):
        return CompletionResult(text=self.responses.pop(0))


VALID_PLAN = """{
  "project_summary": "sample",
  "assumptions": [],
  "risks": [],
  "tasks": [{
    "task_id": "task-001",
    "title": "Add filter",
    "goal": "Add a completed filter",
    "context": "Todo app",
    "allowed_files": ["src/todos.py"],
    "forbidden_changes": [],
    "acceptance_criteria": ["Filter works"],
    "validation_commands": ["pytest"],
    "complexity": "low",
    "recommended_executor": "cheap",
    "max_attempts": 2
  }]
}"""


def test_create_plan_retries_invalid_json_and_writes_tasks(tmp_path):
    init_state_dir(tmp_path)
    config = MMDevConfig(workdir=tmp_path, openai_planner_model="planner")
    plan = create_plan("add filter", config, FakeClient(["not json", VALID_PLAN]))
    path = write_plan(config.mmdev_dir, plan)
    assert path.exists()
    assert "task-001" in path.read_text(encoding="utf-8")


def test_create_plan_fails_after_two_bad_responses(tmp_path):
    config = MMDevConfig(workdir=tmp_path, openai_planner_model="planner")
    with pytest.raises(ModelJSONError):
        create_plan("add filter", config, FakeClient(["bad", "still bad"]))

