from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_CLAUDE_EXECUTOR_ENV = {
    "MMDEV_EXECUTOR_PROVIDER": "deepseek_byok",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_EXECUTOR_MODEL": "deepseek-v4-pro",
}


@dataclass(frozen=True)
class ClaudeCodeInstallResult:
    mcp_path: Path
    memory_path: Path
    launcher_path: Path
    mcp_backup_path: Path | None
    memory_backup_path: Path | None
    mcp_changed: bool
    memory_changed: bool
    dry_run: bool
    mcp_config: dict
    memory_text: str


def default_claude_mcp_path(workdir: Path) -> Path:
    return workdir / ".mcp.json"


def default_claude_memory_path(workdir: Path) -> Path:
    return workdir / ".claude" / "CLAUDE.md"


def default_claude_launcher_path(workdir: Path) -> Path:
    return workdir / ".claude" / "tokenpatch_mcp_launcher.py"


def install_claude_code(
    *,
    workdir: Path,
    package_root: Path,
    mcp_path: Path | None = None,
    memory_path: Path | None = None,
    launcher_path: Path | None = None,
    dry_run: bool = False,
    python_command: str = sys.executable,
) -> ClaudeCodeInstallResult:
    target_mcp = mcp_path or default_claude_mcp_path(workdir)
    target_memory = memory_path or default_claude_memory_path(workdir)
    target_launcher = launcher_path or default_claude_launcher_path(workdir)

    original_mcp = read_json_file(target_mcp)
    mcp_config = upsert_tokenpatch_mcp(
        original_mcp,
        command=python_command,
        launcher_path=target_launcher,
    )
    original_mcp_text = target_mcp.read_text(encoding="utf-8") if target_mcp.exists() else ""
    next_mcp_text = json.dumps(mcp_config, ensure_ascii=False, indent=2) + "\n"
    mcp_changed = normalize_json_text(original_mcp_text) != normalize_json_text(next_mcp_text)

    original_memory = target_memory.read_text(encoding="utf-8") if target_memory.exists() else ""
    memory_text = upsert_tokenpatch_claude_block(original_memory)
    memory_changed = memory_text != original_memory

    mcp_backup_path: Path | None = None
    memory_backup_path: Path | None = None
    if not dry_run:
        target_mcp.parent.mkdir(parents=True, exist_ok=True)
        target_memory.parent.mkdir(parents=True, exist_ok=True)
        target_launcher.parent.mkdir(parents=True, exist_ok=True)
        if mcp_changed and target_mcp.exists():
            mcp_backup_path = target_mcp.with_suffix(target_mcp.suffix + f".tokenpatch-{timestamp()}.bak")
            mcp_backup_path.write_text(original_mcp_text, encoding="utf-8")
        if memory_changed and target_memory.exists():
            memory_backup_path = target_memory.with_suffix(target_memory.suffix + f".tokenpatch-{timestamp()}.bak")
            memory_backup_path.write_text(original_memory, encoding="utf-8")
        if mcp_changed:
            target_mcp.write_text(next_mcp_text, encoding="utf-8")
        if memory_changed:
            target_memory.write_text(memory_text, encoding="utf-8")
        write_claude_launcher(target_launcher, package_root=package_root, project_workdir=workdir)

    return ClaudeCodeInstallResult(
        mcp_path=target_mcp,
        memory_path=target_memory,
        launcher_path=target_launcher,
        mcp_backup_path=mcp_backup_path,
        memory_backup_path=memory_backup_path,
        mcp_changed=mcp_changed,
        memory_changed=memory_changed,
        dry_run=dry_run,
        mcp_config=mcp_config,
        memory_text=memory_text,
    )


def read_json_file(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def upsert_tokenpatch_mcp(config: dict, *, command: str, launcher_path: Path) -> dict:
    updated = dict(config)
    servers = dict(updated.get("mcpServers") or {})
    servers["tokenpatch"] = {
        "command": command,
        "args": [str(launcher_path.resolve())],
        "env": DEFAULT_CLAUDE_EXECUTOR_ENV,
    }
    updated["mcpServers"] = servers
    return updated


def normalize_json_text(text: str) -> str:
    if not text.strip():
        return ""
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True)
    except json.JSONDecodeError:
        return text


def upsert_tokenpatch_claude_block(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    start_marker = "<!-- tokenpatch:start -->"
    end_marker = "<!-- tokenpatch:end -->"
    block = tokenpatch_claude_block()
    start = normalized.find(start_marker)
    end = normalized.find(end_marker)
    if start != -1 and end != -1 and end > start:
        end += len(end_marker)
        return (normalized[:start] + block + normalized[end:]).rstrip() + "\n"
    prefix = normalized.rstrip()
    return (prefix + "\n\n" if prefix else "") + block + "\n"


def tokenpatch_claude_block() -> str:
    return """<!-- tokenpatch:start -->
## tokenpatch

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
- In user-facing summaries, say "tokenpatch" or "tokenpatch CLI fallback"; do not say "mmdev CLI".

tokenpatch CLI fallback for coding edits:

```bash
python -m mmdev.cli do "<requirement>" --allowed-file <file> --workdir .
```

Repeat `--allowed-file` for every allowed file. Add `--acceptance "<check>"` when useful.

tokenpatch CLI fallback for metrics and reports:

```bash
python -m mmdev.cli report --workdir .
python -m mmdev.cli metrics --workdir .
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
<!-- tokenpatch:end -->"""


def write_claude_launcher(path: Path, *, package_root: Path, project_workdir: Path) -> None:
    content = f'''from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PACKAGE_ROOT = Path({str(package_root.resolve())!r})
PROJECT_WORKDIR = Path({str(project_workdir.resolve())!r})
LOG_PATH = Path.home() / ".claude" / "tokenpatch_mcp_debug.log"

os.chdir(str(PACKAGE_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT))

from mmdev.mcp_server import run_stdio_server

if __name__ == "__main__":
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(f"{{datetime.now().isoformat()}} start package={{PACKAGE_ROOT}} workdir={{PROJECT_WORKDIR}} python={{sys.executable}}\\n")
    except Exception:
        pass
    run_stdio_server(default_workdir=str(PROJECT_WORKDIR))
'''
    path.write_text(content, encoding="utf-8")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
