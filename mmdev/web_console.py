from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request

from mmdev.checkpoint import checkpoint_diff, create_checkpoint, list_checkpoints, restore_checkpoint
from mmdev.config import global_config_path, init_global_config, load_toml_file, init_state_dir, load_config, resolve_workdir, write_global_config
from mmdev.doctor import run_doctor
from mmdev.executor import execute_task, find_task, load_plan
from mmdev.memory import load_memory, refresh_memory, render_memory_markdown
from mmdev.metrics import build_metrics
from mmdev.planner import create_plan, write_plan
from mmdev.reporter import generate_report, write_final_report
from mmdev.state import task_statuses


class PlanRequest(BaseModel):
    requirement: str = Field(min_length=1)


class CheckpointRequest(BaseModel):
    label: str = "manual"


class RestoreRequest(BaseModel):
    yes: bool = False
    allow_head_mismatch: bool = False


class SetupConfigRequest(BaseModel):
    strong_model_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_mode: str = "responses"
    openai_planner_model: str = ""
    openai_reviewer_model: str = ""
    claude_api_key: str = ""
    claude_base_url: str = "https://api.anthropic.com/v1"
    claude_planner_model: str = ""
    claude_reviewer_model: str = ""
    executor_provider: str = "deepseek_byok"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_executor_model: str = "deepseek-v4-pro"
    mmdev_gateway_url: str = ""
    mmdev_gateway_token: str = ""
    mmdev_gateway_executor_model: str = "gateway-executor"


Builder = Callable[[object], object]


def default_strong_client_builder(config):
    from mmdev.cli import build_strong_client

    return build_strong_client(config)


def default_executor_client_builder(config):
    from mmdev.cli import build_executor_client

    return build_executor_client(config)


