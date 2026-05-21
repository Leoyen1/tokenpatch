from __future__ import annotations

import subprocess
from pathlib import Path
from dataclasses import dataclass


class GitError(RuntimeError):
    pass


@dataclass
class Hunk:
    old_start: int
    old_lines: list[str]
    new_lines: list[str]


@dataclass
class FilePatch:
    old_path: str | None
    new_path: str | None
    hunks: list[Hunk]


def run_command(args: list[str], cwd: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
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
    if result.returncode == 0:
        return
    message = result.stderr.strip() or result.stdout.strip() or "git apply failed"
    try:
        apply_patch_by_context_search(workdir, patch_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GitError(f"{message}\nfallback context apply failed: {exc}") from exc


def apply_patch_by_context_search(workdir: Path, patch_text: str) -> None:
    file_patches = parse_unified_diff(patch_text)
    if not file_patches:
        raise GitError("patch contains no file hunks")
    for file_patch in file_patches:
        target = file_patch.new_path or file_patch.old_path
        if target is None:
            raise GitError("patch deletes a file; fallback apply does not support deletes")
        path = workdir / target
        if file_patch.old_path is None:
            current_lines: list[str] = []
        else:
            if not path.exists():
                raise GitError(f"target file missing: {target}")
            current_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        cursor = 0
        for hunk in file_patch.hunks:
            index = find_sequence(current_lines, hunk.old_lines, start=max(cursor, hunk.old_start - 3))
            if index is None:
                index = find_sequence(current_lines, hunk.old_lines, start=0)
            if index is None:
                raise GitError(f"hunk context not found in {target}")
            current_lines[index : index + len(hunk.old_lines)] = hunk.new_lines
            cursor = index + len(hunk.new_lines)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(current_lines) + "\n", encoding="utf-8")


def parse_unified_diff(patch_text: str) -> list[FilePatch]:
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    current_hunk: Hunk | None = None
    for raw_line in patch_text.splitlines():
        if raw_line.startswith("diff --git "):
            if current is not None:
                patches.append(current)
            current = FilePatch(old_path=None, new_path=None, hunks=[])
            current_hunk = None
            continue
        if raw_line.startswith("--- "):
            if current is None:
                current = FilePatch(old_path=None, new_path=None, hunks=[])
            current.old_path = normalize_git_diff_path(raw_line[4:])
            continue
        if raw_line.startswith("+++ "):
            if current is None:
                current = FilePatch(old_path=None, new_path=None, hunks=[])
            current.new_path = normalize_git_diff_path(raw_line[4:])
            continue
        if raw_line.startswith("@@ "):
            if current is None:
                raise GitError("hunk found before file header")
            old_start = parse_hunk_old_start(raw_line)
            current_hunk = Hunk(old_start=old_start, old_lines=[], new_lines=[])
            current.hunks.append(current_hunk)
            continue
        if current_hunk is None:
            continue
        if raw_line.startswith("\\ No newline"):
            continue
        prefix = raw_line[:1]
        line = raw_line[1:] if prefix in {" ", "-", "+"} else raw_line
        if prefix == " ":
            current_hunk.old_lines.append(line)
            current_hunk.new_lines.append(line)
        elif prefix == "-":
            current_hunk.old_lines.append(line)
        elif prefix == "+":
            current_hunk.new_lines.append(line)
    if current is not None:
        patches.append(current)
    return [patch for patch in patches if patch.hunks]


def parse_hunk_old_start(line: str) -> int:
    # Example: @@ -3,7 +3,7 @@
    try:
        old_part = line.split(" ", 2)[1]
        old_start = old_part.split(",", 1)[0].lstrip("-")
        return max(int(old_start), 1)
    except Exception as exc:
        raise GitError(f"invalid hunk header: {line}") from exc


def normalize_git_diff_path(value: str) -> str | None:
    path = value.split("\t", 1)[0].strip()
    if path == "/dev/null":
        return None
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    if path.startswith("/") or ".." in Path(path).parts:
        raise GitError(f"unsafe patch path: {value}")
    return path.replace("\\", "/")


def find_sequence(lines: list[str], needle: list[str], *, start: int) -> int | None:
    if not needle:
        return min(max(start, 0), len(lines))
    start = min(max(start, 0), len(lines))
    max_index = len(lines) - len(needle)
    for index in range(start, max_index + 1):
        if lines[index : index + len(needle)] == needle:
            return index
    return None
