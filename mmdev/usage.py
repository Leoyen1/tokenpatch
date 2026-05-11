from __future__ import annotations

import json
import time
from pathlib import Path

from mmdev.config import MMDevConfig
from mmdev.cost import estimate_cost, estimate_tokens
from mmdev.models.base import CompletionResult
from mmdev.schemas import ModelUsage, Purpose
from mmdev.state import record_usage


USAGE_FILE = "model-usage.jsonl"


def build_usage(
    *,
    model: str,
    prompt: str,
    result: CompletionResult,
    purpose: Purpose,
    started_at: float,
    config: MMDevConfig | None = None,
) -> ModelUsage:
    input_tokens = result.input_tokens if result.input_tokens is not None else estimate_tokens(prompt)
    output_tokens = result.output_tokens if result.output_tokens is not None else estimate_tokens(result.text)
    input_rate, output_rate = pricing_for_purpose(config, purpose)
    return ModelUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimate_cost(input_tokens, output_tokens, input_rate, output_rate),
        duration_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
        purpose=purpose,
        charged_credits=result.charged_credits,
        provider_cost=result.provider_cost,
    )


def pricing_for_purpose(config: MMDevConfig | None, purpose: Purpose) -> tuple[float, float]:
    if config is None:
        return 0.0, 0.0
    if purpose == "plan":
        return config.planner_input_cost_per_million, config.planner_output_cost_per_million
    if purpose == "review":
        return config.reviewer_input_cost_per_million, config.reviewer_output_cost_per_million
    if purpose in {"execute", "repair"}:
        return config.executor_input_cost_per_million, config.executor_output_cost_per_million
    return 0.0, 0.0


def append_usage(mmdev_dir: Path, usage: ModelUsage) -> Path:
    path = mmdev_dir / "reports" / USAGE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(usage.model_dump(), ensure_ascii=False) + "\n")
    record_usage(mmdev_dir, usage)
    return path


def read_usage(mmdev_dir: Path) -> list[ModelUsage]:
    path = mmdev_dir / "reports" / USAGE_FILE
    if not path.exists():
        return []
    records: list[ModelUsage] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            records.append(ModelUsage.model_validate_json(line))
    return records
