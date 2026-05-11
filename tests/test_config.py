from pathlib import Path

from mmdev.config import init_state_dir, load_config


def test_init_state_dir_creates_expected_files(tmp_path):
    mmdev_dir = init_state_dir(tmp_path)
    assert mmdev_dir.name == ".mmdev"
    assert (mmdev_dir / "config.toml").exists()
    assert (mmdev_dir / "logs").is_dir()
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
