# Contributing

Thanks for improving tokenpatch.

## Development Setup

```bash
python -m pip install -e ".[test,gateway]"
```

## Basic Workflow

1. Create a feature branch.
2. Keep changes scoped to one concern.
3. Add or update tests for behavior changes.
4. Run test suite before opening PR.

```bash
python gateway/scripts/verify_dashboard_contract.py --json
python -m pytest -q
```

## Commit and PR Expectations

- Use clear commit messages with intent and scope.
- Document any config/env changes in `README.md` or `gateway/README.md`.
- For gateway security-sensitive changes, describe risk and mitigation in PR notes.
- For user-visible changes, update `CHANGELOG.md` under `[Unreleased]`.

## Release Notes

- Tag format: `vX.Y.Z` triggers `.github/workflows/release.yml`.
- For automated PyPI publish, configure repository secret `PYPI_API_TOKEN`.
- Follow `docs/RELEASE_CHECKLIST.md` for preflight, verification, and rollback procedure.

## Out of Scope for Open Repository

Please do not submit secrets, production credentials, or private billing integrations.  
`tokenpatch.com` payment and production key-management code is intentionally outside this repository.
