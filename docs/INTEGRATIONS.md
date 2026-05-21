# tokenpatch Integration Guide

This guide is for integrating tokenpatch into the coding tools users already use.
For GUI apps, configure tokenpatch inside the app's MCP server settings. For
terminal-first workflows, use the global tokenpatch setup page.

## Core Routing Strategy

- The user's existing coding app and strong model decide what should change.
- tokenpatch runs narrow, file-scoped implementation patches with a cheaper executor.
- The local client checks patch boundaries and reports usage/cost.

Local recovery checkpoints and compact context are automatic support mechanisms.
They exist to reduce wasted retries and repeated context, not to change the
user's normal editor workflow.

## App Mode: Codex / Claude Code / Cursor

GUI apps already have the user's strong model configured. In this mode,
tokenpatch should not ask for another OpenAI or Claude key. The host app acts as
the strong planning model, then tokenpatch safely runs the low-cost executor.

Bootstrap the current project, then set executor environment variables in the
app's MCP server settings when you want app-level credential storage.

```bash
tokenpatch bootstrap
```

DeepSeek BYOK:

```text
MMDEV_EXECUTOR_PROVIDER=deepseek_byok
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro
```

Future tokenpatch hosted gateway private beta:

```text
MMDEV_EXECUTOR_PROVIDER=mmdev_gateway
MMDEV_GATEWAY_URL=https://api.tokenpatch.com
MMDEV_GATEWAY_TOKEN=your-tokenpatch-token
MMDEV_GATEWAY_EXECUTOR_MODEL=gateway-executor
```

The open-source launch is BYOK-first. tokenpatch.com hosted credits are a later
private beta path and may not be publicly online yet.

That hosted path is planned for users who cannot easily get, recharge, or manage
a DeepSeek API key directly. It should not be treated as required for normal
tokenpatch usage.

After restarting the app, use natural language:

```text
tp: implement ... Only modify <files>.
```

Equivalent requests in other languages are valid. The host app should preserve
the user's original requirement language when passing the task to tokenpatch and
reply in the user's language unless asked otherwise.

The recommended MCP flow is `tokenpatch_auto`: the host model chooses a narrow
goal, allowed files, and acceptance criteria; tokenpatch runs the executor,
checks patch boundaries, and reports cost. Recovery points and memory refresh
happen in the background.

## CLI Mode: Global Setup

Use this path when running tokenpatch directly from a terminal, CI, or another
CLI agent that does not provide GUI MCP environment settings.

Configure once:

```bash
tokenpatch setup
```

Then initialize each project:

```bash
tokenpatch init
```

## Config Template: DeepSeek BYOK

This template is for `~/.tokenpatch/config.toml` or advanced local config.
In MCP App Mode, prefer the environment variables above instead.

```toml
strong_model_provider = "openai" # or "claude"
executor_provider = "deepseek_byok"

# OpenAI strong model
openai_api_key = "..."
openai_base_url = "https://api.openai.com/v1"
openai_api_mode = "responses" # responses or chat_completions
openai_planner_model = "..."
openai_reviewer_model = "..."

# Claude strong model (optional alternative)
claude_api_key = ""
claude_base_url = "https://api.anthropic.com/v1"
claude_planner_model = ""
claude_reviewer_model = ""

# DeepSeek BYOK executor
deepseek_api_key = "..."
deepseek_base_url = "https://api.deepseek.com"
deepseek_executor_model = "deepseek-v4-pro"
```

## Config Template: tokenpatch Hosted Gateway Private Beta

This template is for terminal workflows. In GUI app MCP settings, use the
gateway environment variables from App Mode. Use this only if you have been
given a private beta gateway token.

```toml
strong_model_provider = "openai" # or "claude"
executor_provider = "mmdev_gateway"

openai_api_key = "..."
openai_base_url = "https://api.openai.com/v1"
openai_api_mode = "responses"
openai_planner_model = "..."
openai_reviewer_model = "..."

mmdev_gateway_url = "https://api.tokenpatch.com"
mmdev_gateway_token = "tp_..."
mmdev_gateway_executor_model = "gateway-executor"
mmdev_gateway_country = "SG"       # optional
mmdev_gateway_entity = "team-001"  # optional
```

## Environment Variable Equivalent

Set these in your shell/tool runtime when file-based config is not convenient:

- `MMDEV_STRONG_MODEL_PROVIDER`
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_API_MODE`, `OPENAI_PLANNER_MODEL`, `OPENAI_REVIEWER_MODEL`
- `CLAUDE_API_KEY`, `CLAUDE_BASE_URL`, `CLAUDE_PLANNER_MODEL`, `CLAUDE_REVIEWER_MODEL`
- `MMDEV_EXECUTOR_PROVIDER`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_EXECUTOR_MODEL`
- `MMDEV_GATEWAY_URL`, `MMDEV_GATEWAY_TOKEN`, `MMDEV_GATEWAY_EXECUTOR_MODEL`
- `MMDEV_GATEWAY_COUNTRY`, `MMDEV_GATEWAY_ENTITY`

### OpenAI-compatible relay, including cc switch

If your GPT model is provided through an OpenAI-compatible relay, keep
`strong_model_provider = "openai"` and configure the relay endpoint:

