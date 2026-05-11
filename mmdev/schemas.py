from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Complexity = Literal["low", "medium", "high"]
RecommendedExecutor = Literal["cheap", "strong"]
Severity = Literal["low", "medium", "high"]
NextAction = Literal["approve", "retry-cheap", "escalate-strong", "ask-human"]
Purpose = Literal["plan", "execute", "review", "repair"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DevTask(StrictModel):
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    context: str = ""
    allowed_files: list[str] = Field(min_length=1)
    forbidden_changes: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    complexity: Complexity
    recommended_executor: RecommendedExecutor
    max_attempts: int = Field(default=2, ge=1, le=5)

    @field_validator("allowed_files")
    @classmethod
    def allowed_files_are_relative(cls, files: list[str]) -> list[str]:
        for file_name in files:
            normalized = file_name.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError("allowed_files must be relative paths inside the project")
        return files


class ProjectPlan(StrictModel):
    project_summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tasks: list[DevTask] = Field(min_length=1)


class ExecutionResult(StrictModel):
    task_id: str
    changed_files: list[str]
    patch_path: str
    summary: str
    known_risks: list[str] = Field(default_factory=list)
    needs_human_input: bool = False


class ExecutorModelOutput(StrictModel):
    patch: str = Field(min_length=1)
    changed_files: list[str] = Field(default_factory=list)
    summary: str = ""
    risks: list[str] = Field(default_factory=list)
    verification_hint: str = ""
    needs_human_input: bool = False


class CommandResult(StrictModel):
    command: str
    exit_code: int
    stdout_tail: str = ""
    stderr_tail: str = ""


class ValidationResult(StrictModel):
    task_id: str
    command_results: list[CommandResult]
    passed: bool


class ReviewFinding(StrictModel):
    severity: Severity
    file: str
    line: int = Field(ge=1)
    message: str


class ReviewResult(StrictModel):
    task_id: str
    approved: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    missing_acceptance_criteria: list[str] = Field(default_factory=list)
    recommended_next_action: NextAction


class ModelUsage(StrictModel):
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    duration_ms: int = Field(ge=0)
    purpose: Purpose
    charged_credits: float | None = Field(default=None, ge=0)
    provider_cost: float | None = Field(default=None, ge=0)
