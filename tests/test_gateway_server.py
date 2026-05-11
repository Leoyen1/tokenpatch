import importlib
import time

from fastapi.testclient import TestClient


def load_app(monkeypatch, tmp_path, tokens: str = "test-token", default_account_status: str = "active"):
    monkeypatch.setenv("MMDEV_GATEWAY_TOKENS", tokens)
    monkeypatch.setenv("MMDEV_GATEWAY_ADMIN_TOKENS", "admin-token")
    monkeypatch.setenv("MMDEV_GATEWAY_STARTING_CREDITS", "1")
    monkeypatch.setenv("MMDEV_GATEWAY_DEFAULT_ACCOUNT_STATUS", default_account_status)
    monkeypatch.setenv("MMDEV_GATEWAY_DB_PATH", str(tmp_path / "gateway.sqlite"))
    monkeypatch.setenv("MMDEV_GATEWAY_FAKE_EXECUTOR", "1")
    monkeypatch.setenv("MMDEV_GATEWAY_INPUT_COST_PER_MILLION", "1000")
    monkeypatch.setenv("MMDEV_GATEWAY_OUTPUT_COST_PER_MILLION", "1000")
    monkeypatch.setenv("MMDEV_GATEWAY_MARKUP_MULTIPLIER", "2")
    module = importlib.import_module("gateway.mmdev_gateway.app")
    return importlib.reload(module).app


def auth():
    return {"Authorization": "Bearer test-token"}


def admin_auth():
    return {"Authorization": "Bearer admin-token"}


def test_gateway_executor_run_charges_credits_and_records_usage(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))
    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["patch"]
    assert payload["charged_credits"] > 0

    balance = client.get("/v1/balance", headers=auth()).json()
    assert balance["credits"] < 1
    usage = client.get("/v1/usage", headers=auth()).json()
    assert usage[0]["task_id"] == payload["task_id"]


def test_gateway_rejects_missing_auth(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))
    response = client.get("/v1/balance")
    assert response.status_code == 401


def test_gateway_persists_balance_and_usage_across_reload(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))
    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 200
    first_balance = client.get("/v1/balance", headers=auth()).json()["credits"]

    reloaded = TestClient(load_app(monkeypatch, tmp_path))
    assert reloaded.get("/v1/balance", headers=auth()).json()["credits"] == first_balance
    assert len(reloaded.get("/v1/usage", headers=auth()).json()) == 1


def test_gateway_rejects_request_when_token_usage_too_high(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "120")
    client = TestClient(load_app(monkeypatch, tmp_path))
    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 429
    assert "token usage too high" in response.text


def test_gateway_rejects_request_when_daily_limit_exceeded(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_DAILY_TOKEN_LIMIT", "200")
    client = TestClient(load_app(monkeypatch, tmp_path))

    first = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert second.status_code == 429
    assert "daily token limit exceeded" in second.text


def test_gateway_rejects_request_when_monthly_limit_exceeded(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MONTHLY_TOKEN_LIMIT", "200")
    client = TestClient(load_app(monkeypatch, tmp_path))

    first = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert second.status_code == 429
    assert "monthly token limit exceeded" in second.text


def test_gateway_freezes_account_on_policy_violation_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "120")
    monkeypatch.setenv("MMDEV_GATEWAY_FREEZE_ON_POLICY_VIOLATION", "1")
    client = TestClient(load_app(monkeypatch, tmp_path))

    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 429

    after = client.get("/v1/balance", headers=auth())
    assert after.status_code == 403


def test_gateway_admin_endpoints_require_admin_token(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))

    missing = client.get("/v1/admin/accounts")
    assert missing.status_code == 401

    wrong = client.get("/v1/admin/accounts", headers=auth())
    assert wrong.status_code == 403