def create_web_app(
    workdir: str | Path | None = None,
    *,
    strong_client_builder: Builder | None = None,
    executor_client_builder: Builder | None = None,
) -> FastAPI:
    resolved_workdir = resolve_workdir(workdir)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    build_strong = strong_client_builder or default_strong_client_builder
    build_executor = executor_client_builder or default_executor_client_builder

    app = FastAPI(title="tokenpatch Local Web Console", version="0.1.0")

    def current_config():
        return load_config(resolved_workdir)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        config = current_config()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "workdir": str(config.workdir),
                "strong_provider": config.normalized_strong_model_provider,
                "executor_provider": config.executor_provider,
                "default_executor": "deepseek_byok",
            },
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request):
        config = current_config()
        doctor = run_doctor(config, check_api=False)
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "workdir": str(config.workdir),
                "strong_provider": config.normalized_strong_model_provider,
                "executor_provider": config.executor_provider,
                "planner_model": config.planner_model or "",
                "reviewer_model": config.reviewer_model or "",
                "executor_model": config.mmdev_gateway_executor_model
                if config.executor_provider == "mmdev_gateway"
                else (config.deepseek_executor_model or ""),
                "doctor_ok": doctor.ok,
                "checks": [check.model_dump() for check in doctor.checks],
            },
        )

    @app.get("/setup", response_class=HTMLResponse)
    def setup(request: Request):
        init_global_config()
        config = current_config()
        return templates.TemplateResponse(
            "setup.html",
            {
                "request": request,
                "global_config_path": str(global_config_path()),
                "config": public_setup_config(config),
            },
        )

    @app.get("/onboarding", response_class=HTMLResponse)
    def onboarding(request: Request):
        config = current_config()
        payload = onboarding_payload(config)
        return templates.TemplateResponse(
            "onboarding.html",
            {
                "request": request,
                "workdir": str(config.workdir),
                "strong_provider": config.normalized_strong_model_provider,
                "executor_provider": config.executor_provider,
                "ready_to_plan": payload["ready_to_plan"],
                "ready_to_run": payload["ready_to_run"],
                "next_action": payload["next_action"],
                "steps": payload["steps"],
            },
        )

    @app.get("/api/state")
    def api_state():
        config = current_config()
        doctor = run_doctor(config, check_api=False)
        payload: dict[str, object] = {
            "workdir": str(config.workdir),
            "strong_provider": config.normalized_strong_model_provider,
            "executor_provider": config.executor_provider,
            "default_executor_recommendation": "deepseek_byok",
            "doctor": {"ok": doctor.ok, "checks": [check.model_dump() for check in doctor.checks]},
            "task_statuses": task_statuses(config.mmdev_dir),
            "plan": None,
            "report": None,
            "metrics_summary": None,
            "patch_economics": None,
            "checkpoints": [],
            "memory": None,
        }

        tasks_path = config.mmdev_dir / "tasks.json"
        if tasks_path.exists():
            plan = json.loads(tasks_path.read_text(encoding="utf-8-sig"))
            payload["plan"] = {
                "project_summary": plan.get("project_summary", ""),
                "risks": plan.get("risks", []),
                "assumptions": plan.get("assumptions", []),
                "tasks": plan.get("tasks", []),
            }
        report_path = config.mmdev_dir / "reports" / "final-report.md"
        if report_path.exists():
            payload["report"] = {
                "path": str(report_path),
                "preview": "\n".join(report_path.read_text(encoding="utf-8-sig").splitlines()[:30]),
            }
        try:
            metrics = build_metrics(config.mmdev_dir, window="all")
            payload["metrics_summary"] = metrics.get("summary")
            payload["patch_economics"] = metrics.get("patch_economics")
        except Exception:
            payload["metrics_summary"] = None
            payload["patch_economics"] = None
        payload["checkpoints"] = [record.model_dump() for record in list_checkpoints(config.mmdev_dir)[:5]]
        memory = load_memory(config.mmdev_dir)
        if memory is not None:
            payload["memory"] = {
                "generated_at": memory.generated_at,
                "project_summary": memory.project_summary,
                "preview": "\n".join(render_memory_markdown(memory).splitlines()[:40]),
            }
        return payload

    @app.get("/api/onboarding")
    def api_onboarding():
        return onboarding_payload(current_config())

    @app.get("/api/setup")
    def api_setup():
        init_global_config()
        return {
            "ok": True,
            "global_config_path": str(global_config_path()),
            "config": public_setup_config(current_config()),
        }

    @app.post("/api/setup")
    def api_save_setup(body: SetupConfigRequest):
        try:
            path = write_global_config(body.model_dump())
            config = current_config()
            doctor = run_doctor(config, check_api=False)
            return {
                "ok": True,
                "global_config_path": str(path),
                "config": public_setup_config(config),
                "doctor": {"ok": doctor.ok, "checks": [check.model_dump() for check in doctor.checks]},
            }
        except Exception as exc:
            return error_response(exc)

    @app.post("/api/setup/test")
    def api_test_setup(body: SetupConfigRequest):
        try:
            write_global_config(body.model_dump())
            config = current_config()
            doctor = run_doctor(config, check_api=True)
            return {"ok": doctor.ok, "checks": [check.model_dump() for check in doctor.checks]}
        except Exception as exc:
            return error_response(exc)

    @app.post("/api/plan")
    def api_plan(body: PlanRequest):
        config = current_config()
        init_state_dir(config.workdir)
        try:
            client = build_strong(config)
            plan = create_plan(body.requirement, config, client)
            path = write_plan(config.mmdev_dir, plan)
            return {"ok": True, "tasks_path": str(path), "plan": plan.model_dump()}
        except Exception as exc:  # pragma: no cover - normalized via tests by API status
            return error_response(exc)

    @app.post("/api/run/{task_id}")
    def api_run(task_id: str):
        config = current_config()
        try:
            plan = load_plan(config.mmdev_dir)
            task = find_task(plan, task_id)
            client = build_executor(config)
            checkpoint = create_checkpoint(config, f"before-run-{task_id}", source="web-run")
            result = execute_task(task, config, client)
            return {"ok": True, "checkpoint": checkpoint.model_dump(), "execution": result.model_dump()}
        except Exception as exc:  # pragma: no cover - normalized via tests by API status
            return error_response(exc)

    @app.get("/api/checkpoints")
    def api_checkpoints():
        config = current_config()
        return {"ok": True, "checkpoints": [record.model_dump() for record in list_checkpoints(config.mmdev_dir)]}

    @app.post("/api/checkpoints")
    def api_create_checkpoint(body: CheckpointRequest):
        config = current_config()
        try:
            record = create_checkpoint(config, body.label, source="web")
            return {"ok": True, "checkpoint": record.model_dump()}
        except Exception as exc:
            return error_response(exc)

    @app.get("/api/checkpoints/{checkpoint_id}/diff")
    def api_checkpoint_diff(checkpoint_id: str):
        config = current_config()
        try:
            return {"ok": True, "checkpoint_id": checkpoint_id, "diff": checkpoint_diff(config.mmdev_dir, checkpoint_id)}
        except Exception as exc:
            return error_response(exc)

    @app.post("/api/checkpoints/{checkpoint_id}/restore")
    def api_checkpoint_restore(checkpoint_id: str, body: RestoreRequest):
        config = current_config()
        try:
            return restore_checkpoint(config, checkpoint_id, yes=body.yes, allow_head_mismatch=body.allow_head_mismatch)
        except Exception as exc:
            return error_response(exc)

    @app.get("/api/memory")
    def api_memory():
        config = current_config()
        memory = load_memory(config.mmdev_dir)
        if memory is None:
            return {"ok": True, "memory": None, "markdown": ""}
        return {"ok": True, "memory": memory.model_dump(), "markdown": render_memory_markdown(memory)}

    @app.post("/api/memory/refresh")
    def api_memory_refresh():
        config = current_config()
        try:
            memory = refresh_memory(config)
            return {"ok": True, "memory": memory.model_dump(), "markdown": render_memory_markdown(memory)}
        except Exception as exc:
            return error_response(exc)

    @app.post("/api/report")
    def api_report():
        config = current_config()
        try:
            path = write_final_report(config.mmdev_dir)
            text = generate_report(config.mmdev_dir)
            metrics = build_metrics(config.mmdev_dir, window="all")
            return {
                "ok": True,
                "report_path": str(path),
                "report_text": text,
                "metrics_summary": metrics.get("summary", {}),
                "patch_economics": metrics.get("patch_economics", {}),
            }
        except Exception as exc:  # pragma: no cover - normalized via tests by API status
            return error_response(exc)

    return app


