from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import httpx
from pathlib import Path
import re
import sqlite3

from mmdev.reporter import read_run_events, summarize_auto_route_stats, summarize_strong_route_stats, summarize_usage_by_model_purpose
from mmdev.schemas import ModelUsage
from mmdev.state import state_path
from mmdev.usage import read_usage


def build_metrics(mmdev_dir: Path, window: str = "all") -> dict:
    window_start = parse_window_start(window)
    usage = read_usage_from_state(mmdev_dir, window_start)
    run_events = filter_run_events_by_window(read_run_events(mmdev_dir), window_start)
    usage_by_purpose = Counter(record.purpose for record in usage)

    total_input = sum(record.input_tokens for record in usage)
    total_output = sum(record.output_tokens for record in usage)
    total_cost = sum(record.estimated_cost for record in usage)
    total_credits = sum(record.charged_credits or 0 for record in usage)
    total_provider_cost = sum(record.provider_cost or 0 for record in usage)

    normalized_window = (window or "all").strip().lower() or "all"
    return {
        "window": {
            "spec": normalized_window,
            "started_at": window_start.isoformat() if window_start is not None else None,
        },
        "summary": {
            "model_calls": len(usage),
            "run_events": len(run_events),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "estimated_cost": total_cost,
            "charged_credits": total_credits,
            "provider_cost": total_provider_cost,
            "calls_by_purpose": {
                "plan": usage_by_purpose.get("plan", 0),
                "execute": usage_by_purpose.get("execute", 0),
                "review": usage_by_purpose.get("review", 0),
                "repair": usage_by_purpose.get("repair", 0),
            },
        },
        "usage_by_model_purpose": summarize_usage_by_model_purpose(usage),
        "strong_route_stats": summarize_strong_route_stats(run_events),
        "auto_route_stats": summarize_auto_route_stats(run_events),
    }


def parse_window_start(window: str) -> datetime | None:
    normalized = (window or "all").strip().lower() or "all"
    if normalized == "all":
        return None
    match = re.fullmatch(r"(\d+)([hd])", normalized)
    if not match:
        raise ValueError("window must be 'all' or <N>h/<N>d (e.g. 24h, 7d, 30d)")
    amount = int(match.group(1))
    unit = match.group(2)
    delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
    return datetime.now(timezone.utc) - delta


def read_usage_from_state(mmdev_dir: Path, window_start: datetime | None) -> list[ModelUsage]:
    db = state_path(mmdev_dir)
    if not db.exists():
        return read_usage(mmdev_dir)
    query = """
        select model, purpose, input_tokens, output_tokens, estimated_cost, duration_ms, charged_credits, provider_cost, created_at
        from model_usage
    """
    params: list[str] = []
    if window_start is not None:
        query += " where created_at >= ?"
        params.append(window_start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    query += " order by id asc"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [
        ModelUsage(
            model=str(row["model"]),
            purpose=str(row["purpose"]),
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
            estimated_cost=float(row["estimated_cost"]),
            duration_ms=int(row["duration_ms"]),
            charged_credits=float(row["charged_credits"]) if row["charged_credits"] is not None else None,
            provider_cost=float(row["provider_cost"]) if row["provider_cost"] is not None else None,
        )
        for row in rows
    ]


def filter_run_events_by_window(events: list[dict], window_start: datetime | None) -> list[dict]:
    if window_start is None:
        return events
    filtered: list[dict] = []
    for item in events:
        ts = parse_event_time(item.get("ts"))
        if ts is not None and ts >= window_start:
            filtered.append(item)
    return filtered


def parse_event_time(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def write_metrics_csvs(metrics: dict, csv_dir: Path, prefix: str | None = None) -> list[Path]:
    csv_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    normalized_prefix = (prefix or "").strip()
    filename_prefix = f"{normalized_prefix}-" if normalized_prefix else ""
    specs = [
        (
            f"{filename_prefix}usage_by_model_purpose.csv",
            "usage_by_model_purpose",
            ["purpose", "model", "calls", "input_tokens", "output_tokens", "estimated_cost"],
        ),
        (
            f"{filename_prefix}strong_route_stats.csv",
            "strong_route_stats",
            ["command", "provider", "model", "runs", "successes", "errors", "success_rate"],
        ),
        (
            f"{filename_prefix}auto_route_stats.csv",
            "auto_route_stats",
            [
                "provider",
                "planner_model",
                "reviewer_model",
                "executor_provider",
                "executor_model",
                "runs",
                "successes",
                "errors",
                "success_rate",
            ],
        ),
    ]
    for filename, key, columns in specs:
        rows = metrics.get(key) or []
        path = csv_dir / filename
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in columns})
        paths.append(path)
    return paths


def write_metrics_meta_csv(metrics: dict, csv_dir: Path, prefix: str | None = None) -> Path:
    csv_dir.mkdir(parents=True, exist_ok=True)
    normalized_prefix = (prefix or "").strip()
    filename_prefix = f"{normalized_prefix}-" if normalized_prefix else ""
    path = csv_dir / f"{filename_prefix}meta.csv"
    summary = metrics.get("summary", {})
    calls_by_purpose = summary.get("calls_by_purpose", {})
    row = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "window_spec": metrics.get("window", {}).get("spec"),
        "window_started_at": metrics.get("window", {}).get("started_at"),
        "model_calls": summary.get("model_calls", 0),
        "run_events": summary.get("run_events", 0),
        "input_tokens": summary.get("input_tokens", 0),
        "output_tokens": summary.get("output_tokens", 0),
        "estimated_cost": summary.get("estimated_cost", 0.0),
        "charged_credits": summary.get("charged_credits", 0.0),
        "provider_cost": summary.get("provider_cost", 0.0),
        "calls_plan": calls_by_purpose.get("plan", 0),
        "calls_execute": calls_by_purpose.get("execute", 0),
        "calls_review": calls_by_purpose.get("review", 0),
        "calls_repair": calls_by_purpose.get("repair", 0),
        "usage_rows": len(metrics.get("usage_by_model_purpose", []) or []),
        "strong_route_rows": len(metrics.get("strong_route_stats", []) or []),
        "auto_route_rows": len(metrics.get("auto_route_stats", []) or []),
    }
    columns = list(row.keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerow(row)
    return path


def push_metrics(
    metrics: dict,
    url: str,
    *,
    token: str | None = None,
    timeout_seconds: int = 20,
) -> int:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.post(url, json=metrics, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    return int(response.status_code)
