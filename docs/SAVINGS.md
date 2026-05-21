# tokenpatch Savings Estimates

This document explains the current savings model for large AI coding projects.

The short version:

- On the executor work that can be safely routed to tokenpatch, estimated savings are roughly **84% to 94%** versus running the same implementation tokens through GPT-5.5 or Claude Opus 4.7.
- For a large project with 500M total coding tokens and 70% to 85% safely routable executor work, estimated savings are roughly:
  - **Codex + GPT-5.5**: `$3,410` to `$4,141`
  - **Cursor + GPT-5.5**: `$3,410` to `$4,141`
  - **Cursor + Opus 4.7**: `$2,965` to `$3,600`
  - **Claude Code + Opus 4.7**: `$2,965` to `$3,600`

These are estimates, not billing statements.

## The Metric That Matters

Generic LLM cost tools usually stop at request-level cost. tokenpatch is focused on AI coding economics:

- how much one development task cost
- whether the task produced an accepted patch
- whether the generated patch was applied locally
- cost per applied patch
- cost per accepted patch
- savings ratio versus an all-strong-model baseline
- savings per accepted patch versus an all-strong-model baseline
- failed tasks and retries that did not produce usable code

This is why the final report includes a `Patch Economics` section. A cheap model call is not useful by itself; a cheap applied patch is what gives the user immediate confidence, and a cheap accepted patch is the stricter quality signal after validation or review.

## Why tokenpatch Can Save Money

AI coding sessions often mix two kinds of work:

1. Strong-model work:
   - understanding the requirement
   - planning
   - choosing files
   - reviewing risky changes
   - deciding when to stop

2. Executor work:
   - editing bounded files
   - applying small refactors
   - making UI tweaks
   - fixing local bugs
   - repeating safe implementation attempts

tokenpatch keeps the user's existing AI coding app as the strong model and routes bounded executor work to a cheaper model, currently DeepSeek v4 pro by default.

## Pricing Assumptions

DeepSeek v4 pro pricing used in this document:

| Token Type | Price per 1M tokens |
|---|---:|
| Input, cache hit | `$0.011` |
| Input, cache miss | `$1.286` |
| Output | `$2.572` |

Strong-model assumptions used for estimates:

| Model | Input per 1M | Output per 1M |
|---|---:|---:|
| GPT-5.5 | `$5` | `$30` |
| Claude Opus 4.7 | `$5` | `$25` |

Cursor is estimated by the underlying model used. If Cursor uses GPT-5.5, use the GPT-5.5 row. If Cursor uses Opus 4.7, use the Opus 4.7 row.

## Current Observed Token Mix

The current local MVP smoke test produced this approximate executor token mix:

| Token Type | Count | Share |
|---|---:|---:|
| Input | `10,317` | `74.6%` |
| Output | `3,517` | `25.4%` |

This mix is used for the blended per-token estimates below.

## Blended Cost Per 1M Executor Tokens

Using the observed token mix:

| Route | Estimated cost per 1M blended tokens |
|---|---:|
| GPT-5.5 | `$11.36` |
| Claude Opus 4.7 | `$10.08` |
| DeepSeek v4 pro, input cache miss | `$1.61` |
| DeepSeek v4 pro, 50% input cache hit | `$1.14` |
| DeepSeek v4 pro, input cache hit | `$0.66` |

## Savings Per 100M Routable Executor Tokens

This table measures only the work that tokenpatch can safely route to the low-cost executor.

| Tool / Strong Model | DeepSeek input all cache miss | DeepSeek input 50% cache hit | DeepSeek input all cache hit |
|---|---:|---:|---:|
| Codex + GPT-5.5 | `$974` saved | `$1,022` saved | `$1,069` saved |
| Cursor + GPT-5.5 | `$974` saved | `$1,022` saved | `$1,069` saved |
| Cursor + Opus 4.7 | `$847` saved | `$895` saved | `$942` saved |
| Claude Code + Opus 4.7 | `$847` saved | `$895` saved | `$942` saved |

Conservative savings ratio:

| Strong Model | DeepSeek cache miss savings ratio |
|---|---:|
| GPT-5.5 | `85.8%` |
| Claude Opus 4.7 | `84.0%` |

With better input cache hit rates, savings can rise toward `90%` to `94%` on routable executor work.

