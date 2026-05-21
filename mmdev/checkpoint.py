from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.git_utils import GitError, git_diff_against_head, is_git_project, run_command


class CheckpointError(RuntimeError):
    pass


class CheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    created_at: str
    base_head: str
    status_summary: str
    tracked_patch_path: str
    untracked_files: list[str] = Field(default_factory=list)
    source: str = "manual"


def create_checkpoint(config: MMDevConfig, label: str, *, source: str = "manual") -> CheckpointRecord:
    init_state_dir(config.workdir)
    if not is_git_project(config.workdir, config.command_timeout_seconds):
        raise CheckpointError("checkpoint requires a Git project")
    base_head = current_head(config)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    checkpoint_id = unique_checkpoint_id(config.mmdev_dir, label, created_at)
    root = checkpoint_dir(config.mmdev_dir, checkpoint_id)
    root.mkdir(parents=True, exist_ok=False)

    tracked_patch = git_diff_against_head(config.workdir, config.command_timeout_seconds)
    untracked_files = list_untracked_files(config)
    status_summary = git_status(config)

    patch_path = root / "tracked.patch"
    patch_path.write_text(tracked_patch, encoding="utf-8")
    (root / "git-status.txt").write_text(status_summary + "\n", encoding="utf-8")
    (root / "untracked-files.txt").write_text("\n".join(untracked_files) + ("\n" if untracked_files else ""), encoding="utf-8")

    record = CheckpointRecord(
        id=checkpoint_id,
        label=label,
        created_at=created_at,
        base_head=base_head,
        status_summary=status_summary,
        tracked_patch_path=str(patch_path),
        untracked_files=untracked_files,
        source=source,
    )
    write_meta(root, record)
    return record


def list_checkpoints(mmdev_dir: Path) -> list[CheckpointRecord]:
    root = mmdev_dir / "checkpoints"
    if not root.exists():
        return []
    records: list[CheckpointRecord] = []
    for meta in root.glob("*/meta.json"):
        try:
            records.append(CheckpointRecord.model_validate_json(meta.read_text(encoding="utf-8-sig")))
        except Exception:
            continue
    return sorted(records, key=lambda item: item.created_at, reverse=True)


def read_checkpoint(mmdev_dir: Path, checkpoint_id: str) -> CheckpointRecord:
    path = checkpoint_dir(mmdev_dir, checkpoint_id) / "meta.json"
    if not path.exists():
        raise CheckpointError(f"checkpoint not found: {checkpoint_id}")
    return CheckpointRecord.model_validate_json(path.read_text(encoding="utf-8-sig"))


def checkpoint_diff(mmdev_dir: Path, checkpoint_id: str) -> str:
    record = read_checkpoint(mmdev_dir, checkpoint_id)
    path = Path(record.tracked_patch_path)
    if not path.exists():
        raise CheckpointError(f"checkpoint patch missing: {checkpoint_id}")
    return path.read_text(encoding="utf-8-sig")


def restore_checkpoint(
    config: MMDevConfig,
    checkpoint_id: str,
    *,
    yes: bool = False,
    allow_head_mismatch: bool = False,
) -> dict[str, object]:
    record = read_checkpoint(config.mmdev_dir, checkpoint_id)
    if not is_git_project(config.workdir, config.command_timeout_seconds):
        raise CheckpointError("restore requires a Git project")
    head = current_head(config)
    if head != record.base_head and not allow_head_mismatch:
        raise CheckpointError("current HEAD differs from checkpoint base_head; pass --allow-head-mismatch to override")
    if not yes:
        return {"ok": True, "dry_run": True, "checkpoint": record.model_dump(), "message": "dry-run only; pass --yes to restore"}

    pre_restore = create_checkpoint(config, f"pre-restore-{checkpoint_id}", source="pre-restore")
    current_patch = git_diff_against_head(config.workdir, config.command_timeout_seconds)
    current_patch_path = config.mmdev_dir / "checkpoints" / f"{pre_restore.id}-current.patch"
    current_patch_path.write_text(current_patch, encoding="utf-8")

    checkpoint_patch = Path(record.tracked_patch_path)
    try:
        if current_patch.strip():
            apply_git_patch(config, current_patch_path, reverse=True)
        if checkpoint_patch.exists() and checkpoint_patch.read_text(encoding="utf-8-sig").strip():
            apply_git_patch(config, checkpoint_patch, reverse=False)
    except Exception as exc:
        if current_patch.strip():
            apply_git_patch(config, current_patch_path, reverse=False)
        raise CheckpointError(f"restore failed and current diff was restored: {exc}") from exc
    return {"ok": True, "dry_run": False, "checkpoint": record.model_dump(), "pre_restore_checkpoint": pre_restore.model_dump()}


def current_head(config: MMDevConfig) -> str:
    result = run_command(["git", "rev-parse", "--verify", "HEAD"], config.workdir, config.command_timeout_seconds)
    if result.returncode != 0:
        raise CheckpointError(result.stderr.strip() or "checkpoint requires a HEAD commit")
    return result.stdout.strip()


def git_status(config: MMDevConfig) -> str:
    result = run_command(["git", "status", "--short"], config.workdir, config.command_timeout_seconds)
    if result.returncode != 0:
        raise CheckpointError(result.stderr.strip() or "git status failed")
    return result.stdout.strip() or "clean"


def list_untracked_files(config: MMDevConfig) -> list[str]:
    result = run_command(["git", "ls-files", "--others", "--exclude-standard"], config.workdir, config.command_timeout_seconds)
    if result.returncode != 0:
        raise CheckpointError(result.stderr.strip() or "git ls-files failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def apply_git_patch(config: MMDevConfig, patch_path: Path, *, reverse: bool) -> None:
    args = ["git", "apply"]
    if reverse:
        args.append("--reverse")
    args.append(str(patch_path))
    result = run_command(args, config.workdir, config.command_timeout_seconds)
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or result.stdout.strip() or "git apply failed")


def unique_checkpoint_id(mmdev_dir: Path, label: str, created_at: str) -> str:
    stamp = created_at.replace("+00:00", "z").replace(":", "").replace("-", "")
    slug = slugify(label) or "checkpoint"
    base = f"{stamp}-{slug}"[:80]
    candidate = base
    index = 2
    while checkpoint_dir(mmdev_dir, candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def slugify(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip().lower()).strip("-")
    return value[:40]


def checkpoint_dir(mmdev_dir: Path, checkpoint_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", checkpoint_id):
        raise CheckpointError(f"invalid checkpoint id: {checkpoint_id}")
    return mmdev_dir / "checkpoints" / checkpoint_id


def write_meta(root: Path, record: CheckpointRecord) -> None:
    (root / "meta.json").write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
