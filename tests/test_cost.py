from mmdev.cost import estimate_cost, estimate_tokens


def test_estimate_tokens_handles_chinese_english_and_code():
    assert estimate_tokens("中文测试") >= 1
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens("def f():\n    return {'x': 1}") >= 1


def test_estimate_cost_uses_per_million_rates():
    assert estimate_cost(1_000_000, 500_000, 1.0, 2.0) == 2.0

