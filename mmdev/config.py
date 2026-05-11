from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from mmdev.state import initialize_state


CONFIG_DIR = ".mmdev"
CONFIG_FILE = "config.toml"


class MMDevConfig(BaseModel):
    workdir: Path = Field(default_factory=Path.cwd)
    strong_model_provider: str = "openai"
    openai_api_key: str | None = None
    openai_planner_model: str | None = None
    openai_reviewer_model: str | None = None
    claude_api_key: str | None = None
    claude_base_url: str = "https://api.anthropic.com/v1"
    claude_planner_model: str | None = None
    claude_reviewer_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = None
    deepseek_executor_model: str | None = None
    executor_provider: str = "deepseek_byok"
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
    executor_input_cost_per_million: float = 0.0
    executor_output_cost_per_million: float = 0.0
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


ENV_MAP = {
    "MMDEV_STRONG_MODEL_PROVIDER": "strong_model_provider",
    "OPENAI_API_KEY": "openai_api_key",
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


def load_config(workdir: str | Path | None = None) -> MMDevConfig:
    resolved_workdir = resolve_workdir(workdir)
    data: dict[str, object] = {"workdir": resolved_workdir}
    config_path = resolved_workdir / CONFIG_DIR / CONFIG_FILE
    if config_path.exists():
        with config_path.open("rb") as fh:
            file_data = tomllib.load(fh)
        data.update(file_data)

    for env_name, field_name in ENV_MAP.items():
        value = os.getenv(env_name)
        if value:
            data[field_name] = Path(value).expanduser().resolve() if field_name == "workdir" else value

    return MMDevConfig(**data)


def default_config_text() -> str:
    return """# tokenpatch local configuration.
# Environment variables override these values.

strong_model_provider = "openai" # openai or claude
openai_api_key = ""
openai_planner_model = ""
openai_reviewer_model = ""
claude_api_key = ""
claude_base_url = "https://api.anthropic.com/v1"
claude_planner_model = ""
claude_reviewer_model = ""
deepseek_api_key = ""
deepseek_base_url = ""
deepseek_executor_model = ""
executor_provider = "deepseek_byok" # deepseek_byok or mmdev_gateway
mmdev_gateway_url = ""
mmdev_gateway_token = ""
mmdev_gateway_executor_model = "gateway-executor"
mmdev_gateway_country = "" # optional, sent as X-MMDEV-Country in gateway mode
mmdev_gateway_entity = "" # optional, sent as X-MMDEV-Entity in gateway mode
command_timeout_seconds = 120
request_timeout_seconds = 120

# Estimated pricing, in cost units per 1M tokens. Leave as 0 if unknown.
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


def init_state_dir(workdir: str | Path | None = None) -> Path:
    root = resolve_workdir(workdir)
    mmdev_dir = root / CONFIG_DIR
    for child in ("logs", "patches", "reports", "worktrees"):
        (mmdev_dir / child).mkdir(parents=True, exist_ok=True)
    initialize_state(mmdev_dir)
    config_path = mmdev_dir / CONFIG_FILE
    if not config_path.exists():
        config_path.write_text(default_config_text(), encoding="utf-8")
    return mmdev_dir
