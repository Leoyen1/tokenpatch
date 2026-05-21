from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmdev.savings_estimator import DeepSeekPricing, ScenarioPricing, estimate_savings, load_token_split


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate tokenpatch savings with strong+cheap routing.")
    parser.add_argument(
        "--usage-file",
        default=".mmdev/reports/model-usage.jsonl",
        help="Path to model-usage.jsonl (default: .mmdev/reports/model-usage.jsonl)",
    )
    parser.add_argument(
        "--cache-hit-ratio",
        type=float,
        default=0.0,
        help="DeepSeek input cache hit ratio in [0,1]. Default 0.",
    )
    parser.add_argument("--deepseek-input-hit", type=float, default=0.011, help="USD per 1M input tokens (cache hit)")
    parser.add_argument("--deepseek-input-miss", type=float, default=1.286, help="USD per 1M input tokens (cache miss)")
    parser.add_argument("--deepseek-output", type=float, default=2.572, help="USD per 1M output tokens")
    parser.add_argument(
        "--scenario",
        choices=["both", "gpt55", "opus47", "custom"],
        default="both",
        help="Strong model pricing scenario",
    )
    parser.add_argument(
        "--monthly-runs",
        type=int,
        default=0,
        help="Optional monthly run count for monthly savings projection",
    )
    parser.add_argument("--strong-input", type=float, default=0.0, help="Custom strong model input price per 1M tokens")
    parser.add_argument("--strong-output", type=float, default=0.0, help="Custom strong model output price per 1M tokens")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args(argv)


def build_scenarios(args: argparse.Namespace) -> list[ScenarioPricing]:
    scenarios: list[ScenarioPricing] = []
    if args.scenario in {"both", "gpt55"}:
        scenarios.append(ScenarioPricing(name="gpt55", strong_input_per_million=5.0, strong_output_per_million=30.0))
    if args.scenario in {"both", "opus47"}:
        scenarios.append(ScenarioPricing(name="opus47", strong_input_per_million=5.0, strong_output_per_million=25.0))
    if args.scenario == "custom":
        if args.strong_input <= 0 or args.strong_output <= 0:
            raise ValueError("--strong-input and --strong-output must be > 0 for custom scenario")
        scenarios.append(
            ScenarioPricing(
                name="custom",
                strong_input_per_million=args.strong_input,
                strong_output_per_million=args.strong_output,
            )
        )
    return scenarios


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cache_hit_ratio < 0 or args.cache_hit_ratio > 1:
        raise ValueError("--cache-hit-ratio must be within [0,1]")
    if args.monthly_runs < 0:
        raise ValueError("--monthly-runs must be >= 0")
    usage_file = Path(args.usage_file).expanduser().resolve()
    if not usage_file.exists():
        raise FileNotFoundError(f"usage file not found: {usage_file}")

    split = load_token_split(usage_file)
    deepseek = DeepSeekPricing(
        input_hit_per_million=args.deepseek_input_hit,
        input_miss_per_million=args.deepseek_input_miss,
        output_per_million=args.deepseek_output,
    )
    scenarios = build_scenarios(args)

    results = []
    for scenario in scenarios:
        row = estimate_savings(split, scenario, deepseek, args.cache_hit_ratio)
        if args.monthly_runs > 0:
            row["monthly_projection"] = {
                "runs": args.monthly_runs,
                "baseline_all_strong_usd": row["baseline_all_strong_usd"] * args.monthly_runs,
                "mixed_cost_usd": row["mixed_cost_usd"] * args.monthly_runs,
                "savings_usd": row["savings_usd"] * args.monthly_runs,
            }
        results.append(row)
    payload = {
        "usage_file": str(usage_file),
        "monthly_runs": args.monthly_runs,
        "token_split": {
            "strong_input": split.strong_input,
            "strong_output": split.strong_output,
            "cheap_input": split.cheap_input,
            "cheap_output": split.cheap_output,
            "total_input": split.total_input,
            "total_output": split.total_output,
        },
        "deepseek_pricing": {
            "input_hit_per_million": deepseek.input_hit_per_million,
            "input_miss_per_million": deepseek.input_miss_per_million,
            "output_per_million": deepseek.output_per_million,
        },
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
