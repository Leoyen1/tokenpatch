from __future__ import annotations

from typing import Any


def summarize_patch_economics(
    *,
    total_tasks: int,
    task_statuses: list[dict[str, Any]],
    validation_results,
    review_results,
    actual_cost: float,
    baseline_cost: float,
) -> dict[str, float | int]:
    accepted_task_ids = {result.task_id for result in validation_results if result.passed}
    accepted_task_ids.update(result.task_id for result in review_results if result.approved)

    applied_statuses = {"executed", "validated", "approved"}
    failed_status_prefixes = ("execution-failed", "validation-failed", "review-")
    applied_task_ids = {
        str(item.get("task_id"))
        for item in task_statuses
        if str(item.get("status")) in applied_statuses
    }
    failed_tasks = sum(
        1
        for item in task_statuses
        if any(str(item.get("status", "")).startswith(prefix) for prefix in failed_status_prefixes)
    )

    accepted_patches = len(accepted_task_ids)
    applied_patches = len(applied_task_ids | accepted_task_ids)
    generated_patches = applied_patches
    cost_per_accepted_patch = actual_cost / accepted_patches if accepted_patches > 0 else 0.0
    cost_per_applied_patch = actual_cost / applied_patches if applied_patches > 0 else 0.0
    cost_per_generated_patch = actual_cost / generated_patches if generated_patches > 0 else 0.0
    baseline_per_accepted_patch = baseline_cost / accepted_patches if accepted_patches > 0 else 0.0
    baseline_per_applied_patch = baseline_cost / applied_patches if applied_patches > 0 else 0.0
    savings_per_accepted_patch = baseline_per_accepted_patch - cost_per_accepted_patch
    savings_per_applied_patch = baseline_per_applied_patch - cost_per_applied_patch
    savings_ratio_accepted = (savings_per_accepted_patch / baseline_per_accepted_patch * 100.0) if baseline_per_accepted_patch > 0 else 0.0
    savings_ratio_applied = (savings_per_applied_patch / baseline_per_applied_patch * 100.0) if baseline_per_applied_patch > 0 else 0.0
    total_savings = baseline_cost - actual_cost
    total_savings_ratio = (total_savings / baseline_cost * 100.0) if baseline_cost > 0 else 0.0

    return {
        "total_tasks": total_tasks,
        "accepted_patches": accepted_patches,
        "applied_patches": applied_patches,
        "generated_patches": generated_patches,
        "failed_tasks": failed_tasks,
        "actual_cost": actual_cost,
        "baseline_cost": baseline_cost,
        "cost_per_accepted_patch": cost_per_accepted_patch,
        "cost_per_applied_patch": cost_per_applied_patch,
        "cost_per_generated_patch": cost_per_generated_patch,
        "baseline_cost_per_accepted_patch": baseline_per_accepted_patch,
        "baseline_cost_per_applied_patch": baseline_per_applied_patch,
        "savings_per_accepted_patch": savings_per_accepted_patch,
        "savings_per_applied_patch": savings_per_applied_patch,
        "savings_ratio_per_accepted_patch": savings_ratio_accepted,
        "savings_ratio_per_applied_patch": savings_ratio_applied,
        "estimated_savings": total_savings,
        "estimated_savings_ratio": total_savings_ratio,
    }
