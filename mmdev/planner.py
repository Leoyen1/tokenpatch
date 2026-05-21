from __future__ import annotations

import json
import time
from pathlib import Path

from mmdev.config import MMDevConfig
from mmdev.cost import estimate_tokens
from mmdev.json_utils import ModelJSONError, parse_model_json
from mmdev.memory import memory_prompt_block
from mmdev.models.base import CompletionClient
from mmdev.schemas import ProjectPlan
from mmdev.state import record_plan
from mmdev.usage import append_usage, build_usage


def load_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "planner.md").read_text(encoding="utf-8")


def build_project_summary(workdir: Path) -> str:
    names = []
    for path in sorted(workdir.iterdir(), key=lambda item: item.name.lower()):
        if path.name in {".git", ".mmdev"}:
            continue
        names.append(path.name + ("/" if path.is_dir() else ""))
        if len(names) >= 80:
            break
    return "Project root entries:\n" + "\n".join(names)


def create_plan(requirement: str, config: MMDevConfig, client: CompletionClient) -> ProjectPlan:
    model = config.planner_model
    if not model:
        if config.normalized_strong_model_provider == "claude":
            raise ValueError("CLAUDE_PLANNER_MODEL or claude_planner_model is required")
        raise ValueError("OPENAI_PLANNER_MODEL or openai_planner_model is required")
    prompt = (
        load_prompt()
        .replace("__REQUIREMENT__", requirement)
        .replace("__PROJECT_SUMMARY__", build_project_summary(config.workdir))
    )
    memory = memory_prompt_block(config.mmdev_dir)
    if memory:
        prompt += "\n\n" + memory
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
                purpose="plan",
                started_at=started_at,
                config=config,
            ),
        )
        try:
            return parse_model_json(result.text, ProjectPlan)
        except ModelJSONError as exc:
            last_error = exc
            prompt += "\n\nYour previous response failed schema validation. Return only corrected JSON."
    raise ModelJSONError(f"planner returned invalid JSON twice: {last_error}")


def write_plan(mmdev_dir: Path, plan: ProjectPlan) -> Path:
    path = mmdev_dir / "tasks.json"
    path.write_text(
        json.dumps(plan.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    record_plan(mmdev_dir, plan)
    return path


def estimated_plan_tokens(requirement: str, plan: ProjectPlan) -> tuple[int, int]:
    return estimate_tokens(requirement), estimate_tokens(plan.model_dump_json())
