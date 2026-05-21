# tokenpatch Install Guide

This guide covers the practical install paths for early users and local development.

## Requirements

- Python 3.11+
- Git
- One AI coding app or agent, such as Codex App, Cursor, Claude Code, Codex CLI, or a terminal-based agent
- One executor option:
  - your own DeepSeek API key, or
  - a tokenpatch.com gateway token for private beta / manual-top-up access

Codex, Cursor, and Claude Code keep using their own strong-model settings. tokenpatch does not need a second GPT or Claude key in App Mode.

## Install From PyPI

After release:

```bash
python -m pip install tokenpatch
```

Verify:

```bash
tokenpatch --help
```

## Install From Source

For local development from this repository:

```bash
git clone https://github.com/Leoyen1/tokenpatch
cd tokenpatch
python -m pip install -e ".[test,web]"
```

Verify:

```bash
tokenpatch --help
python -m pytest
```

## Configure DeepSeek BYOK

Use this when you want to run the executor with your own DeepSeek key:

```text
MMDEV_EXECUTOR_PROVIDER=deepseek_byok
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro
```

You can store these in:

- your app's MCP server environment settings
- your shell environment
- `~/.tokenpatch/config.toml` via `tokenpatch setup`

## Configure tokenpatch.com Gateway

Use this only if you have been invited to the hosted executor private beta.
The initial GitHub release is BYOK-first, and tokenpatch.com may not be
publicly online yet.

This future path is intended for users who cannot easily get, recharge, or
manage a DeepSeek API key directly. If you already have a DeepSeek key, use
DeepSeek BYOK first.

```text
MMDEV_EXECUTOR_PROVIDER=mmdev_gateway
MMDEV_GATEWAY_URL=https://api.tokenpatch.com
MMDEV_GATEWAY_TOKEN=your-tokenpatch-token
MMDEV_GATEWAY_EXECUTOR_MODEL=gateway-executor
```

## Bootstrap A Project

Run once per project:

```bash
tokenpatch bootstrap
```

Or target a specific project:

```bash
tokenpatch bootstrap --workdir /path/to/project
```

Bootstrap does these local setup steps:

- initializes `.mmdev`
- installs Codex App MCP guidance and skill files
- installs Claude Code project MCP config and `.claude/CLAUDE.md`
- installs Cursor project rules
- prints a smoke-test prompt

It does not upload your GPT/Claude keys.

## Codex App

1. Install tokenpatch.
2. Run `tokenpatch bootstrap` in the project.
3. Add executor environment variables in Codex App's MCP server settings if you want app-level credential storage.
4. Restart Codex App or open a new chat.
5. Ask:

```text
tp: update the page title. Only modify index.html.
```

If custom MCP tools are not visible, the installed guidance should use tokenpatch CLI fallback.

## Cursor

1. Install tokenpatch.
2. Run `tokenpatch bootstrap` in the project.
3. Reopen the project in Cursor.
4. Use Agent mode.
5. Ask:

```text
tp: add a button. Only modify index.html and script.js.
```

Cursor can use the generated `.cursor/rules/tokenpatch.mdc` rule and fall back to the tokenpatch CLI when MCP tools are unavailable.

## Claude Code

Claude Code can use tokenpatch through project-level MCP plus `.claude/CLAUDE.md` guidance.

Recommended first path:

```bash
tokenpatch bootstrap
```

Claude Code-only install path:

```bash
tokenpatch install-claude-code
```

This writes:

- `.mcp.json`
- `.claude/CLAUDE.md`
- `.claude/tokenpatch_mcp_launcher.py`

Then ask Claude Code to use tokenpatch for bounded tasks and keep `allowed_files` narrow:

```text
tp: implement ... Only modify <files>.
```

## CLI And Terminal Agents

For CLI-first usage:

```bash
tokenpatch setup
tokenpatch init
tokenpatch doctor --api
tokenpatch auto "Add a status filter to the order list"
tokenpatch report
```

If you want a single bounded executor task without strong-model planning:

```bash
tokenpatch do "Change the page title to TokenPatch Test" --allowed-file index.html --workdir .
```

## Windows Notes

If `tokenpatch` is not on PATH, use Python module mode:

```powershell
C:\Python314\python.exe -m mmdev.cli bootstrap --workdir D:\path\to\project
```

The public command is `tokenpatch`; `mmdev.cli` is the legacy Python module path kept for compatibility.

## Verify A Successful Install

Ask your coding app:

```text
tp: show metrics and report. Do not modify source files.
```

Or run:

```bash
tokenpatch metrics --workdir .
tokenpatch report --workdir .
```

You should see model usage, estimated executor cost, checkpoint count, and a final report path.

## Uninstall

Python package:

```bash
python -m pip uninstall tokenpatch
```

Local project state is stored in `.mmdev`. Do not delete it unless you intentionally want to remove checkpoints, metrics, reports, memory, and patches.

Codex integration files live under `~/.codex`. Claude Code project files live in `.mcp.json` and `.claude/`. Cursor project rules live under `.cursor/rules/tokenpatch.mdc`.
