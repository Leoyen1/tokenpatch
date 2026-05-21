import json
from pathlib import Path

from mmdev.savings_estimator import DeepSeekPricing, ScenarioPricing, estimate_savings, load_token_split


def write_usage(path: Path) -> None:
    rows = [
        {"purpose": "plan", "input_tokens": 500, "output_tokens": 300},
        {"purpose": "execute", "input_tokens": 800, "output_tokens": 600},
        {"purpose": "review", "input_tokens": 700, "output_tokens": 120},
    ]
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n", encoding="utf-8")


def test_load_token_split(tmp_path):
    usage = tmp_path / "model-usage.jsonl"
    write_usage(usage)
    split = load_token_split(usage)
    assert split.strong_input == 1200
    assert split.strong_output == 420
    assert split.cheap_input == 800
    assert split.cheap_output == 600
    assert split.total_input == 2000
    assert split.total_output == 1020


def test_estimate_savings_gpt55_cache_miss(tmp_path):
    usage = tmp_path / "model-usage.jsonl"
    write_usage(usage)
    split = load_token_split(usage)
    strong = ScenarioPricing(name="gpt55", strong_input_per_million=5.0, strong_output_per_million=30.0)
    deepseek = DeepSeekPricing(input_hit_per_million=0.011, input_miss_per_million=1.286, output_per_million=2.572)
    result = estimate_savings(split, strong, deepseek, cache_hit_ratio=0.0)
    assert result["baseline_all_strong_usd"] == 0.0406
    assert round(result["mixed_cost_usd"], 6) == 0.021172
    assert round(result["savings_usd"], 6) == 0.019428
    assert round(result["savings_ratio_percent"], 2) == 47.85
