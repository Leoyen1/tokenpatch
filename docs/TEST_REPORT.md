# tokenpatch MVP Test Report

Date: 2026-05-20

This report summarizes the current local MVP validation for tokenpatch across Codex App, Cursor, and Claude Code.

The goal of this round was not to benchmark model quality. The goal was to verify that the main user workflow works:

```text
User keeps their existing AI coding app
-> asks for tokenpatch
-> tokenpatch routes bounded executor work to DeepSeek v4 pro
-> allowed_files boundary is enforced locally
-> Safe Mode checkpoint is created
-> metrics/report are updated with patch economics
```

## Environment

- OS: Windows
- Project under test: `D:\Documents\GitHub\test`
- tokenpatch source repo: `D:\Documents\GitHub\modelt\tokenpatch`
- Executor provider: `deepseek_byok`
- Executor model: `deepseek-v4-pro`
- Primary invocation path: app guidance plus tokenpatch CLI fallback
- Local state: `.mmdev`

## Automated Test Suite

Latest full test suite result:

```text
128 passed, 91 warnings
```

Warnings are FastAPI / Python 3.14 deprecation warnings seen in the test environment. They are not functional blockers for the MVP.

## 2026-05-20 tp: Smoke Update

The latest app-facing UX is the short trigger:

```text
tp: implement the requested change. Only modify <files>.
```

Validated behavior:

- Codex App can follow the installed tokenpatch guidance and use tokenpatch CLI fallback when MCP tools are not visible. Codex may show a local command or network permission prompt during fallback; allowing the command and retrying the same prompt is expected.
- Cursor can use the project rule and CLI fallback with `tp:` prompts.
- Claude Code can use project guidance and CLI fallback with `tp:` prompts.
- User requirements can be English or Chinese. The installed guidance preserves the user's original requirement language.
- `tokenpatch report` prints a Savings Snapshot directly to stdout, including actual cost, all-strong baseline, estimated savings, savings ratio, applied patches, and cost per applied patch.

Observed real BYOK DeepSeek executor snapshot:

```text
Executor model: deepseek-v4-pro
Model calls: 18
Input tokens: 11,000
Output tokens: 3,775
Actual estimated cost: $0.023855
All-strong baseline estimate: $0.156915
Estimated savings: $0.133060
Estimated savings ratio: 84.80%
```

This is a local smoke result, not a guaranteed production benchmark. It is strong enough to use as careful public wording:

```text
In a local smoke test, tokenpatch showed about 84.8% estimated savings versus the default all-strong baseline.
```

## Manual App Tests

### Codex App

Status: usable MVP

Validated:

- Codex can follow tokenpatch guidance.
- When MCP tools are not visible, Codex can run tokenpatch CLI fallback.
- Bounded edits can be applied through tokenpatch.
- Metrics and final report can be viewed.
- Patch Economics reports generated patches, applied patches, accepted patches, cost per applied patch, and cost per accepted patch.
- DeepSeek executor usage is recorded.
- Safe Mode restore points are created.

Known limitation:

- Custom tokenpatch MCP tool visibility in Codex App is not fully reliable in every session.
- The reliable MVP path is tokenpatch CLI fallback through installed guidance.

### Cursor

Status: usable MVP

Validated:

- `tokenpatch bootstrap` installs `.cursor/rules/tokenpatch.mdc`.
- Cursor can interpret natural-language tokenpatch requests.
- Cursor can use tokenpatch CLI fallback when MCP tools are not visible.
- Cursor successfully performed bounded edits on `index.html` and `script.js`.
- Cursor preserved the user's language in replies after the multilingual rule update.
- Metrics and report retrieval work.
- Reports expose task-level cost, not only request-level cost.

Known limitation:

- Cursor MCP native tool exposure was not treated as the required MVP path.
- The stable path is project rule plus tokenpatch CLI fallback.

### Claude Code

Status: usable MVP

Validated:

- `tokenpatch bootstrap` writes project-level `.mcp.json`.
- Claude Code detects the new MCP server from `.mcp.json`.
- Claude Code asks the user to approve the project MCP server.
- `.claude/CLAUDE.md` guidance is installed.
- Claude Code can run tokenpatch metrics/report.
- Claude Code can perform a real bounded edit through tokenpatch.
- Chinese user prompts work and Claude Code replies in Chinese.
- Metrics increased after the edit, confirming executor usage.

Known limitation:

- In the observed run, Claude Code displayed `python -m mmdev.cli ...` for the shell command. This is the legacy internal Python module path. User-facing summaries should call it tokenpatch or tokenpatch CLI fallback.

## Latest Local Usage Snapshot

From `.mmdev/reports/final-report.md` in the test project:

```text
Total tasks: 1
Model calls: 17
Estimated input tokens: 10,317
Estimated output tokens: 3,517
Estimated total cost: $0.021123
Generated patches: 17
Cost per generated patch: about $0.001243
Execute calls: 17
Plan calls: 0
Review calls: 0
Repair calls: 0
Safe Mode restore points: 17
Latest restore point: 20260515T100330z-before-do-task-001
Project Memory Pack: key_files=3, recent_tasks=1
```

Cost by model:

```text
deepseek-chat: calls=1, input=538, output=194, cost=$0
deepseek-v4-pro: calls=16, input=9,779, output=3,323, cost=$0.021123
```

Interpretation:

- The early `deepseek-chat` call is historical from before the default executor model was standardized.
- Current executor calls are routed to `deepseek-v4-pro`.
- This test used direct bounded executor calls, so `plan/review/repair` are `0`.
- Older smoke runs did not configure all-strong baseline pricing, so their savings
  ratio was not meaningful. Current local reporting has a default all-strong
  baseline for clearer first-run feedback.

## Safety Checks Verified

Verified in manual runs and automated tests:

- `allowed_files` is enforced before patch application.
- Patches outside allowed files are rejected.
- Git project checks are required before applying patches.
- Safe Mode checkpoints are created before `do`, `run`, and app-driven task execution.
- Restore defaults to dry-run unless `--yes` is passed.
- `.mmdev` records patches, reports, metrics, memory, and checkpoints.
- tokenpatch does not auto-commit, reset, checkout, or delete user files.

## Multilingual Behavior

Validated:

- English prompts trigger tokenpatch.
- Chinese prompts trigger tokenpatch.
- Cursor and Claude Code can reply in the user's language.

Product rule:

- UI, docs, metrics, and structured reports are English-first.
- User requirements can be in any language.
- Installed app guidance tells agents to preserve the user's original requirement language.

## Recommended Smoke Tests

After running:

```bash
tokenpatch bootstrap
```

Use these prompts in Codex App, Cursor, or Claude Code:

```text
tp: change the page title to TokenPatch Smoke Test. Only modify index.html.
```

```text
tp: show metrics and report. Do not modify source files.
```

Multilingual test:

```text
用 tokenpatch 把页面标题改成多语言测试。只允许修改 index.html。
```
Expected result:

- The app uses tokenpatch MCP or tokenpatch CLI fallback.
- The edit is limited to `index.html`.
- A checkpoint is created.
- Metrics increase by one executor call.
- `deepseek-v4-pro` appears in usage.
- The final report is updated and includes `Patch Economics`.
- The report stdout includes `Savings Snapshot`.

## MVP Conclusion

The MVP is usable through the three highest-value entry points:

- Codex App
- Cursor
- Claude Code

The most reliable launch path is:

```text
bootstrap-installed guidance
-> tokenpatch MCP when visible
-> tokenpatch CLI fallback when MCP is not visible
```

This is acceptable for the first open-source/internal-test release because the user can keep their existing AI coding app and does not need to learn tokenpatch's low-level commands.

## Remaining Work

- Improve native MCP visibility and tool-call reliability per app.
- Add a dedicated Claude Code smoke-test section with screenshots once available.
- Add a packaged `tokenpatch` PyPI install path after release.
- Continue improving native MCP visibility and tool-call reliability per app.
- Keep public examples centered on `tp:` and `tp report`.
