from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from mmdev.config import MMDevConfig
from mmdev.git_utils import git_status_short, is_git_project, run_command
from mmdev.models.base import CompletionClient
from mmdev.models.claude_client import ClaudeMessagesClient
from mmdev.models.deepseek_client import DeepSeekChatClient
from mmdev.models.gateway_client import MMDevGatewayClient
from mmdev.models.openai_client import OpenAIChatCompletionsClient, OpenAIResponsesClient


class DoctorCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    message: str


class DoctorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks)


def run_doctor(
    config: MMDevConfig,
    *,
    check_api: bool = False,
    openai_client: CompletionClient | None = None,
    deepseek_client: CompletionClient | None = None,
) -> DoctorResult:
    checks = [
        check_workdir(config),
        check_mmdev_dir(config),
        check_python_dependencies(),
        check_git(config),
        check_git_head(config),
        check_worktree_support(config),
        check_strong_model_config(config),
        check_executor_config(config),
        check_tasks(config),
    ]
    if check_api:
        checks.extend(check_model_apis(config, strong_client=openai_client, executor_client=deepseek_client))
    return DoctorResult(checks=checks)


def check_workdir(config: MMDevConfig) -> DoctorCheck:
    if config.workdir.exists() and config.workdir.is_dir():
        return DoctorCheck(name="workdir", status="pass", message=str(config.workdir))
    return DoctorCheck(name="workdir", status="fail", message=f"missing directory: {config.workdir}")


def check_mmdev_dir(config: MMDevConfig) -> DoctorCheck:
    if config.mmdev_dir.exists():
        state = config.mmdev_dir / "state.sqlite"
        if state.exists():
            return DoctorCheck(name="local-state", status="pass", message=str(config.mmdev_dir))
        return DoctorCheck(name="local-state", status="warn", message=".mmdev exists but state.sqlite is missing; run mmdev init")
    return DoctorCheck(name="local-state", status="warn", message=".mmdev is not initialized; run mmdev init")


def check_python_dependencies() -> DoctorCheck:
    missing = [name for name in ("typer", "pydantic", "httpx") if importlib.util.find_spec(name) is None]
    if missing:
        return DoctorCheck(name="python-dependencies", status="fail", message="missing: " + ", ".join(missing))
    return DoctorCheck(name="python-dependencies", status="pass", message="typer, pydantic, httpx available")


def check_git(config: MMDevConfig) -> DoctorCheck:
    if not is_git_project(config.workdir, 10):
        return DoctorCheck(name="git", status="fail", message="not a Git repository")
    return DoctorCheck(name="git", status="pass", message=git_status_short(config.workdir, 10))


def check_git_head(config: MMDevConfig) -> DoctorCheck:
    if not is_git_project(config.workdir, 10):
        return DoctorCheck(name="git-head", status="fail", message="not a Git repository")
    result = run_command(["git", "rev-parse", "--verify", "HEAD"], config.workdir, 10)
    if result.returncode == 0:
        return DoctorCheck(name="git-head", status="pass", message=result.stdout.strip()[:12])
    return DoctorCheck(name="git-head", status="warn", message="no HEAD commit yet; worktree isolation will not work")


def check_worktree_support(config: MMDevConfig) -> DoctorCheck:
    if not is_git_project(config.workdir, 10):
        return DoctorCheck(name="worktree-support", status="fail", message="requires Git repository")
    result = run_command(["git", "worktree", "list"], config.workdir, 10)
    if result.returncode == 0:
        return DoctorCheck(name="worktree-support", status="pass", message="git worktree available")
    return DoctorCheck(name="worktree-support", status="warn", message=result.stderr.strip() or "git worktree unavailable")


def check_strong_model_config(config: MMDevConfig) -> DoctorCheck:
    provider = config.normalized_strong_model_provider
    missing = []
    if provider == "claude":
        if not config.claude_api_key:
            missing.append("CLAUDE_API_KEY")
        if not config.claude_planner_model:
            missing.append("CLAUDE_PLANNER_MODEL")
        if not config.claude_reviewer_model:
            missing.append("CLAUDE_REVIEWER_MODEL")
    elif provider == "openai":
        if not config.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not config.openai_planner_model:
            missing.append("OPENAI_PLANNER_MODEL")
        if not config.openai_reviewer_model:
            missing.append("OPENAI_REVIEWER_MODEL")
    else:
        return DoctorCheck(name="strong-model-config", status="fail", message="unknown strong_model_provider")
    if missing:
        return DoctorCheck(name="strong-model-config", status="warn", message="missing: " + ", ".join(missing))
    return DoctorCheck(name="strong-model-config", status="pass", message=f"{provider} planner and reviewer config present")


