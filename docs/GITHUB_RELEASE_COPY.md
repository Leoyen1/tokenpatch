# GitHub Release Copy

Use this file when creating the public GitHub repository, first release, and
announcement posts.

## Repository About

Description:

```text
Save AI coding tokens without switching editors.
```

Website:

```text
https://github.com/Leoyen1/tokenpatch
```

Use the tokenpatch.com website only after it is publicly online.

Topics:

```text
ai-coding
coding-agent
mcp
codex
cursor
claude-code
deepseek
developer-tools
llm-cost
ai-agents
```

## One-Sentence Pitch

```text
tokenpatch helps Codex, Cursor, Claude Code, and MCP agents save AI coding tokens by routing bounded implementation patches to a lower-cost executor, then reporting cost per applied patch and estimated savings.
```

## Project Vision

```text
AI coding should not require every implementation token to run through the most expensive frontier model.

tokenpatch keeps the model you trust in charge of planning and review, while moving narrow implementation work to a lower-cost executor with local patch safety, recovery checkpoints, and visible savings.

The goal is to make serious AI coding cheaper without asking developers to switch editors, abandon their favorite agent, or give up control of their code.
```

## First Release Title

```text
tokenpatch v0.1.0: save AI coding tokens without switching editors
```

## First Release Notes

```markdown
tokenpatch v0.1.0 is the first public BYOK release.

It is designed for developers who already use Codex, Cursor, Claude Code, or MCP-capable coding agents and want to reduce AI coding cost without changing their main tool.

### Highlights

- `tp:` natural-language trigger for app workflows
- `tp` and `tokenpatch` CLI commands
- DeepSeek BYOK executor mode
- Codex, Cursor, and Claude Code guidance/bootstrap helpers
- local patch boundary checks with `allowed_files`
- Safe Mode checkpoints before AI edits
- Project Memory Pack for compact local context
- Metrics and reports with Savings Snapshot
- cost per applied patch, accepted patches, and estimated savings ratio

### Install

```bash
python -m pip install tokenpatch
```

For source install:

```bash
git clone https://github.com/Leoyen1/tokenpatch
cd tokenpatch
python -m pip install -e ".[test,web]"
```

### First run

```bash
tokenpatch bootstrap
```

Then ask your coding app:

```text
tp: implement a small bounded change. Only modify <files>.
```

### Rollout note

This release is BYOK-first: use your own DeepSeek API key for the executor path.

tokenpatch.com hosted executor credits are planned later as an optional convenience for users who cannot easily get, recharge, or manage a DeepSeek API key directly. The hosted path is not required for using tokenpatch.
```

## Launch Post

```text
I just released tokenpatch, an open-source tool layer for reducing AI coding cost.

It lets you keep using Codex, Cursor, Claude Code, or your own MCP-capable agent as the strong model, while routing narrow implementation patches to a lower-cost executor such as DeepSeek V4 Pro.

The focus is not generic request-level LLM cost. tokenpatch reports the metric developers actually care about: cost per applied AI coding patch.

First release is BYOK-first. Bring your own DeepSeek key, run `tokenpatch bootstrap`, then ask:

tp: implement a small bounded change. Only modify <files>.

GitHub: https://github.com/Leoyen1/tokenpatch
```

## Careful Savings Wording

Use:

```text
In a local smoke test, tokenpatch showed about 84.8% estimated savings versus the default all-strong baseline.
```

Avoid:

```text
Guaranteed 85% savings.
```

Savings depend on task shape, model choice, cache hit rate, prompt size, retry
rate, and whether the patch is actually useful.

## Hosted Credits Wording

Use:

```text
The first public release is BYOK-first. tokenpatch.com hosted executor credits are planned later as an optional convenience for users who cannot easily get, recharge, or manage a DeepSeek API key directly.
```

Avoid:

```text
Buy DeepSeek tokens from tokenpatch.
```

The product should be framed as an AI coding cost optimizer, not upstream token
resale.
