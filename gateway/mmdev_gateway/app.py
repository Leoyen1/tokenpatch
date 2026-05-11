from __future__ import annotations

import csv
from datetime import datetime, timezone
import os
from io import StringIO
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response

from gateway.mmdev_gateway.deepseek import DeepSeekExecutor
from gateway.mmdev_gateway.policy import GatewayPolicy
from gateway.mmdev_gateway.schemas import (
    AccountInfo,
    BalanceResponse,
    DashboardOverviewResponse,
    EventSummaryResponse,
    EventTrendResponse,
    ExecutorRunRequest,
    ExecutorRunResponse,
    FreezeRequest,
    ManualTopUpRecord,
    ManualTopUpRequest,
    PolicyEvent,
    SavingsEstimate,
    SetCreditsRequest,
    UpdateAccountRequest,
    TopUpRequest,
    UnfreezeRequest,
    UsagePayload,
    UsageRecord,
    UsageSummaryResponse,
)
from gateway.mmdev_gateway.store import Account, SQLiteStore


app = FastAPI(title="tokenpatch Gateway", version="0.1.0")
POLICY = GatewayPolicy()
DASHBOARD_SCHEMA_VERSION = "2026-05-11.v1"


@app.middleware("http")
async def propagate_request_id(request: Request, call_next):
    response = await call_next(request)
    request_id = request.headers.get("X-Request-ID", "").strip()
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


def build_store() -> SQLiteStore:
    tokens = [token.strip() for token in os.getenv("MMDEV_GATEWAY_TOKENS", "dev-token").split(",") if token.strip()]
    starting = float(os.getenv("MMDEV_GATEWAY_STARTING_CREDITS", "0"))
    default_account_status = os.getenv("MMDEV_GATEWAY_DEFAULT_ACCOUNT_STATUS", "invited")
    db_path = os.getenv("MMDEV_GATEWAY_DB_PATH", ".mmdev-gateway/gateway.sqlite")
    return SQLiteStore(
        db_path=Path(db_path),
        tokens=tokens,
        starting_credits=starting,
        default_account_status=default_account_status,
    )


STORE = build_store()


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


def current_account(token: Annotated[str, Depends(bearer_token)]) -> tuple[str, Account]:
    account = STORE.require_account(token)
    if account is None:
        raise HTTPException(status_code=403, detail="invalid gateway token")
    return token, account


