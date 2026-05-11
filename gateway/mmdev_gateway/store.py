from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from gateway.mmdev_gateway.schemas import AccountInfo, ExecutorRunResponse, PolicyEvent, UsageRecord


@dataclass
class Account:
    token: str
    credits: float
    frozen: bool
    status: str
    owner_id: str | None = None
    email: str | None = None
    freeze_reason: str | None = None
    freeze_level: str | None = None


class SQLiteStore:
    def __init__(self, db_path: Path, tokens: list[str], starting_credits: float, default_account_status: str = "invited") -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            self.init_db(conn)
            for token in tokens:
                conn.execute(
                    "insert or ignore into accounts (token, credits, status) values (?, ?, ?)",
                    (token, starting_credits, default_account_status),
                )
            conn.commit()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            create table if not exists accounts (
                token text primary key,
                credits real not null,
                frozen integer not null default 0,
                freeze_reason text,
                freeze_level text,
                owner_id text,
                email text,
                status text not null default 'invited',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create table if not exists tasks (
                task_id text primary key,
                token text not null,
                response_json text not null,
                created_at text not null default current_timestamp
            );

            create table if not exists usage_records (
                id integer primary key autoincrement,
                token text not null,
                task_id text not null,
                input_tokens integer not null,
                output_tokens integer not null,
                charged_credits real not null,
                provider_cost real not null,
                created_at text not null default current_timestamp
            );

            create table if not exists policy_events (
                id integer primary key autoincrement,
                token text not null,
                event_type text not null,
                detail text not null,
                request_id text,
                actor text not null default 'system',
                severity text,
                created_at text not null default current_timestamp
            );

            create table if not exists manual_topups (
                id integer primary key autoincrement,
                token text not null,
                operator text not null,
                reason text not null,
                before_credits real not null,
                amount real not null,
                after_credits real not null,
                request_id text,
                created_at text not null default current_timestamp
            );
            """
        )
        self.ensure_column(conn, "accounts", "freeze_reason", "text")
        self.ensure_column(conn, "accounts", "freeze_level", "text")
        self.ensure_column(conn, "accounts", "owner_id", "text")
        self.ensure_column(conn, "accounts", "email", "text")
        self.ensure_column(conn, "accounts", "status", "text not null default 'invited'")
        self.ensure_column(conn, "policy_events", "request_id", "text")
        self.ensure_column(conn, "policy_events", "actor", "text not null default 'system'")
        self.ensure_column(conn, "policy_events", "severity", "text")

    def ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"alter table {table} add column {column} {definition}")

    def require_account(self, token: str) -> Account | None:
        with self.connect() as conn:
            row = conn.execute(
                "select token, credits, frozen, freeze_reason, freeze_level, owner_id, email, status from accounts where token=?",
                (token,),
            ).fetchone()
        if row is None or row["frozen"]:
            return None
        return Account(
            token=row["token"],
            credits=row["credits"],
            frozen=False,
            status=row["status"],
            owner_id=row["owner_id"],
            email=row["email"],
            freeze_reason=row["freeze_reason"],
            freeze_level=row["freeze_level"],
        )

    def balance(self, token: str) -> float:
        account = self.require_account(token)
        if account is None:
            raise KeyError(token)
        return account.credits

    def topup(self, token: str, credits: float) -> Account | None:
        with self.connect() as conn:
            row = conn.execute(
                "select credits, frozen, freeze_reason, freeze_level, owner_id, email, status from accounts where token=?",
                (token,),
            ).fetchone()
            if row is None or row["frozen"]:
                return None
            new_credits = row["credits"] + credits
            conn.execute(
                "update accounts set credits=?, updated_at=current_timestamp where token=?",
                (new_credits, token),
            )
            conn.commit()
        return Account(
            token=token,
            credits=new_credits,
            frozen=False,
            status=row["status"],
            owner_id=row["owner_id"],
            email=row["email"],
            freeze_reason=row["freeze_reason"],
            freeze_level=row["freeze_level"],
        )

    def freeze(self, token: str, reason: str = "policy-violation", level: str = "medium") -> bool:
        return self.set_frozen(token, True, reason=reason, level=level)

    def unfreeze(self, token: str) -> bool:
        return self.set_frozen(token, False, reason=None, level=None)

    def set_frozen(self, token: str, frozen: bool, reason: str | None, level: str | None) -> bool:
        with self.connect() as conn:
            row = conn.execute("select token from accounts where token=?", (token,)).fetchone()
            if row is None:
                return False
            conn.execute(
                "update accounts set frozen=?, freeze_reason=?, freeze_level=?, updated_at=current_timestamp where token=?",
                (1 if frozen else 0, reason, level, token),
            )
            conn.commit()
        return True

    def charge_and_record(self, token: str, response: ExecutorRunResponse) -> bool:
        with self.connect() as conn:
            row = conn.execute("select credits, frozen, status from accounts where token=?", (token,)).fetchone()
            if (
                row is None
                or row["frozen"]
                or row["status"] != "active"
                or row["credits"] < response.charged_credits
            ):
                return False
            conn.execute(
                "update accounts set credits=credits-?, updated_at=current_timestamp where token=?",
                (response.charged_credits, token),
            )
            conn.execute(
                "insert into tasks (task_id, token, response_json) values (?, ?, ?)",
                (response.task_id, token, response.model_dump_json()),
            )
            conn.execute(
                """
                insert into usage_records
                    (token, task_id, input_tokens, output_tokens, charged_credits, provider_cost)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    response.task_id,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.charged_credits,
                    response.provider_cost,
                ),
            )
            conn.commit()
        return True

    def daily_token_total(self, token: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                select coalesce(sum(input_tokens + output_tokens), 0) as total_tokens
                from usage_records
                where token=? and date(created_at)=date('now')
                """,
                (token,),
            ).fetchone()
        return int(row["total_tokens"]) if row else 0

    def monthly_token_total(self, token: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                select coalesce(sum(input_tokens + output_tokens), 0) as total_tokens
                from usage_records
                where token=? and strftime('%Y-%m', created_at)=strftime('%Y-%m', 'now')
                """,
                (token,),
            ).fetchone()
        return int(row["total_tokens"]) if row else 0

    def daily_credits_total(self, token: str) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                select coalesce(sum(charged_credits), 0) as total_credits
                from usage_records
                where token=? and date(created_at)=date('now')
                """,
                (token,),
            ).fetchone()
        return float(row["total_credits"]) if row else 0.0

    def monthly_credits_total(self, token: str) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                select coalesce(sum(charged_credits), 0) as total_credits
                from usage_records
                where token=? and strftime('%Y-%m', created_at)=strftime('%Y-%m', 'now')
                """,
                (token,),
            ).fetchone()
        return float(row["total_credits"]) if row else 0.0

    def set_credits(self, token: str, credits: float) -> bool:
        with self.connect() as conn:
            row = conn.execute("select token from accounts where token=?", (token,)).fetchone()
            if row is None:
                return False
            conn.execute(
                "update accounts set credits=?, updated_at=current_timestamp where token=?",
                (credits, token),
            )
            conn.commit()
        return True

    def update_account(self, token: str, *, owner_id: str | None, email: str | None, status: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("select token from accounts where token=?", (token,)).fetchone()
            if row is None:
                return False
            conn.execute(
                """
                update accounts
                set owner_id=?, email=?, status=?, updated_at=current_timestamp
                where token=?
                """,
                (owner_id, email, status, token),
            )
            conn.commit()
        return True

    def manual_topup(
        self,
        token: str,
        *,
        amount: float,
        operator: str,
        reason: str,
        request_id: str | None = None,
    ) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("select credits from accounts where token=?", (token,)).fetchone()
            if row is None:
                return None
            before_credits = float(row["credits"])
            after_credits = before_credits + amount
            conn.execute(
                "update accounts set credits=?, updated_at=current_timestamp where token=?",
                (after_credits, token),
            )
            conn.execute(
                """
                insert into manual_topups
                    (token, operator, reason, before_credits, amount, after_credits, request_id)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (token, operator, reason, before_credits, amount, after_credits, request_id),
            )
            row2 = conn.execute(
                """
                select token, operator, reason, before_credits, amount, after_credits, request_id, created_at
                from manual_topups
                where id=last_insert_rowid()
                """
            ).fetchone()
            conn.commit()
        return dict(row2) if row2 else None

    def manual_topups(self, token: str, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select token, operator, reason, before_credits, amount, after_credits, request_id, created_at
                from manual_topups
                where token=?
                order by id desc
                limit ?
                """,
                (token, max(1, min(limit, 1000))),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_summary(self, token: str, window: str = "all") -> dict:
        clauses = {
            "24h": "and created_at >= datetime('now', '-24 hours')",
            "7d": "and created_at >= datetime('now', '-7 days')",
            "30d": "and created_at >= datetime('now', '-30 days')",
            "all": "",
        }
        where_window = clauses.get(window, "")
        with self.connect() as conn:
            row = conn.execute(
                f"""
                select
                    count(*) as calls,
                    coalesce(sum(input_tokens), 0) as input_tokens,
                    coalesce(sum(output_tokens), 0) as output_tokens,
                    coalesce(sum(charged_credits), 0) as charged_credits,
                    coalesce(sum(provider_cost), 0) as provider_cost
                from usage_records
                where token=?
                {where_window}
                """,
                (token,),
            ).fetchone()
        input_tokens = int(row["input_tokens"]) if row else 0
        output_tokens = int(row["output_tokens"]) if row else 0
        return {
            "window": window if window in clauses else "all",
            "calls": int(row["calls"]) if row else 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "charged_credits": float(row["charged_credits"]) if row else 0.0,
            "provider_cost": float(row["provider_cost"]) if row else 0.0,
        }

    def account_info(self, token: str) -> AccountInfo | None:
        with self.connect() as conn:
            row = conn.execute(
                "select token, credits, frozen, freeze_reason, freeze_level, owner_id, email, status, updated_at from accounts where token=?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        return AccountInfo(
            token=row["token"],
            credits=row["credits"],
            frozen=bool(row["frozen"]),
            freeze_reason=row["freeze_reason"],
            freeze_level=row["freeze_level"],
            owner_id=row["owner_id"],
            email=row["email"],
            status=row["status"],
            updated_at=row["updated_at"],
        )

    def list_accounts(self) -> list[AccountInfo]:
        with self.connect() as conn:
            rows = conn.execute(
                "select token, credits, frozen, freeze_reason, freeze_level, owner_id, email, status, updated_at from accounts order by token"
            ).fetchall()
        return [
            AccountInfo(
                token=row["token"],
                credits=row["credits"],
                frozen=bool(row["frozen"]),
                freeze_reason=row["freeze_reason"],
                freeze_level=row["freeze_level"],
                owner_id=row["owner_id"],
                email=row["email"],
                status=row["status"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def record_policy_event(
        self,
        token: str,
        event_type: str,
        detail: str,
        *,
        request_id: str | None = None,
        actor: str = "system",
        severity: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "insert into policy_events (token, event_type, detail, request_id, actor, severity) values (?, ?, ?, ?, ?, ?)",
                (token, event_type, detail, request_id, actor, severity),
            )
            conn.commit()

    def policy_events(self, token: str, limit: int = 100) -> list[PolicyEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select event_type, detail, request_id, actor, severity, created_at
                from policy_events
                where token=?
                order by id desc
                limit ?
                """,
                (token, max(1, min(limit, 1000))),
            ).fetchall()
        return [
            PolicyEvent(
                event_type=row["event_type"],
                detail=row["detail"],
                request_id=row["request_id"],
                actor=row["actor"],
                severity=row["severity"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def query_policy_event_rows(
        self,
        *,
        token: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        actor: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        cursor: int | None = None,
        ascending: bool = False,
        limit: int = 1000,
    ) -> list[dict]:
        where_clauses: list[str] = []
        params: list[object] = []
        if token:
            where_clauses.append("token=?")
            params.append(token)
        if event_type:
            where_clauses.append("event_type=?")
            params.append(event_type)
        if severity:
            where_clauses.append("coalesce(severity, 'none')=?")
            params.append(severity)
        if actor:
            where_clauses.append("actor=?")
            params.append(actor)
        if created_from:
            where_clauses.append("created_at>=?")
            params.append(created_from)
        if created_to:
            where_clauses.append("created_at<=?")
            params.append(created_to)
        if cursor is not None:
            where_clauses.append("id>?")
            params.append(cursor)

        where_sql = ""
        if where_clauses:
            where_sql = "where " + " and ".join(where_clauses)

        safe_limit = max(1, min(limit, 10000))
        order_sql = "id asc" if ascending else "id desc"
        query = f"""
            select id, token, event_type, detail, request_id, actor, severity, created_at
            from policy_events
            {where_sql}
            order by {order_sql}
            limit ?
        """
        params.append(safe_limit)
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def policy_event_summary(
        self,
        *,
        token: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        actor: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> dict:
        where_clauses: list[str] = []
        params: list[object] = []
        if token:
            where_clauses.append("token=?")
            params.append(token)
        if event_type:
            where_clauses.append("event_type=?")
            params.append(event_type)
        if severity:
            where_clauses.append("coalesce(severity, 'none')=?")
            params.append(severity)
        if actor:
            where_clauses.append("actor=?")
            params.append(actor)
        if created_from:
            where_clauses.append("created_at>=?")
            params.append(created_from)
        if created_to:
            where_clauses.append("created_at<=?")
            params.append(created_to)

        where_sql = ""
        if where_clauses:
            where_sql = "where " + " and ".join(where_clauses)

        with self.connect() as conn:
            total_row = conn.execute(
                f"select count(*) as total from policy_events {where_sql}",
                tuple(params),
            ).fetchone()
            type_rows = conn.execute(
                f"""
                select event_type as name, count(*) as count
                from policy_events
                {where_sql}
                group by event_type
                order by count desc, event_type asc
                """,
                tuple(params),
            ).fetchall()
            severity_rows = conn.execute(
                f"""
                select coalesce(severity, 'none') as name, count(*) as count
                from policy_events
                {where_sql}
                group by coalesce(severity, 'none')
                order by count desc, name asc
                """,
                tuple(params),
            ).fetchall()
            actor_rows = conn.execute(
                f"""
                select actor as name, count(*) as count
                from policy_events
                {where_sql}
                group by actor
                order by count desc, actor asc
                """,
                tuple(params),
            ).fetchall()

        return {
            "total": int(total_row["total"]) if total_row else 0,
            "by_event_type": [dict(row) for row in type_rows],
            "by_severity": [dict(row) for row in severity_rows],
            "by_actor": [dict(row) for row in actor_rows],
        }

    def policy_event_trend(
        self,
        *,
        bucket: str,
        token: str | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        actor: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        limit: int = 365,
    ) -> dict:
        where_clauses: list[str] = []
        params: list[object] = []
        if token:
            where_clauses.append("token=?")
            params.append(token)
        if event_type:
            where_clauses.append("event_type=?")
            params.append(event_type)
        if severity:
            where_clauses.append("coalesce(severity, 'none')=?")
            params.append(severity)
        if actor:
            where_clauses.append("actor=?")
            params.append(actor)
        if created_from:
            where_clauses.append("created_at>=?")
            params.append(created_from)
        if created_to:
            where_clauses.append("created_at<=?")
            params.append(created_to)

        where_sql = ""
        if where_clauses:
            where_sql = "where " + " and ".join(where_clauses)

        if bucket == "hour":
            bucket_expr = "strftime('%Y-%m-%d %H:00:00', created_at)"
        else:
            bucket_expr = "date(created_at)"

        safe_limit = max(1, min(limit, 5000))
        with self.connect() as conn:
            total_row = conn.execute(
                f"select count(*) as total from policy_events {where_sql}",
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                f"""
                select {bucket_expr} as bucket, count(*) as count
                from policy_events
                {where_sql}
                group by {bucket_expr}
                order by bucket asc
                limit ?
                """,
                tuple(params + [safe_limit]),
            ).fetchall()
        return {
            "bucket": bucket,
            "total": int(total_row["total"]) if total_row else 0,
            "points": [dict(row) for row in rows],
        }

    def usage(self, token: str) -> list[UsageRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select task_id, input_tokens, output_tokens, charged_credits, provider_cost
                from usage_records
                where token=?
                order by id
                """,
                (token,),
            ).fetchall()
        return [UsageRecord(**dict(row)) for row in rows]

    def task(self, token: str, task_id: str) -> ExecutorRunResponse | None:
        with self.connect() as conn:
            row = conn.execute(
                "select response_json from tasks where token=? and task_id=?",
                (token, task_id),
            ).fetchone()
        if row is None:
            return None
        return ExecutorRunResponse.model_validate_json(row["response_json"])
