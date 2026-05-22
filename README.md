# tokenpatch

Save AI coding tokens without switching editors.

Official website: [tokenpatch.com](https://tokenpatch.com)

tokenpatch lets Codex, Cursor, Claude Code, CLI agents, and MCP clients keep their configured strong model in charge, then route safe implementation patches to a cheaper executor such as DeepSeek V4 Pro.

The key metric is not just request cost. tokenpatch measures the cost per applied AI coding patch, then tracks accepted patches as the stricter validation/review signal.

## Vision

AI coding should not require every implementation token to run through the most
expensive frontier model. tokenpatch keeps the model you trust in charge of
planning and judgment, while moving narrow implementation work to a lower-cost
executor with local patch safety, recovery checkpoints, and visible savings.

The goal is simple: make serious AI coding cheaper without asking developers to
switch editors, abandon their favorite agent, or give up control of their code.

The main workflow is intentionally simple:

```text
Your coding app's strong model decides what should change.
tokenpatch sends the bounded patch work to a low-cost executor.
tokenpatch checks the patch, applies it locally, and reports what it cost.
```

## Why It Exists

AI coding gets expensive when every implementation token is spent on a frontier model. Most projects do not need the most expensive model to write every small diff. tokenpatch keeps the expensive model focused on judgment and uses a low-cost executor for narrow, file-scoped changes.

What users see:

- one natural-language request inside the coding app they already use
- a narrow `allowed_files` scope
- lower-cost executor usage
- savings ratio, cost per applied patch, usage, and accepted-patch reporting after the run

What tokenpatch handles automatically:

- `allowed_files` is checked before any patch is applied.
- A local recovery checkpoint is created before AI edits.
- Compact project context reduces repeated exploration.
- Metrics and reports track executor tokens, estimated cost, and savings.
- No auto-commit, reset, checkout, or user-file deletion.

## Works With

- Codex App and Codex CLI
- Claude Code
- Cursor
- VS Code / Cline / other MCP-capable agents
- Terminal workflows and CI

You can ask in any language. The docs, UI labels, metrics, and reports are English-first.

## Install

First public release is BYOK-first. Bring your own DeepSeek API key for the
executor path. tokenpatch.com hosted credits are planned later for users who
cannot easily get, recharge, or manage a DeepSeek key directly.

```bash
python -m pip install -e ".[test,web]"
```

See [Install Guide](docs/INSTALL.md) for PyPI, source, Codex, Cursor, Claude Code, Windows, and CLI setup.

## App Quickstart

For Codex App, Claude Code App, Cursor, or other GUI MCP clients:

1. Bootstrap the current project.

```bash
tokenpatch bootstrap
```

This initializes `.mmdev`, installs app guidance for Codex, Claude Code, and Cursor, and prints a smoke-test prompt.

2. If you use app-level MCP environment settings, add executor variables:

```text
MMDEV_EXECUTOR_PROVIDER=deepseek_byok
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro
```

Then ask naturally:

```text
tp: implement ... Only modify <files>.
```

Long-form requests like `Use tokenpatch to implement ...` still work.

You can ask in any language. The app UI, docs, and structured reports are English-first, but tokenpatch preserves your original requirement text for the coding task.

See [Quickstart](docs/QUICKSTART.md) for the full first-run flow and [FAQ](docs/FAQ.md) for common questions.

## CLI/Web Quickstart

For terminal, CLI agents, CI, or shared configuration across tools:

```bash
tokenpatch setup
tokenpatch init
tokenpatch doctor --api
tokenpatch do "Add a status filter" --allowed-file src/orders.tsx
```

## CLI Commands

Most users only need:

```bash
tokenpatch bootstrap
tokenpatch do "Implement a small change" --allowed-file path/to/file
tp do "Implement a small change" --allowed-file path/to/file
tokenpatch metrics
tp metrics
tokenpatch report
tp report
```

Advanced/debug commands:

```bash
tokenpatch init
tokenpatch status
tokenpatch doctor
tokenpatch plan "Add a status filter to the order list"
tokenpatch run task-001
tokenpatch validate task-001
tokenpatch review task-001
tokenpatch report
tokenpatch auto "Add a status filter to the order list"
tokenpatch export task-001
tokenpatch metrics --pretty
tokenpatch checkpoint create "before refactor"
tokenpatch checkpoint list
tokenpatch checkpoint restore <checkpoint-id> --yes
tokenpatch memory refresh
tokenpatch memory show
tokenpatch web
tokenpatch mcp --workdir .
```

Compatibility note: legacy `mmdev` command alias is still available.

## Example Project

Use `examples/todo-app`:

```bash
cd examples/todo-app
git init
python -m pytest
tokenpatch init
tokenpatch auto --workdir examples/todo-app "Add a completed-status filter to the todo list"
```

Web demo path:

```bash
tokenpatch web --workdir examples/todo-app
```

Then perform: requirement -> run -> report.

## Configuration

GUI apps should use their MCP server settings for executor environment variables. CLI and terminal workflows can use `tokenpatch setup` to configure the low-cost executor once.
When tokenpatch is used through Codex, Claude Code, or Cursor MCP, those tools keep using their own strong-model configuration; tokenpatch only needs executor credentials.

The setup page writes:

```text
~/.tokenpatch/config.toml
```

New projects only need:

```bash
tokenpatch init
```

Config priority is: environment variables > project `.mmdev/config.toml` > global `~/.tokenpatch/config.toml`.

Executor provider selection:

1. Explicit `MMDEV_EXECUTOR_PROVIDER` / `executor_provider`
2. Gateway token present -> `mmdev_gateway`
3. DeepSeek key present -> `deepseek_byok`
4. Otherwise defaults to `deepseek_byok` and asks for executor credentials

If both a gateway token and a DeepSeek key are configured, the explicit provider wins. `tokenpatch status` and `tokenpatch doctor` show the active provider, why it was selected, and which credentials are ignored.

Key env vars:

- `MMDEV_STRONG_MODEL_PROVIDER`
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_API_MODE`, `OPENAI_PLANNER_MODEL`, `OPENAI_REVIEWER_MODEL`
- `CLAUDE_API_KEY`, `CLAUDE_BASE_URL`, `CLAUDE_PLANNER_MODEL`, `CLAUDE_REVIEWER_MODEL`
- `MMDEV_EXECUTOR_PROVIDER`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_EXECUTOR_MODEL`
- `MMDEV_GATEWAY_URL`, `MMDEV_GATEWAY_TOKEN`, `MMDEV_GATEWAY_EXECUTOR_MODEL`
- `MMDEV_GATEWAY_COUNTRY`, `MMDEV_GATEWAY_ENTITY`
- `MMDEV_WORKDIR`

For OpenAI-compatible relay services such as cc switch, set `OPENAI_BASE_URL`
to the relay `/v1` endpoint. Keep `OPENAI_API_MODE=responses` if the relay
supports `/v1/responses`; otherwise use `OPENAI_API_MODE=chat_completions`.

## Open-Source vs Hosted Boundary

This repository is the open-source client and workflow layer.

- Open-source: local CLI/Web workflows, MCP integration, patch safety, examples, docs, and public protocol contracts.
- Hosted/closed: future tokenpatch.com billing, production key management,
  credit balances, manual top-ups, and operational dashboards.
- The first GitHub release is BYOK-first. tokenpatch.com and hosted credits are
  private beta / invite-only and may not be publicly online yet.
- The planned hosted path is for users who cannot easily get, recharge, or
  manage a DeepSeek API key themselves. It is a convenience layer, not a
  requirement for using tokenpatch.

Execution modes:

- `deepseek_byok` for user-owned DeepSeek keys
- `mmdev_gateway` for future hosted executor tokens / private beta

Strong model planning and review remain BYOK through OpenAI or Claude.

## Integrations

- [Install Guide](docs/INSTALL.md)
- [Quickstart](docs/QUICKSTART.md)
- [Savings Estimates](docs/SAVINGS.md)
- [MVP Test Report](docs/TEST_REPORT.md)
- [GitHub Publication Review](docs/GITHUB_PUBLICATION.md)
- [Public Release Manifest](docs/PUBLIC_RELEASE_MANIFEST.md)
- [MCP Client Setup](docs/MCP_CLIENTS.md)
- [Integration Guide](docs/INTEGRATIONS.md)
- [FAQ](docs/FAQ.md)

Use MCP or app rules when you want Codex, Claude Code, Cursor, or another agent to call tokenpatch without changing your editor:

```bash
tokenpatch bootstrap
```

After that, ask naturally: `tp: implement ... Only modify <files>.`

The `tp:` prefix is the shortest app trigger. The `tp` terminal command is the
short CLI alias for `tokenpatch`.

## Cost And Savings

tokenpatch saves money primarily by delegating safe implementation patches to a cheaper executor while the strong model stays in charge of judgment. Its reports focus on task-level economics: how much a useful applied patch cost, whether it became an accepted patch after validation/review, and how that compares with an all-strong-model baseline.

Report highlights include:

- estimated savings ratio as the first-glance "did this save money?" signal
- applied patches, so users can see that a bounded edit really landed even before formal review
- accepted patches and generated patches
- cost per applied patch for the immediate "what did this useful change cost?" moment
- actual cost per accepted patch for stricter validation/review workflows
- all-strong baseline cost per applied and accepted patch
- estimated savings per applied and accepted patch
- route success, retries, and model usage by purpose

Safe Mode and Memory Pack are supporting mechanisms:

- Safe Mode creates restore points before AI edits, so failed runs do not require long strong-model debugging sessions to recover the project.
- Memory Pack stores deterministic project/task summaries locally, so prompts can reuse compact context instead of repeatedly explaining the same codebase.

Estimate from usage log:

```bash
python scripts/estimate_savings.py --usage-file .mmdev/reports/model-usage.jsonl --scenario both --cache-hit-ratio 0.0 --pretty
```

Monthly projection:

```bash
python scripts/estimate_savings.py --usage-file .mmdev/reports/model-usage.jsonl --scenario both --cache-hit-ratio 0.0 --monthly-runs 1000 --pretty
```

## Common Troubleshooting

| Symptom | Likely Cause | Quick Fix |
|---|---|---|
| Plan fails before request | Missing strong model key/model | Configure API key and planner/reviewer model |
| Run fails with git error | Not a git repository | Run `git init` and commit baseline |
| Run rejected by boundary check | Patch changed files outside `allowed_files` | Narrow task scope and re-plan |
| Executor config missing | DeepSeek/hosted settings incomplete | Fill `deepseek_*` or `mmdev_gateway_*` fields |

Default DeepSeek executor settings follow the official OpenAI-compatible API:

```toml
deepseek_base_url = "https://api.deepseek.com"
deepseek_executor_model = "deepseek-v4-pro"
```

## CI and Release

- CI: `.github/workflows/tokenpatch-ci.yml`
- Release: `.github/workflows/release.yml`

