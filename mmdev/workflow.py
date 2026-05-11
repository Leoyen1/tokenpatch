from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from mmdev.config import MMDevConfig, init_state_dir
from mmdev.executor import execute_task
from mmdev.git_utils import GitError
from mmdev.isolation import IsolationError, cleanup_worktree, prepare_worktree
from mmdev.models.base import CompletionClient
from mmdev.patcher import PatchSafetyError
from mmdev.planner import create_plan, write_plan
from mmdev.reporter import write_final_report
from mmdev.reviewer import review_task, write_review_result
from mmdev.schemas import DevTask, ExecutionResult, ReviewResult, ValidationResult
from mmdev.validator import validate_task, write_validation_result


class AutoTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    attempts: int
    final_status: str
    next_action: str
    executions: list[ExecutionResult]
    validations: list[ValidationResult]
    reviews: list[ReviewResult]

    @property
    def execution(self) -> ExecutionResult:
        return self.executions[-1]

    @property
    def validation(self) -> ValidationResult:
        return self.validations[-1]

    @property
    def review(self) -> ReviewResult:
        return self.reviews[-1]


class AutoResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[AutoTaskResult]
    report_path: str


def run_auto(
    requirement: str,
    config: MMDevConfig,
    planner_client: CompletionClient,
    executor_client: CompletionClient,
    reviewer_client: CompletionClient,
    isolation: str = "none",
) -> AutoResult:
    init_state_dir(config.workdir)
    plan = create_plan(requirement, config, planner_client)
    write_plan(config.mmdev_dir, plan)

    task_results: list[AutoTaskResult] = []
    for task in plan.tasks:
        task_result = run_task_with_retries(task, config, executor_client, reviewer_client, isolation=isolation)
        task_results.append(task_result)
        if task_result.next_action in {"ask-human", "escalate-strong"}:
            break

    report_path = write_final_report(config.mmdev_dir)
    return AutoResult(tasks=task_results, report_path=str(report_path))


def run_task_with_retries(
    task: DevTask,
    config: MMDevConfig,
    executor_client: CompletionClient,
    reviewer_client: CompletionClient,
    isolation: str = "none",
) -> AutoTaskResult:
    executions: list[ExecutionResult] = []
    validations: list[ValidationResult] = []
    reviews: list[ReviewResult] = []
    max_attempts = max(1, task.max_attempts)

    for attempt in range(1, max_attempts + 1):
        active_config = config
        try:
            if isolation == "worktree":
                active_config = prepare_worktree(config, task.task_id)
            elif isolation != "none":
                raise ValueError(f"unsupported isolation mode: {isolation}")
            execution = execute_task(task, active_config, executor_client)
        except (GitError, IsolationError, PatchSafetyError, ValueError) as exc:
            return AutoTaskResult(
                task_id=task.task_id,
                attempts=attempt,
                final_status="failed",
                next_action="ask-human",
                executions=executions,
                validations=validations,
                reviews=reviews,
            )
        executions.append(execution)

        if execution.needs_human_input:
            return AutoTaskResult(
                task_id=task.task_id,
                attempts=attempt,
                final_status="needs-human-input",
                next_action="ask-human",
                executions=executions,
                validations=validations,
                reviews=reviews,
            )

        validation = validate_task(task, active_config)
        write_validation_result(config.mmdev_dir, validation)
        validations.append(validation)

        review = review_task(task, validation, active_config, reviewer_client)
        write_review_result(config.mmdev_dir, review)
        reviews.append(review)

        if validation.passed and review.approved and review.recommended_next_action == "approve":
            return AutoTaskResult(
                task_id=task.task_id,
                attempts=attempt,
                final_status="approved",
                next_action="approve",
                executions=executions,
                validations=validations,
                reviews=reviews,
            )

        if isolation == "worktree" and attempt >= max_attempts:
            cleanup_worktree(config, task.task_id)

        if review.recommended_next_action in {"ask-human", "escalate-strong"}:
            return AutoTaskResult(
                task_id=task.task_id,
                attempts=attempt,
                final_status="blocked",
                next_action=review.recommended_next_action,
                executions=executions,
                validations=validations,
                reviews=reviews,
            )

        if attempt >= max_attempts:
            return AutoTaskResult(
                task_id=task.task_id,
                attempts=attempt,
                final_status="max-attempts-reached",
                next_action="escalate-strong",
                executions=executions,
                validations=validations,
                reviews=reviews,
            )

    return AutoTaskResult(
        task_id=task.task_id,
        attempts=max_attempts,
        final_status="max-attempts-reached",
        next_action="escalate-strong",
        executions=executions,
        validations=validations,
        reviews=reviews,
    )
