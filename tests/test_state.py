from mmdev.config import init_state_dir
from mmdev.schemas import ExecutionResult, ModelUsage, ProjectPlan, ReviewResult, ValidationResult
from mmdev.state import (
    connect,
    record_execution,
    record_execution_failure,
    record_plan,
    record_review,
    record_usage,
    record_validation,
    task_statuses,
)


def make_plan():
    return ProjectPlan.model_validate(
        {
            "project_summary": "sample",
            "assumptions": [],
            "risks": [],
            "tasks": [
                {
                    "task_id": "task-001",
                    "title": "Add filter",
                    "goal": "Add a filter",
                    "context": "",
                    "allowed_files": ["src/todos.py"],
                    "forbidden_changes": [],
                    "acceptance_criteria": ["Works"],
                    "validation_commands": ["pytest"],
                    "complexity": "low",
                    "recommended_executor": "cheap",
                    "max_attempts": 2,
                }
            ],
        }
    )


def test_init_state_dir_creates_sqlite_database(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    assert (mmdev_dir / "state.sqlite").exists()


def test_state_tracks_task_lifecycle_and_usage(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    plan = make_plan()
    task = plan.tasks[0]
    record_plan(mmdev_dir, plan)
    assert task_statuses(mmdev_dir)[0]["status"] == "planned"

    record_execution(
        mmdev_dir,
        task,
        ExecutionResult(
            task_id="task-001",
            changed_files=["src/todos.py"],
            patch_path=".mmdev/patches/task-001.patch",
            summary="done",
        ),
    )
    assert task_statuses(mmdev_dir)[0]["status"] == "executed"

    record_validation(mmdev_dir, ValidationResult(task_id="task-001", command_results=[], passed=True))
    assert task_statuses(mmdev_dir)[0]["status"] == "validated"

    record_review(
        mmdev_dir,
        ReviewResult(
            task_id="task-001",
            approved=True,
            findings=[],
            missing_acceptance_criteria=[],
            recommended_next_action="approve",
        ),
    )
    assert task_statuses(mmdev_dir)[0]["status"] == "approved"

    record_usage(
        mmdev_dir,
        ModelUsage(
            model="planner",
            input_tokens=1,
            output_tokens=2,
            estimated_cost=0,
            duration_ms=3,
            purpose="plan",
        ),
    )
    with connect(mmdev_dir) as conn:
        assert conn.execute("select count(*) from model_usage").fetchone()[0] == 1


def test_state_tracks_execution_failure(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    plan = make_plan()
    task = plan.tasks[0]
    record_plan(mmdev_dir, plan)

    record_execution_failure(mmdev_dir, task, "ModelJSONError", "invalid executor JSON")

    assert task_statuses(mmdev_dir)[0]["status"] == "execution-failed"
    with connect(mmdev_dir) as conn:
        row = conn.execute("select result_json from executions where task_id=?", ("task-001",)).fetchone()
    assert "invalid executor JSON" in row["result_json"]