def test_gateway_admin_can_manage_account_state(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))

    accounts = client.get("/v1/admin/accounts", headers=admin_auth())
    assert accounts.status_code == 200
    assert any(item["token"] == "test-token" for item in accounts.json())

    set_credits = client.post(
        "/v1/admin/accounts/test-token/credits/set",
        headers=admin_auth(),
        json={"credits": 9.5},
    )
    assert set_credits.status_code == 200
    assert set_credits.json()["credits"] == 9.5

    freeze = client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-check", "level": "high", "note": "suspicious pattern"},
    )
    assert freeze.status_code == 200
    assert freeze.json()["frozen"] is True
    assert freeze.json()["freeze_reason"] == "manual-check"
    assert freeze.json()["freeze_level"] == "high"

    blocked = client.get("/v1/balance", headers=auth())
    assert blocked.status_code == 403

    unfreeze = client.post("/v1/admin/accounts/test-token/unfreeze", headers=admin_auth())
    assert unfreeze.status_code == 200
    assert unfreeze.json()["frozen"] is False

    balance = client.get("/v1/balance", headers=auth())
    assert balance.status_code == 200
    assert balance.json()["credits"] == 9.5


def test_gateway_invited_account_cannot_run_until_activated(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, default_account_status="invited"))

    denied = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert denied.status_code == 403
    assert "account is not active" in denied.text

    activated = client.post(
        "/v1/admin/accounts/test-token/profile",
        headers=admin_auth(),
        json={"owner_id": "u-001", "email": "user@example.com", "status": "active"},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert activated.json()["owner_id"] == "u-001"

    ok = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert ok.status_code == 200


def test_gateway_admin_manual_topup_records_audit_ledger(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))
    topped = client.post(
        "/v1/admin/accounts/test-token/credits/manual-topup",
        headers=admin_auth() | {"X-Request-ID": "topup-req-1"},
        json={"credits": 5.0, "reason": "invite-beta-manual-topup"},
    )
    assert topped.status_code == 200
    payload = topped.json()
    assert payload["before_credits"] == 1.0
    assert payload["after_credits"] == 6.0
    assert payload["request_id"] == "topup-req-1"
    assert payload["operator"] == "admin-token"

    balance = client.get("/v1/balance", headers=auth())
    assert balance.status_code == 200
    assert balance.json()["credits"] == 6.0

    topups = client.get("/v1/admin/accounts/test-token/topups", headers=admin_auth())
    assert topups.status_code == 200
    assert len(topups.json()) == 1
    assert topups.json()[0]["reason"] == "invite-beta-manual-topup"


def test_gateway_usage_summary_window(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))

    run = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert run.status_code == 200

    summary = client.get("/v1/usage/summary", headers=auth(), params={"window": "24h"})
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["window"] == "24h"
    assert payload["calls"] == 1
    assert payload["input_tokens"] == 100
    assert payload["output_tokens"] == 50
    assert payload["total_tokens"] == 150

    admin_summary = client.get(
        "/v1/admin/accounts/test-token/usage/summary",
        headers=admin_auth(),
        params={"window": "all"},
    )
    assert admin_summary.status_code == 200
    assert admin_summary.json()["calls"] == 1


def test_gateway_dashboard_overview_includes_balance_usage_and_savings(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_BASELINE_STRONG_INPUT_COST_PER_MILLION", "10000")
    monkeypatch.setenv("MMDEV_GATEWAY_BASELINE_STRONG_OUTPUT_COST_PER_MILLION", "10000")
    client = TestClient(load_app(monkeypatch, tmp_path))

    run = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert run.status_code == 200

    overview = client.get("/v1/dashboard/overview", headers=auth())
    assert overview.status_code == 200
    assert overview.headers.get("X-TokenPatch-Schema-Version") == "2026-05-11.v1"
    payload = overview.json()
    assert payload["schema_version"] == "2026-05-11.v1"
    assert payload["token"] == "test-token"
    assert payload["balance_credits"] < 1.0
    assert payload["generated_at"]
    assert payload["usage_7d"]["calls"] == 1
    assert payload["usage_30d"]["calls"] == 1
    assert payload["savings_estimate_7d"]["window"] == "7d"
    assert payload["savings_estimate_30d"]["window"] == "30d"
    assert payload["savings_estimate_7d"]["baseline_strong_cost"] > 0

    admin_overview = client.get("/v1/admin/accounts/test-token/dashboard/overview", headers=admin_auth())
    assert admin_overview.status_code == 200
    assert admin_overview.headers.get("X-TokenPatch-Schema-Version") == "2026-05-11.v1"
    assert admin_overview.json()["token"] == "test-token"


def test_gateway_manual_topup_requires_admin_token(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path))
    response = client.post(
        "/v1/admin/accounts/test-token/credits/manual-topup",
        headers=auth(),
        json={"credits": 1.0, "reason": "x"},
    )
    assert response.status_code == 403


