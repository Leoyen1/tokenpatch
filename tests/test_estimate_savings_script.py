import json
from pathlib import Path

from scripts import estimate_savings


def write_usage(path: Path) -> None:
    rows = [
        {"purpose": "plan", "input_tokens": 500, "output_tokens": 300},
        {"purpose": "execute", "input_tokens": 800, "output_tokens": 600},
        {"purpose": "review", "input_tokens": 700, "output_tokens": 120},
    ]
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n", encoding="utf-8")


def test_script_outputs_monthly_projection(tmp_path, capsys):
    usage_file = tmp_path / "model-usage.jsonl"
    write_usage(usage_file)
    rc = estimate_savings.main(
        [
            "--usage-file",
            str(usage_file),
            "--scenario",
            "gpt55",
            "--cache-hit-ratio",
            "0.0",
            "--monthly-runs",
            "1000",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["monthly_runs"] == 1000
    result = payload["results"][0]
    monthly = result["monthly_projection"]
    assert monthly["runs"] == 1000
    assert round(monthly["baseline_all_strong_usd"], 3) == 40.6
    assert round(monthly["mixed_cost_usd"], 3) == 21.172
    assert round(monthly["savings_usd"], 3) == 19.428
