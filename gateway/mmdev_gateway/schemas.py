from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutorRunRequest(StrictModel):
    protocol: str = "mmdev.executor.v1"
    executor_model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)


class UsagePayload(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ExecutorRunResponse(StrictModel):
    task_id: str
    patch: str
    changed_files: list[str]
    summary: str
    risks: list[str] = Field(default_factory=list)
    verification_hint: str = ""
    needs_human_input: bool = False
    usage: UsagePayload
    charged_credits: float = Field(ge=0)
    provider_cost: float = Field(ge=0)


class BalanceResponse(StrictModel):
    credits: float = Field(ge=0)


class TopUpRequest(StrictModel):
    credits: float = Field(gt=0)


class UsageRecord(StrictModel):
    task_id: str
    input_tokens: int
    output_tokens: int
    charged_credits: float
    provider_cost: float


class UsageSummaryResponse(StrictModel):
    window: Literal["24h", "7d", "30d", "all"]
    calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    charged_credits: float = Field(ge=0)
    provider_cost: float = Field(ge=0)


class SavingsEstimate(StrictModel):
    window: Literal["7d", "30d"]
    baseline_strong_cost: float = Field(ge=0)
    actual_charged_credits: float = Field(ge=0)
    provider_cost: float = Field(ge=0)
    savings_vs_charged: float
    savings_vs_provider: float
    savings_ratio_vs_charged: float
    savings_ratio_vs_provider: float


class DashboardOverviewResponse(StrictModel):
    schema_version: str
    token: str
    balance_credits: float = Field(ge=0)
    generated_at: str
    usage_7d: UsageSummaryResponse
    usage_30d: UsageSummaryResponse
    savings_estimate_7d: SavingsEstimate
    savings_estimate_30d: SavingsEstimate


class AccountInfo(StrictModel):
    token: str
    credits: float = Field(ge=0)
    frozen: bool
    freeze_reason: str | None = None
    freeze_level: str | None = None
    owner_id: str | None = None
    email: str | None = None
    status: Literal["invited", "active", "suspended"] = "invited"
    updated_at: str


class SetCreditsRequest(StrictModel):
    credits: float = Field(ge=0)


class UpdateAccountRequest(StrictModel):
    owner_id: str | None = None
    email: str | None = None
    status: Literal["invited", "active", "suspended"]


class ManualTopUpRequest(StrictModel):
    credits: float = Field(gt=0)
    reason: str = Field(min_length=1)


class ManualTopUpRecord(StrictModel):
    token: str
    operator: str
    reason: str
    before_credits: float
    amount: float
    after_credits: float
    request_id: str | None = None
    created_at: str


class FreezeRequest(StrictModel):
    reason: str = "manual-admin-freeze"
    level: Literal["low", "medium", "high", "critical"] = "medium"
    note: str = ""


class UnfreezeRequest(StrictModel):
    reason: str = "manual-admin-unfreeze"
    approval_note: str = ""


class PolicyEvent(StrictModel):
    event_type: str
    detail: str
    request_id: str | None = None
    actor: str = "system"
    severity: str | None = None
    created_at: str


class EventCount(StrictModel):
    name: str
    count: int = Field(ge=0)


class EventSummaryResponse(StrictModel):
    total: int = Field(ge=0)
    by_event_type: list[EventCount] = Field(default_factory=list)
    by_severity: list[EventCount] = Field(default_factory=list)
    by_actor: list[EventCount] = Field(default_factory=list)


class TrendPoint(StrictModel):
    bucket: str
    count: int = Field(ge=0)


class EventTrendResponse(StrictModel):
    bucket: Literal["hour", "day"]
    total: int = Field(ge=0)
    points: list[TrendPoint] = Field(default_factory=list)