def public_setup_config(config) -> dict[str, object]:
    global_values = load_toml_file(global_config_path())
    return {
        "strong_model_provider": config.strong_model_provider,
        "openai_api_key": global_values.get("openai_api_key", "") or "",
        "openai_base_url": config.openai_base_url,
        "openai_api_mode": config.openai_api_mode,
        "openai_planner_model": config.openai_planner_model or "",
        "openai_reviewer_model": config.openai_reviewer_model or "",
        "claude_api_key": global_values.get("claude_api_key", "") or "",
        "claude_base_url": config.claude_base_url,
        "claude_planner_model": config.claude_planner_model or "",
        "claude_reviewer_model": config.claude_reviewer_model or "",
        "executor_provider": config.executor_provider,
        "deepseek_api_key": global_values.get("deepseek_api_key", "") or "",
        "deepseek_base_url": config.deepseek_base_url or "https://api.deepseek.com",
        "deepseek_executor_model": config.deepseek_executor_model or "deepseek-v4-pro",
        "mmdev_gateway_url": config.mmdev_gateway_url or "",
        "mmdev_gateway_token": global_values.get("mmdev_gateway_token", "") or "",
        "mmdev_gateway_executor_model": config.mmdev_gateway_executor_model,
    }


def onboarding_payload(config) -> dict[str, object]:
    doctor = run_doctor(config, check_api=False)
    checks = {check.name: check for check in doctor.checks}

    local_state = checks.get("local-state")
    git = checks.get("git")
    git_head = checks.get("git-head")
    strong = checks.get("strong-model-config")
    executor = checks.get("executor-config")
    tasks = checks.get("tasks")

    steps = [
        step_from_check(
            "Initialize local state",
            local_state,
            "Run `tokenpatch init` in the project root.",
            required=True,
        ),
        git_step(git, git_head),
        step_from_check(
            "Configure strong model",
            strong,
            strong_model_fix(config.normalized_strong_model_provider),
            required=True,
        ),
        step_from_check(
            "Configure executor",
            executor,
            executor_fix(config.executor_provider),
            required=True,
        ),
        step_from_check(
            "Generate task plan",
            tasks,
            "Enter a requirement on the console page and click `Plan Tasks`.",
            required=False,
        ),
    ]
    ready_to_plan = steps[0]["status"] == "pass" and steps[2]["status"] == "pass"
    ready_to_run = (
        ready_to_plan
        and steps[1]["status"] in {"pass", "warn"}
        and steps[3]["status"] == "pass"
        and steps[4]["status"] == "pass"
        and git_head_status(git_head) != "fail"
    )
    next_action = next((step for step in steps if step["status"] != "pass"), None)
    return {
        "workdir": str(config.workdir),
        "strong_provider": config.normalized_strong_model_provider,
        "executor_provider": config.executor_provider,
        "ready_to_plan": ready_to_plan,
        "ready_to_run": ready_to_run,
        "next_action": next_action,
        "steps": steps,
    }


