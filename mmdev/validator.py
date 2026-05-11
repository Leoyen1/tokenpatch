from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mmdev.config import MMDevConfig
from mmdev.schemas import CommandResult, DevTask, ValidationResult
from mmdev.state import record_validation


TAIL_CHARS = 4000


class ValidationCommandError(ValueError):
    pass


def validate_task(task: DevTask, config: MMDevConfig) -> ValidationResult:
    command_results = [
        run_validation_command(command, config.workdir, config.command_timeout_seconds)
        for command in task.validation_commands
    ]
    return ValidationResult(
        task_id=task.task_id,
        command_results=command_results,
        passed=all(result.exit_code == 0 for result in command_results),
    )


def run_validation_command(command: str, workdir: Path, timeout_seconds: int) -> CommandResult:
    if not command.strip():
        raise ValidationCommandError("validation command cannot be empty")
    try:
        completed = subprocess.run(
            command,
            cwd=workdir,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout_tail=tail(completed.stdout),
            stderr_tail=tail(completed.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            exit_code=124,
            stdout_tail=tail(exc.stdout or ""),
            stderr_tail=tail((exc.stderr or "") + f"\nCommand timed out after {timeout_seconds}s"),
        )


def write_validation_result(mmdev_dir: Path, result: ValidationResult) -> Path:
    path = mmdev_dir / "reports" / f"{result.task_id}-validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_validation(mmdev_dir, result)
    return path


def read_validation_result(mmdev_dir: Path, task_id: str) -> ValidationResult:
    path = mmdev_dir / "reports" / f"{task_id}-validation.json"
    if not path.exists():
        raise FileNotFoundError(f"missing validation result for {task_id}; run mmdev validate {task_id} first")
    return ValidationResult.model_validate_json(path.read_text(encoding="utf-8-sig"))


def tail(value: str | bytes, limit: int = TAIL_CHARS) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]
