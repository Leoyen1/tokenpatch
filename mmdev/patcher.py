from __future__ import annotations

from pathlib import Path, PurePosixPath


class PatchSafetyError(ValueError):
    pass


def normalize_patch_path(path: str) -> str | None:
    cleaned = path.strip()
    if cleaned == "/dev/null":
        return None
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    cleaned = cleaned.replace("\\", "/")
    pure = PurePosixPath(cleaned)
    if pure.is_absolute() or ".." in pure.parts:
        raise PatchSafetyError(f"unsafe patch path: {path}")
    return str(pure)


def changed_files_from_patch(patch_text: str) -> list[str]:
    changed: set[str] = set()
    for raw_line in patch_text.splitlines():
        if raw_line.startswith("+++ ") or raw_line.startswith("--- "):
            value = raw_line[4:].split("\t", 1)[0].strip()
            normalized = normalize_patch_path(value)
            if normalized:
                changed.add(normalized)
    return sorted(changed)


def assert_patch_within_allowed_files(patch_text: str, allowed_files: list[str]) -> list[str]:
    changed = changed_files_from_patch(patch_text)
    allowed = {normalize_patch_path(file_name) for file_name in allowed_files}
    disallowed = [file_name for file_name in changed if file_name not in allowed]
    if disallowed:
        raise PatchSafetyError(
            "patch modifies files outside allowed_files: " + ", ".join(disallowed)
        )
    if not changed:
        raise PatchSafetyError("patch does not modify any files")
    return changed


def save_patch(mmdev_dir: Path, task_id: str, patch_text: str) -> Path:
    patch_dir = mmdev_dir / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"{task_id}.patch"
    patch_path.write_text(patch_text, encoding="utf-8")
    return patch_path

