import argparse
import json
from pathlib import Path

import httpx
import pytest

from gateway.scripts import sync_events


def make_response(status: int, text: str, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        request=httpx.Request("GET", "https://gateway.example.test/v1/admin/events/export"),
        text=text,
        headers=headers or {},
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.sent_headers = []

    def get(self, url, headers, params):
        self.calls += 1
        self.sent_headers.append(dict(headers))
        if not self.responses:
            raise RuntimeError("no more fake responses")
        return self.responses.pop(0)


class FakeClientContext:
    def __init__(self, responses):
        self.client = FakeClient(responses)

    def __call__(self, timeout=30):
        return self

    def __enter__(self):
        return self.client

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_page_with_retry_retries_on_429(tmp_path):
    client = FakeClient(
        [
            make_response(429, "rate limited"),
            make_response(200, "event_id,token,event_type,detail,actor,severity,created_at\n1,t,e,d,a,s,c\n"),
        ]
    )
    sleeps = []
    log_path = tmp_path / "sync.log"

    response = sync_events.fetch_page_with_retry(
        client=client,
        url="https://gateway.example.test/v1/admin/events/export",
        headers={"Authorization": "Bearer admin"},
        params={"cursor": 0, "limit": 100},
        retries=2,
        backoff_seconds=0.1,
        max_backoff_seconds=1.0,
        sleep_fn=lambda seconds: sleeps.append(seconds),
        log_path=log_path,
    )

    assert response.status_code == 200
    assert client.calls == 2
    assert sleeps == [0.1]
    assert "retry=1/2" in log_path.read_text(encoding="utf-8")


def test_fetch_page_with_retry_does_not_retry_on_400(tmp_path):
    client = FakeClient([make_response(400, "bad request")])
    sleeps = []

    with pytest.raises(httpx.HTTPStatusError):
        sync_events.fetch_page_with_retry(
            client=client,
            url="https://gateway.example.test/v1/admin/events/export",
            headers={"Authorization": "Bearer admin"},
            params={"cursor": 0, "limit": 100},
            retries=3,
            backoff_seconds=0.1,
            max_backoff_seconds=1.0,
            sleep_fn=lambda seconds: sleeps.append(seconds),
            log_path=tmp_path / "sync.log",
        )

    assert client.calls == 1
    assert sleeps == []


def test_run_sync_updates_cursor_and_logs(monkeypatch, tmp_path):
    responses = [
        make_response(
            200,
            "event_id,token,event_type,detail,actor,severity,created_at\n1,t,a,d,system,high,2026-01-01 00:00:00\n",
            {"X-MMDEV-Next-Cursor": "1"},
        ),
        make_response(
            200,
            "event_id,token,event_type,detail,actor,severity,created_at\n2,t,b,d,admin,low,2026-01-01 00:01:00\n",
            {},
        ),
    ]
    monkeypatch.setattr(sync_events.httpx, "Client", FakeClientContext(responses))

    output = tmp_path / "events.csv"
    cursor_file = tmp_path / "cursor.txt"
    log_file = tmp_path / "sync.log"
    args = argparse.Namespace(
        base_url="https://gateway.example.test",
        admin_token="admin-token",
        output=str(output),
        cursor_file=str(cursor_file),
        token="",
        event_type="",
        severity="",
        actor="",
        since="",
        limit=100,
        max_pages=5,
        retries=2,
        backoff_seconds=0.1,
        max_backoff_seconds=1.0,
        log_file=str(log_file),
        state_file=str(tmp_path / "state.json"),
        metrics_file=str(tmp_path / "metrics.jsonl"),
        metrics_tags="env=test,region=local",
        request_id_header="X-Request-ID",
        request_id_prefix="mmdev-sync",
        dedupe_event_id=True,
        dedupe_scan_limit=0,
    )

    summary = sync_events.run_sync(args, sleep_fn=lambda _: None)

    assert summary["wrote_rows"] == 2
    assert summary["cursor"] == 1
    assert output.read_text(encoding="utf-8").count("\n") == 3
    assert cursor_file.read_text(encoding="utf-8").strip() == "1"
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["last_cursor"] == 1
    assert state["last_rows_written"] == 2
    assert state["total_rows_written"] == 2
    assert state["last_success_at"]
    assert state["last_error"] == ""
    metrics_lines = (tmp_path / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(metrics_lines) == 1
    metric = json.loads(metrics_lines[0])
    assert metric["status"] == "ok"
    assert metric["wrote_rows"] == 2
    assert metric["tags"] == {"env": "test", "region": "local"}
    logs = log_file.read_text(encoding="utf-8")
    assert "sync start" in logs
    assert "sync done" in logs


def test_run_sync_skips_duplicate_event_ids(monkeypatch, tmp_path):
    output = tmp_path / "events.csv"
    output.write_text(
        "event_id,token,event_type,detail,actor,severity,created_at\n"
        "1,t,a,d,system,high,2026-01-01 00:00:00\n",
        encoding="utf-8",
    )
    responses = [
        make_response(
            200,
            "event_id,token,event_type,detail,actor,severity,created_at\n"
            "1,t,a,d,system,high,2026-01-01 00:00:00\n"
            "2,t,b,d,admin,low,2026-01-01 00:01:00\n",
            {},
        ),
    ]
    monkeypatch.setattr(sync_events.httpx, "Client", FakeClientContext(responses))

    args = argparse.Namespace(
        base_url="https://gateway.example.test",
        admin_token="admin-token",
        output=str(output),
        cursor_file=str(tmp_path / "cursor.txt"),
        token="",
        event_type="",
        severity="",
        actor="",
        since="",
        limit=100,
        max_pages=5,
        retries=2,
        backoff_seconds=0.1,
        max_backoff_seconds=1.0,
        log_file=str(tmp_path / "sync.log"),
        state_file=str(tmp_path / "state.json"),
        metrics_file=str(tmp_path / "metrics.jsonl"),
        metrics_tags="env=test",
        request_id_header="X-Request-ID",
        request_id_prefix="mmdev-sync",
        dedupe_event_id=True,
        dedupe_scan_limit=0,
    )

    summary = sync_events.run_sync(args, sleep_fn=lambda _: None)
    assert summary["wrote_rows"] == 1
    assert summary["skipped_duplicates"] == 1
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_run_sync_failure_updates_state(monkeypatch, tmp_path):
    responses = [make_response(500, "server error")]
    monkeypatch.setattr(sync_events.httpx, "Client", FakeClientContext(responses))
    state_file = tmp_path / "state.json"

    args = argparse.Namespace(
        base_url="https://gateway.example.test",
        admin_token="admin-token",
        output=str(tmp_path / "events.csv"),
        cursor_file=str(tmp_path / "cursor.txt"),
        token="",
        event_type="",
        severity="",
        actor="",
        since="",
        limit=100,
        max_pages=1,
        retries=0,
        backoff_seconds=0.1,
        max_backoff_seconds=1.0,
        log_file=str(tmp_path / "sync.log"),
        state_file=str(state_file),
        metrics_file=str(tmp_path / "metrics.jsonl"),
        metrics_tags="env=test",
        request_id_header="X-Request-ID",
        request_id_prefix="mmdev-sync",
        dedupe_event_id=True,
        dedupe_scan_limit=0,
    )

    with pytest.raises(httpx.HTTPStatusError):
        sync_events.run_sync(args, sleep_fn=lambda _: None)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["last_error"]
    assert state["last_error_at"]
    assert state["last_cursor"] == 0
    metrics_lines = (tmp_path / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(metrics_lines) == 1
    metric = json.loads(metrics_lines[0])
    assert metric["status"] == "error"
    assert metric["error_type"] == "HTTPStatusError"
    assert metric["tags"] == {"env": "test"}


def test_parse_metrics_tags_ignores_invalid_parts():
    tags = sync_events.parse_metrics_tags("env=prod,invalid,region=sg,=oops, k = v ")
    assert tags == {"env": "prod", "region": "sg", "k": "v"}


def test_fetch_page_with_retry_sets_request_id_header(tmp_path):
    client = FakeClient(
        [
            make_response(500, "server error"),
            make_response(200, "event_id,token,event_type,detail,actor,severity,created_at\n1,t,e,d,a,s,c\n"),
        ]
    )
    sync_events.fetch_page_with_retry(
        client=client,
        url="https://gateway.example.test/v1/admin/events/export",
        headers={"Authorization": "Bearer admin"},
        params={"cursor": 0, "limit": 100},
        retries=1,
        backoff_seconds=0.0,
        max_backoff_seconds=0.0,
        sleep_fn=lambda _: None,
        log_path=tmp_path / "sync.log",
        request_id_header="X-Request-ID",
        request_id_prefix="unit",
        page_index=3,
    )
    assert len(client.sent_headers) == 2
    for header in client.sent_headers:
        assert "X-Request-ID" in header
        assert header["X-Request-ID"].startswith("unit-")
