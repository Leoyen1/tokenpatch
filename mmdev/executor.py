from __future__ import annotations

import json
import time
from pathlib import Path

from mmdev.config import MMDevConfig
from mmdev.git_utils import GitError, apply_patch, is_git_project
from mmdev.json_utils import ModelJSONError, parse_model_json
from mmdev.memory import memory_prompt_block
from mmdev.models.base import CompletionClient
from mmdev.patcher import PatchSafetyError, assert_patch_within_allowed_files, save_patch
from mmdev.schemas import DevTask, ExecutionResult, ExecutorModelOutput, ProjectPlan
from mmdev.state import record_execution, record_execution_failure
from mmdev.usage import append_usage, build_usage


def load_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "executor.md").read_text(encoding="utf-8")


def load_plan(mmdev_dir: Path) -> ProjectPlan:
    path = mmdev_dir / "tasks.json"
    if not path.exists():
        raise FileNotFoundError("missing .mmdev/tasks.json; run mmdev plan first")
    return ProjectPlan.model_validate_json(path.read_text(encoding="utf-8-sig"))


def find_task(plan: ProjectPlan, task_id: str) -> DevTask:
    for task in plan.tasks:
        if task.task_id == task_id:
            return task
    raise KeyError(f"task not found: {task_id}")


def execute_task(task: DevTask, config: MMDevConfig, client: CompletionClient, *, apply: bool = True) -> ExecutionResult:
    if task.complexity != "low" or task.recommended_executor != "cheap":
        raise ValueError("Phase 1-3 only supports low complexity tasks recommended for cheap executor")
    executor_model = config.executor_model
    if not executor_model:
        raise ValueError("executor model is required")
    if apply and not is_git_project(config.workdir, config.command_timeout_seconds):
        raise GitError("mmdev run requires a Git project before applying patches")

    prompt = build_executor_prompt(task, config.workdir, config.mmdev_dir)
    last_error: Exception | None = None
    output: ExecutorModelOutput | None = None
    for _ in range(2):
        started_at = time.perf_counter()
        result = client.complete(
            prompt=prompt,
            model=executor_model,
            timeout_seconds=config.request_timeout_seconds,
        )
        append_usage(
            config.mmdev_dir,
            build_usage(
                model=executor_model,
                prompt=prompt,
                result=result,
                purpose="execute",
                started_at=started_at,
                config=config,
            ),
        )
        try:
            output = parse_model_json(result.text, ExecutorModelOutput)
            break
        except ModelJSONError as exc:
            last_error = exc
            prompt += "\n\nYour previous response failed schema validation. Return only corrected JSON."
    if output is None:
        error = ModelJSONError(f"executor returned invalid JSON twice: {last_error}")
        record_execution_failure(config.mmdev_dir, task, type(error).__name__, str(error))
        raise error
    if output.needs_human_input:
        result = ExecutionResult(
            task_id=task.task_id,
            changed_files=[],
            patch_path="",
            summary=output.summary or "executor requested human input",
            known_risks=output.risks,
            needs_human_input=True,
        )
        record_execution(config.mmdev_dir, task, result)
        return result

    try:
        changed_files = assert_patch_within_allowed_files(output.patch, task.allowed_files)
        patch_path = save_patch(config.mmdev_dir, task.task_id, output.patch)
        if apply:
            apply_patch(config.workdir, patch_path, config.command_timeout_seconds)
    except (PatchSafetyError, GitError) as exc:
        record_execution_failure(config.mmdev_dir, task, type(exc).__name__, str(exc))
        raise
    result = ExecutionResult(
        task_id=task.task_id,
        changed_files=changed_files,
        patch_path=display_patch_path(patch_path, config.workdir),
        summary=output.summary,
        known_risks=output.risks,
        needs_human_input=False,
    )
    record_execution(config.mmdev_dir, task, result)
    return result


def display_patch_path(patch_path: Path, workdir: Path) -> str:
    try:
        return str(patch_path.relative_to(workdir))
    except ValueError:
        return str(patch_path)


def build_executor_prompt(task: DevTask, workdir: Path, mmdev_dir: Path | None = None) -> str:
    snippets = collect_allowed_file_snippets(task, workdir)
    prompt = (
        load_prompt()
        .replace("__TASK_JSON__", json.dumps(task.model_dump(), ensure_ascii=False, indent=2))
        .replace("__FILE_SNIPPETS__", snippets)
    )
    if mmdev_dir is not None:
        memory = memory_prompt_block(mmdev_dir)
        if memory:
            prompt += "\n\n" + memory
    return prompt


def collect_allowed_file_snippets(task: DevTask, workdir: Path, max_chars: int = 8000) -> str:
    chunks: list[str] = []
    budget = max_chars
    for file_name in task.allowed_files:
        path = workdir / file_name
        if not path.exists() or not path.is_file():
            chunks.append(f"### {file_name}\n<missing>\n")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        excerpt = text[:budget]
        budget -= len(excerpt)
        chunks.append(f"### {file_name}\n```\n{excerpt}\n```\n")
        if budget <= 0:
            break
    return "\n".join(chunks)