## Large Project Estimate

Not every token in a real project should be routed to tokenpatch. Strong models should still handle planning, judgment, risky review, and ambiguous architecture decisions.

For large projects, two practical routing assumptions are:

- Conservative: `70%` of total coding tokens can be routed to tokenpatch executor work.
- Strong: `85%` of total coding tokens can be routed to tokenpatch executor work.

The table below assumes DeepSeek input cache miss, which is the conservative DeepSeek case.

### 500M Total Coding Tokens

| Tool / Strong Model | 70% routable | 85% routable |
|---|---:|---:|
| Codex + GPT-5.5 | `$3,410` saved | `$4,141` saved |
| Cursor + GPT-5.5 | `$3,410` saved | `$4,141` saved |
| Cursor + Opus 4.7 | `$2,965` saved | `$3,600` saved |
| Claude Code + Opus 4.7 | `$2,965` saved | `$3,600` saved |

### 1B Total Coding Tokens

| Tool / Strong Model | 70% routable | 85% routable |
|---|---:|---:|
| Codex + GPT-5.5 | `$6,820` saved | `$8,281` saved |
| Cursor + GPT-5.5 | `$6,820` saved | `$8,281` saved |
| Cursor + Opus 4.7 | `$5,930` saved | `$7,201` saved |
| Claude Code + Opus 4.7 | `$5,930` saved | `$7,201` saved |

## Tool-by-Tool Notes

### Codex with GPT-5.5

Codex using GPT-5.5 has the largest estimated dollar savings in this model because GPT-5.5 output is expensive.

Best fit:

- large feature implementation
- repeated local fixes
- UI and frontend tasks
- bounded refactors
- test-driven small changes

Estimated conservative savings:

- about `$974` per 100M routable executor tokens
- about `$4,871` per 500M routable executor tokens
- about `$9,743` per 1B routable executor tokens

### Cursor

Cursor savings depend on the underlying model and plan.

If Cursor is effectively using GPT-5.5-priced model usage, use the GPT-5.5 estimate.

If Cursor is effectively using Opus 4.7-priced model usage, use the Opus 4.7 estimate.

Because Cursor users often perform many small iterative edits, tokenpatch may be especially useful when Cursor can reliably use project rules and CLI fallback.

### Claude Code with Opus 4.7

Claude Code plus Opus is one of the strongest use cases.

Opus is valuable for planning, reasoning, and review, but many implementation steps do not need Opus-level intelligence. tokenpatch can preserve Opus for the judgment layer while routing bounded patch execution to DeepSeek v4 pro.

Estimated conservative savings:

- about `$847` per 100M routable executor tokens
- about `$4,236` per 500M routable executor tokens
- about `$8,472` per 1B routable executor tokens

## What Makes Savings Higher

Savings improve when:

- many tasks are bounded to a small `allowed_files` list
- the project has repeated implementation loops
- DeepSeek input cache hit rate is meaningful
- Memory Pack reduces repeated project explanation
- Safe Mode avoids long strong-model recovery sessions after a bad edit
- the strong model is expensive, especially for output tokens

## What Makes Savings Lower

Savings are smaller when:

- tasks are mostly architecture, product strategy, or ambiguous reasoning
- the strong model must review every small change in detail
- changes span many files and cannot be safely bounded
- the project is tiny
- the user already uses a very cheap model for most implementation work
- failed executor attempts require repeated strong-model intervention

## Practical Product Claim

A conservative, defensible claim for the current MVP is:

```text
For bounded AI coding implementation work, tokenpatch can reduce executor-model token cost by roughly 84% to 94% compared with GPT-5.5 or Claude Opus 4.7, depending on the strong model and DeepSeek input cache hit rate.
```

For whole projects, a more careful claim is:

```text
On large coding projects where 70% to 85% of tokens are implementation-heavy and safely routable, tokenpatch may reduce total model spend by roughly 55% to 80%, depending on routing quality, cache behavior, and review needs.
```

Do not present these estimates as guaranteed savings. Treat them as a planning model and validate against real usage with:

```bash
tokenpatch metrics --workdir .
tokenpatch report --workdir .
python scripts/estimate_savings.py --usage-file .mmdev/reports/model-usage.jsonl --scenario both --pretty
```
