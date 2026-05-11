# tokenpatch Gateway Reference Server

Reference implementation for the hosted executor gateway.

This service is intentionally separate from the open-source local client. In production, keep DeepSeek API keys, billing, fraud controls, and user balances on the server side only.

## Run locally

```bash
set MMDEV_GATEWAY_TOKENS=dev-token
set MMDEV_GATEWAY_ADMIN_TOKENS=admin-token
set MMDEV_GATEWAY_POLICY_PATH=.mmdev-gateway/policy.toml
set MMDEV_GATEWAY_STARTING_CREDITS=10
set MMDEV_GATEWAY_DB_PATH=.mmdev-gateway/gateway.sqlite
set DEEPSEEK_API_KEY=...
set DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
set DEEPSEEK_EXECUTOR_MODEL=...
uvicorn gateway.mmdev_gateway.app:app --host 127.0.0.1 --port 8080
```

## Endpoints

- `POST /v1/executor/run`
- `GET /v1/balance`
- `GET /v1/usage`
- `GET /v1/usage/summary?window=24h|7d|30d|all`
- `GET /v1/dashboard/overview`
- `POST /v1/credits/topup`
- `GET /v1/tasks/{id}`
- `GET /v1/admin/accounts`
- `GET /v1/admin/accounts/{token}`
- `POST /v1/admin/accounts/{token}/profile`
- `POST /v1/admin/accounts/{token}/credits/set`
- `POST /v1/admin/accounts/{token}/credits/manual-topup`
- `GET /v1/admin/accounts/{token}/topups`
- `GET /v1/admin/accounts/{token}/usage/summary?window=24h|7d|30d|all`
- `GET /v1/admin/accounts/{token}/dashboard/overview`
- `POST /v1/admin/accounts/{token}/freeze`
- `POST /v1/admin/accounts/{token}/unfreeze`
- `GET /v1/admin/accounts/{token}/events`
- `GET /v1/admin/events/export` (CSV)
- `GET /v1/admin/events/summary` (JSON aggregates)
- `GET /v1/admin/events/trend` (JSON bucket trend)

This reference stores accounts, balances, usage, and task responses in SQLite. For production, replace local SQLite with managed durable storage, replace test top-up with real payments, and add fraud/compliance controls.

## Guardrail Environment Variables

- `MMDEV_GATEWAY_MAX_PROMPT_CHARS` (default `120000`)
- `MMDEV_GATEWAY_DEFAULT_ACCOUNT_STATUS` (default `invited`; only `active` accounts can run executor)
- `MMDEV_GATEWAY_MAX_PATCH_CHARS` (default `0`, disabled)
- `MMDEV_GATEWAY_MAX_TOTAL_TOKENS_PER_REQUEST` (default `0`, disabled)
- `MMDEV_GATEWAY_DAILY_TOKEN_LIMIT` (default `0`, disabled)
- `MMDEV_GATEWAY_MONTHLY_TOKEN_LIMIT` (default `0`, disabled)
- `MMDEV_GATEWAY_FREEZE_ON_POLICY_VIOLATION` (`0` or `1`, default `0`)
- `MMDEV_GATEWAY_ADMIN_TOKENS` (comma-separated admin bearer tokens)
- `MMDEV_GATEWAY_REQUIRE_COMPLIANCE_METADATA` (`0` or `1`, default `0`)
- `MMDEV_GATEWAY_BLOCKED_COUNTRIES` (comma-separated ISO country codes, e.g. `IR,KP`)
- `MMDEV_GATEWAY_ALLOWED_COUNTRIES` (optional allow list; when set, only listed countries can run)
- `MMDEV_GATEWAY_BLOCKED_ENTITIES` (comma-separated entity identifiers)
- `MMDEV_GATEWAY_MAX_CHARGED_CREDITS_PER_REQUEST` (default `0`, disabled)
- `MMDEV_GATEWAY_MAX_CHARGE_TO_BALANCE_RATIO` (default `0`, disabled)
- `MMDEV_GATEWAY_DAILY_CREDITS_LIMIT` (default `0`, disabled)
- `MMDEV_GATEWAY_MONTHLY_CREDITS_LIMIT` (default `0`, disabled)
- `MMDEV_GATEWAY_UNFREEZE_REQUIRES_NOTE` (`0` or `1`, default `0`)
- `MMDEV_GATEWAY_POLICY_PATH` (optional TOML policy file path; values override env and hot-reload by mtime)

Pricing and charging:

- `MMDEV_GATEWAY_INPUT_COST_PER_MILLION`
- `MMDEV_GATEWAY_OUTPUT_COST_PER_MILLION`
- `MMDEV_GATEWAY_MARKUP_MULTIPLIER`
- `MMDEV_GATEWAY_MIN_CHARGE_CREDITS`
- `MMDEV_GATEWAY_BASELINE_STRONG_INPUT_COST_PER_MILLION` (optional, for savings estimate in dashboard overview)
- `MMDEV_GATEWAY_BASELINE_STRONG_OUTPUT_COST_PER_MILLION` (optional, for savings estimate in dashboard overview)

