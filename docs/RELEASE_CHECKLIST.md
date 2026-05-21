# tokenpatch Release Checklist

This checklist is for publishing tokenpatch releases with repeatable quality and rollback clarity.

## 1) Scope and Version

- Decide release scope (features/fixes/docs only).
- Select version number (recommended SemVer): `vMAJOR.MINOR.PATCH`.
- Confirm release notes draft is ready.
- Update `CHANGELOG.md` (`[Unreleased]` -> released version section).

## 2) Pre-Release Local Checks

From repository root:

```bash
python -m pytest -q
python -m pytest -q examples/todo-app
python -m build
```

Expected:

- All tests pass
- Wheel and sdist build successfully

## 3) Security and Config Sanity

- Confirm no secrets are committed.
- Confirm `DEEPSEEK_API_KEY` is never required in open-source CI.
- Confirm docs still describe open-source vs hosted boundary correctly.
- Confirm any hosted-credit wording is clearly marked private beta / invite-only
  until tokenpatch.com and automated payment are live.
- Confirm `mmdev/prompts/*.md` and `mmdev/templates/*.html` are included in the package.
- Confirm `tokenpatchweb/` and internal hosted-service docs are not part of the public repository.

## 4) Tag and Trigger Release Workflow

```bash
git tag v0.1.0
git push origin v0.1.0
```

This triggers `.github/workflows/release.yml`:

- tests
- build sdist/wheel
- upload artifacts
- optional PyPI publish when `PYPI_API_TOKEN` exists

## 5) Post-Release Verification

- Check GitHub Actions run status is green.
- Download `tokenpatch-dist` artifact and verify wheel/sdist exist.
- If PyPI publish is enabled, confirm package version appears on PyPI.
- Smoke-test install in clean environment:

```bash
python -m pip install tokenpatch==0.1.0
tokenpatch --help
```

## 6) Rollback / Mitigation

If release pipeline fails:

1. Stop further tag pushes.
2. Diagnose failure (tests, packaging, documentation, or release config).
3. Fix in a PR and re-run CI.
4. Publish a new patch version tag (`vX.Y.Z+1`) instead of mutating old release artifacts.

If PyPI release is problematic:

1. Publish a corrected patch version immediately.
2. Mark broken version as yanked on PyPI (if needed).
3. Add incident note in release changelog.

## 7) Optional Communication Template

- What changed
- Any migration or config impact
- Known limitations
- Next planned milestone
