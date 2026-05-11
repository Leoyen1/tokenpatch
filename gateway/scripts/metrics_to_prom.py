from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert sync metrics JSONL to Prometheus textfile format.")
    parser.add_argument("--input", required=True, help="Input JSONL path from sync_events --metrics-file")
    parser.add_argument("--output", required=True, help="Output Prometheus textfile path")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False, help="Render and print summary without writing output")
    parser.add_argument("--output-mode", choices=["replace", "append"], default="replace", help="Write mode for output file")
    parser.add_argument("--max-append-lines", type=int, default=0, help="Keep only latest N lines in append mode; 0 disables")
    parser.add_argument("--max-append-bytes", type=int, default=0, help="Keep only latest N bytes in append mode; 0 disables")
    parser.add_argument("--window-hours", type=float, default=0.0, help="Only include metrics in recent N hours; 0 disables")
    parser.add_argument("--group-by", default="", help="Comma-separated tag keys used for grouping, e.g. env,region")
    parser.add_argument(
        "--emit-zero-series",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Emit zero-value metrics even when no rows match current window/filter",
    )
    parser.add_argument(
        "--zero-series-tags",
        default="",
        help="Tags for zero series, e.g. env=prod,region=sg",
    )
    parser.add_argument(
        "--atomic-write",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write output atomically via temp file + rename",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def parse_ts_epoch(ts: str) -> int:
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return 0


def sanitize_label_key(key: str) -> str:
    out = []
    for ch in key:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    normalized = "".join(out) or "tag"
    if normalized[0].isdigit():
        normalized = f"tag_{normalized}"
    return normalized


def parse_group_by(raw: str) -> set[str] | None:
    text = raw.strip()
    if not text:
        return None
    keys = set()
    for item in text.split(","):
        part = item.strip()
        if not part:
            continue
        keys.add(sanitize_label_key(part))
    return keys or None


def parse_label_kv_csv(raw: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not raw.strip():
        return labels
    for item in raw.split(","):
        part = item.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        labels[sanitize_label_key(key)] = value
    return labels


def escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = []
    for key in sorted(labels):
        parts.append(f'{key}="{escape_label_value(labels[key])}"')
    return "{" + ",".join(parts) + "}"


def build_groups(rows: list[dict], *, group_by: set[str] | None = None) -> list[dict]:
    grouped: dict[tuple[tuple[str, str], ...], dict] = {}
    for row in rows:
        tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}
        labels = {sanitize_label_key(str(k)): str(v) for k, v in tags.items()}
        if group_by is not None:
            labels = {k: v for k, v in labels.items() if k in group_by}
        key = tuple(sorted(labels.items()))
        group = grouped.get(key)
        if group is None:
            group = {
                "labels": dict(key),
                "runs_ok": 0,
                "runs_error": 0,
                "rows_written_total": 0,
                "skipped_duplicates_total": 0,
                "latest_ts_epoch": 0,
                "latest_status": "error",
                "latest_cursor": 0,
                "latest_pages": 0,
                "latest_duration": 0.0,
            }
            grouped[key] = group

        status = str(row.get("status", "error"))
        if status == "ok":
            group["runs_ok"] += 1
        else:
            group["runs_error"] += 1
        group["rows_written_total"] += int(row.get("wrote_rows", 0) or 0)
        group["skipped_duplicates_total"] += int(row.get("skipped_duplicates", 0) or 0)

        ts_epoch = parse_ts_epoch(str(row.get("ts", "")))
        if ts_epoch >= group["latest_ts_epoch"]:
            group["latest_ts_epoch"] = ts_epoch
            group["latest_status"] = status
            group["latest_cursor"] = int(row.get("cursor", 0) or 0)
            group["latest_pages"] = int(row.get("pages", 0) or 0)
            group["latest_duration"] = float(row.get("duration_seconds", 0.0) or 0.0)

    return [grouped[key] for key in sorted(grouped.keys())]


def filter_rows_by_window(rows: list[dict], window_hours: float, *, now_epoch: int | None = None) -> list[dict]:
    if window_hours <= 0:
        return rows
    base_now = now_epoch if now_epoch is not None else int(time.time())
    cutoff = base_now - int(window_hours * 3600)
    filtered: list[dict] = []
    for row in rows:
        ts_epoch = parse_ts_epoch(str(row.get("ts", "")))
        if ts_epoch >= cutoff:
            filtered.append(row)
    return filtered


def render_prometheus_text(
    rows: list[dict],
    *,
    window_hours: float = 0.0,
    now_epoch: int | None = None,
    group_by: set[str] | None = None,
    emit_zero_series: bool = False,
    zero_series_labels: dict[str, str] | None = None,
) -> str:
    filtered_rows = filter_rows_by_window(rows, window_hours, now_epoch=now_epoch)
    groups = build_groups(filtered_rows, group_by=group_by)
    if emit_zero_series and not groups:
        labels = dict(zero_series_labels or {})
        if group_by is not None:
            labels = {k: v for k, v in labels.items() if k in group_by}
        groups = [
            {
                "labels": labels,
                "runs_ok": 0,
                "runs_error": 0,
                "rows_written_total": 0,
                "skipped_duplicates_total": 0,
                "latest_ts_epoch": 0,
                "latest_status": "error",
                "latest_cursor": 0,
                "latest_pages": 0,
                "latest_duration": 0.0,
            }
        ]
    lines: list[str] = []
    lines.append("# HELP mmdev_sync_runs_total Number of sync runs.")
    lines.append("# TYPE mmdev_sync_runs_total counter")
    lines.append("# HELP mmdev_sync_rows_written_total Total rows written by sync runs.")
    lines.append("# TYPE mmdev_sync_rows_written_total counter")
    lines.append("# HELP mmdev_sync_duplicates_skipped_total Total duplicate rows skipped by sync runs.")
    lines.append("# TYPE mmdev_sync_duplicates_skipped_total counter")
    lines.append("# HELP mmdev_sync_last_run_success Last run status as 1 for success and 0 for error.")
    lines.append("# TYPE mmdev_sync_last_run_success gauge")
    lines.append("# HELP mmdev_sync_last_run_timestamp_seconds Last run timestamp in epoch seconds.")
    lines.append("# TYPE mmdev_sync_last_run_timestamp_seconds gauge")
    lines.append("# HELP mmdev_sync_last_cursor Last observed cursor value.")
    lines.append("# TYPE mmdev_sync_last_cursor gauge")
    lines.append("# HELP mmdev_sync_last_pages Last run page count.")
    lines.append("# TYPE mmdev_sync_last_pages gauge")
    lines.append("# HELP mmdev_sync_last_duration_seconds Last run duration in seconds.")
    lines.append("# TYPE mmdev_sync_last_duration_seconds gauge")

    for group in groups:
        labels = dict(group["labels"])
        ok_labels = dict(labels)
        ok_labels["status"] = "ok"
        err_labels = dict(labels)
        err_labels["status"] = "error"
        lines.append(f"mmdev_sync_runs_total{format_labels(ok_labels)} {group['runs_ok']}")
        lines.append(f"mmdev_sync_runs_total{format_labels(err_labels)} {group['runs_error']}")
        lines.append(f"mmdev_sync_rows_written_total{format_labels(labels)} {group['rows_written_total']}")
        lines.append(f"mmdev_sync_duplicates_skipped_total{format_labels(labels)} {group['skipped_duplicates_total']}")
        success = 1 if group["latest_status"] == "ok" else 0
        lines.append(f"mmdev_sync_last_run_success{format_labels(labels)} {success}")
        lines.append(f"mmdev_sync_last_run_timestamp_seconds{format_labels(labels)} {group['latest_ts_epoch']}")
        lines.append(f"mmdev_sync_last_cursor{format_labels(labels)} {group['latest_cursor']}")
        lines.append(f"mmdev_sync_last_pages{format_labels(labels)} {group['latest_pages']}")
        lines.append(f"mmdev_sync_last_duration_seconds{format_labels(labels)} {group['latest_duration']}")

    return "\n".join(lines) + "\n"


def trim_file_to_last_lines(path: Path, max_lines: int) -> None:
    if max_lines <= 0 or not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= max_lines:
        return
    trimmed = "\n".join(lines[-max_lines:]) + "\n"
    path.write_text(trimmed, encoding="utf-8")


def trim_file_to_last_bytes(path: Path, max_bytes: int) -> None:
    if max_bytes <= 0 or not path.exists():
        return
    data = path.read_bytes()
    if len(data) <= max_bytes:
        return
    tail = data[-max_bytes:]
    newline_pos = tail.find(b"\n")
    if newline_pos != -1 and newline_pos + 1 < len(tail):
        tail = tail[newline_pos + 1 :]
    path.write_bytes(tail)


def write_output(
    path: Path,
    content: str,
    *,
    atomic_write: bool = True,
    output_mode: str = "replace",
    max_append_lines: int = 0,
    max_append_bytes: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_mode == "append":
        with path.open("a", encoding="utf-8") as fh:
            fh.write(content)
        trim_file_to_last_lines(path, max_append_lines)
        trim_file_to_last_bytes(path, max_append_bytes)
        return
    if not atomic_write:
        path.write_text(content, encoding="utf-8")
        return
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def count_non_comment_lines(content: str) -> int:
    count = 0
    for line in content.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            count += 1
    return count


def maybe_write_output(
    path: Path,
    content: str,
    *,
    dry_run: bool,
    atomic_write: bool,
    output_mode: str,
    max_append_lines: int,
    max_append_bytes: int,
) -> bool:
    if dry_run:
        return False
    write_output(
        path,
        content,
        atomic_write=atomic_write,
        output_mode=output_mode,
        max_append_lines=max_append_lines,
        max_append_bytes=max_append_bytes,
    )
    return True


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = load_jsonl(input_path)
    rendered = render_prometheus_text(
        rows,
        window_hours=args.window_hours,
        group_by=parse_group_by(args.group_by),
        emit_zero_series=args.emit_zero_series,
        zero_series_labels=parse_label_kv_csv(args.zero_series_tags),
    )
    wrote = maybe_write_output(
        output_path,
        rendered,
        dry_run=args.dry_run,
        atomic_write=args.atomic_write,
        output_mode=args.output_mode,
        max_append_lines=max(0, args.max_append_lines),
        max_append_bytes=max(0, args.max_append_bytes),
    )
    if wrote:
        print(f"wrote {output_path}")
    else:
        print(
            f"dry-run: output={output_path} lines={len(rendered.splitlines())} "
            f"series={count_non_comment_lines(rendered)}"
        )


if __name__ == "__main__":
    main()
