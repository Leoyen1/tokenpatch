import pytest

from mmdev.config import MMDevConfig
from mmdev.models.base import CompletionResult
from mmdev.schemas import ModelUsage
from mmdev.usage import append_usage, build_usage, read_usage


def test_usage_round_trips(tmp_path):
    usage = ModelUsage(
        model="planner",
        input_tokens=10,
        output_tokens=20,
        estimated_cost=0,
        duration_ms=3,
        purpose="plan",
    )
    append_usage(tmp_path / ".mmdev", usage)
    loaded = read_usage(tmp_path / ".mmdev")
    assert loaded == [usage]


def test_build_usage_uses_provider_tokens_when_present():
    usage = build_usage(
        model="executor",
        prompt="hello",
        result=CompletionResult(text="world", input_tokens=5, output_tokens=7),
        purpose="execute",
        started_at=0,
    )
    assert usage.input_tokens == 5
    assert usage.output_tokens == 7


def test_build_usage_applies_configured_pricing():
    usage = build_usage(
        model="executor",
        prompt="hello",
        result=CompletionResult(text="world", input_tokens=1_000_000, output_tokens=500_000),
        purpose="execute",
        started_at=0,
        config=MMDevConfig(
            executor_input_cost_per_million=1.0,
            executor_output_cost_per_million=2.0,
        ),
    )
    assert usage.estimated_cost == pytest.approx(2.0)
