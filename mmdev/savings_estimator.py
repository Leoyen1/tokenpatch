from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


STRONG_PURPOSES = {"plan", "review"}
CHEAP_PURPOSES = {"execute", "repair"}


@dataclass(frozen=True)
class TokenSplit:
    strong_input: int
    strong_output: int
    cheap_input: int
    cheap_output: int

    @property
    def total_input(self) -> int:
        return self.strong_input + self.cheap_input

    @property
    def total_output(self) -> int:
        return self.strong_output + self.cheap_output


@dataclass(frozen=True)
class ScenarioPricing:
    name: str
    strong_input_per_million: float
    strong_output_per_million: float


@dataclass(frozen=True)
class DeepSeekPricing:
    input_hit_per_million: float
    input_miss_per_million: float
    output_per_million: float


def load_token_split(usage_file: Path) -> TokenSplit:
    strong_input = 0
    strong_output = 0
    cheap_input = 0
    cheap_output = 0
    for raw_line in usage_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        purpose = str(payload.get("purpose", ""))
        input_tokens = int(payload.get("input_tokens") or 0)
        output_tokens = int(payload.get("output_tokens") or 0)
        if purpose in STRONG_PURPOSES:
            strong_input += input_tokens
            strong_output += output_tokens
        elif purpose in CHEAP_PURPOSES:
            cheap_input += input_tokens
            cheap_output += output_tokens
    return TokenSplit(
        strong_input=strong_input,
        strong_output=strong_output,
        cheap_input=cheap_input,
        cheap_output=cheap_output,
    )


def token_cost(input_tokens: int, output_tokens: int, input_rate: float, output_rate: float) -> float:
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def mixed_cost(split: TokenSplit, strong: ScenarioPricing, deepseek: DeepSeekPricing, cache_hit_ratio: float) -> float:
    ds_input_rate = deepseek.input_hit_per_million * cache_hit_ratio + deepseek.input_miss_per_million * (1.0 - cache_hit_ratio)
    strong_cost = token_cost(
        split.strong_input,
        split.strong_output,
        strong.strong_input_per_million,
        strong.strong_output_per_million,
    )
    cheap_cost = token_cost(
        split.cheap_input,
        split.cheap_output,
        ds_input_rate,
        deepseek.output_per_million,
    )
    return strong_cost + cheap_cost


def all_strong_cost(split: TokenSplit, strong: ScenarioPricing) -> float:
    return token_cost(
        split.total_input,
        split.total_output,
        strong.strong_input_per_million,
        strong.strong_output_per_million,
    )


def estimate_savings(split: TokenSplit, strong: ScenarioPricing, deepseek: DeepSeekPricing, cache_hit_ratio: float) -> dict:
    baseline = all_strong_cost(split, strong)
    mixed = mixed_cost(split, strong, deepseek, cache_hit_ratio)
    savings = baseline - mixed
    ratio = (savings / baseline * 100.0) if baseline > 0 else 0.0
    return {
        "scenario": strong.name,
        "cache_hit_ratio": cache_hit_ratio,
        "baseline_all_strong_usd": baseline,
        "mixed_cost_usd": mixed,
        "savings_usd": savings,
        "savings_ratio_percent": ratio,
    }
