# tokenpatch MCP Client Setup

tokenpatch is designed to run inside the AI coding tool you already use. Start it as a local stdio MCP server and let Codex, Claude Code, Cursor, or another MCP-capable client call tokenpatch tools.

## Simplest Setup

For GUI apps, configure tokenpatch where the app already manages MCP servers.

### App Mode

```bash
tokenpatch bootstrap
```

This initializes `.mmdev`, installs Codex App guidance, installs Claude Code project MCP/memory files, installs Cursor project rules, and prints a smoke-test prompt.

Then open the app's MCP server settings for `tokenpatch` and add executor environment variables when you want app-level credential storage:

```text
MMDEV_EXECUTOR_PROVIDER=deepseek_byok
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro
```

For the future tokenpatch.com hosted executor private beta:

```text
MMDEV_EXECUTOR_PROVIDER=mmdev_gateway
MMDEV_GATEWAY_URL=https://api.tokenpatch.com
MMDEV_GATEWAY_TOKEN=your-tokenpatch-token
MMDEV_GATEWAY_EXECUTOR_MODEL=gateway-executor
```

The initial GitHub release is BYOK-first. If tokenpatch.com is not publicly
online yet, configure DeepSeek BYOK and ignore the gateway variables.

Hosted executor credits are planned as an optional convenience for users who
cannot easily manage a DeepSeek API key themselves.

Codex, Claude Code, and Cursor keep using their own strong-model settings, so tokenpatch does not need a second GPT/Claude key for MCP usage.

Users can ask in any language. Keep the UI, docs, metrics, and report labels English-first, but preserve the user's original requirement language when calling tokenpatch.

Open that project in Codex, Claude Code, or Cursor and ask it to use tokenpatch. You do not need to copy GPT/Claude API keys into tokenpatch; the host app remains the strong model.

### CLI Mode

For Codex CLI, Claude Code CLI, terminal agents, CI, or shared local config:

```bash
tokenpatch setup
```

This writes executor settings to `~/.tokenpatch/config.toml`.

## Generate Config

From your project root:

```bash
tokenpatch mcp-config --workdir .
tokenpatch mcp-config --workdir . --format markdown
```

Generic MCP config:

```json
{
  "mcpServers": {
    "tokenpatch": {
      "command": "tokenpatch",
      "args": ["mcp", "--workdir", "/absolute/path/to/project"]
    }
  }
}
```

## Recommended Agent Instruction

```text
When the user starts with tp:, asks to use tokenpatch, save tokens, run a low-cost executor, or make a safe AI coding change, prefer tokenpatch_auto. Strip only the tp: prefix and preserve the rest as the requirement. You are the strong planning model: choose a narrow allowed_files list and acceptance criteria, then let tokenpatch execute safely with its configured cheap executor. Use tokenpatch_plan and tokenpatch_run_task only when the user explicitly asks for step-by-step control.
```

## Codex

- Keep using Codex as the main coding experience.
- Easiest app install path:

```bash
tokenpatch bootstrap
```

- Codex-only install path:

```bash
tokenpatch install-codex
```

This backs up `~/.codex/config.toml`, installs the `tokenpatch` MCP server section, and prints the snippet it wrote. By default it uses dynamic workdir mode:

```toml
[mcp_servers.tokenpatch]
type = "stdio"
command = "tokenpatch"
args = ["mcp"]
```

In this mode Codex should launch tokenpatch from the active project directory, so you do not need to reinstall for every project. If you want a fixed project path instead, use:

```bash
tokenpatch install-codex --workdir /absolute/path/to/project --fixed-workdir
```

- Add tokenpatch as a stdio MCP server manually when you prefer editing config yourself.
- Configure executor credentials in the Codex MCP server settings environment variable section.
- If MCP is unavailable in your current Codex environment, use the same commands in the integrated terminal:

```bash
tokenpatch checkpoint create "before codex task"
tokenpatch memory refresh
tokenpatch plan "your requirement"
tokenpatch run task-001
tokenpatch report
```

## Claude Code

- Recommended: run the bootstrap command in each Claude Code workspace:

```bash
tokenpatch bootstrap
```

- Claude Code-only path:

```bash
tokenpatch install-claude-code
```

- This writes project-level `.mcp.json`, `.claude/CLAUDE.md`, and `.claude/tokenpatch_mcp_launcher.py`.
- Keep Claude API keys local to your own environment.
- Ask Claude Code to use tokenpatch tools for restore points, memory refresh, metrics, reports, and low-risk executor tasks.

## Cursor

- Recommended: run the bootstrap command in each Cursor workspace:

```bash
tokenpatch bootstrap
```

- Cursor-only path: install the project rule in the current workspace:

```bash
tokenpatch install-cursor
```

- The rule tells Cursor to try tokenpatch MCP first, then fall back to the tokenpatch CLI command `python -m mmdev.cli do ...` from the project terminal if MCP tools are not visible.
- Add tokenpatch as a stdio MCP server in Cursor MCP settings when available, but the CLI fallback is the reliable first MVP path.
- Keep tokenpatch credentials in global `~/.tokenpatch/config.toml`, project `.mmdev/config.toml`, Cursor MCP environment variables, or process environment variables available to Cursor.

## Smoke Test Prompt

After adding the MCP server, ask your coding tool:

```text
tp: check project status, create a restore point, refresh memory, and show the current tokenpatch report if one exists. Do not modify source files.
```

Expected tool calls:

- `tokenpatch_status`
- `tokenpatch_checkpoint_create`
- `tokenpatch_memory_refresh`
- `tokenpatch_report` or `tokenpatch_metrics`
