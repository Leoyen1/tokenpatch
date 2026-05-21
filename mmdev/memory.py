from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from mmdev.checkpoint import list_checkpoints
from mmdev.config import MMDevConfig, init_state_dir
from mmdev.git_utils import is_git_project, run_command
from mmdev.schemas import ProjectPlan
from mmdev.state import connect, task_statuses


MEMORY_JSON = "project-memory.json"
MEMORY_MD = "project-memory.md"
MEMORY_PROMPT_LIMIT = 6000


class ProjectMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str
    project_summary: str = ""
    known_commands: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    recent_tasks: list[dict[str, str]] = Field(default_factory=list)
    failed_attempts: list[dict[str, str]] = Field(default_factory=list)
    approved_patterns: list[str] = Field(default_factory=list)
    token_savings_notes: list[str] = Field(default_factory=list)


def refresh_memory(config: MMDevConfig) -> ProjectMemory:
    init_state_dir(config.workdir)
    memory = build_memory(config)
    memory_dir(config.mmdev_dir).mkdir(parents=True, exist_ok=True)
    memory_json_path(config.mmdev_dir).write_text(
        json.dumps(memory.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    memory_markdown_path(config.mmdev_dir).write_text(render_memory_markdown(memory), encoding="utf-8")
    return memory


def load_memory(mmdev_dir: Path) -> ProjectMemory | None:
    path = memory_json_path(mmdev_dir)
    if not path.exists():
        return None
    return ProjectMemory.model_validate_json(path.read_text(encoding="utf-8-sig"))


def memory_prompt_block(mmdev_dir: Path, max_chars: int = MEMORY_PROMPT_LIMIT) -> str:
    memory = load_memory(mmdev_dir)
    if memory is None:
        return ""
    text = render_memory_markdown(memory)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[Memory truncated]\n"
    return "## tokenpatch Project Memory Pack\n\n" + text


def build_memory(config: MMDevConfig) -> ProjectMemory:
    plan = try_load_plan(config.mmdev_dir)
    statuses = task_statuses(config.mmdev_dir)
    metrics_summary = try_metrics_summary(config.mmdev_dir)
    checkpoints = list_checkpoints(config.mmdev_dir)[:5]
    tracked_files = list_tracked_files(config)[:80]

    key_files = ordered_unique(
        [file_name for task in (plan.tasks if plan else []) for file_name in task.allowed_files]
        + tracked_files[:30]
    )[:50]
    known_commands = ordered_unique(
        [cmd for task in (plan.tasks if plan else []) for cmd in task.validation_commands]
        + infer_known_commands(tracked_files)
    )
    recent_tasks = [
        {
            "task_id": str(row.get("task_id", "")),
            "title": str(row.get("title", "")),
            "status": str(row.get("status", "")),
        }
        for row in statuses[-10:]
    ]
    failed_attempts = [
        item
        for item in recent_tasks
        if item["status"] in {"validation-failed", "review-retry-cheap", "review-escalate-strong", "failed"}
    ]
    approved_patterns = [
        f"{item['task_id']}: {item['title']}"
        for item in recent_tasks
        if item["status"] == "approved"
    ]

    notes = [
        "Memory Pack is deterministic and does not call a model.",
        "Use this summary instead of repeatedly sending broad project context.",
    ]
    if metrics_summary:
        notes.append(
            "Current recorded model usage: "
            + f"calls={metrics_summary.get('model_calls', 0)}, "
            + f"input={metrics_summary.get('input_tokens', 0)}, output={metrics_summary.get('output_tokens', 0)}."
        )
    if checkpoints:
        notes.append(f"Safe Mode checkpoints available: {len(checkpoints)} recent restore points.")

    project_summary = plan.project_summary if plan and plan.project_summary else summarize_project_root(config, tracked_files)
    return ProjectMemory(
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        project_summary=project_summary,
        known_commands=known_commands,
        key_files=key_files,
        recent_tasks=recent_tasks,
        failed_attempts=failed_attempts,
        approved_patterns=approved_patterns,
        token_savings_notes=notes,
    )


def render_memory_markdown(memory: ProjectMemory) -> str:
    lines = [
        "# Project Memory Pack",
        "",
        f"Generated: {memory.generated_at}",
        "",
        "## Project Summary",
        "",
        memory.project_summary or "<empty>",
        "",
        "## Known Commands",
        "",
    ]
    lines.extend(f"- `{cmd}`" for cmd in memory.known_commands) if memory.known_commands else lines.append("- <none>")
    lines.extend(["", "## Key Files", ""])
    lines.extend(f"- `{file_name}`" for file_name in memory.key_files) if memory.key_files else lines.append("- <none>")
    lines.extend(["", "## Recent Tasks", ""])
    if memory.recent_tasks:
        lines.extend(f"- {task['task_id']} [{task['status']}]: {task['title']}" for task in memory.recent_tasks)
    else:
        lines.append("- <none>")
    lines.extend(["", "## Failed Attempts To Avoid Repeating", ""])
    if memory.failed_attempts:
        lines.extend(f"- {task['task_id']} [{task['status']}]: {task['title']}" for task in memory.failed_attempts)
    else:
        lines.append("- <none>")
    lines.extend(["", "## Approved Patterns", ""])
    lines.extend(f"- {item}" for item in memory.approved_patterns) if memory.approved_patterns else lines.append("- <none>")
    lines.extend(["", "## Token Savings Notes", ""])
    lines.extend(f"- {note}" for note in memory.token_savings_notes)
    return "\n".join(lines).rstrip() + "\n"


def try_load_plan(mmdev_dir: Path):
    path = mmdev_dir / "tasks.json"
    if not path.exists():
        return None
    try:
        return ProjectPlan.model_validate_json(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def try_metrics_summary(mmdev_dir: Path) -> dict | None:
    try:
        with connect(mmdev_dir) as conn:
            row = conn.execute(
                """
                select count(*) as model_calls,
                       coalesce(sum(input_tokens), 0) as input_tokens,
                       coalesce(sum(output_tokens), 0) as output_tokens
                from model_usage
                """
            ).fetchone()
        return dict(row) if row is not None else None
    except Exception:
        return None


def list_tracked_files(config: MMDevConfig) -> list[str]:
    if not is_git_project(config.workdir, config.command_timeout_seconds):
        return []
    result = run_command(["git", "ls-files"], config.workdir, config.command_timeout_seconds)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip() and not line.startswith(".mmdev/")]


def infer_known_commands(tracked_files: list[str]) -> list[str]:
    commands: list[str] = []
    names = set(tracked_files)
    if "pyproject.toml" in names or any(name.startswith("tests/") for name in names):
        commands.append("python -m pytest")
    if "package.json" in names:
        commands.append("npm test")
        commands.append("npm run build")
    return commands


def summarize_project_root(config: MMDevConfig, tracked_files: list[str]) -> str:
    entries = []
    for path in sorted(config.workdir.iterdir(), key=lambda item: item.name.lower()):
        if path.name in {".git", ".mmdev"}:
            continue
        entries.append(path.name + ("/" if path.is_dir() else ""))
        if len(entries) >= 40:
            break
    return "Project root entries:\n" + "\n".join(entries) + f"\nTracked files: {len(tracked_files)}"


def ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def memory_dir(mmdev_dir: Path) -> Path:
    return mmdev_dir / "memory"


def memory_json_path(mmdev_dir: Path) -> Path:
    return memory_dir(mmdev_dir) / MEMORY_JSON


def memory_markdown_path(mmdev_dir: Path) -> Path:
    return memory_dir(mmdev_dir) / MEMORY_MD
