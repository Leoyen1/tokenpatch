from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class CursorInstallResult:
    rules_path: Path
    backup_path: Path | None
    changed: bool
    dry_run: bool
    rule_text: str


def default_cursor_rule_path(workdir: Path) -> Path:
    return workdir / ".cursor" / "rules" / "tokenpatch.mdc"


def install_cursor_rules(
    *,
    workdir: Path,
    rules_path: Path | None = None,
    dry_run: bool = False,
    python_command: str = "python",
) -> CursorInstallResult:
    target = rules_path or default_cursor_rule_path(workdir)
    rule_text = cursor_rule_text(python_command=python_command)
    original = target.read_text(encoding="utf-8") if target.exists() else ""
    changed = original != rule_text
    backup_path: Path | None = None
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        if changed and target.exists():
            backup_path = target.with_suffix(target.suffix + f".tokenpatch-{timestamp()}.bak")
            backup_path.write_text(original, encoding="utf-8")
        if changed:
            target.write_text(rule_text, encoding="utf-8")
    return CursorInstallResult(
        rules_path=target,
        backup_path=backup_path,
        changed=changed,
        dry_run=dry_run,
        rule_text=rule_text,
    )


def cursor_rule_text(*, python_command: str = "python") -> str:
    cli = f"{python_command} -m mmdev.cli"
    return f"""---
description: Use tokenpatch for safe low-cost coding edits
alwaysApply: true
---

# tokenpatch

Use tokenpatch when the user starts with `tp:` or `tp：`, says tokenpatch, save tokens, low-cost edit, safe edit, restore point, metrics, or report.

Rules:
- Treat `tp:` and `tp：` as the shortest tokenpatch trigger. Strip only that prefix and pass the rest of the message as the original requirement.
- Users may ask in any language. Preserve the user's original requirement language when passing it to tokenpatch.
- Reply to the user in their language unless they ask otherwise.
- Do not directly edit source files before trying tokenpatch.
- If tokenpatch MCP tools are visible, use them first.
- If tokenpatch MCP tools are not visible, use the tokenpatch CLI fallback from the current project root.
- Keep `allowed_files` narrow. If the user gives allowed files, pass exactly those files.
- If the user does not give allowed files, inspect only enough to choose the smallest reasonable file list.
- Do not delete `.mmdev`; it stores checkpoints, patches, metrics, memory, and reports.
- If tokenpatch is unavailable or blocked, explain the blocker before falling back to direct edits.
- In user-facing summaries, say "tokenpatch" or "tokenpatch CLI fallback"; do not say "mmdev CLI".

tokenpatch CLI fallback for coding edits:

```powershell
{cli} do "<requirement>" --allowed-file <file> --workdir .
```

Repeat `--allowed-file` for every allowed file. Add `--acceptance "<check>"` when useful.

tokenpatch CLI fallback for metrics and reports:

```powershell
{cli} report --workdir .
{cli} metrics --workdir .
```

When summarizing metrics/report results, show Savings ratio, Estimated savings, Applied patches, Cost per applied patch, and Savings per applied patch first.

Preferred user phrasing:

```text
tp: implement ... Only modify file1, file2.
```

Long-form equivalent:

```text
Use tokenpatch to implement ... Only modify file1, file2.
```

Equivalent requests in other languages are also valid.
"""


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
