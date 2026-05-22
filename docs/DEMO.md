# Demo Evidence

This is the kind of small, bounded task tokenpatch is designed to make cheaper.

## Task

```text
tp: change the page title to TokenPatch Test. Only modify index.html.
```

## Scope

```text
Allowed files:
- index.html
```

## Result

```text
Patch applied: yes
Changed files: index.html
Tests: passed
```

## Savings Snapshot

```text
All-strong estimate: $0.42
tokenpatch actual: $0.08
Saved: 81%
Cost per applied patch: $0.08
```

## Why This Matters

Most AI coding cost tools report request-level cost. tokenpatch reports task-level cost:

- what the coding task changed
- whether the patch was applied
- whether the task passed checks
- how much the bounded executor cost
- how much an all-strong-model baseline would likely have cost

The numbers above are an illustrative first-run demo, not a universal guarantee. Real savings depend on model prices, prompt size, cache behavior, task complexity, retries, and review strategy.

## Good First Tasks

Use tokenpatch first on small bounded tasks:

- update page copy
- add a simple UI control
- write or update a test
- fix a narrow bug in one or two files
- refactor a small helper

Avoid using tokenpatch as the first tool for open-ended architecture decisions, broad rewrites, security-sensitive code, or tasks where the target files are unknown.
