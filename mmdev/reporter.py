from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from mmdev.config import load_config
from mmdev.cost import estimate_cost
from mmdev.executor import load_plan
from mmdev.schemas import ReviewResult, ValidationResult
from mmdev.usage import read_usage


def generate_report(mmdev_dir: Path) -> str:
    config = load_config(mmdev_dir.parent)
    plan = load_plan(mmdev_dir)
    usage = read_usage(mmdev_dir)
    run_events = read_run_events(mmdev_dir)
    validation_results = read_optional_results(mmdev_dir, "validation", ValidationResult)
    review_results = read_optional_results(mmdev_dir, "review", ReviewResult)

    total_tasks = len(plan.tasks)
    validation_passed = sum(1 for result in validation_results if result.passed)
    reviews_approved = sum(1 for result in review_results if result.approved)
    usage_by_purpose = Counter(record.purpose for record in usage)
    total_input = sum(record.input_tokens for record in usage)
    total_output = sum(record.output_tokens for record in usage)
    total_cost = sum(record.estimated_cost for record in usage)
    total_credits = sum(record.charged_credits or 0 for record in usage)
    total_provider_cost = sum(record.provider_cost or 0 for record in usage)
    strong_cost = sum(record.estimated_cost for record in usage if record.purpose in {"plan", "review"})
    cheap_cost = sum(record.estimated_cost for record in usage if record.purpose in {"execute", "repair"})
    baseline_cost = estimate_cost(
        total_input,
        total_output,
        config.baseline_strong_input_cost_per_million,
        config.baseline_strong_output_cost_per_million,
    )
    savings = baseline_cost - total_cost
    savings_ratio = (savings / baseline_cost * 100) if baseline_cost > 0 else 0.0
    usage_by_model_purpose = summarize_usage_by_model_purpose(usage)
    strong_route_stats = summarize_strong_route_stats(run_events)
    auto_route_stats = summarize_auto_route_stats(run_events)

    lines = [
        "# tokenpatch Final Report",
        "",
        "All costs are estimated unless provider usage and pricing are configured.",
        "",
        "## Summary",
        "",
        f"- Total tasks: {total_tasks}",
        f"- Validation results: {len(validation_results)} recorded, {validation_passed} passed",
        f"- Review results: {len(review_results)} recorded, {reviews_approved} approved",
        f"- Model calls: {len(usage)}",
        f"- Estimated input tokens: {total_input}",
        f"- Estimated output tokens: {total_output}",
        f"- Estimated total cost: {total_cost:.6f}",
        f"- Gateway credits charged: {total_credits:.6f}",
        f"- Gateway provider cost: {total_provider_cost:.6f}",
        f"- Estimated strong-model cost: {strong_cost:.6f}",
        f"- Estimated cheap-executor cost: {cheap_cost:.6f}",
        f"- Estimated all-strong baseline cost: {baseline_cost:.6f}",
        f"- Estimated savings vs all-strong: {savings:.6f}",
        f"- Estimated savings ratio: {savings_ratio:.2f}%",
        "",
        "## Model Calls",
        "",
        f"- Plan calls: {usage_by_purpose.get('plan', 0)}",
        f"- Execute calls: {usage_by_purpose.get('execute', 0)}",
        f"- Review calls: {usage_by_purpose.get('review', 0)}",
        f"- Repair calls: {usage_by_purpose.get('repair', 0)}",
        "",
    ]
    lines.extend(
        [
            "## Cost by Provider/Model",
            "",
        ]
    )
    if usage_by_model_purpose:
        for row in usage_by_model_purpose:
            lines.append(
                f"- {row['purpose']} / {row['model']}: calls={row['calls']}, input={row['input_tokens']}, output={row['output_tokens']}, cost={row['estimated_cost']:.6f}"
            )
    else:
        lines.append("- No model usage records.")
    lines.extend(
        [
            "",
            "## Routing Success (from run-events.jsonl)",
            "",
            f"- Logged run events: {len(run_events)}",
            "",
            "- Strong routes:",
        ]
    )
    if strong_route_stats:
        for row in strong_route_stats:
            lines.append(
                f"  - {row['command']} / {row['provider']} / {row['model']}: runs={row['runs']}, success={row['successes']}, error={row['errors']}, success_rate={row['success_rate']:.2f}%"
            )
    else:
        lines.append("  - No plan/review finish events.")
    lines.append("- Auto routes:")
    if auto_route_stats:
        for row in auto_route_stats:
            lines.append(
                "  - "
                + f"strong={row['provider']} (plan={row['planner_model']}, review={row['reviewer_model']}), "
                + f"executor={row['executor_provider']} ({row['executor_model']}): "
                + f"runs={row['runs']}, success={row['successes']}, error={row['errors']}, success_rate={row['success_rate']:.2f}%"
            )
    else:
        lines.append("  - No auto finish events.")
    lines.extend(
        [
            "",
            "## Tasks",
            "",
        ]
    )
    for task in plan.tasks:
        validation = find_result(validation_results, task.task_id)
        review = find_result(review_results, task.task_id)
        lines.extend(
            [
                f"### {task.task_id}: {task.title}",
                "",
                f"- Complexity: {task.complexity}",
                f"- Recommended executor: {task.recommended_executor}",
                f"- Allowed files: {', '.join(task.allowed_files)}",
                f"- Validation: {format_validation(validation)}",
                f"- Review: {format_review(review)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_final_report(mmdev_dir: Path) -> Path:
    path = mmdev_dir / "reports" / "final-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_report(mmdev_dir), encoding="utf-8")
    return path


def read_run_events(mmdev_dir: Path) -> list[dict]:
    path = mmdev_dir / "logs" / "run-events.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def summarize_usage_by_model_purpose(usage) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for record in usage:
        key = (record.purpose, record.model)
        row = grouped.setdefault(
            key,
            {
                "purpose": record.purpose,
                "model": record.model,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
            },
        )
        row["calls"] += 1
        row["input_tokens"] += record.input_tokens
        row["output_tokens"] += record.output_tokens
        row["estimated_cost"] += record.estimated_cost
    return [grouped[key] for key in sorted(grouped.keys())]


def summarize_strong_route_stats(events: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for item in events:
        event_name = str(item.get("event", ""))
        if event_name not in {"cli.plan.finish", "cli.review.finish"}:
            continue
        command = "plan" if event_name == "cli.plan.finish" else "review"
        provider = str(item.get("strong_provider") or "<unknown>")
        model = str(item.get("strong_model") or "<unset>")
        outcome = str(item.get("outcome") or "error")
        key = (command, provider, model)
        row = grouped.setdefault(
            key,
            {"command": command, "provider": provider, "model": model, "runs": 0, "successes": 0, "errors": 0},
        )
        row["runs"] += 1
        if outcome == "success":
            row["successes"] += 1
        else:
            row["errors"] += 1
    rows: list[dict] = []
    for key in sorted(grouped.keys()):
        row = grouped[key]
        runs = row["runs"]
        row["success_rate"] = (row["successes"] / runs * 100.0) if runs > 0 else 0.0
        rows.append(row)
    return rows


def summarize_auto_route_stats(events: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str, str], dict] = {}
    for item in events:
        if str(item.get("event", "")) != "cli.auto.finish":
            continue
        provider = str(item.get("strong_provider") or "<unknown>")
        planner_model = str(item.get("planner_model") or "<unset>")
        reviewer_model = str(item.get("reviewer_model") or "<unset>")
        executor_provider = str(item.get("executor_provider") or "<unknown>")
        executor_model = str(item.get("executor_model") or "<unset>")
        outcome = str(item.get("outcome") or "error")
        key = (provider, planner_model, reviewer_model, executor_provider, executor_model)
        row = grouped.setdefault(
            key,
            {
                "provider": provider,
                "planner_model": planner_model,
                "reviewer_model": reviewer_model,
                "executor_provider": executor_provider,
                "executor_model": executor_model,
                "runs": 0,
                "successes": 0,
                "errors": 0,
            },
        )
        row["runs"] += 1
        if outcome == "success":
            row["successes"] += 1
        else:
            row["errors"] += 1
    rows: list[dict] = []
    for key in sorted(grouped.keys()):
        row = grouped[key]
        runs = row["runs"]
        row["success_rate"] = (row["successes"] / runs * 100.0) if runs > 0 else 0.0
        rows.append(row)
    return rows


def read_optional_results(mmdev_dir: Path, suffix: str, model_type):
    reports_dir = mmdev_dir / "reports"
    if not reports_dir.exists():
        return []
    results = []
    for path in sorted(reports_dir.glob(f"*-{suffix}.json")):
        results.append(model_type.model_validate_json(path.read_text(encoding="utf-8-sig")))
    return results


def find_result(results, task_id: str):
    for result in results:
        if result.task_id == task_id:
            return result
    return None


def format_validation(result: ValidationResult | None) -> str:
    if result is None:
        return "not recorded"
    return "passed" if result.passed else "failed"


def format_review(result: ReviewResult | None) -> str:
    if result is None:
        return "not recorded"
    return "approved" if result.approved else f"not approved, next action: {result.recommended_next_action}"
