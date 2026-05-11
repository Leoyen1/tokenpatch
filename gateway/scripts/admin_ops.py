from __future__ import annotations

import argparse
import json
from typing import Any

import httpx


def request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.request(method, url, headers=headers, json=payload, params=params)
    response.raise_for_status()
    return response.json()


def admin_headers(admin_token: str, request_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {admin_token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    return headers


def user_headers(user_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_token}"}


def cmd_activate(args: argparse.Namespace) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/v1/admin/accounts/{args.user_token}/profile"
    payload = {
        "owner_id": args.owner_id,
        "email": args.email,
        "status": args.status,
    }
    return request_json(
        method="POST",
        url=url,
        headers=admin_headers(args.admin_token),
        timeout_seconds=args.timeout_seconds,
        payload=payload,
    )


def cmd_manual_topup(args: argparse.Namespace) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/v1/admin/accounts/{args.user_token}/credits/manual-topup"
    payload = {"credits": args.credits, "reason": args.reason}
    return request_json(
        method="POST",
        url=url,
        headers=admin_headers(args.admin_token, args.request_id),
        timeout_seconds=args.timeout_seconds,
        payload=payload,
    )


def cmd_balance(args: argparse.Namespace) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/v1/balance"
    return request_json(
        method="GET",
        url=url,
        headers=user_headers(args.user_token),
        timeout_seconds=args.timeout_seconds,
    )


def cmd_usage(args: argparse.Namespace) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/v1/usage/summary"
    return request_json(
        method="GET",
        url=url,
        headers=user_headers(args.user_token),
        timeout_seconds=args.timeout_seconds,
        params={"window": args.window},
    )


def cmd_dashboard(args: argparse.Namespace) -> dict[str, Any]:
    url = f"{args.base_url.rstrip('/')}/v1/dashboard/overview"
    return request_json(
        method="GET",
        url=url,
        headers=user_headers(args.user_token),
        timeout_seconds=args.timeout_seconds,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="tokenpatch gateway admin ops helper")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    activate = subparsers.add_parser("activate", help="activate invited account and update owner profile")
    activate.add_argument("--admin-token", required=True)
    activate.add_argument("--user-token", required=True)
    activate.add_argument("--owner-id", default=None)
    activate.add_argument("--email", default=None)
    activate.add_argument("--status", choices=["invited", "active", "suspended"], default="active")
    activate.set_defaults(handler=cmd_activate)

    topup = subparsers.add_parser("manual-topup", help="manual top-up with audit fields")
    topup.add_argument("--admin-token", required=True)
    topup.add_argument("--user-token", required=True)
    topup.add_argument("--credits", required=True, type=float)
    topup.add_argument("--reason", required=True)
    topup.add_argument("--request-id", default=None)
    topup.set_defaults(handler=cmd_manual_topup)

    balance = subparsers.add_parser("balance", help="query user balance")
    balance.add_argument("--user-token", required=True)
    balance.set_defaults(handler=cmd_balance)

    usage = subparsers.add_parser("usage-summary", help="query user usage/charge summary by window")
    usage.add_argument("--user-token", required=True)
    usage.add_argument("--window", choices=["24h", "7d", "30d", "all"], default="7d")
    usage.set_defaults(handler=cmd_usage)

    dashboard = subparsers.add_parser("dashboard-overview", help="query dashboard overview (balance/usage/savings)")
    dashboard.add_argument("--user-token", required=True)
    dashboard.set_defaults(handler=cmd_dashboard)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = args.handler(args)
    if args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
