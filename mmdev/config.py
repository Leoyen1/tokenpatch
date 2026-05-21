from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mmdev.state import initialize_state


CONFIG_DIR = ".mmdev"
CONFIG_FILE = "config.toml"
GLOBAL_CONFIG_DIR = ".tokenpatch"
GLOBAL_CONFIG_FILE = "config.toml"
PRICING_FIELDS = {
    "planner_input_cost_per_million",
    "planner_output_cost_per_million",
    "reviewer_input_cost_per_million",
    "reviewer_output_cost_per_million",
    "executor_input_cost_per_million",
    "executor_output_cost_per_million",
    "baseline_strong_input_cost_per_million",
    "baseline_strong_output_cost_per_million",
}


class MMDevConfig(BaseModel):
    workdir: Path = Field(default_factory=Path.cwd)
    strong_model_provider: str = "openai"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_mode: str = "responses"
    openai_planner_model: str | None = None
    openai_reviewer_model: str | None = None
    claude_api_key: str | None = None
    claude_base_url: str = "https://api.anthropic.com/v1"
    claude_planner_model: str | None = None
    claude_reviewer_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = "https://api.deepseek.com"
    deepseek_executor_model: str | None = "deepseek-v4-pro"
    executor_provider: str = "deepseek_byok"
    executor_provider_source: str = "auto"
    executor_provider_reason: str = "auto: no gateway token or DeepSeek key found; defaulting to deepseek_byok"
    mmdev_gateway_url: str | None = None
    mmdev_gateway_token: str | None = None
    mmdev_gateway_executor_model: str = "gateway-executor"
    mmdev_gateway_country: str | None = None
    mmdev_gateway_entity: str | None = None
    command_timeout_seconds: int = 120
    request_timeout_seconds: int = 120
    planner_input_cost_per_million: float = 0.0
    planner_output_cost_per_million: float = 0.0
    reviewer_input_cost_per_million: float = 0.0
    reviewer_output_cost_per_million: float = 0.0
    executor_input_cost_per_million: float = 1.286
    executor_output_cost_per_million: float = 2.572
    baseline_strong_input_cost_per_million: float = 0.0
    baseline_strong_output_cost_per_million: float = 0.0
    state_dir: Path | None = None

    @property
    def mmdev_dir(self) -> Path:
        return self.state_dir or (self.workdir / CONFIG_DIR)

    @property
    def config_path(self) -> Path:
        return self.mmdev_dir / CONFIG_FILE

    @property
    def normalized_strong_model_provider(self) -> str:
        return (self.strong_model_provider or "openai").strip().lower()

    @property
    def planner_model(self) -> str | None:
        if self.normalized_strong_model_provider == "claude":
            return self.claude_planner_model
        return self.openai_planner_model

    @property
    def reviewer_model(self) -> str | None:
        if self.normalized_strong_model_provider == "claude":
            return self.claude_reviewer_model
        return self.openai_reviewer_model

    @property
    def normalized_executor_provider(self) -> str:
        return (self.executor_provider or "deepseek_byok").strip().lower()

    @property
    def deepseek_byok_configured(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def gateway_configured(self) -> bool:
        return bool(self.mmdev_gateway_token)

    @property
    def executor_provider_notes(self) -> list[str]:
        notes: list[str] = [self.executor_provider_reason]
        if self.normalized_executor_provider == "mmdev_gateway" and self.deepseek_byok_configured:
            notes.append("DeepSeek BYOK key is also configured but ignored because provider is mmdev_gateway.")
        if self.normalized_executor_provider == "deepseek_byok" and self.gateway_configured:
            notes.append("Gateway token is also configured but ignored because provider is deepseek_byok.")
        return notes

    @property
    def executor_model(self) -> str | None:
        if self.normalized_executor_provider == "mmdev_gateway":
            return self.mmdev_gateway_executor_model
        return self.deepseek_executor_model


ENV_MAP = {
    "MMDEV_STRONG_MODEL_PROVIDER": "strong_model_provider",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_BASE_URL": "openai_base_url",
    "OPENAI_API_MODE": "openai_api_mode",
    "OPENAI_PLANNER_MODEL": "openai_planner_model",
    "OPENAI_REVIEWER_MODEL": "openai_reviewer_model",
    "CLAUDE_API_KEY": "claude_api_key",
    "CLAUDE_BASE_URL": "claude_base_url",
    "CLAUDE_PLANNER_MODEL": "claude_planner_model",
    "CLAUDE_REVIEWER_MODEL": "claude_reviewer_model",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "DEEPSEEK_BASE_URL": "deepseek_base_url",
    "DEEPSEEK_EXECUTOR_MODEL": "deepseek_executor_model",
    "MMDEV_EXECUTOR_PROVIDER": "executor_provider",
    "MMDEV_GATEWAY_URL": "mmdev_gateway_url",
    "MMDEV_GATEWAY_TOKEN": "mmdev_gateway_token",
    "MMDEV_GATEWAY_EXECUTOR_MODEL": "mmdev_gateway_executor_model",
    "MMDEV_GATEWAY_COUNTRY": "mmdev_gateway_country",
    "MMDEV_GATEWAY_ENTITY": "mmdev_gateway_entity",
    "MMDEV_WORKDIR": "workdir",
}


def resolve_workdir(workdir: str | Path | None = None) -> Path:
    env_workdir = os.getenv("MMDEV_WORKDIR")
    selected = workdir or env_workdir or Path.cwd()
    return Path(selected).expanduser().resolve()


def global_config_path() -> Path:
    override = os.getenv("TOKENPATCH_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / GLOBAL_CONFIG_DIR / GLOBAL_CONFIG_FILE


def load_toml_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def drop_unset_values(data: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in data.items():
        if value == "":
            continue
        if key in PRICING_FIELDS and value in {0, 0.0}:
            continue
        cleaned[key] = value
    return cleaned


CONFIG_FIELDS = {
    "strong_model_provider",
    "openai_api_key",
    "openai_base_url",
    "openai_api_mode",
    "openai_planner_model",
    "openai_reviewer_model",
    "claude_api_key",
    "claude_base_url",
    "claude_planner_model",
    "claude_reviewer_model",
    "deepseek_api_key",
    "deepseek_base_url",
    "deepseek_executor_model",
    "executor_provider",
    "mmdev_gateway_url",
    "mmdev_gateway_token",
    "mmdev_gateway_executor_model",
    "mmdev_gateway_country",
    "mmdev_gateway_entity",
    "command_timeout_seconds",
    "request_timeout_seconds",
    "planner_input_cost_per_million",
    "planner_output_cost_per_million",
    "reviewer_input_cost_per_million",
    "reviewer_output_cost_per_million",
    "executor_input_cost_per_million",
    "executor_output_cost_per_million",
    "baseline_strong_input_cost_per_million",
    "baseline_strong_output_cost_per_million",
}


def load_config(workdir: str | Path | None = None) -> MMDevConfig:
    resolved_workdir = resolve_workdir(workdir)
    data: dict[str, object] = {"workdir": resolved_workdir}

    global_data = drop_unset_values(load_toml_file(global_config_path()))
    global_data.pop("workdir", None)
    global_data.pop("state_dir", None)
    data.update(global_data)

    config_path = resolved_workdir / CONFIG_DIR / CONFIG_FILE
    local_data = drop_unset_values(load_toml_file(config_path))
    data.update(local_data)

    codex_data = load_codex_tokenpatch_env()
    data.update(codex_data)

    env_data: dict[str, object] = {}
    for env_name, field_name in ENV_MAP.items():
        value = os.getenv(env_name)
        if value:
            env_data[field_name] = Path(value).expanduser().resolve() if field_name == "workdir" else value
    data.update(env_data)

    provider, source, reason = resolve_executor_provider(
        data,
        sources=[
            ("global config", global_data),
            ("project config", local_data),
            ("app MCP environment", codex_data),
            ("environment", env_data),
        ],
    )
    data["executor_provider"] = provider
    data["executor_provider_source"] = source
    data["executor_provider_reason"] = reason

    return MMDevConfig(**data)


def resolve_executor_provider(
    data: dict[str, object],
    *,
    sources: list[tuple[str, dict[str, object]]],
) -> tuple[str, str, str]:
    explicit_source: str | None = None
    explicit_provider: str | None = None
    for source_name, source_data in sources:
        value = source_data.get("executor_provider")
        if isinstance(value, str) and value.strip():
            explicit_source = source_name
            explicit_provider = value.strip().lower()
    if explicit_provider:
        return (
            explicit_provider,
            explicit_source or "explicit",
            f"explicit {explicit_source or 'configuration'} executor_provider={explicit_provider}",
        )
    if str(data.get("mmdev_gateway_token") or "").strip():
        return (
            "mmdev_gateway",
            "auto",
            "auto: MMDEV_GATEWAY_TOKEN/mmdev_gateway_token is configured",
        )
    if str(data.get("deepseek_api_key") or "").strip():
        return (
            "deepseek_byok",
            "auto",
            "auto: DEEPSEEK_API_KEY/deepseek_api_key is configured",
        )
    return (
        "deepseek_byok",
        "auto",
        "auto: no gateway token or DeepSeek key found; defaulting to deepseek_byok",
    )


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def load_codex_tokenpatch_env(path: Path | None = None) -> dict[str, object]:
    config_path = path or codex_config_path()
    if not config_path.exists():
        return {}
    try:
        parsed = load_toml_file(config_path)
    except tomllib.TOMLDecodeError:
        return {}
    tokenpatch = parsed.get("mcp_servers", {}).get("tokenpatch", {})
    if not isinstance(tokenpatch, dict):
        return {}
    env = tokenpatch.get("env", {})
    if not isinstance(env, dict):
        return {}
    mapped: dict[str, object] = {}
    for env_name, field_name in ENV_MAP.items():
        if field_name == "workdir":
            continue
        value = env.get(env_name)
        if value:
            mapped[field_name] = value
    return mapped


def write_global_config(values: dict[str, Any]) -> Path:
    path = init_global_config()
    current = load_toml_file(path)
    for key, value in values.items():
        if key in CONFIG_FIELDS:
            current[key] = value
    path.write_text(render_config_toml(current), encoding="utf-8")
    return path


def render_config_toml(values: dict[str, Any]) -> str:
    lines = [
        "# tokenpatch global configuration.",
        "# This file is shared by all projects on this machine.",
        "# Project .mmdev/config.toml can override these values; environment variables override both.",
        "",
    ]
    for key in sorted(CONFIG_FIELDS):
        if key not in values:
            continue
        lines.append(f"{key} = {toml_value(values[key])}")
    return "\n".join(lines).rstrip() + "\n"


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if value is None:
        return '""'
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def global_config_text() -> str:
    return """# tokenpatch global configuration.
# This file is shared by all projects on this machine.
# Project .mmdev/config.toml can override these values; environment variables override both.

strong_model_provider = "openai" # openai or claude
openai_api_key = ""
openai_base_url = "https://api.openai.com/v1"
openai_api_mode = "responses" # responses or chat_completions
openai_planner_model = ""
openai_reviewer_model = ""
claude_api_key = ""
claude_base_url = "https://api.anthropic.com/v1"
claude_planner_model = ""
claude_reviewer_model = ""
deepseek_api_key = ""
deepseek_base_url = "https://api.deepseek.com"
deepseek_executor_model = "deepseek-v4-pro"
executor_provider = "" # optional: deepseek_byok or mmdev_gateway; blank enables auto-detect
mmdev_gateway_url = ""
mmdev_gateway_token = ""
mmdev_gateway_executor_model = "gateway-executor"
mmdev_gateway_country = ""
mmdev_gateway_entity = ""
command_timeout_seconds = 120
request_timeout_seconds = 120

# Estimated pricing, in USD per 1M tokens. Executor defaults use DeepSeek V4 Pro
# conservative non-cache input pricing when cache token details are unavailable.
planner_input_cost_per_million = 0.0
planner_output_cost_per_million = 0.0
reviewer_input_cost_per_million = 0.0
reviewer_output_cost_per_million = 0.0
executor_input_cost_per_million = 1.286
executor_output_cost_per_million = 2.572
baseline_strong_input_cost_per_million = 0.0
baseline_strong_output_cost_per_million = 0.0
"""


def default_config_text() -> str:
    return """# tokenpatch local configuration.
# Global defaults are read from ~/.tokenpatch/config.toml.
# This project file overrides global values; environment variables override both.
# Leave model credentials empty here when using global config.

strong_model_provider = "openai" # openai or claude
openai_api_key = ""
openai_base_url = "https://api.openai.com/v1"
openai_api_mode = "responses" # responses or chat_completions
openai_planner_model = ""
openai_reviewer_model = ""
claude_api_key = ""
claude_base_url = "https://api.anthropic.com/v1"
claude_planner_model = ""
claude_reviewer_model = ""
deepseek_api_key = ""
deepseek_base_url = ""
deepseek_executor_model = ""
executor_provider = "" # optional: deepseek_byok or mmdev_gateway; blank enables auto-detect
mmdev_gateway_url = ""
mmdev_gateway_token = ""
mmdev_gateway_executor_model = "gateway-executor"
mmdev_gateway_country = "" # optional, sent as X-MMDEV-Country in gateway mode
mmdev_gateway_entity = "" # optional, sent as X-MMDEV-Entity in gateway mode
command_timeout_seconds = 120
request_timeout_seconds = 120

# Estimated pricing, in USD per 1M tokens. Project values of 0 are treated as
# unset so global/default pricing can still apply.
planner_input_cost_per_million = 0.0
planner_output_cost_per_million = 0.0
reviewer_input_cost_per_million = 0.0
reviewer_output_cost_per_million = 0.0
executor_input_cost_per_million = 0.0
executor_output_cost_per_million = 0.0

# Optional baseline used by reports to estimate "all strong model" cost.
baseline_strong_input_cost_per_million = 0.0
baseline_strong_output_cost_per_million = 0.0
"""


def init_global_config(*, overwrite: bool = False) -> Path:
    path = global_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not path.exists():
        path.write_text(global_config_text(), encoding="utf-8")
    return path


def init_state_dir(workdir: str | Path | None = None) -> Path:
    root = resolve_workdir(workdir)
    mmdev_dir = root / CONFIG_DIR
    for child in ("checkpoints", "logs", "memory", "patches", "reports", "worktrees"):
        (mmdev_dir / child).mkdir(parents=True, exist_ok=True)
    initialize_state(mmdev_dir)
    config_path = mmdev_dir / CONFIG_FILE
    if not config_path.exists():
        config_path.write_text(default_config_text(), encoding="utf-8")
    return mmdev_dir