def check_executor_config(config: MMDevConfig) -> DoctorCheck:
    provider = config.normalized_executor_provider
    notes = " ".join(config.executor_provider_notes)
    if provider == "mmdev_gateway":
        missing = []
        if not config.mmdev_gateway_url:
            missing.append("MMDEV_GATEWAY_URL")
        if not config.mmdev_gateway_token:
            missing.append("MMDEV_GATEWAY_TOKEN")
        if missing:
            return DoctorCheck(name="executor-config", status="warn", message="missing: " + ", ".join(missing) + f"; {notes}")
        return DoctorCheck(name="executor-config", status="pass", message=f"tokenpatch gateway config present; {notes}")
    if provider != "deepseek_byok":
        return DoctorCheck(name="executor-config", status="fail", message="unknown executor_provider")
    missing = []
    if not config.deepseek_api_key:
        missing.append("DEEPSEEK_API_KEY")
    if not config.deepseek_base_url:
        missing.append("DEEPSEEK_BASE_URL")
    if not config.deepseek_executor_model:
        missing.append("DEEPSEEK_EXECUTOR_MODEL")
    if missing:
        return DoctorCheck(name="executor-config", status="warn", message="missing: " + ", ".join(missing) + f"; {notes}")
    return DoctorCheck(name="executor-config", status="pass", message=f"DeepSeek BYOK executor config present; {notes}")


def check_tasks(config: MMDevConfig) -> DoctorCheck:
    tasks = config.mmdev_dir / "tasks.json"
    if tasks.exists():
        return DoctorCheck(name="tasks", status="pass", message=str(tasks))
    return DoctorCheck(name="tasks", status="warn", message="missing .mmdev/tasks.json; run mmdev plan")


def check_model_apis(
    config: MMDevConfig,
    *,
    strong_client: CompletionClient | None = None,
    executor_client: CompletionClient | None = None,
) -> list[DoctorCheck]:
    return [
        check_strong_model_api(config, strong_client),
        check_executor_api(config, executor_client),
    ]


def check_strong_model_api(config: MMDevConfig, client: CompletionClient | None = None) -> DoctorCheck:
    provider = config.normalized_strong_model_provider
    if provider == "claude":
        if not config.claude_api_key or not config.claude_planner_model:
            return DoctorCheck(name="strong-model-api", status="warn", message="skipped; missing CLAUDE_API_KEY or CLAUDE_PLANNER_MODEL")
        client = client or ClaudeMessagesClient(config.claude_api_key, config.claude_base_url)
        model = config.claude_planner_model
    elif provider == "openai":
        if not config.openai_api_key or not config.openai_planner_model:
            return DoctorCheck(name="strong-model-api", status="warn", message="skipped; missing OPENAI_API_KEY or OPENAI_PLANNER_MODEL")
        client = client or build_openai_client(config)
        model = config.openai_planner_model
    else:
        return DoctorCheck(name="strong-model-api", status="fail", message="unknown strong_model_provider")
    return check_json_completion(
        name="strong-model-api",
        client=client,
        model=model,
        timeout_seconds=config.request_timeout_seconds,
    )


def check_executor_api(config: MMDevConfig, client: CompletionClient | None = None) -> DoctorCheck:
    if config.normalized_executor_provider == "mmdev_gateway":
        if not config.mmdev_gateway_url or not config.mmdev_gateway_token:
            return DoctorCheck(name="executor-api", status="warn", message="skipped; missing gateway config")
        client = client or MMDevGatewayClient(
            config.mmdev_gateway_url,
            config.mmdev_gateway_token,
            country=config.mmdev_gateway_country,
            entity=config.mmdev_gateway_entity,
        )
        return check_json_completion(
            name="executor-api",
            client=client,
            model=config.mmdev_gateway_executor_model,
            timeout_seconds=config.request_timeout_seconds,
        )
    if not config.deepseek_api_key or not config.deepseek_base_url or not config.deepseek_executor_model:
        return DoctorCheck(name="executor-api", status="warn", message="skipped; missing DeepSeek executor config")
    client = client or DeepSeekChatClient(config.deepseek_api_key, config.deepseek_base_url)
    return check_json_completion(
        name="executor-api",
        client=client,
        model=config.deepseek_executor_model,
        timeout_seconds=config.request_timeout_seconds,
    )


def check_json_completion(name: str, client: CompletionClient, model: str, timeout_seconds: int) -> DoctorCheck:
    prompt = 'Return only this JSON object: {"ok": true}'
    try:
        result = client.complete(prompt=prompt, model=model, timeout_seconds=timeout_seconds)
        payload = json.loads(result.text.strip())
        if payload.get("ok") is True:
            return DoctorCheck(name=name, status="pass", message=f"{model} returned valid JSON")
        return DoctorCheck(name=name, status="fail", message=f"{model} returned JSON without ok=true")
    except Exception as exc:
        return DoctorCheck(name=name, status="fail", message=f"{model} check failed: {exc}")


def build_openai_client(config: MMDevConfig) -> CompletionClient:
    mode = (config.openai_api_mode or "responses").strip().lower()
    if mode == "responses":
        return OpenAIResponsesClient(config.openai_api_key or "", config.openai_base_url)
    if mode == "chat_completions":
        return OpenAIChatCompletionsClient(config.openai_api_key or "", config.openai_base_url)
    raise ValueError("OPENAI_API_MODE/openai_api_mode must be 'responses' or 'chat_completions'")


def format_doctor(result: DoctorResult) -> str:
    lines = []
    for check in result.checks:
        marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}.get(check.status, check.status.upper())
        lines.append(f"[{marker}] {check.name}: {check.message}")
    return "\n".join(lines)
