from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from mmdev.schemas import DevTask, ExecutionResult, ModelUsage, ProjectPlan, ReviewResult, ValidationResult


STATE_FILE = "state.sqlite"


def state_path(mmdev_dir: Path) -> Path:
    return mmdev_dir / STATE_FILE


def connect(mmdev_dir: Path) -> sqlite3.Connection:
    mmdev_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_path(mmdev_dir))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists tasks (
            task_id text primary key,
            title text not null,
            status text not null,
            complexity text not null,
            recommended_executor text not null,
            allowed_files_json text not null,
            task_json text not null,
            updated_at text not null default current_timestamp
        );

        create table if not exists executions (
            task_id text primary key,
            result_json text not null,
            updated_at text not null default current_timestamp
        );

        create table if not exists validations (
            task_id text primary key,
            result_json text not null,
            passed integer not null,
            updated_at text not null default current_timestamp
        );

        create table if not exists reviews (
            task_id text primary key,
            result_json text not null,
            approved integer not null,
            recommended_next_action text not null,
            updated_at text not null default current_timestamp
        );

        create table if not exists model_usage (
            id integer primary key autoincrement,
            model text not null,
            purpose text not null,
            input_tokens integer not null,
            output_tokens integer not null,
            estimated_cost real not null,
            duration_ms integer not null,
            charged_credits real,
            provider_cost real,
            created_at text not null default current_timestamp
        );
        """
    )
    ensure_column(conn, "model_usage", "charged_credits", "real")
    ensure_column(conn, "model_usage", "provider_cost", "real")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column} {definition}")


def initialize_state(mmdev_dir: Path) -> None:
    with connect(mmdev_dir):
        pass


def record_plan(mmdev_dir: Path, plan: ProjectPlan) -> None:
    with connect(mmdev_dir) as conn:
        for task in plan.tasks:
            upsert_task(conn, task, "planned")
        conn.commit()


def upsert_task(conn: sqlite3.Connection, task: DevTask, status: str) -> None:
    conn.execute(
        """
        insert into tasks (task_id, title, status, complexity, recommended_executor, allowed_files_json, task_json, updated_at)
        values (?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(task_id) do update set
            title=excluded.title,
            status=excluded.status,
            complexity=excluded.complexity,
            recommended_executor=excluded.recommended_executor,
            allowed_files_json=excluded.allowed_files_json,
            task_json=excluded.task_json,
            updated_at=current_timestamp
        """,
        (
            task.task_id,
            task.title,
            status,
            task.complexity,
            task.recommended_executor,
            json.dumps(task.allowed_files, ensure_ascii=False),
            task.model_dump_json(),
        ),
    )


def record_execution(mmdev_dir: Path, task: DevTask, result: ExecutionResult) -> None:
    status = "needs-human-input" if result.needs_human_input else "executed"
    with connect(mmdev_dir) as conn:
        upsert_task(conn, task, status)
        conn.execute(
            """
            insert into executions (task_id, result_json, updated_at)
            values (?, ?, current_timestamp)
            on conflict(task_id) do update set result_json=excluded.result_json, updated_at=current_timestamp
            """,
            (result.task_id, result.model_dump_json()),
        )
        conn.commit()


def record_validation(mmdev_dir: Path, result: ValidationResult) -> None:
    status = "validated" if result.passed else "validation-failed"
    with connect(mmdev_dir) as conn:
        conn.execute("update tasks set status=?, updated_at=current_timestamp where task_id=?", (status, result.task_id))
        conn.execute(
            """
            insert into validations (task_id, result_json, passed, updated_at)
            values (?, ?, ?, current_timestamp)
            on conflict(task_id) do update set
                result_json=excluded.result_json,
                passed=excluded.passed,
                updated_at=current_timestamp
            """,
            (result.task_id, result.model_dump_json(), int(result.passed)),
        )
        conn.commit()


def record_review(mmdev_dir: Path, result: ReviewResult) -> None:
    status = "approved" if result.approved else f"review-{result.recommended_next_action}"
    with connect(mmdev_dir) as conn:
        conn.execute("update tasks set status=?, updated_at=current_timestamp where task_id=?", (status, result.task_id))
        conn.execute(
            """
            insert into reviews (task_id, result_json, approved, recommended_next_action, updated_at)
            values (?, ?, ?, ?, current_timestamp)
            on conflict(task_id) do update set
                result_json=excluded.result_json,
                approved=excluded.approved,
                recommended_next_action=excluded.recommended_next_action,
                updated_at=current_timestamp
            """,
            (result.task_id, result.model_dump_json(), int(result.approved), result.recommended_next_action),
        )
        conn.commit()


def record_usage(mmdev_dir: Path, usage: ModelUsage) -> None:
    with connect(mmdev_dir) as conn:
        conn.execute(
            """
            insert into model_usage (model, purpose, input_tokens, output_tokens, estimated_cost, duration_ms, charged_credits, provider_cost)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usage.model,
                usage.purpose,
                usage.input_tokens,
                usage.output_tokens,
                usage.estimated_cost,
                usage.duration_ms,
                usage.charged_credits,
                usage.provider_cost,
            ),
        )
        conn.commit()


def task_statuses(mmdev_dir: Path) -> list[dict[str, Any]]:
    if not state_path(mmdev_dir).exists():
        return []
    with connect(mmdev_dir) as conn:
        rows = conn.execute(
            "select task_id, title, status, complexity, recommended_executor, updated_at from tasks order by task_id"
        ).fetchall()
    return [dict(row) for row in rows]
