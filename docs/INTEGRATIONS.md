# tokenpatch Integration Guide (CLI-First)

This guide is for configuration-first integration across popular coding agent tools.

## Recommended Routing Strategy

- Strong model (plan/review): user BYOK (`openai` or `claude`)
- Cheap executor (run): `deepseek_byok` or hosted `mmdev_gateway`

## Config Template: DeepSeek BYOK

```toml
strong_model_provider = "openai" # or "claude"
executor_provider = "deepseek_byok"

# OpenAI strong model
openai_api_key = "..."
openai_planner_model = "..."
openai_reviewer_model = "..."

# Claude strong model (optional alternative)
claude_api_key = ""
claude_base_url = "https://api.anthropic.com/v1"
claude_planner_model = ""
claude_reviewer_model = ""

# DeepSeek BYOK executor
deepseek_api_key = "..."
deepseek_base_url = "https://api.deepseek.com/v1"
deepseek_executor_model = "..."
```

## Config Template: tokenpatch Hosted Gateway

```toml
strong_model_provider = "openai" # or "claude"
executor_provider = "mmdev_gateway"

openai_api_key = "..."
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
- `OPENAI_API_KEY`, `OPENAI_PLANNER_MODEL`, `OPENAI_REVIEWER_MODEL`
- `CLAUDE_API_KEY`, `CLAUDE_BASE_URL`, `CLAUDE_PLANNER_MODEL`, `CLAUDE_REVIEWER_MODEL`
- `MMDEV_EXECUTOR_PROVIDER`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_EXECUTOR_MODEL`
- `MMDEV_GATEWAY_URL`, `MMDEV_GATEWAY_TOKEN`, `MMDEV_GATEWAY_EXECUTOR_MODEL`
- `MMDEV_GATEWAY_COUNTRY`, `MMDEV_GATEWAY_ENTITY`

## Entry-by-Entry Notes

### Codex CLI / Codex App

- Ensure workspace has `.mmdev/config.toml` via `tokenpatch init`.
- Export env vars in the same shell/session used by Codex.
- Run `tokenpatch plan`, then `tokenpatch run <task-id>` or `tokenpatch auto`.

### Claude Code

- Keep Claude API key in local env only.
- Use tokenpatch for execution orchestration instead of direct executor prompts.
- Prefer `tokenpatch auto --isolation worktree` for safer patch staging.

### Cursor

- Configure terminal env variables inside Cursor workspace shell profile.
- Use tokenpatch CLI commands in integrated terminal for deterministic runs.

### VS Code

- Same as Cursor: workspace terminal env + `tokenpatch` commands.
- Recommended: create VS Code tasks for `tokenpatch doctor`, `plan`, `auto`.

### Cline / Hermes (and similar agents)

- Keep strong model BYOK in agent environment.
- Route executor stage through tokenpatch CLI/gateway config.
- Keep protocol bounded to structured executor task flow; avoid free-form proxying.

## 30-Minute Bring-Up Checklist

1. `python -m pip install -e ".[test]"`
2. `tokenpatch init`
3. Fill strong model + executor config (BYOK or gateway)
4. `tokenpatch doctor --api`
5. `tokenpatch plan "<your requirement>"`
6. `tokenpatch run task-001` (or `tokenpatch auto ...`)
7. `tokenpatch report`
