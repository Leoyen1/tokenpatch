# tokenpatch FAQ

## What is tokenpatch?

tokenpatch is a local-first tool layer for AI coding. It helps a strong model plan or supervise work while a cheaper executor model applies bounded patches.

## Is tokenpatch a coding app, a plugin, or an agent?

It is best understood as a tool layer. You keep using Codex, Cursor, Claude Code, or your own agent. tokenpatch provides safe low-cost execution, checkpoints, memory, metrics, and reports.

## Do I need to configure my GPT or Claude key again?

Not in App Mode. Codex, Cursor, and Claude Code keep using their own strong-model configuration. tokenpatch only needs executor credentials. For the first public GitHub release, use your own DeepSeek key. tokenpatch.com gateway tokens are a later private beta path.

## Why does tokenpatch ask for allowed files?

Allowed files are the main safety boundary. tokenpatch rejects a generated patch if it changes files outside the allowed list.

Example:

```text
tp: update the login page. Only modify src/Login.tsx and src/login.css.
```

Long-form prompts such as `Use tokenpatch to update ...` still work. The
short `tp:` prefix is meant for daily use.

## Why is there a `.mmdev` directory?

`.mmdev` stores local audit and recovery state:

- checkpoints
- generated patches
- usage metrics
- reports
- project memory
- task state

Do not delete it if you want cost reporting and restore points.

## Why do I sometimes see CLI fallback instead of MCP?

Some apps do not reliably expose custom MCP tools in every session. tokenpatch installs app guidance so the coding app can fall back to the tokenpatch CLI while preserving the same safety checks.

If you see `tokenpatch CLI fallback`, that is expected for the MVP path.

## Why does the command still contain `python -m mmdev.cli`?

`mmdev` is the legacy internal Python package name kept for compatibility. The product name is tokenpatch. User-facing summaries should say `tokenpatch` or `tokenpatch CLI fallback`.

## Is `tp` the same as `tokenpatch`?

Yes. In terminal workflows, `tp` is a short command alias:

```bash
tp do "Update the title" --allowed-file index.html
tp metrics
tp report
```

In app workflows, `tp:` or the full-width-colon variant is the short natural-language trigger:

```text
tp: update the title. Only modify index.html.
```

## Can I use languages other than English?

Yes. Users can ask in any language. tokenpatch preserves the original requirement text. The docs, UI labels, metrics, and structured reports are English-first for open-source distribution.

## Does tokenpatch automatically commit my code?

No. tokenpatch does not automatically commit, reset, checkout, or delete user files. It applies bounded patches only after checking `allowed_files`.

## Does Safe Mode restore untracked files?

The first version restores Git-tracked files only. It records untracked files in the checkpoint metadata but does not delete or restore them automatically.

## Which DeepSeek model should I use?

For AI coding, the current default is `deepseek-v4-pro`. It costs more than a flash model but should have a better task completion rate for coding work.

## What is Project Memory Pack?

Project Memory Pack is a local deterministic summary of recent tasks, key files, checkpoints, validation/review status, and usage. It reduces repeated project explanation and helps avoid repeating failed approaches.

## Does tokenpatch send my whole repository to the executor?

No by design. The executor flow should receive bounded task context and allowed file snippets. The local safety layer still checks generated patches before applying them.

## Can I use tokenpatch.com credits instead of my own DeepSeek key?

That is the hosted gateway mode. In the current rollout, it is private beta /
invite-only and tokenpatch.com may not be publicly online yet:

```text
MMDEV_EXECUTOR_PROVIDER=mmdev_gateway
MMDEV_GATEWAY_URL=https://api.tokenpatch.com
MMDEV_GATEWAY_TOKEN=your-tokenpatch-token
```

The open-source client remains usable with your own DeepSeek key.

The planned hosted path exists because some users cannot easily apply for,
recharge, or manage a DeepSeek API key directly. For those users, tokenpatch.com
can eventually provide a convenience gateway token. It is optional, and BYOK
remains the core open-source path.

## What if I configure both tokenpatch.com credits and my own DeepSeek key?

They do not conflict. tokenpatch chooses the executor provider in this order:

1. Explicit `MMDEV_EXECUTOR_PROVIDER` / `executor_provider`
2. Gateway token present -> `mmdev_gateway`
3. DeepSeek key present -> `deepseek_byok`
4. Otherwise default to `deepseek_byok` and show a missing-credentials warning

If both are configured, set `executor_provider = "deepseek_byok"` to force your own DeepSeek key, or `executor_provider = "mmdev_gateway"` to force tokenpatch.com credits. `tokenpatch doctor` and `tokenpatch status` show the active provider and ignored credentials.

## How do I verify cost savings?

Run:

```bash
tokenpatch metrics --workdir .
tokenpatch report --workdir .
```

For projections:

```bash
python scripts/estimate_savings.py --usage-file .mmdev/reports/model-usage.jsonl --scenario both --pretty
```

Savings estimates are not exact billing statements. They are meant to make executor cost, strong-model baseline, checkpoints, and repeated-context avoidance visible.

For a detailed model of Codex/GPT-5.5, Cursor, and Claude Code/Opus 4.7 savings, see [Savings Estimates](SAVINGS.md).
