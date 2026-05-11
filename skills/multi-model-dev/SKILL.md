---
name: multi-model-dev
description: Run a local multi-model coding workflow with the tokenpatch CLI. Use when Codex needs to reduce AI coding cost by using a strong model for planning/review, a cheaper bounded executor model for low-risk implementation, local validation commands, patch boundary checks, and final reporting.
---

# Multi-Model Dev

Use the repository's `tokenpatch` CLI. Do not bypass validation or patch boundary checks.

## Workflow

1. Inspect project state first:

   ```bash
   git status --short
   tokenpatch status
   tokenpatch doctor
   ```

   `doctor` is local-only unless `--api` is passed. Use it before real model calls to catch missing config, Git/worktree problems, and missing `.mmdev/tasks.json`. Use `tokenpatch doctor --api` only when the user wants to send minimal smoke-test requests to configured model APIs.

2. Initialize local state if needed:

   ```bash
   tokenpatch init
   ```

3. For full automation, run:

   ```bash
   tokenpatch auto "<user requirement>"
   ```

   `auto` may retry low-risk cheap-executor tasks up to `max_attempts` when review recommends `retry-cheap`. It stops on `ask-human` or `escalate-strong`; do not force continuation manually.

   Executor provider can be either local BYOK DeepSeek or the hosted tokenpatch gateway. In gateway mode, verify `executor_provider = "mmdev_gateway"`, `mmdev_gateway_url`, and `mmdev_gateway_token` are configured. Never place the service-side DeepSeek API key in this open-source client.

   Prefer worktree isolation for real projects that have at least one commit:

   ```bash
   tokenpatch auto --isolation worktree "<user requirement>"
   ```

5. To bring an approved isolated result back to the main worktree, export first:

   ```bash
   tokenpatch export task-001
   ```

   Apply only with explicit user intent:

   ```bash
   tokenpatch export task-001 --apply
   ```

4. For manual control, run:

   ```bash
   tokenpatch plan "<user requirement>"
   tokenpatch run task-001
   tokenpatch validate task-001
   tokenpatch review task-001
   tokenpatch report
   ```

## Required Checks

- Review `.mmdev/tasks.json` after planning when the task is risky, broad, or ambiguous.
- Only run cheap executor tasks when `complexity` is `low` and `recommended_executor` is `cheap`.
- Treat `allowed_files` as a hard boundary.
- Stop and ask the user if a task touches security, auth, permissions, migrations, destructive operations, or unclear architecture.
- Do not run validation commands that are not in `tasks.json` unless the user explicitly confirms them.
- Always report where `.mmdev/reports/final-report.md` was written.

## Failure Handling

- If `tokenpatch run` rejects a patch for modifying files outside `allowed_files`, do not apply it manually.
- If validation fails with clear logs, retry the bounded executor once only if the task remains low risk.
- If validation fails for unclear reasons, use strong-model analysis or ask the user.
- If review recommends `ask-human` or `escalate-strong`, stop the cheap-executor path.

## References

- Read `references/task-schema.md` when inspecting or editing `.mmdev/tasks.json`.
- Read `references/routing-rules.md` when deciding whether cheap execution is appropriate.
- Read `references/review-rules.md` when interpreting review results.

## Helper Script

Use `scripts/mmdev.py` as a thin wrapper when you want a stable command surface:

```bash
python skills/multi-model-dev/scripts/mmdev.py status
python skills/multi-model-dev/scripts/mmdev.py auto "<user requirement>"
```
