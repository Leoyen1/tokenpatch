from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time
import uuid

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incrementally sync tokenpatch gateway policy events CSV.")
    parser.add_argument("--base-url", required=True, help="Gateway base URL, e.g. https://api.example.com")
    parser.add_argument("--admin-token", required=True, help="Admin bearer token")
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument("--cursor-file", required=True, help="Cursor state file path")
    parser.add_argument("--token", default="", help="Optional account token filter")
    parser.add_argument("--event-type", default="", help="Optional event_type filter")
    parser.add_argument("--severity", default="", help="Optional severity filter")
    parser.add_argument("--actor", default="", help="Optional actor filter")
    parser.add_argument("--since", default="", help="Optional first-round start time, e.g. 2026-01-01 00:00:00")
    parser.add_argument("--limit", type=int, default=500, help="Rows per pull")
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages per run")
    parser.add_argument("--retries", type=int, default=3, help="Retries per page on transient failures")
    parser.add_argument("--backoff-seconds", type=float, default=1.0, help="Initial backoff seconds")
    parser.add_argument("--max-backoff-seconds", type=float, default=8.0, help="Max backoff seconds")
    parser.add_argument("--log-file", default=".mmdev-gateway/sync-events.log", help="Sync log file")
    parser.add_argument("--state-file", default=".mmdev-gateway/sync-events.state.json", help="Sync state file")
    parser.add_argument("--metrics-file", default="", help="Optional JSONL metrics output file")
    parser.add_argument("--metrics-tags", default="", help="Optional metrics tags, e.g. env=prod,region=sg")
    parser.add_argument("--request-id-header", default="X-Request-ID", help="Optional per-request id header name; empty disables")
    parser.add_argument("--request-id-prefix", default="tokenpatch-sync", help="Prefix for generated request ids")
    parser.add_argument(
        "--dedupe-event-id",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip duplicate event_id rows",
    )
    parser.add_argument("--dedupe-scan-limit", type=int, default=0, help="Existing output scan limit rows; 0 means full scan")
    return parser.parse_args()


