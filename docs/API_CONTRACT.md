# tokenpatch API Contract (MVP)

This document defines the stable API contract for tokenpatch hosted gateway integrations.

## Scope

- Applies to dashboard read APIs in gateway MVP.
- Execution protocol (`mmdev.executor.v1`) remains separately documented in code and gateway README.

## Versioning

- Current dashboard schema version: `2026-05-11.v1`
- Response header for dashboard APIs:
  - `X-TokenPatch-Schema-Version: 2026-05-11.v1`
- Response body fixed field:
  - `schema_version: "2026-05-11.v1"`

## Compatibility Rules

1. Additive-only changes are allowed inside a schema version (new optional fields only).
2. Existing fields must not change type or semantic meaning within the same schema version.
3. Removing or changing required fields requires a new schema version.
4. Clients should gate parsing by `X-TokenPatch-Schema-Version`.
5. Clients should ignore unknown fields for forward compatibility.

## Authentication

- User endpoints use user gateway bearer token:
  - `Authorization: Bearer <gateway_token>`
- Admin endpoints use admin bearer token:
  - `Authorization: Bearer <admin_token>`

## Dashboard Endpoints

### 1) User Overview

- Method: `GET`
- Path: `/v1/dashboard/overview`
- Auth: user token

### 2) Admin Overview (for a target account)

- Method: `GET`
- Path: `/v1/admin/accounts/{token}/dashboard/overview`
- Auth: admin token

## Dashboard Response Schema

```json
{
  "schema_version": "2026-05-11.v1",
  "token": "string",
  "balance_credits": 0.0,
  "generated_at": "2026-05-11T10:00:00+00:00",
  "usage_7d": {
    "window": "7d",
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "charged_credits": 0.0,
    "provider_cost": 0.0
  },
  "usage_30d": {
    "window": "30d",
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "charged_credits": 0.0,
    "provider_cost": 0.0
  },
  "savings_estimate_7d": {
    "window": "7d",
    "baseline_strong_cost": 0.0,
    "actual_charged_credits": 0.0,
    "provider_cost": 0.0,
    "savings_vs_charged": 0.0,
    "savings_vs_provider": 0.0,
    "savings_ratio_vs_charged": 0.0,
    "savings_ratio_vs_provider": 0.0
  },
  "savings_estimate_30d": {
    "window": "30d",
    "baseline_strong_cost": 0.0,
    "actual_charged_credits": 0.0,
    "provider_cost": 0.0,
    "savings_vs_charged": 0.0,
    "savings_vs_provider": 0.0,
    "savings_ratio_vs_charged": 0.0,
    "savings_ratio_vs_provider": 0.0
  }
}
```

Reference artifacts:

- JSON example: `docs/dashboard-overview.example.json`
- TypeScript types: `docs/dashboard-overview.types.ts`
- OpenAPI fragment: `docs/dashboard-overview.openapi-fragment.yaml`

## Field Notes

- `balance_credits`: current available gateway credits.
- `usage_7d` / `usage_30d`: observed usage aggregates by rolling window.
- `baseline_strong_cost`: estimated hypothetical all-strong cost based on configured baseline rates.
- `actual_charged_credits`: amount charged to account by gateway pricing policy.
- `provider_cost`: upstream provider raw cost estimate.
- `savings_vs_charged`: `baseline_strong_cost - actual_charged_credits`.
- `savings_vs_provider`: `baseline_strong_cost - provider_cost`.
- `savings_ratio_*`: percentage against `baseline_strong_cost`; returns `0` when baseline is `0`.

## Related Configuration

- `MMDEV_GATEWAY_BASELINE_STRONG_INPUT_COST_PER_MILLION`
- `MMDEV_GATEWAY_BASELINE_STRONG_OUTPUT_COST_PER_MILLION`

Without baseline config, baseline cost is `0`, and savings ratios are returned as `0` to avoid divide-by-zero.

## Error Behavior

- `401`: missing/invalid bearer auth header.
- `403`: invalid token or token not authorized for endpoint.
- `404` (admin path): target account does not exist.

## Change Process (Recommended)

1. Update `gateway/mmdev_gateway/schemas.py` and `gateway/mmdev_gateway/app.py`.
2. Add or update gateway contract tests in `tests/test_gateway_server.py`.
3. If breaking contract, bump schema version and keep old version in compatibility window.
4. Update this document and `gateway/README.md` in same change.

## Consistency Check Script

Run this before release to verify cross-file version consistency:

```bash
python gateway/scripts/verify_dashboard_contract.py --json
```
