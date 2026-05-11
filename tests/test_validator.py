import subprocess

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.schemas import DevTask
from mmdev.validator import read_validation_result, validate_task, write_validation_result


def task_with_commands(commands):
    return DevTask.model_validate(
        {
            "task_id": "task-001",
            "title": "Validate",
            "goal": "Run commands",
            "context": "",
            "allowed_files": ["src/todos.py"],
            "forbidden_changes": [],
            "acceptance_criteria": ["Commands pass"],
            "validation_commands": commands,
            "complexity": "low",
            "recommended_executor": "cheap",
            "max_attempts": 2,
        }
    )


def test_validate_task_records_pass_and_failure(tmp_path, monkeypatch):
    config = MMDevConfig(workdir=tmp_path, command_timeout_seconds=5)
    task = task_with_commands(["ok", "fail"])

    def fake_run(command, cwd, shell, text, capture_output, timeout, check):
        if command == "ok":
            return subprocess.CompletedProcess(command, 0, "passed", "")
        return subprocess.CompletedProcess(command, 2, "", "failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = validate_task(task, config)
    assert result.passed is False
    assert [item.exit_code for item in result.command_results] == [0, 2]


def test_validation_result_round_trips(tmp_path):
    init_state_dir(tmp_path)
    config = MMDevConfig(workdir=tmp_path)
    result = validate_task(task_with_commands([]), config)
    write_validation_result(config.mmdev_dir, result)
    loaded = read_validation_result(config.mmdev_dir, "task-001")
    assert loaded.passed is True

