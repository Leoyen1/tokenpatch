# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added

- `tp` terminal entry point and `tp:` natural-language trigger for Codex,
  Cursor, Claude Code, and other app workflows.
- Report stdout now includes a Savings Snapshot so coding apps can summarize
  actual cost, all-strong baseline, savings ratio, and patch economics without
  opening `final-report.md`.
- Default all-strong local reporting baseline is now available when users have
  not configured their own baseline rates.
- Local Web Console displays Patch Economics cards.
- Metrics JSON and meta CSV now include task-level patch economics:
  generated patches, applied patches, accepted patches, failed tasks, cost per
  applied patch, savings per applied patch, cost per accepted patch, baseline
  cost per accepted patch, and savings per accepted patch.
- Public docs now emphasize savings ratio and cost per applied AI coding patch
  instead of only request-level token cost.

### Validated

- Local smoke tests through Codex, Cursor, and Claude Code can use tokenpatch
  through installed guidance and CLI fallback.
- A real DeepSeek BYOK smoke run with `deepseek-v4-pro` produced an estimated
  84.80% savings ratio versus the default all-strong baseline.

## [0.1.0] - 2026-05-11

### Added

- Rebranded CLI/package identity to `tokenpatch` while keeping `mmdev` command
  alias for compatibility.
- Local multi-model workflow covering planner, executor, validator/reviewer,
  report, metrics, and auto flow.
- Gateway executor provider mode in CLI (`mmdev_gateway`) alongside DeepSeek
  BYOK mode.
- Hosted executor client mode for tokenpatch.com gateway integration.
- Dashboard contract artifacts for frontend integration:
  - API contract doc
  - JSON example
  - TypeScript type definitions
  - OpenAPI fragment
- GitHub Actions workflows:
  - CI gate (tests)
  - release workflow (tag-triggered build/tests/artifact upload + optional PyPI publish)
- Open-source governance and launch docs:
  - `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`
  - AUP/ToS summary
  - integrations guide
  - release checklist

### Security

- Added explicit open-source vs hosted boundary documentation for key
  management and billing services.
- Added baseline compliance and guardrail documentation for hosted gateway
  operations.