def test_gateway_admin_events_include_policy_and_admin_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "120")
    monkeypatch.setenv("MMDEV_GATEWAY_FREEZE_ON_POLICY_VIOLATION", "1")
    client = TestClient(load_app(monkeypatch, tmp_path))

    violation = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert violation.status_code == 429

    client.post("/v1/admin/accounts/test-token/unfreeze", headers=admin_auth())
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-audit"},
    )

    events = client.get("/v1/admin/accounts/test-token/events", headers=admin_auth())
    assert events.status_code == 200
    event_types = [item["event_type"] for item in events.json()]
    admin_freeze_event = next(item for item in events.json() if item["event_type"] == "admin_freeze")
    assert admin_freeze_event["actor"] == "admin"
    assert admin_freeze_event["severity"] == "medium"
    assert "request_tokens_too_high" in event_types
    assert "admin_unfreeze" in event_types
    assert "admin_freeze" in event_types


def test_gateway_requires_compliance_metadata_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_REQUIRE_COMPLIANCE_METADATA", "1")
    client = TestClient(load_app(monkeypatch, tmp_path))

    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 400
    assert "compliance metadata required" in response.text


def test_gateway_rejects_blocked_country(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_BLOCKED_COUNTRIES", "IR,KP")
    client = TestClient(load_app(monkeypatch, tmp_path))

    headers = auth() | {"X-MMDEV-Country": "IR"}
    response = client.post(
        "/v1/executor/run",
        headers=headers,
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 403
    assert "country is blocked" in response.text


def test_gateway_rejects_blocked_entity(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_BLOCKED_ENTITIES", "bad-actor,blocked-org")
    client = TestClient(load_app(monkeypatch, tmp_path))

    headers = auth() | {"X-MMDEV-Entity": "blocked-org"}
    response = client.post(
        "/v1/executor/run",
        headers=headers,
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 403
    assert "entity is blocked" in response.text


def test_gateway_rejects_when_charged_credits_too_high(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_CHARGED_CREDITS_PER_REQUEST", "0.2")
    client = TestClient(load_app(monkeypatch, tmp_path))

    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 429
    assert "charged credits too high" in response.text


def test_gateway_rejects_when_daily_credits_limit_exceeded(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_DAILY_CREDITS_LIMIT", "0.4")
    client = TestClient(load_app(monkeypatch, tmp_path))

    first = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert second.status_code == 429
    assert "daily credits limit exceeded" in second.text


def test_gateway_echoes_request_id_and_records_it_in_policy_event(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "120")
    client = TestClient(load_app(monkeypatch, tmp_path))
    headers = auth() | {"X-Request-ID": "req-123"}

    response = client.post(
        "/v1/executor/run",
        headers=headers,
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 429
    assert response.headers.get("X-Request-ID") == "req-123"

    events = client.get("/v1/admin/accounts/test-token/events", headers=admin_auth())
    assert events.status_code == 200
    violation = next(item for item in events.json() if item["event_type"] == "request_tokens_too_high")
    assert violation["request_id"] == "req-123"


def test_gateway_unfreeze_requires_approval_note_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_UNFREEZE_REQUIRES_NOTE", "1")
    client = TestClient(load_app(monkeypatch, tmp_path))

    frozen = client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-check", "level": "medium"},
    )
    assert frozen.status_code == 200

    missing_note = client.post("/v1/admin/accounts/test-token/unfreeze", headers=admin_auth())
    assert missing_note.status_code == 400
    assert "approval note required" in missing_note.text

    ok = client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ticket-123 approved"},
    )
    assert ok.status_code == 200
    assert ok.json()["frozen"] is False

    events = client.get("/v1/admin/accounts/test-token/events", headers=admin_auth())
    assert events.status_code == 200
    unfreeze_event = next(item for item in events.json() if item["event_type"] == "admin_unfreeze")
    assert unfreeze_event["actor"] == "admin"
    assert "ticket-123 approved" in unfreeze_event["detail"]


def test_gateway_policy_file_overrides_env(monkeypatch, tmp_path):
    policy_file = tmp_path / "policy.toml"
    policy_file.write_text("max_total_tokens_per_request = 120\n", encoding="utf-8")
    monkeypatch.setenv("MMDEV_GATEWAY_POLICY_PATH", str(policy_file))
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "999999")
    client = TestClient(load_app(monkeypatch, tmp_path))

    response = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert response.status_code == 429
    assert "token usage too high" in response.text


def test_gateway_policy_file_hot_reload(monkeypatch, tmp_path):
    policy_file = tmp_path / "policy.toml"
    policy_file.write_text("max_total_tokens_per_request = 200\n", encoding="utf-8")
    monkeypatch.setenv("MMDEV_GATEWAY_POLICY_PATH", str(policy_file))
    client = TestClient(load_app(monkeypatch, tmp_path))

    first = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert first.status_code == 200

    time.sleep(0.02)
    policy_file.write_text("max_total_tokens_per_request = 120\n", encoding="utf-8")

    second = client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    assert second.status_code == 429
    assert "token usage too high" in second.text


def test_gateway_admin_can_export_events_csv(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token,second-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "medium"},
    )
    client.post(
        "/v1/admin/accounts/second-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "high"},
    )

    exported = client.get("/v1/admin/events/export", headers=admin_auth())
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "event_id,token,event_type,detail,request_id,actor,severity,created_at" in exported.text
    assert ",test-token,admin_freeze" in exported.text
    assert ",second-token,admin_freeze" in exported.text


def test_gateway_admin_export_events_csv_supports_filters(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token,second-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "medium"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )
    client.post(
        "/v1/admin/accounts/second-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "high"},
    )

    filtered = client.get(
        "/v1/admin/events/export",
        headers=admin_auth(),
        params={"token": "test-token", "event_type": "admin_unfreeze"},
    )
    assert filtered.status_code == 200
    assert ",test-token,admin_unfreeze" in filtered.text
    assert ",second-token,admin_freeze" not in filtered.text
    assert ",test-token,admin_freeze" not in filtered.text


def test_gateway_admin_export_events_csv_supports_cursor(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "medium"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "high"},
    )

    first = client.get(
        "/v1/admin/events/export",
        headers=admin_auth(),
        params={"token": "test-token", "cursor": 0, "limit": 2},
    )
    assert first.status_code == 200
    assert "X-MMDEV-Next-Cursor" in first.headers
    next_cursor = first.headers["X-MMDEV-Next-Cursor"]
    assert next_cursor
    assert first.text.count("\n") == 3  # header + 2 rows

    second = client.get(
        "/v1/admin/events/export",
        headers=admin_auth(),
        params={"token": "test-token", "cursor": int(next_cursor), "limit": 10},
    )
    assert second.status_code == 200
    assert second.text.count("\n") == 2  # header + 1 row


def test_gateway_admin_export_events_cursor_takes_precedence_over_since(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "medium"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )

    first = client.get(
        "/v1/admin/events/export",
        headers=admin_auth(),
        params={"token": "test-token", "cursor": 0, "since": "9999-01-01 00:00:00", "limit": 10},
    )
    assert first.status_code == 200
    # cursor=0 still uses since filter as first-round guard, so no data rows
    assert first.text.count("\n") == 1

    second = client.get(
        "/v1/admin/events/export",
        headers=admin_auth(),
        params={"token": "test-token", "cursor": 1, "since": "9999-01-01 00:00:00", "limit": 10},
    )
    assert second.status_code == 200
    # cursor>0 ignores since/created_from and continues incrementally
    assert second.text.count("\n") >= 2
    assert second.headers.get("X-MMDEV-Filter-Note") == "cursor takes precedence over since/created_from"


def test_gateway_admin_events_summary_returns_aggregates(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token,second-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "high"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )
    client.post(
        "/v1/admin/accounts/second-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "critical"},
    )

    summary = client.get("/v1/admin/events/summary", headers=admin_auth())
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total"] == 3
    by_type = {item["name"]: item["count"] for item in payload["by_event_type"]}
    assert by_type["admin_freeze"] == 2
    assert by_type["admin_unfreeze"] == 1
    by_actor = {item["name"]: item["count"] for item in payload["by_actor"]}
    assert by_actor["admin"] == 3


def test_gateway_admin_events_summary_supports_filters(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token,second-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "high"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )
    client.post(
        "/v1/admin/accounts/second-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "critical"},
    )

    filtered = client.get(
        "/v1/admin/events/summary",
        headers=admin_auth(),
        params={"token": "test-token", "event_type": "admin_unfreeze"},
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] == 1
    by_type = {item["name"]: item["count"] for item in payload["by_event_type"]}
    assert by_type["admin_unfreeze"] == 1


def test_gateway_admin_events_summary_supports_severity_and_actor_filters(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "120")
    monkeypatch.setenv("MMDEV_GATEWAY_FREEZE_ON_POLICY_VIOLATION", "1")
    client = TestClient(load_app(monkeypatch, tmp_path))

    client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )

    filtered = client.get(
        "/v1/admin/events/summary",
        headers=admin_auth(),
        params={"severity": "high", "actor": "system"},
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] >= 1
    by_actor = {item["name"]: item["count"] for item in payload["by_actor"]}
    assert set(by_actor.keys()) == {"system"}
    by_severity = {item["name"]: item["count"] for item in payload["by_severity"]}
    assert set(by_severity.keys()) == {"high"}


def test_gateway_admin_events_trend_returns_bucketed_counts(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token,second-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "high"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )
    client.post(
        "/v1/admin/accounts/second-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "critical"},
    )

    trend = client.get("/v1/admin/events/trend", headers=admin_auth(), params={"bucket": "day"})
    assert trend.status_code == 200
    payload = trend.json()
    assert payload["bucket"] == "day"
    assert payload["total"] == 3
    assert len(payload["points"]) >= 1
    assert sum(point["count"] for point in payload["points"]) == 3


def test_gateway_admin_events_trend_supports_filters(monkeypatch, tmp_path):
    client = TestClient(load_app(monkeypatch, tmp_path, tokens="test-token,second-token"))
    client.post(
        "/v1/admin/accounts/test-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-a", "level": "high"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )
    client.post(
        "/v1/admin/accounts/second-token/freeze",
        headers=admin_auth(),
        json={"reason": "manual-b", "level": "critical"},
    )

    trend = client.get(
        "/v1/admin/events/trend",
        headers=admin_auth(),
        params={"bucket": "hour", "token": "test-token", "event_type": "admin_unfreeze"},
    )
    assert trend.status_code == 200
    payload = trend.json()
    assert payload["bucket"] == "hour"
    assert payload["total"] == 1
    assert sum(point["count"] for point in payload["points"]) == 1


def test_gateway_admin_events_trend_supports_severity_and_actor_filters(monkeypatch, tmp_path):
    monkeypatch.setenv("MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST", "120")
    monkeypatch.setenv("MMDEV_GATEWAY_FREEZE_ON_POLICY_VIOLATION", "1")
    client = TestClient(load_app(monkeypatch, tmp_path))

    client.post(
        "/v1/executor/run",
        headers=auth(),
        json={"protocol": "mmdev.executor.v1", "executor_model": "fake", "prompt": "bounded task"},
    )
    client.post(
        "/v1/admin/accounts/test-token/unfreeze",
        headers=admin_auth(),
        json={"reason": "manual-admin-unfreeze", "approval_note": "ok"},
    )

    trend = client.get(
        "/v1/admin/events/trend",
        headers=admin_auth(),
        params={"bucket": "day", "severity": "high", "actor": "system"},
    )
    assert trend.status_code == 200
    payload = trend.json()
    assert payload["bucket"] == "day"
    assert payload["total"] >= 1
    assert sum(point["count"] for point in payload["points"]) == payload["total"]
