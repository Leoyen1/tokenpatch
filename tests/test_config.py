from pathlib import Path

from mmdev.config import global_config_path, init_global_config, init_state_dir, load_codex_tokenpatch_env, load_config


def test_init_state_dir_creates_expected_files(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    assert mmdev_dir.name == ".mmdev"
    assert (mmdev_dir / "config.toml").exists()
    assert (mmdev_dir / "checkpoints").is_dir()
    assert (mmdev_dir / "logs").is_dir()
    assert (mmdev_dir / "memory").is_dir()
    assert (mmdev_dir / "patches").is_dir()
    assert (mmdev_dir / "reports").is_dir()
    assert (mmdev_dir / "state.sqlite").exists()


def test_environment_overrides_config(tmp_path, monkeypatch):
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text(
        'openai_planner_model = "from-file"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_PLANNER_MODEL", "from-env")
    config = load_config(tmp_path)
    assert config.openai_planner_model == "from-env"
    assert config.workdir == Path(tmp_path).resolve()


def test_load_config_uses_global_config_and_local_overrides(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: tmp_path / "missing-codex.toml")
    init_global_config()
    global_path.write_text(
        'openai_planner_model = "from-global"\n'
        'deepseek_executor_model = "global-executor"\n'
        'workdir = "ignored-global-workdir"\n',
        encoding="utf-8",
    )
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text(
        'openai_planner_model = "from-local"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert global_config_path() == global_path
    assert config.openai_planner_model == "from-local"
    assert config.deepseek_executor_model == "global-executor"
    assert config.workdir == Path(tmp_path).resolve()


def test_empty_local_values_do_not_override_global_config(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: tmp_path / "missing-codex.toml")
    init_global_config()
    global_path.write_text(
        'deepseek_api_key = "global-key"\n'
        'deepseek_base_url = "https://global.example"\n'
        'deepseek_executor_model = "global-model"\n',
        encoding="utf-8",
    )
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text(
        'deepseek_api_key = ""\n'
        'deepseek_base_url = ""\n'
        'deepseek_executor_model = ""\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.deepseek_api_key == "global-key"
    assert config.deepseek_base_url == "https://global.example"
    assert config.deepseek_executor_model == "global-model"


def test_zero_local_pricing_does_not_override_default_executor_pricing(tmp_path):
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text(
        "executor_input_cost_per_million = 0.0\nexecutor_output_cost_per_million = 0.0\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.executor_input_cost_per_million == 1.286
    assert config.executor_output_cost_per_million == 2.572


def test_codex_mcp_env_overrides_old_global_executor_model(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    codex_config = tmp_path / "home" / ".codex" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: codex_config)
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text('deepseek_executor_model = "deepseek-chat"\n', encoding="utf-8")
    codex_config.parent.mkdir(parents=True, exist_ok=True)
    codex_config.write_text(
        """
[mcp_servers.tokenpatch]
type = "stdio"
command = "python"
args = ["launcher.py"]
env = { DEEPSEEK_EXECUTOR_MODEL = "deepseek-v4-pro" }
""",
        encoding="utf-8",
    )
    init_state_dir(tmp_path)

    config = load_config(tmp_path)

    assert config.deepseek_executor_model == "deepseek-v4-pro"


def test_load_codex_tokenpatch_env_maps_executor_fields(tmp_path):
    codex_config = tmp_path / "config.toml"
    codex_config.write_text(
        """
[mcp_servers.tokenpatch]
type = "stdio"
command = "python"
args = ["launcher.py"]
env = { MMDEV_EXECUTOR_PROVIDER = "deepseek_byok", DEEPSEEK_API_KEY = "codex-key", DEEPSEEK_BASE_URL = "https://api.deepseek.com", DEEPSEEK_EXECUTOR_MODEL = "deepseek-v4-pro" }
""",
        encoding="utf-8",
    )

    values = load_codex_tokenpatch_env(codex_config)

    assert values["executor_provider"] == "deepseek_byok"
    assert values["deepseek_api_key"] == "codex-key"
    assert values["deepseek_base_url"] == "https://api.deepseek.com"
    assert values["deepseek_executor_model"] == "deepseek-v4-pro"


def test_executor_provider_auto_selects_gateway_when_token_is_present(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: tmp_path / "missing-codex.toml")
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        'mmdev_gateway_url = "https://api.tokenpatch.com"\n'
        'mmdev_gateway_token = "tp_live_test"\n'
        'deepseek_api_key = "deepseek-key"\n',
        encoding="utf-8",
    )
    init_state_dir(tmp_path)

    config = load_config(tmp_path)

    assert config.executor_provider == "mmdev_gateway"
    assert config.executor_provider_source == "auto"
    assert "MMDEV_GATEWAY_TOKEN" in config.executor_provider_reason
    assert any("DeepSeek BYOK key is also configured but ignored" in note for note in config.executor_provider_notes)


def test_executor_provider_auto_selects_deepseek_when_only_deepseek_key_is_present(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: tmp_path / "missing-codex.toml")
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text('deepseek_api_key = "deepseek-key"\n', encoding="utf-8")
    init_state_dir(tmp_path)

    config = load_config(tmp_path)

    assert config.executor_provider == "deepseek_byok"
    assert config.executor_provider_source == "auto"
    assert "DEEPSEEK_API_KEY" in config.executor_provider_reason


def test_explicit_executor_provider_overrides_gateway_token(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: tmp_path / "missing-codex.toml")
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        'mmdev_gateway_url = "https://api.tokenpatch.com"\n'
        'mmdev_gateway_token = "tp_live_test"\n',
        encoding="utf-8",
    )
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text(
        'executor_provider = "deepseek_byok"\n'
        'deepseek_api_key = "deepseek-key"\n'
        'deepseek_base_url = "https://api.deepseek.com"\n'
        'deepseek_executor_model = "deepseek-v4-pro"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.executor_provider == "deepseek_byok"
    assert config.executor_provider_source == "project config"
    assert any("Gateway token is also configured but ignored" in note for note in config.executor_provider_notes)


def test_environment_executor_provider_has_highest_priority(tmp_path, monkeypatch):
    global_path = tmp_path / "home" / ".tokenpatch" / "config.toml"
    monkeypatch.setenv("TOKENPATCH_CONFIG", str(global_path))
    monkeypatch.setattr("mmdev.config.codex_config_path", lambda: tmp_path / "missing-codex.toml")
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text('executor_provider = "deepseek_byok"\n', encoding="utf-8")
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text('executor_provider = "deepseek_byok"\n', encoding="utf-8")
    monkeypatch.setenv("MMDEV_EXECUTOR_PROVIDER", "mmdev_gateway")
    monkeypatch.setenv("MMDEV_GATEWAY_URL", "https://api.tokenpatch.com")
    monkeypatch.setenv("MMDEV_GATEWAY_TOKEN", "tp_live_test")

    config = load_config(tmp_path)

    assert config.executor_provider == "mmdev_gateway"
    assert config.executor_provider_source == "environment"


def test_openai_base_url_and_api_mode_environment_fields(tmp_path, monkeypatch):
    init_state_dir(tmp_path)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://cc-switch.example/v1")
    monkeypatch.setenv("OPENAI_API_MODE", "chat_completions")
    config = load_config(tmp_path)
    assert config.openai_base_url == "https://cc-switch.example/v1"
    assert config.openai_api_mode == "chat_completions"


def test_config_loads_pricing_fields(tmp_path):
    init_state_dir(tmp_path)
    (tmp_path / ".mmdev" / "config.toml").write_text(
        "executor_input_cost_per_million = 1.25\nexecutor_output_cost_per_million = 2.5\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.executor_input_cost_per_million == 1.25
    assert config.executor_output_cost_per_million == 2.5


def test_claude_provider_environment_fields(tmp_path, monkeypatch):
    init_state_dir(tmp_path)
    monkeypatch.setenv("MMDEV_STRONG_MODEL_PROVIDER", "claude")
    monkeypatch.setenv("CLAUDE_API_KEY", "claude-key")
    monkeypatch.setenv("CLAUDE_PLANNER_MODEL", "claude-plan")
    monkeypatch.setenv("CLAUDE_REVIEWER_MODEL", "claude-review")
    config = load_config(tmp_path)
    assert config.strong_model_provider == "claude"
    assert config.claude_api_key == "claude-key"
    assert config.planner_model == "claude-plan"
    assert config.reviewer_model == "claude-review"