```toml
strong_model_provider = "openai"
openai_api_key = "your-relay-key"
openai_base_url = "https://your-cc-switch-endpoint/v1"
openai_api_mode = "chat_completions"
openai_planner_model = "your-gpt-model-name"
openai_reviewer_model = "your-gpt-model-name"
```

Use `openai_api_mode = "responses"` only when the relay supports
`/v1/responses`. Many OpenAI-compatible relays only support
`/v1/chat/completions`, so `chat_completions` is usually the safer first
choice for cc switch.

## Entry-by-Entry Notes

## MCP Integration (Recommended)

tokenpatch is best used as a tool layer inside the editor or agent you already like. Start the local stdio MCP server:

```bash
tokenpatch mcp --workdir /path/to/project
```

You can generate a copy-paste config with:

```bash
tokenpatch mcp-config --workdir /path/to/project
tokenpatch mcp-config --workdir /path/to/project --format markdown
```

For Codex on your local machine, the simplest install path is:

```bash
tokenpatch bootstrap
```

This initializes `.mmdev`, installs launcher mode so Codex does not depend on
PATH, cwd, or editable install details, installs Claude Code project MCP/memory
files, and installs Cursor project rules.
Configure DeepSeek credentials in the app's MCP server settings environment
variable section or in `~/.tokenpatch/config.toml`. Gateway credentials are for
private beta users only.

See [MCP Client Setup](MCP_CLIENTS.md) for Codex, Claude Code, and Cursor notes.

Expose that command in your MCP-capable client as a stdio server. The client keeps its normal chat/editing workflow, while tokenpatch provides bounded tools for low-cost execution, patch safety, reports, and metrics.

Available MCP tools:

- `tokenpatch_init`
- `tokenpatch_status`
- `tokenpatch_doctor`
- `tokenpatch_checkpoint_create`
- `tokenpatch_checkpoint_list`
- `tokenpatch_checkpoint_diff`
- `tokenpatch_checkpoint_restore`
- `tokenpatch_memory_refresh`
- `tokenpatch_memory_show`
- `tokenpatch_auto`
- `tokenpatch_plan`
- `tokenpatch_run_task`
- `tokenpatch_report`
- `tokenpatch_metrics`

Recommended agent instruction:

```text
When the user starts with tp:, asks to use tokenpatch, save tokens, run a low-cost executor, or make a safe AI coding change, prefer tokenpatch_auto. Strip only the tp: prefix and preserve the rest as the requirement. You are the strong planning model: choose a narrow allowed_files list and acceptance criteria, then let tokenpatch execute safely with its configured cheap executor.
```

Generic stdio config shape:

```json
{
  "mcpServers": {
    "tokenpatch": {
      "command": "tokenpatch",
      "args": ["mcp", "--workdir", "/path/to/project"]
    }
  }
}
```

### Codex CLI / Codex App

- Codex App: configure executor credentials in the MCP server settings.
- Codex CLI or terminal use: configure executor credentials once with `tokenpatch setup`.
- In each workspace, run `tokenpatch init`.
- Prefer `tp: implement ... Only modify <files>.` in Codex App. Use `tokenpatch plan`, `tokenpatch run <task-id>`, or `tokenpatch auto` only when you want CLI control.

### Claude Code

- Keep Claude API key in local env only.
- Run `tokenpatch bootstrap` inside the project. Claude Code-only path: `tokenpatch install-claude-code`.
- `install-claude-code` writes `.mcp.json`, `.claude/CLAUDE.md`, and `.claude/tokenpatch_mcp_launcher.py`.
- In Claude Code App, put tokenpatch executor credentials in the MCP server environment settings.
- Use tokenpatch for bounded execution instead of direct executor prompts.

### Cursor

- Run `tokenpatch bootstrap` inside the project. Cursor-only path: `tokenpatch install-cursor`.
- `install-cursor` installs `.cursor/rules/tokenpatch.mdc`.
- The Cursor rule tells Agent mode to try tokenpatch MCP first, then use CLI fallback if MCP tools are not visible.
- In Cursor App, put tokenpatch executor credentials in MCP server environment settings when using MCP, or keep them in `~/.tokenpatch/config.toml` / process environment for CLI fallback.
- For deterministic runs, Cursor can use the tokenpatch CLI fallback generated by the rule: `python -m mmdev.cli do "<requirement>" --allowed-file <file> --workdir .`.

### VS Code

- Same as Cursor: workspace terminal env + `tokenpatch` commands.
- Recommended: create VS Code tasks for `tokenpatch doctor`, `do`, and `report`.

### Cline / Hermes (and similar agents)

- Keep strong model BYOK in agent environment.
- Route executor stage through tokenpatch CLI/gateway config.
- Keep protocol bounded to structured executor task flow; avoid free-form proxying.

## 30-Minute Bring-Up Checklist

1. `python -m pip install -e ".[test]"`
2. GUI app: `tokenpatch bootstrap`, then fill executor env vars in MCP settings if needed
3. CLI mode: `tokenpatch setup`
4. GUI app: ask `tp: implement ... Only modify <files>.`
5. CLI mode: `tp doctor --api`, then `tp do "<your requirement>" --allowed-file <file>`
6. `tokenpatch report`
