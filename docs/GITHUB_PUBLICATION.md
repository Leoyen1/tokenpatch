# GitHub Publication Review

This document records the intended public release boundary for the `tokenpatch`
open-source repository.

## Public Repository Scope

The public GitHub repository should contain:

- local CLI and Web Console
- MCP server and app integration helpers
- patch safety checks
- DeepSeek BYOK executor client
- hosted gateway client protocol
- examples, tests, and public documentation
- savings and patch-economics reporting

For the detailed file-by-file release boundary, see
`docs/PUBLIC_RELEASE_MANIFEST.md`.

## Keep Out Of This Repository

Do not publish:

- `tokenpatchweb/`
- hosted service production keys
- payment provider secrets or webhook secrets
- internal margin, markup, or pricing operations spreadsheets
- production database dumps
- customer source snippets or task logs
- private DeepSeek enterprise account details
- internal deployment runbooks

## Public Hosted Boundary

It is acceptable for the public repository to mention hosted gateway mode because
the open-source client needs to support tokenpatch.com tokens. Public docs should
describe it as:

```text
structured hosted executor service for bounded coding tasks
```

Do not describe it as direct resale of upstream model tokens.

If you mention tokenpatch.com hosted credits in the public repo, keep the wording
at private beta / invite-only until the website and automated payments are live.
The first GitHub release should be BYOK-first.

The public rationale is convenience: some users cannot easily get, recharge, or
manage a DeepSeek API key directly, so a future hosted executor token can make
tokenpatch easier to adopt. Do not frame it as required or as upstream token
resale.

## Security Checks Before Push

Run these checks from the repository root:

```bash
python -m pytest -q
python -m build
```

Then search for accidental secrets:

```bash
rg -n "sk-|api_key|secret|token|password" .
```

Expected findings include test fixtures and placeholder configuration names.
There should be no real production credentials.

## Packaging Checks

The Python package must include:

- `mmdev/prompts/*.md`
- `mmdev/templates/*.html`

Without the prompt files, installed planner/executor/reviewer commands will fail
at runtime.

## Recommended First GitHub Release

Recommended first public tag:

```text
v0.1.0
```

Recommended headline:

```text
Save AI coding tokens without switching editors.
```

Recommended differentiator:

```text
tokenpatch measures and reduces the cost per applied AI coding patch.
```

Recommended first-run app prompt:

```text
tp: implement a small bounded change. Only modify <files>.
```

Recommended proof wording:

```text
In a local smoke test, tokenpatch showed about 84.8% estimated savings versus
the default all-strong baseline.
```

Do not present the smoke result as a guaranteed saving. Savings depend on the
host model, executor model, task shape, cache hit rate, and whether the patch is
usable.
