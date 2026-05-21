from __future__ import annotations


DEFAULT_BASELINE_STRONG_INPUT_COST_PER_MILLION = 5.0
DEFAULT_BASELINE_STRONG_OUTPUT_COST_PER_MILLION = 25.0


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    code_chars = sum(1 for char in text if char in "{}[]();=<>/\\")
    other_chars = max(len(text) - chinese_chars - code_chars, 0)
    estimate = (chinese_chars / 1.75) + (code_chars / 3.5) + (other_chars / 4)
    return max(1, int(round(estimate)))


def estimate_cost(input_tokens: int, output_tokens: int, input_per_million: float = 0.0, output_per_million: float = 0.0) -> float:
    return ((input_tokens * input_per_million) + (output_tokens * output_per_million)) / 1_000_000


def effective_baseline_rates(input_per_million: float, output_per_million: float) -> tuple[float, float, bool]:
    if input_per_million > 0 or output_per_million > 0:
        return input_per_million, output_per_million, False
    return DEFAULT_BASELINE_STRONG_INPUT_COST_PER_MILLION, DEFAULT_BASELINE_STRONG_OUTPUT_COST_PER_MILLION, True
