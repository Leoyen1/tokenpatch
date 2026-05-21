from __future__ import annotations

import json
import time
from pathlib import Path

from mmdev.config import MMDevConfig
from mmdev.git_utils import git_diff
from mmdev.json_utils import ModelJSONError, parse_model_json
from mmdev.memory import memory_prompt_block
from mmdev.models.base import CompletionClient
from mmdev.schemas import DevTask, ReviewResult, ValidationResult
from mmdev.state import record_review
from mmdev.usage import append_usage, build_usage


def load_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "reviewer.md").read_text(encoding="utf-8")


def review_task(task: DevTask, validation: ValidationResult, config: MMDevConfig, client: CompletionClient) -> ReviewResult:
    model = config.reviewer_model
    if not model:
        if config.normalized_strong_model_provider == "claude":
            raise ValueError("CLAUDE_REVIEWER_MODEL or claude_reviewer_model is required")
        raise ValueError("OPENAI_REVIEWER_MODEL or openai_reviewer_model is required")
    diff_text = git_diff(config.workdir, config.command_timeout_seconds)
    prompt = build_reviewer_prompt(task, validation, diff_text, config.workdir, config.mmdev_dir)
    last_error: Exception | None = None
    for _ in range(2):
        started_at = time.perf_counter()
        result = client.complete(
            prompt=prompt,
            model=model,
            timeout_seconds=config.request_timeout_seconds,
        )
        append_usage(
            config.mmdev_dir,
            build_usage(
                model=model,
                prompt=prompt,
                result=result,
                purpose="review",
                started_at=started_at,
                config=config,
            ),
        )
        try:
            return parse_model_json(result.text, ReviewResult)
        except ModelJSONError as exc:
            last_error = exc
            prompt += "\n\nYour previous response failed schema validation. Return only corrected JSON."
    raise ModelJSONError(f"reviewer returned invalid JSON twice: {last_error}")


def build_reviewer_prompt(
    task: DevTask,
    validation: ValidationResult,
    diff_text: str,
    workdir: Path,
    mmdev_dir: Path | None = None,
) -> str:
    prompt = (
        load_prompt()
        .replace("__TASK_JSON__", json.dumps(task.model_dump(), ensure_ascii=False, indent=2))
        .replace("__VALIDATION_JSON__", json.dumps(validation.model_dump(), ensure_ascii=False, indent=2))
        .replace("__GIT_DIFF__", diff_text)
        .replace("__FILE_SNIPPETS__", collect_reviewer_snippets(task, workdir))
    )
    if mmdev_dir is not None:
        memory = memory_prompt_block(mmdev_dir)
        if memory:
            prompt += "\n\n" + memory
    return prompt


def collect_reviewer_snippets(task: DevTask, workdir: Path, max_chars: int = 8000) -> str:
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


def write_review_result(mmdev_dir: Path, result: ReviewResult) -> Path:
    path = mmdev_dir / "reports" / f"{result.task_id}-review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    record_review(mmdev_dir, result)
    return path