Dashboard response contract:

- `GET /v1/dashboard/overview` and admin counterpart include fixed fields:
  - `schema_version`, `generated_at`, `token`, `balance_credits`
  - `usage_7d`, `usage_30d`
  - `savings_estimate_7d`, `savings_estimate_30d`
- Both endpoints also return header `X-TokenPatch-Schema-Version` for client-side compatibility gating.
- Full contract document: `../docs/API_CONTRACT.md`.
- Frontend-ready artifacts:
  - `../docs/dashboard-overview.example.json`
  - `../docs/dashboard-overview.types.ts`
  - `../docs/dashboard-overview.openapi-fragment.yaml`

When account freeze is enabled, policy violations can set `freeze_reason`, and all policy/admin actions are appended to the per-account event log (`/v1/admin/accounts/{token}/events`).
Policy events include `actor`, optional `severity`, and optional structured `request_id` for audit and traceability.
Manual top-ups are persisted into `manual_topups` ledger for operator audit (`operator`, `reason`, `before_credits`, `amount`, `after_credits`, `request_id`, `created_at`).

Compliance metadata can be passed by client headers:

- `X-MMDEV-Country`
- `X-MMDEV-Entity`
- `X-Request-ID` (echoed by gateway response and stored in policy event `request_id` when available)

## Policy File (Optional)

When `MMDEV_GATEWAY_POLICY_PATH` points to a TOML file, gateway reads policy values from that file first and hot-reloads after file updates.

```toml
max_total_tokens_per_request = 120000
daily_token_limit = 2000000
monthly_token_limit = 20000000
blocked_countries = ["IR", "KP"]
blocked_entities = ["blocked-org"]
unfreeze_requires_note = true
```

## Admin API examples

```bash
# List accounts
curl -H "Authorization: Bearer admin-token" http://127.0.0.1:8080/v1/admin/accounts

# Freeze account with reason
curl -X POST -H "Authorization: Bearer admin-token" -H "Content-Type: application/json" ^
  -d "{\"reason\":\"manual-review\",\"level\":\"high\",\"note\":\"ticket-123\"}" ^
  http://127.0.0.1:8080/v1/admin/accounts/dev-token/freeze

# Unfreeze account with approval note (recommended; can be enforced)
curl -X POST -H "Authorization: Bearer admin-token" -H "Content-Type: application/json" ^
  -d "{\"reason\":\"manual-admin-unfreeze\",\"approval_note\":\"ticket-123 approved\"}" ^
  http://127.0.0.1:8080/v1/admin/accounts/dev-token/unfreeze

# Set account credits
curl -X POST -H "Authorization: Bearer admin-token" -H "Content-Type: application/json" ^
  -d "{\"credits\":100}" ^
  http://127.0.0.1:8080/v1/admin/accounts/dev-token/credits/set

# Activate invited account and set owner metadata
curl -X POST -H "Authorization: Bearer admin-token" -H "Content-Type: application/json" ^
  -d "{\"owner_id\":\"user-001\",\"email\":\"dev@example.com\",\"status\":\"active\"}" ^
  http://127.0.0.1:8080/v1/admin/accounts/dev-token/profile

# Manual top-up with audit request id
curl -X POST -H "Authorization: Bearer admin-token" -H "X-Request-ID: topup-001" -H "Content-Type: application/json" ^
  -d "{\"credits\":20,\"reason\":\"invite-beta-manual-topup\"}" ^
  http://127.0.0.1:8080/v1/admin/accounts/dev-token/credits/manual-topup

# Query top-up ledger rows
curl -H "Authorization: Bearer admin-token" ^
  "http://127.0.0.1:8080/v1/admin/accounts/dev-token/topups?limit=50"

# User usage/cost summary
curl -H "Authorization: Bearer dev-token" ^
  "http://127.0.0.1:8080/v1/usage/summary?window=7d"

# User dashboard overview (balance + usage + savings estimate)
curl -H "Authorization: Bearer dev-token" ^
  "http://127.0.0.1:8080/v1/dashboard/overview"

# Export policy/admin events as CSV
curl -H "Authorization: Bearer admin-token" ^
  "http://127.0.0.1:8080/v1/admin/events/export?token=dev-token&event_type=admin_freeze&limit=500"

# Incremental CSV export (use cursor and read X-MMDEV-Next-Cursor from response header)
curl -i -H "Authorization: Bearer admin-token" ^
  "http://127.0.0.1:8080/v1/admin/events/export?token=dev-token&cursor=0&limit=200"

# Get event summary for dashboard
curl -H "Authorization: Bearer admin-token" ^
  "http://127.0.0.1:8080/v1/admin/events/summary?token=dev-token&severity=high&actor=system"

# Get bucketed trend for dashboard chart
curl -H "Authorization: Bearer admin-token" ^
  "http://127.0.0.1:8080/v1/admin/events/trend?bucket=day&token=dev-token&severity=high&actor=system&limit=30"
```

