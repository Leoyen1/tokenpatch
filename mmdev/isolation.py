from __future__ import annotations

import shutil
from pathlib import Path

from mmdev.config import MMDevConfig
from mmdev.executor import load_plan, find_task
from mmdev.git_utils import GitError, apply_patch, git_diff_against_head, is_git_project, run_command
from mmdev.patcher import assert_patch_within_allowed_files


class IsolationError(RuntimeError):
    pass


def worktree_path(config: MMDevConfig, task_id: str) -> Path:
    safe_task_id = "".join(char if char.isalnum() or char in "-_" else "-" for char in task_id)
    return config.mmdev_dir / "worktrees" / safe_task_id


def prepare_worktree(config: MMDevConfig, task_id: str) -> MMDevConfig:
    if not is_git_project(config.workdir, config.command_timeout_seconds):
        raise IsolationError("worktree isolation requires a Git project")
    target = worktree_path(config, task_id)
    if target.exists():
        cleanup_worktree(config, task_id)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    branch = f"mmdev/{task_id}"
    create = run_command(
        ["git", "worktree", "add", "-B", branch, str(target), "HEAD"],
        config.workdir,
        config.command_timeout_seconds,
    )
    if create.returncode != 0:
        message = create.stderr.strip() or create.stdout.strip() or "git worktree add failed"
        raise IsolationError(message)
    return config.model_copy(update={"workdir": target, "state_dir": config.mmdev_dir})


def cleanup_worktree(config: MMDevConfig, task_id: str) -> None:
    target = worktree_path(config, task_id)
    if not target.exists():
        return
    remove = run_command(
        ["git", "worktree", "remove", "--force", str(target)],
        config.workdir,
        config.command_timeout_seconds,
    )
    if remove.returncode != 0:
        raise GitError(remove.stderr.strip() or remove.stdout.strip() or "git worktree remove failed")


def export_worktree_diff(config: MMDevConfig, task_id: str, *, apply_to_main: bool = False) -> Path:
    target = worktree_path(config, task_id)
    if not target.exists():
        raise IsolationError(f"missing worktree for {task_id}: {target}")
    plan = load_plan(config.mmdev_dir)
    task = find_task(plan, task_id)
    diff_text = git_diff_against_head(target, config.command_timeout_seconds)
    assert_patch_within_allowed_files(diff_text, task.allowed_files)
    if not diff_text.strip():
        raise IsolationError(f"worktree has no diff to export for {task_id}")

    patch_path = config.mmdev_dir / "patches" / f"{task_id}-approved.patch"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(diff_text, encoding="utf-8")
    if apply_to_main:
        apply_patch(config.workdir, patch_path, config.command_timeout_seconds)
    return patch_path