def admin_guard(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    admin_tokens = POLICY.get_csv_set("MMDEV_GATEWAY_ADMIN_TOKENS", upper=False)
    if token not in admin_tokens:
        raise HTTPException(status_code=403, detail="admin token required")
    return token


@app.get("/v1/balance", response_model=BalanceResponse)
def balance(auth: Annotated[tuple[str, Account], Depends(current_account)]) -> BalanceResponse:
    token, _ = auth
    return BalanceResponse(credits=STORE.balance(token))


@app.get("/v1/usage", response_model=list[UsageRecord])
def usage(auth: Annotated[tuple[str, Account], Depends(current_account)]) -> list[UsageRecord]:
    token, _ = auth
    return STORE.usage(token)


@app.get("/v1/usage/summary", response_model=UsageSummaryResponse)
def usage_summary(
    auth: Annotated[tuple[str, Account], Depends(current_account)],
    window: Literal["24h", "7d", "30d", "all"] = "all",
) -> UsageSummaryResponse:
    token, _ = auth
    return UsageSummaryResponse.model_validate(STORE.usage_summary(token, window=window))


@app.get("/v1/dashboard/overview", response_model=DashboardOverviewResponse)
def dashboard_overview(
    response: Response,
    auth: Annotated[tuple[str, Account], Depends(current_account)],
) -> DashboardOverviewResponse:
    token, _ = auth
    response.headers["X-TokenPatch-Schema-Version"] = DASHBOARD_SCHEMA_VERSION
    return build_dashboard_overview(token)


@app.post("/v1/credits/topup", response_model=BalanceResponse)
def topup(request: TopUpRequest, auth: Annotated[tuple[str, Account], Depends(current_account)]) -> BalanceResponse:
    token, _ = auth
    account = STORE.topup(token, request.credits)
    if account is None:
        raise HTTPException(status_code=403, detail="invalid gateway token")
    return BalanceResponse(credits=account.credits)


@app.get("/v1/tasks/{task_id}", response_model=ExecutorRunResponse)
def task(task_id: str, auth: Annotated[tuple[str, Account], Depends(current_account)]) -> ExecutorRunResponse:
    token, _ = auth
    result = STORE.task(token, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="task not found")
    return result


@app.get("/v1/admin/accounts", response_model=list[AccountInfo], dependencies=[Depends(admin_guard)])
def admin_accounts() -> list[AccountInfo]:
    return STORE.list_accounts()


@app.get("/v1/admin/accounts/{token}", response_model=AccountInfo, dependencies=[Depends(admin_guard)])
def admin_account(token: str) -> AccountInfo:
    account = STORE.account_info(token)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account


@app.post("/v1/admin/accounts/{token}/profile", response_model=AccountInfo, dependencies=[Depends(admin_guard)])
def admin_update_account_profile(token: str, request: UpdateAccountRequest) -> AccountInfo:
    if not STORE.update_account(
        token,
        owner_id=request.owner_id,
        email=request.email,
        status=request.status,
    ):
        raise HTTPException(status_code=404, detail="account not found")
    account = STORE.account_info(token)
    assert account is not None
    return account


@app.post("/v1/admin/accounts/{token}/credits/set", response_model=AccountInfo, dependencies=[Depends(admin_guard)])
def admin_set_credits(token: str, request: SetCreditsRequest) -> AccountInfo:
    if not STORE.set_credits(token, request.credits):
        raise HTTPException(status_code=404, detail="account not found")
    account = STORE.account_info(token)
    assert account is not None
    return account


@app.post("/v1/admin/accounts/{token}/credits/manual-topup", response_model=ManualTopUpRecord)
def admin_manual_topup(
    token: str,
    request: ManualTopUpRequest,
    admin_token: Annotated[str, Depends(admin_guard)],
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ManualTopUpRecord:
    if STORE.account_info(token) is None:
        raise HTTPException(status_code=404, detail="account not found")
    record = STORE.manual_topup(
        token,
        amount=request.credits,
        operator=admin_token,
        reason=request.reason,
        request_id=request_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="account not found")
    STORE.record_policy_event(
        token,
        "admin_manual_topup",
        f"credits={request.credits}; reason={request.reason}",
        request_id=request_id,
        actor="admin",
        severity="low",
    )
    return ManualTopUpRecord.model_validate(record)


@app.get("/v1/admin/accounts/{token}/topups", response_model=list[ManualTopUpRecord], dependencies=[Depends(admin_guard)])
def admin_topups(token: str, limit: int = 100) -> list[ManualTopUpRecord]:
    if STORE.account_info(token) is None:
        raise HTTPException(status_code=404, detail="account not found")
    return [ManualTopUpRecord.model_validate(item) for item in STORE.manual_topups(token, limit=limit)]


@app.post("/v1/admin/accounts/{token}/freeze", response_model=AccountInfo, dependencies=[Depends(admin_guard)])
def admin_freeze(token: str, request: FreezeRequest) -> AccountInfo:
    if not STORE.freeze(token, reason=request.reason, level=request.level):
        raise HTTPException(status_code=404, detail="account not found")
    detail = request.reason if not request.note else f"{request.reason}; note={request.note}"
    STORE.record_policy_event(token, "admin_freeze", detail, actor="admin", severity=request.level)
    account = STORE.account_info(token)
    assert account is not None
    return account


@app.post("/v1/admin/accounts/{token}/unfreeze", response_model=AccountInfo, dependencies=[Depends(admin_guard)])
def admin_unfreeze(token: str, request: UnfreezeRequest | None = None) -> AccountInfo:
    require_note = POLICY.get_bool("MMDEV_GATEWAY_UNFREEZE_REQUIRES_NOTE", False)
    payload = request or UnfreezeRequest()
    if require_note and not payload.approval_note.strip():
        raise HTTPException(status_code=400, detail="approval note required")
    if not STORE.unfreeze(token):
        raise HTTPException(status_code=404, detail="account not found")
    detail = payload.reason
    if payload.approval_note.strip():
        detail = f"{detail}; approval_note={payload.approval_note.strip()}"
    STORE.record_policy_event(token, "admin_unfreeze", detail, actor="admin", severity="low")
    account = STORE.account_info(token)
    assert account is not None
    return account


@app.get("/v1/admin/accounts/{token}/events", response_model=list[PolicyEvent], dependencies=[Depends(admin_guard)])
def admin_events(token: str, limit: int = 100) -> list[PolicyEvent]:
    account = STORE.account_info(token)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return STORE.policy_events(token, limit=limit)


@app.get("/v1/admin/accounts/{token}/usage/summary", response_model=UsageSummaryResponse, dependencies=[Depends(admin_guard)])
def admin_account_usage_summary(
    token: str,
    window: Literal["24h", "7d", "30d", "all"] = "all",
) -> UsageSummaryResponse:
    account = STORE.account_info(token)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return UsageSummaryResponse.model_validate(STORE.usage_summary(token, window=window))


@app.get("/v1/admin/accounts/{token}/dashboard/overview", response_model=DashboardOverviewResponse, dependencies=[Depends(admin_guard)])
def admin_account_dashboard_overview(token: str, response: Response) -> DashboardOverviewResponse:
    account = STORE.account_info(token)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    response.headers["X-TokenPatch-Schema-Version"] = DASHBOARD_SCHEMA_VERSION
    return build_dashboard_overview(token)


@app.get("/v1/admin/events/export", dependencies=[Depends(admin_guard)])
def admin_export_events_csv(
    token: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    actor: str | None = None,
    since: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    cursor: int | None = None,
    limit: int = 1000,
) -> Response:
    if token and STORE.account_info(token) is None:
        raise HTTPException(status_code=404, detail="account not found")
    # Incremental export contract:
    # - first pull can use since/created_from
    # - when cursor is provided and > 0, cursor takes precedence over since/created_from
    effective_created_from = created_from or since
    if cursor is not None and cursor > 0:
        effective_created_from = None

    rows = STORE.query_policy_event_rows(
        token=token,
        event_type=event_type,
        severity=severity,
        actor=actor,
        created_from=effective_created_from,
        created_to=created_to,
        cursor=cursor,
        ascending=cursor is not None,
        limit=limit,
    )
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["event_id", "token", "event_type", "detail", "request_id", "actor", "severity", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row.get("id", ""),
                row.get("token", ""),
                row.get("event_type", ""),
                row.get("detail", ""),
                row.get("request_id", ""),
                row.get("actor", ""),
                row.get("severity", ""),
                row.get("created_at", ""),
            ]
        )
    filename = "policy-events.csv" if not token else f"policy-events-{token}.csv"
    response_headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if cursor is not None:
        next_cursor = str(max(int(row["id"]) for row in rows)) if rows else ""
        response_headers["X-MMDEV-Next-Cursor"] = next_cursor
    if cursor is not None and cursor > 0 and (since or created_from):
        response_headers["X-MMDEV-Filter-Note"] = "cursor takes precedence over since/created_from"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers=response_headers,
    )


