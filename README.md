# tokenpatch

Local-first CLI for a multi-model AI coding workflow:

- strong model plans structured tasks
- cheap executor model performs bounded low-risk implementation
- generated patches are checked against `allowed_files` before `git apply`
- task state and model usage are persisted in `.mmdev/state.sqlite`

This repository currently implements the local MVP flow from `multi-model-dev-agent-spec.md` for tokenpatch.

## Open-Source vs Hosted Boundary

`tokenpatch` is intentionally split into two parts:

- Open-source: local CLI/App workflows, task protocol, patch safety checks, integration templates, and documentation in this repository.
- Closed-source (or separately hosted): `tokenpatch.com` billing, balance ledger operations, payment/top-up operations, and production DeepSeek key management.

The local client supports two executor modes:

- `deepseek_byok`: user provides their own DeepSeek API key.
- `mmdev_gateway`: user sends bounded executor tasks to your hosted gateway using a gateway token.

In both modes, strong model planning/review can remain BYOK on user side (OpenAI or Claude).

Project governance files:

- [LICENSE](LICENSE)
- [SECURITY.md](SECURITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [AUP/ToS Summary](docs/AUP_TOS_SUMMARY.md)
- [API Contract](docs/API_CONTRACT.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)

## Install for development

```bash
python -m pip install -e ".[test]"
```

## CI Gate

GitHub Actions workflow `.github/workflows/tokenpatch-ci.yml` runs:

- dashboard contract consistency check
- repository test suite
- `examples/todo-app` test

Release workflow `.github/workflows/release.yml` runs on `v*` tags (or manual trigger):

- dashboard contract check
- test suite
- package build (`sdist` + `wheel`)
- artifact upload
- optional PyPI publish when `PYPI_API_TOKEN` is configured

## Commands

```bash
tokenpatch init
tokenpatch status
tokenpatch doctor
tokenpatch metrics
tokenpatch plan "为订单列表增加状态筛选"
tokenpatch run task-001
```

Run `tokenpatch doctor` before real model calls to check local state, dependencies, Git/worktree support, model configuration, and task plan availability. It does not call external APIs unless explicitly requested:

```bash
tokenpatch doctor --api
```

`--api` sends minimal JSON smoke-test requests to the configured OpenAI planner model and DeepSeek executor model.

Compatibility note: the legacy `mmdev` command is still available as an alias.

Phase 4/5 commands now available:

```bash
tokenpatch validate task-001
tokenpatch review task-001
tokenpatch report
tokenpatch auto "为订单列表增加状态筛选"
```

`auto` retries low-risk cheap-executor tasks up to each task's `max_attempts` when validation/review recommends `retry-cheap`. It stops on `ask-human` or `escalate-strong`; it does not automatically perform strong-model takeover.

To avoid modifying the current worktree directly, run against a Git project with at least one commit:

```bash
tokenpatch auto --isolation worktree "为订单列表增加状态筛选"
```

Worktree isolation executes task changes under `.mmdev/worktrees/<task-id>` while writing reports and state back to the main `.mmdev` directory.

Export an approved isolated result:

```bash
tokenpatch export task-001
```

This writes `.mmdev/patches/task-001-approved.patch` without modifying the main worktree. To apply it explicitly:

```bash
tokenpatch export task-001 --apply
```

## Example project

Use `examples/todo-app` for an end-to-end demo target:

```bash
cd examples/todo-app
git init
python -m pytest
tokenpatch init
tokenpatch auto --workdir examples/todo-app "为 todo 列表增加按 completed 状态筛选"
```

## Codex Skill

The repository includes a project-local skill at `skills/multi-model-dev`. It documents the safe Codex workflow and includes a thin wrapper:

```bash
python skills/multi-model-dev/scripts/mmdev.py status
```

## Multi-Entry Integration

`tokenpatch` can be integrated through configuration-first flows before any dedicated plugin work.  
See integration playbooks for Codex, Claude Code, Cursor, VS Code, and Cline/Hermes:

- [Integration Guide](docs/INTEGRATIONS.md)

## Configuration

Run `tokenpatch init` to create `.mmdev/config.toml`, then set values there or through environment variables. Environment variables take precedence:

- `OPENAI_API_KEY`
- `OPENAI_PLANNER_MODEL`
- `OPENAI_REVIEWER_MODEL`
- `CLAUDE_API_KEY`
- `CLAUDE_BASE_URL`
- `CLAUDE_PLANNER_MODEL`
- `CLAUDE_REVIEWER_MODEL`
- `MMDEV_STRONG_MODEL_PROVIDER`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_EXECUTOR_MODEL`
- `MMDEV_WORKDIR`
- `MMDEV_EXECUTOR_PROVIDER`
- `MMDEV_GATEWAY_URL`
- `MMDEV_GATEWAY_TOKEN`
- `MMDEV_GATEWAY_COUNTRY`
- `MMDEV_GATEWAY_ENTITY`
- `MMDEV_GATEWAY_POLICY_PATH`

Model names are not hardcoded; commands that need a model fail clearly if it is missing.

Strong model provider supports OpenAI and Claude BYOK:

```toml
strong_model_provider = "openai" # or "claude"

# OpenAI mode
openai_api_key = ""
openai_planner_model = ""
openai_reviewer_model = ""

# Claude mode
claude_api_key = ""
claude_base_url = "https://api.anthropic.com/v1"
claude_planner_model = ""
claude_reviewer_model = ""
```

Executor supports two modes:

```toml
executor_provider = "deepseek_byok"
deepseek_api_key = ""
deepseek_base_url = "https://api.deepseek.com/v1"
deepseek_executor_model = ""
```

or:

```toml
executor_provider = "mmdev_gateway"
mmdev_gateway_url = "https://api.yourdomain.com"
mmdev_gateway_token = ""
mmdev_gateway_executor_model = "gateway-executor"
mmdev_gateway_country = "SG" # optional
mmdev_gateway_entity = "tenant-001" # optional
```

Gateway mode sends only bounded executor tasks to `/v1/executor/run`; planner/reviewer keys remain local.

## Hosted Gateway Reference

This repository includes a reference server under `gateway/` for the hosted executor model. It is a starting point for a separate closed or independently deployed service:

```bash
python -m pip install -e ".[gateway]"
uvicorn gateway.mmdev_gateway.app:app --host 127.0.0.1 --port 8080
```

The reference gateway implements bearer-token auth, SQLite-backed account/usage storage, structured `/v1/executor/run`, usage/balance queries, admin freeze controls, and manual top-up audit ledger endpoints. Replace demo operations and fake executor behavior before production.

Optional cost estimation fields in `.mmdev/config.toml` use cost units per 1M tokens:

```toml
planner_input_cost_per_million = 0.0
planner_output_cost_per_million = 0.0
reviewer_input_cost_per_million = 0.0
reviewer_output_cost_per_million = 0.0
executor_input_cost_per_million = 0.0
executor_output_cost_per_million = 0.0
baseline_strong_input_cost_per_million = 0.0
baseline_strong_output_cost_per_million = 0.0
```

When set, `model-usage.jsonl`, `state.sqlite`, and `final-report.md` include estimated costs.
The baseline fields estimate what the same token volume would have cost if every call used a strong model, allowing the report to show estimated savings.

CLI run metadata is also recorded in:

- `.mmdev/logs/run-events.jsonl`

Each line includes timestamped route metadata (for example strong model provider/model, executor provider/model, task id, and requirement length) to support cost audit and troubleshooting.
CLI writes both `*.start` and `*.finish` events; `finish` includes `outcome` (`success` or `error`) for report-side route success aggregation.

Export machine-readable aggregates:

```bash
tokenpatch metrics --pretty
```

Use `--compact` for one-line JSON output.
Use `--out <file>` to write JSON directly to a file.
Use `--window 24h|7d|30d` (or `all`) for time-windowed aggregates.
Use `--csv-dir <dir>` to export grouped CSV files (`usage_by_model_purpose.csv`, `strong_route_stats.csv`, `auto_route_stats.csv`).
Use `--csv-prefix <name>` with `--csv-dir` to add a shared filename prefix.
Use `--csv-meta` with `--csv-dir` to export one-row batch metadata CSV (`meta.csv`).
Use `--push <url>` to POST metrics JSON to your collector endpoint (`--push-token` and `--push-timeout-seconds` are optional).
