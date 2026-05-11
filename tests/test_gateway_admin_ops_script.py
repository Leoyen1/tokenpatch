import json

from gateway.scripts import admin_ops


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, calls: list[dict], response_payload: dict):
        self.calls = calls
        self.response_payload = response_payload

    def request(self, method, url, headers=None, json=None, params=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "json": json,
                "params": params,
            }
        )
        return FakeResponse(self.response_payload)


class FakeClientContext:
    def __init__(self, calls: list[dict], response_payload: dict):
        self.client = FakeClient(calls, response_payload)

    def __call__(self, timeout=30):
        return self

    def __enter__(self):
        return self.client

    def __exit__(self, exc_type, exc, tb):
        return False


def test_activate_posts_profile(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        admin_ops.httpx,
        "Client",
        FakeClientContext(calls, {"status": "active", "owner_id": "u-1", "email": "u@example.com"}),
    )
    rc = admin_ops.main(
        [
            "--base-url",
            "https://gateway.example.test",
            "activate",
            "--admin-token",
            "admin-token",
            "--user-token",
            "user-token",
            "--owner-id",
            "u-1",
            "--email",
            "u@example.com",
        ]
    )
    assert rc == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/v1/admin/accounts/user-token/profile")
    assert call["headers"]["Authorization"] == "Bearer admin-token"
    assert call["json"]["status"] == "active"
    captured = capsys.readouterr().out.strip()
    assert json.loads(captured)["status"] == "active"


def test_manual_topup_sends_request_id(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        admin_ops.httpx,
        "Client",
        FakeClientContext(calls, {"after_credits": 11.0, "request_id": "req-1"}),
    )
    rc = admin_ops.main(
        [
            "--base-url",
            "https://gateway.example.test",
            "--pretty",
            "manual-topup",
            "--admin-token",
            "admin-token",
            "--user-token",
            "user-token",
            "--credits",
            "10",
            "--reason",
            "invite-beta-manual-topup",
            "--request-id",
            "req-1",
        ]
    )
    assert rc == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["url"].endswith("/v1/admin/accounts/user-token/credits/manual-topup")
    assert call["headers"]["X-Request-ID"] == "req-1"
    assert call["json"]["credits"] == 10.0
    captured = capsys.readouterr().out
    assert "\"after_credits\": 11.0" in captured


def test_usage_summary_queries_window(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        admin_ops.httpx,
        "Client",
        FakeClientContext(calls, {"window": "7d", "calls": 3, "charged_credits": 2.5}),
    )
    rc = admin_ops.main(
        [
            "--base-url",
            "https://gateway.example.test",
            "usage-summary",
            "--user-token",
            "user-token",
            "--window",
            "7d",
        ]
    )
    assert rc == 0
    call = calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/v1/usage/summary")
    assert call["params"]["window"] == "7d"
    captured = capsys.readouterr().out.strip()
    assert json.loads(captured)["charged_credits"] == 2.5


def test_dashboard_overview_queries_endpoint(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        admin_ops.httpx,
        "Client",
        FakeClientContext(
            calls,
            {
                "token": "user-token",
                "balance_credits": 9.0,
                "usage_7d": {"window": "7d", "calls": 1, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "charged_credits": 0.3, "provider_cost": 0.15},
                "usage_30d": {"window": "30d", "calls": 1, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "charged_credits": 0.3, "provider_cost": 0.15},
                "savings_estimate_7d": {
                    "window": "7d",
                    "baseline_strong_cost": 1.0,
                    "actual_charged_credits": 0.3,
                    "provider_cost": 0.15,
                    "savings_vs_charged": 0.7,
                    "savings_vs_provider": 0.85,
                    "savings_ratio_vs_charged": 70.0,
                    "savings_ratio_vs_provider": 85.0,
                },
                "savings_estimate_30d": {
                    "window": "30d",
                    "baseline_strong_cost": 1.0,
                    "actual_charged_credits": 0.3,
                    "provider_cost": 0.15,
                    "savings_vs_charged": 0.7,
                    "savings_vs_provider": 0.85,
                    "savings_ratio_vs_charged": 70.0,
                    "savings_ratio_vs_provider": 85.0,
                },
            },
        ),
    )
    rc = admin_ops.main(
        [
            "--base-url",
            "https://gateway.example.test",
            "dashboard-overview",
            "--user-token",
            "user-token",
        ]
    )
    assert rc == 0
    call = calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/v1/dashboard/overview")
    captured = capsys.readouterr().out.strip()
    assert json.loads(captured)["token"] == "user-token"
