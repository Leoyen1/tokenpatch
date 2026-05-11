# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added

- TBD

## [0.1.0] - 2026-05-11

### Added

- Rebranded CLI/package identity to `tokenpatch` while keeping `mmdev` command alias for compatibility.
- Local multi-model workflow covering planner, executor, validator/reviewer, report, metrics, and auto flow.
- Gateway executor provider mode in CLI (`mmdev_gateway`) alongside DeepSeek BYOK mode.
- Hosted gateway reference service with:
  - structured executor endpoint (`/v1/executor/run`)
  - usage/balance/task endpoints
  - admin account controls (freeze/unfreeze, set credits, profile updates)
  - manual top-up audit ledger and query endpoints
  - policy event export/summary/trend endpoints
  - dashboard overview endpoints with schema-versioned contract
- Dashboard contract artifacts for frontend integration:
  - API contract doc
  - JSON example
  - TypeScript type definitions
  - OpenAPI fragment
- Operational helper scripts:
  - event sync
  - metrics to Prometheus conversion
  - admin ops helper
  - dashboard contract consistency verifier
- GitHub Actions workflows:
  - CI gate (contract check + tests)
  - release workflow (tag-triggered build/tests/artifact upload + optional PyPI publish)
- Open-source governance and launch docs:
  - `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`
  - AUP/ToS summary
  - integrations guide
  - release checklist

### Security

- Added explicit open-source vs hosted boundary documentation for key management and billing services.
- Added baseline compliance and guardrail documentation for hosted gateway operations.