Incremental export contract:

- First pull: use `cursor=0` and optional `since`/`created_from`.
- Next pulls: use returned `X-MMDEV-Next-Cursor`; when `cursor>0`, cursor takes precedence over `since`/`created_from`.

CSV schema (`/v1/admin/events/export`):

- `event_id,token,event_type,detail,request_id,actor,severity,created_at`
- `request_id` is empty when caller did not send `X-Request-ID`.

## Incremental Sync Script

```bash
python gateway/scripts/sync_events.py ^
  --base-url http://127.0.0.1:8080 ^
  --admin-token admin-token ^
  --output .mmdev-gateway/events.csv ^
  --cursor-file .mmdev-gateway/events.cursor ^
  --log-file .mmdev-gateway/sync-events.log ^
  --state-file .mmdev-gateway/sync-events.state.json ^
  --metrics-file .mmdev-gateway/sync-events.metrics.jsonl ^
  --metrics-tags env=prod,region=sg ^
  --request-id-header X-Request-ID ^
  --request-id-prefix tokenpatch-sync ^
  --dedupe-event-id ^
  --token dev-token ^
  --severity high ^
  --actor system ^
  --since "2026-01-01 00:00:00" ^
  --limit 200
```

Script reliability flags:

- `--retries` (default `3`)
- `--backoff-seconds` (default `1.0`)
- `--max-backoff-seconds` (default `8.0`)
- `--dedupe-event-id` / `--no-dedupe-event-id` (default dedupe enabled)
- `--dedupe-scan-limit` (default `0` full existing-file scan)
- `--state-file` (default `.mmdev-gateway/sync-events.state.json`)
- `--metrics-file` (optional JSONL metrics per run)
- `--metrics-tags` (optional tags injected into each metrics JSON line)
- `--request-id-header` (optional request id header name, empty disables)
- `--request-id-prefix` (request id prefix for per-request traceability)

## Admin Ops Helper (Invite-Only Beta)

Use the helper script for manual invite activation, manual top-up, and quick usage checks during closed beta:

```bash
# Activate invited account
python gateway/scripts/admin_ops.py ^
  --base-url http://127.0.0.1:8080 ^
  activate ^
  --admin-token admin-token ^
  --user-token dev-token ^
  --owner-id user-001 ^
  --email dev@example.com ^
  --status active

# Manual top-up with request id
python gateway/scripts/admin_ops.py ^
  --base-url http://127.0.0.1:8080 ^
  manual-topup ^
  --admin-token admin-token ^
  --user-token dev-token ^
  --credits 20 ^
  --reason invite-beta-manual-topup ^
  --request-id topup-001

# User balance and 7-day usage summary
python gateway/scripts/admin_ops.py --base-url http://127.0.0.1:8080 balance --user-token dev-token
python gateway/scripts/admin_ops.py --base-url http://127.0.0.1:8080 usage-summary --user-token dev-token --window 7d
python gateway/scripts/admin_ops.py --base-url http://127.0.0.1:8080 dashboard-overview --user-token dev-token
```

## Dashboard Contract Consistency Check

```bash
python gateway/scripts/verify_dashboard_contract.py --json
```

State file tracks:

- `last_success_at`
- `last_error` / `last_error_at`
- `last_cursor`
- `last_rows_written` / `last_duplicates_skipped` / `last_pages`
- `total_runs` / `total_rows_written` / `total_duplicates_skipped`

Metrics JSONL fields:

- `ts`
- `status` (`ok` or `error`)
- `cursor`
- `pages`
- `wrote_rows`
- `skipped_duplicates`
- `duration_seconds`
- `error_type` / `error` (error only)

## Prometheus Textfile Conversion

Convert metrics JSONL to node_exporter textfile format:

```bash
python gateway/scripts/metrics_to_prom.py ^
  --input .mmdev-gateway/sync-events.metrics.jsonl ^
  --output .mmdev-gateway/sync-events.prom ^
  --dry-run ^
  --output-mode replace ^
  --max-append-lines 0 ^
  --max-append-bytes 0 ^
  --window-hours 24 ^
  --group-by env,region ^
  --emit-zero-series ^
  --zero-series-tags env=prod,region=sg ^
  --atomic-write
```

`--output-mode`:

- `replace` (default): overwrite output (recommended for node_exporter textfile collector)
- `append`: append new snapshot text to existing file

`--dry-run`:

- Render metrics and print summary only
- Does not write output file

`--max-append-lines`:

- Only applies in `append` mode
- Keeps only latest N lines after each write
- `0` means no trimming

`--max-append-bytes`:

- Only applies in `append` mode
- Keeps only latest N bytes after each write
- `0` means no trimming
