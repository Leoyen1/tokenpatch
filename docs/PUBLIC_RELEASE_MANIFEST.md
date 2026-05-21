# Public Release Manifest

This manifest describes the intended public GitHub repository contents for
`tokenpatch`.

Use it before the first public push to confirm that the repository contains the
open-source client and does not contain hosted-service internals.

## Repository Root

Keep:

- `.github/workflows/tokenpatch-ci.yml`
- `.github/workflows/release.yml`
- `.gitignore`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `README.md`
- `REMOTE_SETUP.md`
- `SECURITY.md`
- `pyproject.toml`

Purpose:

- package metadata
- GitHub Actions
- contribution/security/release documentation
- public project entry point

## Client Package

Keep `mmdev/`.

Important public modules:

- `cli.py`: tokenpatch and legacy mmdev CLI entry points
- `tp` is packaged as the short CLI alias for the same Typer app
- `mcp_server.py`: MCP server for Codex, Claude Code, Cursor, and other clients
- `config.py`: local/global/app environment config resolution
- `executor.py`, `planner.py`, `reviewer.py`, `validator.py`: core workflow
- `patcher.py`, `git_utils.py`: patch safety and Git operations
- `checkpoint.py`: local restore points
- `memory.py`: deterministic project memory pack
- `metrics.py`, `reporter.py`, `patch_economics.py`: task-level cost reporting
  with generated/applied/accepted patch economics
- `web_console.py`, `templates/`: local Web Console
- `models/`: OpenAI, Claude, DeepSeek BYOK, and hosted gateway clients
- `prompts/`: packaged prompt files required at runtime

Packaging requirement:

- `mmdev/prompts/*.md` must be included in the wheel.
- `mmdev/templates/*.html` must be included in the wheel.

## Documentation

Keep `docs/`.

Recommended public docs:

- `INSTALL.md`
- `QUICKSTART.md`
- `INTEGRATIONS.md`
- `MCP_CLIENTS.md`
- `SAVINGS.md`
- `FAQ.md`
- `TEST_REPORT.md`
- `TOKENPATCH_MCP_SMOKE_TEST.md`
- `API_CONTRACT.md`
- `GITHUB_PUBLICATION.md`
- `PUBLIC_RELEASE_MANIFEST.md`
- `RELEASE_CHECKLIST.md`
- `AUP_TOS_SUMMARY.md`

Dashboard contract files may stay public because they describe the client-facing
hosted gateway contract, not the hosted implementation:

- `dashboard-overview.example.json`
- `dashboard-overview.openapi-fragment.yaml`
- `dashboard-overview.types.ts`

## Examples

Keep `examples/todo-app/`.

Purpose:

- simple local project for smoke tests
- fake demo flow without real API keys
- regression target for CI

## Scripts

Keep `scripts/`.

Current public scripts:

- `estimate_savings.py`
- `start_web.ps1`
- `start_web.sh`

These are local helper scripts. They must not require production hosted-service
secrets.

## Skills

Keep `skills/multi-model-dev/` for compatibility with the earlier Codex skill
workflow.

Future cleanup can rename this skill path to tokenpatch, but do not remove it
before confirming no existing users or tests depend on it.

## Tests

Keep `tests/`.

The public test suite should cover:

- CLI commands
- config resolution
- DeepSeek BYOK client behavior with fake transport
- hosted gateway client protocol with fake transport
- MCP server
- checkpoint and memory behavior
- patch safety
- metrics, report, and patch economics
- Web Console API
- install helpers for Codex, Cursor, and Claude Code

## Intentional Deletes

These deletions are expected and should not be restored into the public
repository:

- `gateway/`
- `tests/test_gateway_admin_ops_script.py`
- `tests/test_gateway_server.py`
- `tests/test_metrics_to_prom_script.py`
- `tests/test_sync_events_script.py`
- `tests/test_verify_dashboard_contract_script.py`
- `multi-model-dev-agent-spec.md`

Reason:

- hosted gateway implementation, admin scripts, and operational tests belong in
  `tokenpatchweb/`, not the open-source client repository
- the old specification document was outdated and contained broken encoding

## Do Not Publish

Keep these out of the public GitHub repository:

- `tokenpatchweb/`
- `codex/` handoff notes
- `.mmdev/` runtime state
- generated smoke projects
- real API keys or gateway tokens
- payment provider credentials
- production database files
- customer code snippets, task logs, or usage exports
- internal pricing, margin, or operations documents

## Pre-Push Verification

From `tokenpatch/`:

```bash
python -m pytest -q
python -m pip wheel . --no-deps --no-build-isolation -w dist
```

Then inspect the wheel:

```bash
python -c "import zipfile, pathlib; w=next(pathlib.Path('dist').glob('tokenpatch-*.whl')); print('\n'.join(n for n in zipfile.ZipFile(w).namelist() if 'mmdev/prompts/' in n or 'mmdev/templates/' in n))"
```

Expected prompt/template entries:

```text
mmdev/prompts/executor.md
mmdev/prompts/planner.md
mmdev/prompts/reviewer.md
mmdev/templates/index.html
mmdev/templates/onboarding.html
mmdev/templates/settings.html
mmdev/templates/setup.html
```
