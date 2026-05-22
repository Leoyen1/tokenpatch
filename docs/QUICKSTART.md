# tokenpatch Quickstart

tokenpatch helps your existing AI coding app spend less on implementation tokens.

It reports cost at the level developers care about: one accepted patch, not just one model request.

The simple path is:

```text
Codex / Cursor / Claude Code decides what should change
-> tokenpatch sends a narrow patch task to a cheaper executor
-> tokenpatch checks the patch and reports cost
```

Local recovery checkpoints, compact context, and detailed reports run in the
background. You do not need to learn them before the first run.

## 1. Install

For the first public GitHub release:

```bash
pip install git+https://github.com/Leoyen1/tokenpatch.git
```

After PyPI packaging, the intended shorter command is:

```bash
pip install tokenpatch
```

## 2. Configure The Executor

Codex, Cursor, and Claude Code already have your strong model configured. tokenpatch does not need your GPT or Claude key for App Mode.

For DeepSeek BYOK, set these in the app's MCP/server environment settings, your shell, or `~/.tokenpatch/config.toml`:

```text
MMDEV_EXECUTOR_PROVIDER=deepseek_byok
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro
```

For the future tokenpatch.com gateway private beta:

```text
MMDEV_EXECUTOR_PROVIDER=mmdev_gateway
MMDEV_GATEWAY_URL=https://api.tokenpatch.com
MMDEV_GATEWAY_TOKEN=your-tokenpatch-token
MMDEV_GATEWAY_EXECUTOR_MODEL=gateway-executor
```

The public GitHub launch is BYOK-first. tokenpatch.com and hosted executor
credits are not required for the first release and may not be publicly online
yet.

The planned hosted path is only a convenience option for users who cannot easily
get, recharge, or manage a DeepSeek API key directly.

## 3. Bootstrap A Project

Run this once inside or against each project:

```bash
tokenpatch bootstrap
```

Or with an explicit path:

```bash
tokenpatch bootstrap --workdir /path/to/project
```

Bootstrap initializes `.mmdev`, installs app guidance for Codex, Claude Code,
and Cursor, and prints a smoke-test prompt.

## 4. Use It In Your Coding App

Open the project in Codex App, Cursor, Claude Code, or another MCP-capable coding tool.

Ask naturally:

```text
tp: add a button that changes the page title. Only modify index.html and script.js.
```

Long-form requests like `Use tokenpatch to ...` still work. `tp:` and `tp：`
are just the shortest triggers.

You can ask in any language. The UI, docs, metrics, and structured reports are English-first, but tokenpatch preserves your original requirement text for the coding task.

## 5. Check Metrics And Report

Ask your coding app:

```text
tp: show metrics and report. Do not modify source files.
```

Or run directly:

```bash
tokenpatch metrics --workdir .
tokenpatch report --workdir .
tp metrics --workdir .
tp report --workdir .
```

The report shows executor calls, token usage, generated/applied/accepted patches, cost per applied patch, cost per accepted patch, and a savings ratio versus an all-strong-model baseline.

## 6. Advanced Recovery

tokenpatch creates a checkpoint before AI edits. Most users can ignore this
until something goes wrong. To inspect checkpoints:

```bash
tokenpatch checkpoint list --workdir .
tokenpatch checkpoint diff <checkpoint-id> --workdir .
```

Restore is dry-run by default. To actually restore tracked Git files:

```bash
tokenpatch checkpoint restore <checkpoint-id> --workdir . --yes
```

## 7. Expected First Success

A good first run should show:

- `status: executed`
- changed files limited to your allowed files
- a checkpoint like `before-do-task-001`
- model usage under `deepseek-v4-pro` or gateway executor
- an updated `.mmdev/reports/final-report.md`

If MCP tools are not visible in your app, the installed guidance should use tokenpatch CLI fallback automatically.
