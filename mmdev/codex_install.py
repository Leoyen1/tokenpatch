from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TOKENPATCH_SECTION = "[mcp_servers.tokenpatch]"
DEFAULT_EXECUTOR_ENV = {
    "MMDEV_EXECUTOR_PROVIDER": "deepseek_byok",
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_EXECUTOR_MODEL": "deepseek-v4-pro",
}


@dataclass(frozen=True)
class CodexInstallResult:
    config_path: Path
    backup_path: Path | None
    changed: bool
    dry_run: bool
    snippet: str
    launcher_path: Path | None = None
    skill_path: Path | None = None
    agents_path: Path | None = None


def default_codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def install_codex_mcp(
    *,
    project_workdir: Path | None,
    package_root: Path | None = None,
    config_path: Path | None = None,
    dry_run: bool = False,
    command: str = "tokenpatch",
    dynamic_workdir: bool = False,
    python_module: bool = False,
    launcher_path: Path | None = None,
    include_executor_env_template: bool = True,
    install_skill: bool = True,
    install_agents_instruction: bool = True,
) -> CodexInstallResult:
    target = config_path or default_codex_config_path()
    effective_launcher_path = launcher_path
    if effective_launcher_path is not None and package_root is None:
        raise ValueError("package_root is required when launcher_path is set")
    if effective_launcher_path is not None and project_workdir is None:
        raise ValueError("project_workdir is required when launcher_path is set")
    original = target.read_text(encoding="utf-8") if target.exists() else ""
    executor_env = None
    if include_executor_env_template:
        executor_env = DEFAULT_EXECUTOR_ENV | existing_tokenpatch_env(original)
    snippet = codex_mcp_snippet(
        project_workdir,
        command=command,
        dynamic_workdir=dynamic_workdir,
        python_module=python_module,
        package_root=package_root,
        launcher_path=effective_launcher_path,
        env=executor_env,
    )
    updated = upsert_tokenpatch_section(original, snippet)
    changed = updated != original
    backup_path: Path | None = None
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        if changed and target.exists():
            backup_path = target.with_suffix(target.suffix + f".tokenpatch-{timestamp()}.bak")
            backup_path.write_text(original, encoding="utf-8")
        if changed:
            target.write_text(updated, encoding="utf-8")
        if effective_launcher_path is not None:
            write_launcher(
                effective_launcher_path,
                package_root=package_root,
                project_workdir=project_workdir,
            )
        if install_skill:
            write_codex_skill(default_codex_skill_path(target))
        if install_agents_instruction:
            write_codex_agents_instruction(default_codex_agents_path(target))
    return CodexInstallResult(
        config_path=target,
        backup_path=backup_path,
        changed=changed,
        dry_run=dry_run,
        snippet=snippet,
        launcher_path=effective_launcher_path,
        skill_path=default_codex_skill_path(target) if install_skill else None,
        agents_path=default_codex_agents_path(target) if install_agents_instruction else None,
    )