def step_from_check(title: str, check, fix: str, *, required: bool) -> dict[str, object]:
    status = check.status if check is not None else "warn"
    message = check.message if check is not None else "check unavailable"
    return {
        "title": title,
        "status": status,
        "message": message,
        "fix": fix,
        "required": required,
    }


def git_step(git, git_head) -> dict[str, object]:
    if git is None:
        status = "fail"
        message = "Git check unavailable"
    elif git.status != "pass":
        status = git.status
        message = git.message
    else:
        head_status = git_head_status(git_head)
        status = "pass" if head_status == "pass" else "warn"
        message = git_head.message if git_head is not None else git.message
    return {
        "title": "Prepare Git baseline",
        "status": status,
        "message": message,
        "fix": "Run `git init`, commit a clean baseline, then refresh this page.",
        "required": True,
    }


def git_head_status(git_head) -> str:
    return git_head.status if git_head is not None else "warn"


def strong_model_fix(provider: str) -> str:
    if provider == "claude":
        return "Set CLAUDE_API_KEY, CLAUDE_PLANNER_MODEL, and CLAUDE_REVIEWER_MODEL."
    return "Set OPENAI_API_KEY, OPENAI_PLANNER_MODEL, and OPENAI_REVIEWER_MODEL."


def executor_fix(provider: str) -> str:
    if provider == "mmdev_gateway":
        return "Set MMDEV_GATEWAY_URL and MMDEV_GATEWAY_TOKEN."
    return "Set DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, and DEEPSEEK_EXECUTOR_MODEL."


def error_response(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "ok": False,
            "error": friendly_error_message(exc),
            "error_type": type(exc).__name__,
        },
    )


def friendly_error_message(exc: Exception) -> str:
    text = str(exc).strip()
    if "OPENAI_API_KEY" in text or "CLAUDE_API_KEY" in text:
        return "Missing strong-model API key. Configure it in .mmdev/config.toml, ~/.tokenpatch/config.toml, or environment variables."
    if "OPENAI_PLANNER_MODEL" in text or "CLAUDE_PLANNER_MODEL" in text or "OPENAI_REVIEWER_MODEL" in text:
        return "Missing strong-model name. Configure the planner/reviewer model."
    if "DEEPSEEK_API_KEY" in text or "DEEPSEEK_BASE_URL" in text or "DEEPSEEK_EXECUTOR_MODEL" in text:
        return "Missing DeepSeek executor configuration. Check your deepseek_byok settings."
    if "MMDEV_GATEWAY_URL" in text or "MMDEV_GATEWAY_TOKEN" in text:
        return "Missing gateway configuration. Check MMDEV_GATEWAY_URL and MMDEV_GATEWAY_TOKEN."
    if "missing .mmdev/tasks.json" in text or "task not found" in text:
        return "No task plan exists yet. Run Plan first."
    if "not a Git repository" in text or "requires a Git project" in text:
        return "The current folder is not a Git project. Run git init and commit a baseline before applying patches."
    if "outside allowed_files" in text:
        return "The model patch changed files outside allowed_files, so tokenpatch rejected it."
    if "invalid JSON twice" in text:
        return "The model returned invalid JSON twice. Retry or switch models."
    if "only supports low complexity tasks" in text:
        return "This MVP only runs low-complexity cheap-executor tasks automatically. Split or narrow the task."
    return text or "Unknown error. Check the logs for details."
