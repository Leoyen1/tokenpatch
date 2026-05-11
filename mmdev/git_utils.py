from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def run_command(args: list[str], cwd: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def is_git_project(workdir: Path, timeout_seconds: int = 10) -> bool:
    result = run_command(["git", "rev-parse", "--is-inside-work-tree"], workdir, timeout_seconds)
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_status_short(workdir: Path, timeout_seconds: int = 10) -> str:
    if not is_git_project(workdir, timeout_seconds):
        return "not a git repository"
    result = run_command(["git", "status", "--short"], workdir, timeout_seconds)
    if result.returncode != 0:
        return result.stderr.strip() or "git status failed"
    return result.stdout.strip() or "clean"


def git_diff(workdir: Path, timeout_seconds: int = 10) -> str:
    if not is_git_project(workdir, timeout_seconds):
        raise GitError("not a git repository")
    result = run_command(["git", "diff", "--no-ext-diff"], workdir, timeout_seconds)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git diff failed"
        raise GitError(message)
    return result.stdout


def git_diff_against_head(workdir: Path, timeout_seconds: int = 10) -> str:
    if not is_git_project(workdir, timeout_seconds):
        raise GitError("not a git repository")
    result = run_command(["git", "diff", "--no-ext-diff", "HEAD"], workdir, timeout_seconds)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git diff HEAD failed"
        raise GitError(message)
    return result.stdout


def apply_patch(workdir: Path, patch_path: Path, timeout_seconds: int) -> None:
    result = run_command(["git", "apply", str(patch_path)], workdir, timeout_seconds)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git apply failed"
        raise GitError(message)