@app.get("/v1/admin/events/summary", response_model=EventSummaryResponse, dependencies=[Depends(admin_guard)])
def admin_events_summary(
    token: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    actor: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
) -> EventSummaryResponse:
    if token and STORE.account_info(token) is None:
        raise HTTPException(status_code=404, detail="account not found")
    summary = STORE.policy_event_summary(
        token=token,
        event_type=event_type,
        severity=severity,
        actor=actor,
        created_from=created_from,
        created_to=created_to,
    )
    return EventSummaryResponse.model_validate(summary)


@app.get("/v1/admin/events/trend", response_model=EventTrendResponse, dependencies=[Depends(admin_guard)])
def admin_events_trend(
    bucket: Literal["hour", "day"] = "day",
    token: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    actor: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    limit: int = 365,
) -> EventTrendResponse:
    if token and STORE.account_info(token) is None:
        raise HTTPException(status_code=404, detail="account not found")
    trend = STORE.policy_event_trend(
        bucket=bucket,
        token=token,
        event_type=event_type,
        severity=severity,
        actor=actor,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
    )
    return EventTrendResponse.model_validate(trend)


@app.post("/v1/executor/run", response_model=ExecutorRunResponse)
def executor_run(
    request: ExecutorRunRequest,
    auth: Annotated[tuple[str, Account], Depends(current_account)],
    country: Annotated[str | None, Header(alias="X-MMDEV-Country")] = None,
    entity: Annotated[str | None, Header(alias="X-MMDEV-Entity")] = None,
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> ExecutorRunResponse:
    token, account = auth
    if account.status != "active":
        STORE.record_policy_event(
            token,
            "account_not_active",
            f"status={account.status}",
            request_id=request_id,
            actor="system",
            severity="medium",
        )
        raise HTTPException(status_code=403, detail="account is not active")
    if request.protocol != "mmdev.executor.v1":
        raise HTTPException(status_code=400, detail="unsupported protocol")
    enforce_compliance_guardrails(token, country=country, entity=entity, request_id=request_id)
    max_prompt_chars = POLICY.get_int("MMDEV_GATEWAY_MAX_PROMPT_CHARS", 120000)
    if len(request.prompt) > max_prompt_chars:
        raise HTTPException(status_code=413, detail="prompt too large")

    data, usage = run_executor(request)
    enforce_usage_guardrails(token, data, usage, request_id=request_id)
    charged_credits, provider_cost = calculate_charge(usage)
    result = ExecutorRunResponse(
        task_id=str(uuid.uuid4()),
        patch=data["patch"],
        changed_files=data.get("changed_files", []),
        summary=data.get("summary", ""),
        risks=data.get("risks", []),
        verification_hint=data.get("verification_hint", ""),
        needs_human_input=data.get("needs_human_input", False),
        usage=usage,
        charged_credits=charged_credits,
        provider_cost=provider_cost,
    )
    enforce_credit_guardrails(token, account, charged_credits, request_id=request_id)
    if not STORE.charge_and_record(token, result):
        raise HTTPException(status_code=402, detail="insufficient credits")
    return result


def enforce_usage_guardrails(token: str, data: dict, usage: UsagePayload, request_id: str | None = None) -> None:
    patch = data.get("patch", "")
    max_patch_chars = POLICY.get_int("MMDEV_GATEWAY_MAX_PATCH_CHARS", 0)
    if max_patch_chars > 0 and len(patch) > max_patch_chars:
        record_violation(token, "patch_too_large", f"patch chars={len(patch)} > limit={max_patch_chars}", request_id=request_id)
        maybe_freeze(token, "policy-patch-too-large")
        raise HTTPException(status_code=413, detail="patch too large")

    total_tokens = usage.input_tokens + usage.output_tokens
    max_total_tokens = POLICY.get_int("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", 0)
    if max_total_tokens > 0 and total_tokens > max_total_tokens:
        record_violation(token, "request_tokens_too_high", f"tokens={total_tokens} > limit={max_total_tokens}", request_id=request_id)
        maybe_freeze(token, "policy-request-tokens-too-high")
        raise HTTPException(status_code=429, detail="request token usage too high")

    daily_limit = POLICY.get_int("MMDEV_GATEWAY_DAILY_TOKEN_LIMIT", 0)
    if daily_limit > 0:
        today_total = STORE.daily_token_total(token)
        if today_total + total_tokens > daily_limit:
            record_violation(token, "daily_limit_exceeded", f"today+request={today_total + total_tokens} > limit={daily_limit}", request_id=request_id)
            maybe_freeze(token, "policy-daily-limit-exceeded")
            raise HTTPException(status_code=429, detail="daily token limit exceeded")

    monthly_limit = POLICY.get_int("MMDEV_GATEWAY_MONTHLY_TOKEN_LIMIT", 0)
    if monthly_limit > 0:
        month_total = STORE.monthly_token_total(token)
        if month_total + total_tokens > monthly_limit:
            record_violation(token, "monthly_limit_exceeded", f"month+request={month_total + total_tokens} > limit={monthly_limit}", request_id=request_id)
            maybe_freeze(token, "policy-monthly-limit-exceeded")
            raise HTTPException(status_code=429, detail="monthly token limit exceeded")


def run_executor(request: ExecutorRunRequest) -> tuple[dict, UsagePayload]:
    if POLICY.get_bool("MMDEV_GATEWAY_FAKE_EXECUTOR", False):
        return {
            "patch": POLICY.get_raw("MMDEV_GATEWAY_FAKE_PATCH", "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"),
            "changed_files": ["a.py"],
            "summary": "fake executor response",
            "risks": [],
            "verification_hint": "run validation",
            "needs_human_input": False,
        }, UsagePayload(input_tokens=100, output_tokens=50)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("DEEPSEEK_EXECUTOR_MODEL") or request.executor_model
    if not api_key or not model:
        raise HTTPException(status_code=500, detail="DeepSeek executor is not configured")
    return DeepSeekExecutor(api_key, base_url, model).run(
        request,
        timeout_seconds=POLICY.get_int("MMDEV_GATEWAY_REQUEST_TIMEOUT_SECONDS", 120),
    )


def enforce_credit_guardrails(token: str, account: Account, charged_credits: float, request_id: str | None = None) -> None:
    max_per_request = POLICY.get_float("MMDEV_GATEWAY_MAX_CHARGED_CREDITS_PER_REQUEST", 0)
    if max_per_request > 0 and charged_credits > max_per_request:
        record_violation(
            token,
            "charged_credits_too_high",
            f"charged_credits={charged_credits} > limit={max_per_request}",
            request_id=request_id,
        )
        maybe_freeze(token, "policy-charged-credits-too-high")
        raise HTTPException(status_code=429, detail="charged credits too high")

    max_ratio = POLICY.get_float("MMDEV_GATEWAY_MAX_CHARGE_TO_BALANCE_RATIO", 0)
    if max_ratio > 0 and account.credits > 0:
        ratio = charged_credits / account.credits
        if ratio > max_ratio:
            record_violation(
                token,
                "charge_to_balance_ratio_too_high",
                f"charge_to_balance_ratio={ratio:.6f} > limit={max_ratio}",
                request_id=request_id,
            )
            maybe_freeze(token, "policy-charge-to-balance-ratio-too-high")
            raise HTTPException(status_code=429, detail="charge to balance ratio too high")

    daily_credits_limit = POLICY.get_float("MMDEV_GATEWAY_DAILY_CREDITS_LIMIT", 0)
    if daily_credits_limit > 0:
        daily_total = STORE.daily_credits_total(token)
        if daily_total + charged_credits > daily_credits_limit:
            record_violation(
                token,
                "daily_credits_limit_exceeded",
                f"today+request={daily_total + charged_credits} > limit={daily_credits_limit}",
                request_id=request_id,
            )
            maybe_freeze(token, "policy-daily-credits-limit-exceeded")
            raise HTTPException(status_code=429, detail="daily credits limit exceeded")

    monthly_credits_limit = POLICY.get_float("MMDEV_GATEWAY_MONTHLY_CREDITS_LIMIT", 0)
    if monthly_credits_limit > 0:
        monthly_total = STORE.monthly_credits_total(token)
        if monthly_total + charged_credits > monthly_credits_limit:
            record_violation(
                token,
                "monthly_credits_limit_exceeded",
                f"month+request={monthly_total + charged_credits} > limit={monthly_credits_limit}",
                request_id=request_id,
            )
            maybe_freeze(token, "policy-monthly-credits-limit-exceeded")
            raise HTTPException(status_code=429, detail="monthly credits limit exceeded")


def calculate_charge(usage: UsagePayload) -> tuple[float, float]:
    input_rate = POLICY.get_float("MMDEV_GATEWAY_INPUT_COST_PER_MILLION", 0)
    output_rate = POLICY.get_float("MMDEV_GATEWAY_OUTPUT_COST_PER_MILLION", 0)
    markup = POLICY.get_float("MMDEV_GATEWAY_MARKUP_MULTIPLIER", 1.0)
    provider_cost = ((usage.input_tokens * input_rate) + (usage.output_tokens * output_rate)) / 1_000_000
    charged_credits = provider_cost * markup
    minimum = POLICY.get_float("MMDEV_GATEWAY_MIN_CHARGE_CREDITS", 0)
    return max(charged_credits, minimum), provider_cost


def build_dashboard_overview(token: str) -> DashboardOverviewResponse:
    balance_credits = STORE.balance(token)
    usage_7d = UsageSummaryResponse.model_validate(STORE.usage_summary(token, window="7d"))
    usage_30d = UsageSummaryResponse.model_validate(STORE.usage_summary(token, window="30d"))
    return DashboardOverviewResponse(
        schema_version=DASHBOARD_SCHEMA_VERSION,
        token=token,
        balance_credits=balance_credits,
        generated_at=datetime.now(timezone.utc).isoformat(),
        usage_7d=usage_7d,
        usage_30d=usage_30d,
        savings_estimate_7d=build_savings_estimate(usage_7d),
        savings_estimate_30d=build_savings_estimate(usage_30d),
    )


def build_savings_estimate(usage: UsageSummaryResponse) -> SavingsEstimate:
    baseline_input_rate = POLICY.get_float("MMDEV_GATEWAY_BASELINE_STRONG_INPUT_COST_PER_MILLION", 0)
    baseline_output_rate = POLICY.get_float("MMDEV_GATEWAY_BASELINE_STRONG_OUTPUT_COST_PER_MILLION", 0)
    baseline_cost = ((usage.input_tokens * baseline_input_rate) + (usage.output_tokens * baseline_output_rate)) / 1_000_000
    savings_vs_charged = baseline_cost - usage.charged_credits
    savings_vs_provider = baseline_cost - usage.provider_cost
    savings_ratio_vs_charged = (savings_vs_charged / baseline_cost * 100.0) if baseline_cost > 0 else 0.0
    savings_ratio_vs_provider = (savings_vs_provider / baseline_cost * 100.0) if baseline_cost > 0 else 0.0
    return SavingsEstimate(
        window=usage.window if usage.window in {"7d", "30d"} else "7d",
        baseline_strong_cost=baseline_cost,
        actual_charged_credits=usage.charged_credits,
        provider_cost=usage.provider_cost,
        savings_vs_charged=savings_vs_charged,
        savings_vs_provider=savings_vs_provider,
        savings_ratio_vs_charged=savings_ratio_vs_charged,
        savings_ratio_vs_provider=savings_ratio_vs_provider,
    )


def maybe_freeze(token: str, reason: str) -> None:
    if POLICY.get_bool("MMDEV_GATEWAY_FREEZE_ON_POLICY_VIOLATION", False):
        STORE.freeze(token, reason=reason, level=infer_freeze_level(reason))


def record_violation(token: str, event_type: str, detail: str, request_id: str | None = None) -> None:
    STORE.record_policy_event(
        token,
        event_type,
        detail,
        request_id=request_id,
        actor="system",
        severity="high",
    )


def enforce_compliance_guardrails(token: str, *, country: str | None, entity: str | None, request_id: str | None = None) -> None:
    normalized_country = (country or "").strip().upper()
    normalized_entity = (entity or "").strip().lower()
    require_metadata = POLICY.get_bool("MMDEV_GATEWAY_REQUIRE_COMPLIANCE_METADATA", False)
    if require_metadata and (not normalized_country or not normalized_entity):
        record_violation(token, "compliance_metadata_missing", "missing country or entity metadata", request_id=request_id)
        maybe_freeze(token, "policy-compliance-metadata-missing")
        raise HTTPException(status_code=400, detail="compliance metadata required")

    blocked_countries = POLICY.get_csv_set("MMDEV_GATEWAY_BLOCKED_COUNTRIES", upper=True)
    if normalized_country and normalized_country in blocked_countries:
        record_violation(token, "country_blocked", f"country={normalized_country}", request_id=request_id)
        maybe_freeze(token, "policy-country-blocked")
        raise HTTPException(status_code=403, detail="country is blocked")

    allowed_countries = POLICY.get_csv_set("MMDEV_GATEWAY_ALLOWED_COUNTRIES", upper=True)
    if normalized_country and allowed_countries and normalized_country not in allowed_countries:
        record_violation(token, "country_not_allowed", f"country={normalized_country}", request_id=request_id)
        maybe_freeze(token, "policy-country-not-allowed")
        raise HTTPException(status_code=403, detail="country is not allowed")

    blocked_entities = POLICY.get_csv_set("MMDEV_GATEWAY_BLOCKED_ENTITIES", upper=False)
    if normalized_entity and normalized_entity in blocked_entities:
        record_violation(token, "entity_blocked", f"entity={normalized_entity}", request_id=request_id)
        maybe_freeze(token, "policy-entity-blocked")
        raise HTTPException(status_code=403, detail="entity is blocked")


def infer_freeze_level(reason: str) -> str:
    normalized = reason.lower()
    if any(key in normalized for key in ("country", "entity", "sanction")):
        return "critical"
    if any(key in normalized for key in ("credits", "tokens", "limit")):
        return "high"
    return "medium"