def codex_mcp_snippet(
    project_workdir: Path | None,
    *,
    command: str = "tokenpatch",
    dynamic_workdir: bool = False,
    python_module: bool = False,
    package_root: Path | None = None,
    launcher_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    command_line = f'command = "{escape_toml_string(command)}"'
    args_items = ["mcp"]
    if launcher_path is not None:
        args_items = [str(launcher_path.resolve())]
    elif python_module:
        args_items = ["-m", "mmdev.cli", "mcp"]
    if not dynamic_workdir and launcher_path is None:
        if project_workdir is None:
            raise ValueError("project_workdir is required unless dynamic_workdir=True")
        resolved = str(project_workdir.resolve())
        args_items.extend(["--workdir", resolved])
    lines = [
        TOKENPATCH_SECTION,
        'type = "stdio"',
        command_line,
        "args = [" + ", ".join(f'"{escape_toml_string(item)}"' for item in args_items) + "]",
    ]
    if env:
        env_items = ", ".join(f'{key} = "{escape_toml_string(value)}"' for key, value in sorted(env.items()))
        lines.append(f"env = {{ {env_items} }}")
    if package_root is not None and launcher_path is None:
        lines.append(f'cwd = "{escape_toml_string(str(package_root.resolve()))}"')
    lines.append("")
    return "\n".join(lines)


def write_launcher(path: Path, *, package_root: Path, project_workdir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f'''from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PACKAGE_ROOT = Path({str(package_root.resolve())!r})
PROJECT_WORKDIR = Path({str(project_workdir.resolve())!r})
LOG_PATH = Path.home() / ".codex" / "tokenpatch_mcp_debug.log"

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


def default_codex_skill_path(config_path: Path | None = None) -> Path:
    codex_dir = (config_path or default_codex_config_path()).parent
    return codex_dir / "skills" / "tokenpatch" / "SKILL.md"


def default_codex_agents_path(config_path: Path | None = None) -> Path:
    codex_dir = (config_path or default_codex_config_path()).parent
    return codex_dir / "AGENTS.md"


def write_codex_skill(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tokenpatch_skill_text(), encoding="utf-8")


def write_codex_agents_instruction(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_tokenpatch_agents_block(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")


def upsert_tokenpatch_agents_block(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    start_marker = "<!-- tokenpatch:start -->"
    end_marker = "<!-- tokenpatch:end -->"
    block = tokenpatch_agents_block()
    start = normalized.find(start_marker)
    end = normalized.find(end_marker)
    if start != -1 and end != -1 and end > start:
        end += len(end_marker)
        return (normalized[:start] + block + normalized[end:]).rstrip() + "\n"
    prefix = normalized.rstrip()
    return (prefix + "\n\n" if prefix else "") + block + "\n"


def tokenpatch_agents_block() -> str:
    return """<!-- tokenpatch:start -->
## tokenpatch

When the user starts a message with `tp:` or `tp：`, asks to use tokenpatch, mentions the word "tokenpatch", asks to save tokens, or asks for a low-cost coding edit, use tokenpatch before making direct file edits.

Rules:
- Treat `tp:` and `tp：` as the shortest user trigger for tokenpatch. Strip only that prefix and pass the rest of the message as the original requirement.
- Users may ask in any language. Preserve the user's original requirement language when passing the requirement to tokenpatch.
- Reply to the user in their language unless they ask otherwise.
- If the user gives allowed files, pass them as `allowed_files`.
- First try the `tokenpatch` MCP tool.
- If the `tokenpatch` MCP tool is not visible, run the tokenpatch CLI fallback from the project root: `python -m mmdev.cli do "<requirement>" --allowed-file <file>`.
- Repeat `--allowed-file` for every allowed file. Add `--acceptance` checks when useful.
- Do not implement the requested coding change directly before trying the MCP tool or CLI fallback.
- Do not delete `.mmdev`; it stores tokenpatch checkpoints, patches, metrics, memory, and reports for cost auditing.
- When the user asks for metrics or report, regenerate the report with tokenpatch CLI fallback: `python -m mmdev.cli report --workdir <project>`, then run `python -m mmdev.cli metrics --workdir <project>` if structured JSON is needed.
- In metrics/report summaries, show Savings ratio, Estimated savings, Applied patches, Cost per applied patch, and Savings per applied patch first.
- When summarizing results, call this "tokenpatch" or "tokenpatch CLI fallback"; do not call it "mmdev CLI" in user-facing text.
- If both tokenpatch paths are unavailable or blocked, explain that clearly before falling back.
<!-- tokenpatch:end -->"""


def tokenpatch_skill_text() -> str:
    return """---
name: "tokenpatch"
description: "Use when the user starts with tp: or tp：, says tokenpatch, asks to save tokens, asks for a low-cost coding change, or asks for a safe AI coding edit through tokenpatch."
---

# tokenpatch

tokenpatch is a local MCP tool layer for safe, low-cost coding edits.

When the user starts with `tp:` / `tp：` or asks to use tokenpatch for a coding task, do not implement the edit directly with shell commands or normal file edits first. Call the `tokenpatch` MCP tool first.

Required behavior:

- Treat `tp:` and `tp：` as a tokenpatch request. Strip only that prefix and pass the rest of the message as the original requirement.
- Users may ask in any language. Preserve the user's original requirement language when passing the requirement to tokenpatch.
- Reply to the user in their language unless they ask otherwise.
- If the user gives an explicit file scope, pass it as `allowed_files`.
- If the user does not give a file scope, inspect the project only enough to choose a small `allowed_files` list, then call `tokenpatch`.
- Keep `allowed_files` narrow. Do not give tokenpatch the whole repository.
- Include concise `acceptance_criteria`.
- Let tokenpatch create the checkpoint, call the configured executor, check patch boundaries, refresh memory, and report metrics.
- If tokenpatch returns `needs-file-scope`, choose the smallest reasonable file list and call `tokenpatch` again.
- Only fall back to direct edits if tokenpatch is unavailable or returns a blocking error that cannot be fixed.
- If the MCP tool is not visible, run the tokenpatch CLI fallback from the project root: `python -m mmdev.cli do "<requirement>" --allowed-file <file>` instead of editing directly.
- When summarizing results, call this "tokenpatch" or "tokenpatch CLI fallback"; do not call it "mmdev CLI" in user-facing text.
- Do not delete `.mmdev`; it is the tokenpatch audit and metrics directory.

Example:

User: "tp: Make a snake game. Only modify index.html, styles.css, script.js."

User: "Use tokenpatch to make a snake game. Only modify index.html, styles.css, script.js."

Call MCP tool `tokenpatch` with:

```json
{
  "requirement": "Make a playable snake game.",
  "allowed_files": ["index.html", "styles.css", "script.js"],
  "acceptance_criteria": [
    "The game can start, pause, and restart.",
    "Keyboard controls work.",
    "Score updates when food is eaten."
  ]
}
```
"""


def upsert_tokenpatch_section(config_text: str, snippet: str) -> str:
    text = config_text.replace("\r\n", "\n")
    lines = text.splitlines()
    start = find_section(lines, TOKENPATCH_SECTION)
    if start is None:
        prefix = text.rstrip()
        return (prefix + "\n\n" if prefix else "") + snippet
    end = start + 1
    while end < len(lines):
        line = lines[end].strip()
        if line.startswith("[") and line.endswith("]"):
            break
        end += 1
    new_lines = lines[:start] + snippet.rstrip("\n").splitlines() + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"


def find_section(lines: list[str], header: str) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() == header:
            return index
    return None


def existing_tokenpatch_env(config_text: str) -> dict[str, str]:
    if not config_text.strip():
        return {}
    try:
        parsed = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError:
        return {}
    tokenpatch = parsed.get("mcp_servers", {}).get("tokenpatch", {})
    env = tokenpatch.get("env", {})
    if not isinstance(env, dict):
        return {}
    return {str(key): str(value) for key, value in env.items()}


def escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
