import json

import pytest

from mmdev.claude_install import (
    default_claude_launcher_path,
    default_claude_mcp_path,
    default_claude_memory_path,
    install_claude_code,
    tokenpatch_claude_block,
    upsert_tokenpatch_claude_block,
    upsert_tokenpatch_mcp,
)


def test_default_claude_paths(tmp_path):
    assert default_claude_mcp_path(tmp_path) == tmp_path / ".mcp.json"
    assert default_claude_memory_path(tmp_path) == tmp_path / ".claude" / "CLAUDE.md"
    assert default_claude_launcher_path(tmp_path) == tmp_path / ".claude" / "tokenpatch_mcp_launcher.py"


def test_upsert_tokenpatch_mcp_preserves_existing_servers(tmp_path):
    launcher = tmp_path / ".claude" / "tokenpatch_mcp_launcher.py"
    config = {"mcpServers": {"playwright": {"command": "npx", "args": ["@playwright/mcp"]}}}

    updated = upsert_tokenpatch_mcp(config, command="python", launcher_path=launcher)

    assert "playwright" in updated["mcpServers"]
    tokenpatch = updated["mcpServers"]["tokenpatch"]
    assert tokenpatch["command"] == "python"
    assert tokenpatch["args"] == [str(launcher.resolve())]
    assert tokenpatch["env"]["DEEPSEEK_EXECUTOR_MODEL"] == "deepseek-v4-pro"
    assert "DEEPSEEK_API_KEY" not in tokenpatch["env"]


def test_claude_memory_block_is_idempotent():
    original = "# Project\n\nExisting instructions.\n"
    first = upsert_tokenpatch_claude_block(original)
    second = upsert_tokenpatch_claude_block(first)

    assert "Existing instructions." in first
    assert "Users may ask in any language" in first
    assert "tp:" in first
    assert "Savings ratio" in first
    assert "Equivalent requests in other languages are also valid" in first
    assert first == second
    assert first.count("<!-- tokenpatch:start -->") == 1


def test_install_claude_code_dry_run_does_not_write(tmp_path):
    package_root = tmp_path / "package"
    package_root.mkdir()

    result = install_claude_code(workdir=tmp_path, package_root=package_root, dry_run=True, python_command="python")

    assert result.mcp_changed is True
    assert result.memory_changed is True
    assert result.mcp_backup_path is None
    assert result.memory_backup_path is None
    assert not result.mcp_path.exists()
    assert not result.memory_path.exists()
    assert not result.launcher_path.exists()


def test_install_claude_code_writes_files_and_is_idempotent(tmp_path):
    package_root = tmp_path / "package"
    package_root.mkdir()

    result = install_claude_code(workdir=tmp_path, package_root=package_root, python_command="python")

    assert result.mcp_changed is True
    assert result.memory_changed is True
    assert result.mcp_path.exists()
    assert result.memory_path.exists()
    assert result.launcher_path.exists()
    mcp = json.loads(result.mcp_path.read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["tokenpatch"]["command"] == "python"
    assert "run_stdio_server" in result.launcher_path.read_text(encoding="utf-8")
    assert tokenpatch_claude_block() in result.memory_path.read_text(encoding="utf-8")

    again = install_claude_code(workdir=tmp_path, package_root=package_root, python_command="python")
    assert again.mcp_changed is False
    assert again.memory_changed is False
    assert again.mcp_backup_path is None
    assert again.memory_backup_path is None


def test_install_claude_code_backs_up_existing_files(tmp_path):
    package_root = tmp_path / "package"
    package_root.mkdir()
    mcp_path = tmp_path / ".mcp.json"
    memory_path = tmp_path / ".claude" / "CLAUDE.md"
    memory_path.parent.mkdir()
    mcp_path.write_text(json.dumps({"mcpServers": {"old": {"command": "old"}}}), encoding="utf-8")
    memory_path.write_text("old memory", encoding="utf-8")

    result = install_claude_code(workdir=tmp_path, package_root=package_root, python_command="python")

    assert result.mcp_backup_path is not None
    assert result.memory_backup_path is not None
    assert result.mcp_backup_path.exists()
    assert result.memory_backup_path.exists()
    assert "old" in result.mcp_backup_path.read_text(encoding="utf-8")
    assert result.memory_backup_path.read_text(encoding="utf-8") == "old memory"


def test_install_claude_code_rejects_invalid_mcp_json(tmp_path):
    package_root = tmp_path / "package"
    package_root.mkdir()
    (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        install_claude_code(workdir=tmp_path, package_root=package_root, python_command="python")
