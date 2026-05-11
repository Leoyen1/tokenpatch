import pytest
from pydantic import ValidationError

from mmdev.schemas import DevTask, ProjectPlan


def valid_task(**overrides):
    data = {
        "task_id": "task-001",
        "title": "Add filter",
        "goal": "Add a completed filter",
        "context": "Todo app",
        "allowed_files": ["src/todos.py"],
        "forbidden_changes": ["database schema"],
        "acceptance_criteria": ["Filter works"],
        "validation_commands": ["pytest"],
        "complexity": "low",
        "recommended_executor": "cheap",
        "max_attempts": 2,
    }
    data.update(overrides)
    return data


def test_project_plan_accepts_valid_task():
    plan = ProjectPlan.model_validate(
        {
            "project_summary": "sample",
            "assumptions": [],
            "risks": [],
            "tasks": [valid_task()],
        }
    )
    assert plan.tasks[0].task_id == "task-001"


def test_task_rejects_invalid_complexity():
    with pytest.raises(ValidationError):
        DevTask.model_validate(valid_task(complexity="tiny"))


def test_task_rejects_parent_paths():
    with pytest.raises(ValidationError):
        DevTask.model_validate(valid_task(allowed_files=["../secret.py"]))