def load_cursor(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def save_cursor(path: Path, cursor: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(cursor), encoding="utf-8")


def now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_metrics(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_metrics_tags(raw: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    if not raw.strip():
        return tags
    for item in raw.split(","):
        part = item.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        tags[key] = value
    return tags


def load_existing_event_ids(output_path: Path, scan_limit: int) -> set[str]:
    if not output_path.exists():
        return set()
    seen: set[str] = set()
    with output_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        count = 0
        for row in reader:
            if not row:
                continue
            if row[0].strip():
                seen.add(row[0].strip())
            count += 1
            if scan_limit > 0 and count >= scan_limit:
                break
    return seen


def append_rows(output_path: Path, lines: list[str], include_header: bool, seen_event_ids: set[str] | None = None) -> tuple[int, int]:
    if not lines:
        return 0, 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if output_path.exists() else "w"
    with output_path.open(mode, encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        start_index = 0
        if lines and not include_header:
            start_index = 1
        rows_written = 0
        duplicates_skipped = 0
        for idx, line in enumerate(lines[start_index:], start=start_index):
            if not line:
                continue
            parsed = next(csv.reader([line]))
            if seen_event_ids is not None and parsed:
                event_id = parsed[0].strip()
                if event_id and event_id in seen_event_ids:
                    duplicates_skipped += 1
                    continue
            writer.writerow(parsed)
            # Count data rows only, not header.
            if not (start_index == 0 and idx == 0):
                rows_written += 1
                if seen_event_ids is not None and parsed and parsed[0].strip():
                    seen_event_ids.add(parsed[0].strip())
    return rows_written, duplicates_skipped


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {message}\n")


def should_retry_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def fetch_page_with_retry(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    params: dict[str, object],
    retries: int,
    backoff_seconds: float,
    max_backoff_seconds: float,
    sleep_fn,
    log_path: Path,
    request_id_header: str | None = None,
    request_id_prefix: str = "tokenpatch-sync",
    page_index: int = 1,
) -> httpx.Response:
    attempts = max(0, retries) + 1
    for attempt in range(1, attempts + 1):
        try:
            req_headers = dict(headers)
            if request_id_header:
                req_headers[request_id_header] = build_request_id(request_id_prefix, page_index, attempt)
            response = client.get(url, headers=req_headers, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if attempt >= attempts or not should_retry_status(status):
                raise
            delay = min(backoff_seconds * (2 ** (attempt - 1)), max_backoff_seconds)
            log_line(log_path, f"request failed status={status}, retry={attempt}/{attempts - 1}, sleep={delay:.2f}s")
            sleep_fn(delay)
        except httpx.RequestError as exc:
            if attempt >= attempts:
                raise
            delay = min(backoff_seconds * (2 ** (attempt - 1)), max_backoff_seconds)
            log_line(log_path, f"request error={exc.__class__.__name__}, retry={attempt}/{attempts - 1}, sleep={delay:.2f}s")
            sleep_fn(delay)
    raise RuntimeError("unreachable")


def build_request_id(prefix: str, page_index: int, attempt: int) -> str:
    run = uuid.uuid4().hex[:10]
    return f"{prefix}-{run}-p{page_index}-a{attempt}"


def run_sync(args: argparse.Namespace, *, sleep_fn=time.sleep) -> dict[str, int]:
    base_url = args.base_url.rstrip("/")
    cursor_file = Path(args.cursor_file)
    output_path = Path(args.output)
    log_path = Path(args.log_file)
    state_path = Path(args.state_file)
    metrics_path = Path(args.metrics_file) if args.metrics_file else None
    metrics_tags = parse_metrics_tags(args.metrics_tags)
    cursor = load_cursor(cursor_file)
    started_at = now_utc_iso()
    start_time = time.time()
    include_header = not output_path.exists()
    headers = {"Authorization": f"Bearer {args.admin_token}"}
    total_written = 0
    total_duplicates_skipped = 0
    pages = 0
    seen_event_ids = load_existing_event_ids(output_path, scan_limit=max(0, args.dedupe_scan_limit)) if args.dedupe_event_id else None
    state = load_state(state_path)
    state["total_runs"] = int(state.get("total_runs", 0)) + 1
    state["last_started_at"] = started_at
    state["last_cursor"] = cursor
    save_state(state_path, state)

    try:
        log_line(log_path, f"sync start cursor={cursor} limit={args.limit} max_pages={args.max_pages}")
        with httpx.Client(timeout=30) as client:
            for _ in range(max(1, args.max_pages)):
                pages += 1
                params: dict[str, object] = {"cursor": cursor, "limit": args.limit}
                if args.token:
                    params["token"] = args.token
                if args.event_type:
                    params["event_type"] = args.event_type
                if args.severity:
                    params["severity"] = args.severity
                if args.actor:
                    params["actor"] = args.actor
                if args.since:
                    params["since"] = args.since

                resp = fetch_page_with_retry(
                    client=client,
                    url=f"{base_url}/v1/admin/events/export",
                    headers=headers,
                    params=params,
                    retries=args.retries,
                    backoff_seconds=args.backoff_seconds,
                    max_backoff_seconds=args.max_backoff_seconds,
                    sleep_fn=sleep_fn,
                    log_path=log_path,
                    request_id_header=args.request_id_header.strip() or None,
                    request_id_prefix=args.request_id_prefix,
                    page_index=pages,
                )

                lines = [line for line in resp.text.splitlines() if line.strip()]
                if not lines:
                    log_line(log_path, "empty response, stop")
                    break
                wrote, duplicates_skipped = append_rows(output_path, lines, include_header=include_header, seen_event_ids=seen_event_ids)
                include_header = False
                total_written += wrote
                total_duplicates_skipped += duplicates_skipped

                next_cursor_raw = resp.headers.get("X-MMDEV-Next-Cursor", "").strip()
                if not next_cursor_raw:
                    log_line(log_path, f"page={pages} wrote={wrote} skipped_duplicates={duplicates_skipped} no next cursor, stop")
                    break
                next_cursor = int(next_cursor_raw)
                if next_cursor <= cursor:
                    log_line(log_path, f"page={pages} wrote={wrote} skipped_duplicates={duplicates_skipped} non-increasing cursor={next_cursor}, stop")
                    break
                cursor = next_cursor
                save_cursor(cursor_file, cursor)
                note = resp.headers.get("X-MMDEV-Filter-Note", "").strip()
                if note:
                    log_line(log_path, f"page={pages} wrote={wrote} skipped_duplicates={duplicates_skipped} cursor={cursor} note={note}")
                else:
                    log_line(log_path, f"page={pages} wrote={wrote} skipped_duplicates={duplicates_skipped} cursor={cursor}")

                if wrote == 0:
                    log_line(log_path, "no data rows written, stop")
                    break
    except Exception as exc:
        failed_at = now_utc_iso()
        state["last_error"] = str(exc)
        state["last_error_at"] = failed_at
        state["last_cursor"] = cursor
        state["last_rows_written"] = total_written
        state["last_duplicates_skipped"] = total_duplicates_skipped
        state["last_pages"] = pages
        save_state(state_path, state)
        append_metrics(
            metrics_path,
            {
                "ts": failed_at,
                "status": "error",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "cursor": cursor,
                "pages": pages,
                "wrote_rows": total_written,
                "skipped_duplicates": total_duplicates_skipped,
                "duration_seconds": round(max(0.0, time.time() - start_time), 3),
                "tags": metrics_tags,
            },
        )
        log_line(log_path, f"sync failed error={exc.__class__.__name__}: {exc}")
        raise

    finished_at = now_utc_iso()
    state["last_success_at"] = finished_at
    state["last_error"] = ""
    state["last_cursor"] = cursor
    state["last_rows_written"] = total_written
    state["last_duplicates_skipped"] = total_duplicates_skipped
    state["last_pages"] = pages
    state["total_rows_written"] = int(state.get("total_rows_written", 0)) + total_written
    state["total_duplicates_skipped"] = int(state.get("total_duplicates_skipped", 0)) + total_duplicates_skipped
    save_state(state_path, state)
    append_metrics(
        metrics_path,
        {
            "ts": finished_at,
            "status": "ok",
            "cursor": cursor,
            "pages": pages,
            "wrote_rows": total_written,
            "skipped_duplicates": total_duplicates_skipped,
            "duration_seconds": round(max(0.0, time.time() - start_time), 3),
            "tags": metrics_tags,
        },
    )
    log_line(log_path, f"sync done wrote_rows={total_written} skipped_duplicates={total_duplicates_skipped} cursor={cursor}")
    return {"wrote_rows": total_written, "skipped_duplicates": total_duplicates_skipped, "cursor": cursor, "pages": pages}


def main() -> None:
    args = parse_args()
    summary = run_sync(args)
    print(
        f"sync done: wrote_rows={summary['wrote_rows']}, skipped_duplicates={summary['skipped_duplicates']}, "
        f"cursor={summary['cursor']}, pages={summary['pages']}"
    )


if __name__ == "__main__":
    main()
