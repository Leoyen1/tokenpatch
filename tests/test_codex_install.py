from pathlib import Path

from mmdev.codex_install import (
    codex_mcp_snippet,
    existing_tokenpatch_env,
    install_codex_mcp,
    upsert_tokenpatch_agents_block,
    upsert_tokenpatch_section,
)


def test_upsert_tokenpatch_section_appends_when_missing(tmp_path):
    snippet = codex_mcp_snippet(tmp_path)
    updated = upsert_tokenpatch_section('[mcp_servers]\n\n[mcp_servers.playwright]\ntype = "stdio"\n', snippet)

    assert "[mcp_servers.playwright]" in updated
    assert "[mcp_servers.tokenpatch]" in updated
    assert str(tmp_path).replace("\\", "\\\\") in updated


def test_codex_mcp_snippet_supports_dynamic_workdir():
    snippet = codex_mcp_snippet(None, dynamic_workdir=True)

    assert 'args = ["mcp"]' in snippet
    assert "--workdir" not in snippet


def test_codex_mcp_snippet_supports_python_module_mode(tmp_path):
    snippet = codex_mcp_snippet(
        None,
        command="C:\\Python314\\python.exe",
        dynamic_workdir=True,
        python_module=True,
        package_root=tmp_path,
    )

    assert 'command = "C:\\\\Python314\\\\python.exe"' in snippet
    assert 'args = ["-m", "mmdev.cli", "mcp"]' in snippet
    assert "cwd =" in snippet


def test_codex_mcp_snippet_supports_launcher_mode(tmp_path):
    launcher = tmp_path / "tokenpatch_mcp_launcher.py"
    snippet = codex_mcp_snippet(
        tmp_path,
        command="C:\\Python314\\python.exe",
        dynamic_workdir=False,
        python_module=True,
        package_root=tmp_path,
        launcher_path=launcher,
    )

    assert 'command = "C:\\\\Python314\\\\python.exe"' in snippet
    assert f'args = ["{str(launcher.resolve()).replace("\\", "\\\\")}"]' in snippet
    assert "--workdir" not in snippet
    assert "cwd =" not in snippet


def test_upsert_tokenpatch_section_replaces_existing(tmp_path):
    snippet = codex_mcp_snippet(tmp_path)
    original = """
[mcp_servers]

[mcp_servers.tokenpatch]
type = "stdio"
command = "old"
args = ["old"]

[windows]
sandbox = "elevated"
"""
    updated = upsert_tokenpatch_section(original, snippet)

    assert 'command = "old"' not in updated
    assert "[windows]" in updated
    assert updated.count("[mcp_servers.tokenpatch]") == 1


def test_install_codex_mcp_writes_backup_and_supports_dry_run(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[mcp_servers]\n", encoding="utf-8")

    dry = install_codex_mcp(project_workdir=tmp_path, config_path=config_path, dry_run=True, dynamic_workdir=False)
    assert dry.changed is True
    assert dry.backup_path is None
    assert "[mcp_servers.tokenpatch]" not in config_path.read_text(encoding="utf-8")

    result = install_codex_mcp(project_workdir=tmp_path, config_path=config_path, dynamic_workdir=False)
    assert result.changed is True
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.skill_path is not None
    assert result.skill_path.exists()
    skill_text = result.skill_path.read_text(encoding="utf-8")
    assert "Call the `tokenpatch` MCP tool first" in skill_text
    assert "tp:" in skill_text
    assert "Users may ask in any language" in skill_text
    assert result.agents_path is not None
    assert result.agents_path.exists()
    agents_text = result.agents_path.read_text(encoding="utf-8")
    assert "First try the `tokenpatch` MCP tool." in agents_text
    assert "tp:" in agents_text
    assert "python -m mmdev.cli do" in agents_text
    assert "Savings ratio" in agents_text
    assert "Preserve the user's original requirement language" in agents_text
    written = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.tokenpatch]" in written
    assert "DEEPSEEK_EXECUTOR_MODEL" in written
    assert "deepseek-v4-pro" in written

    again = install_codex_mcp(project_workdir=tmp_path, config_path=config_path, dynamic_workdir=False)
    assert again.changed is False


def test_install_codex_mcp_writes_launcher_even_when_config_unchanged(tmp_path):
    config_path = tmp_path / "config.toml"
    launcher = tmp_path / "tokenpatch_mcp_launcher.py"
    package_root = tmp_path / "package"
    package_root.mkdir()
    snippet = codex_mcp_snippet(
        tmp_path,
        command="python",
        package_root=package_root,
        launcher_path=launcher,
        env={
            "MMDEV_EXECUTOR_PROVIDER": "deepseek_byok",
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_EXECUTOR_MODEL": "deepseek-v4-pro",
        },
    )
    config_path.write_text(snippet, encoding="utf-8")

    result = install_codex_mcp(
        project_workdir=tmp_path,
        package_root=package_root,
        config_path=config_path,
        command="python",
        launcher_path=launcher,
    )

    assert result.changed is False
    assert launcher.exists()
    launcher_text = launcher.read_text(encoding="utf-8")
    assert "run_stdio_server" in launcher_text
    assert str(package_root.resolve()).replace("\\", "\\\\") in launcher_text


def test_install_codex_mcp_preserves_existing_executor_env(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[mcp_servers.tokenpatch]
type = "stdio"
command = "old"
args = ["old"]
env = { MMDEV_EXECUTOR_PROVIDER = "deepseek_byok", DEEPSEEK_API_KEY = "sk-existing" }
""",
        encoding="utf-8",
    )

    result = install_codex_mcp(project_workdir=tmp_path, config_path=config_path, dynamic_workdir=False)

    assert result.changed is True
    written = config_path.read_text(encoding="utf-8")
    assert 'DEEPSEEK_API_KEY = "sk-existing"' in written
    assert 'DEEPSEEK_BASE_URL = "https://api.deepseek.com"' in written
    assert existing_tokenpatch_env(written)["DEEPSEEK_API_KEY"] == "sk-existing"


def test_install_codex_mcp_can_skip_skill_install(tmp_path):
    config_path = tmp_path / "config.toml"
    result = install_codex_mcp(
        project_workdir=tmp_path,
        config_path=config_path,
        dynamic_workdir=False,
        install_skill=False,
    )

    assert result.skill_path is None
    assert not (tmp_path / "skills" / "tokenpatch" / "SKILL.md").exists()


def test_install_codex_mcp_can_skip_agents_instruction(tmp_path):
    config_path = tmp_path / "config.toml"
    result = install_codex_mcp(
        project_workdir=tmp_path,
        config_path=config_path,
        dynamic_workdir=False,
        install_agents_instruction=False,
    )

    assert result.agents_path is None
    assert not (tmp_path / "AGENTS.md").exists()


def test_upsert_tokenpatch_agents_block_is_idempotent():
    original = "# Existing\n\nKeep this.\n"
    first = upsert_tokenpatch_agents_block(original)
    second = upsert_tokenpatch_agents_block(first)

    assert "# Existing" in first
    assert "Keep this." in first
    assert first == second
    assert first.count("<!-- tokenpatch:start -->") == 1
