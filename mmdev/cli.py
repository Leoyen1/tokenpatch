from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from mmdev.checkpoint import checkpoint_diff, create_checkpoint, list_checkpoints, restore_checkpoint
from mmdev.claude_install import install_claude_code
from mmdev.codex_install import default_codex_config_path, install_codex_mcp
from mmdev.config import global_config_path, init_global_config, init_state_dir, load_config
from mmdev.cursor_install import install_cursor_rules
from mmdev.doctor import format_doctor, run_doctor
from mmdev.executor import execute_task, find_task, load_plan
from mmdev.git_utils import git_status_short
from mmdev.isolation import export_worktree_diff, prepare_worktree
from mmdev.models.claude_client import ClaudeMessagesClient
from mmdev.models.deepseek_client import DeepSeekChatClient
from mmdev.models.gateway_client import MMDevGatewayClient
from mmdev.models.openai_client import OpenAIChatCompletionsClient, OpenAIResponsesClient
from mmdev.metrics import build_metrics, push_metrics, write_metrics_csvs, write_metrics_meta_csv
from mmdev.memory import load_memory, memory_markdown_path, refresh_memory, render_memory_markdown
from mmdev.planner import create_plan, write_plan
from mmdev.reporter import write_final_report
from mmdev.reviewer import review_task, write_review_result
from mmdev.run_events import append_run_event
from mmdev.schemas import DevTask, ProjectPlan
from mmdev.state import task_statuses
from mmdev.validator import read_validation_result, validate_task, write_validation_result
from mmdev.workflow import run_auto


app = typer.Typer(no_args_is_help=True)
checkpoint_app = typer.Typer(no_args_is_help=True, help="Advanced: inspect or restore local recovery checkpoints.")
memory_app = typer.Typer(no_args_is_help=True, help="Advanced: refresh or show compact local project context.")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(memory_app, name="memory")


def strong_model_provider_label(config) -> str:
    return config.normalized_strong_model_provider


def executor_model_label(config) -> str:
    return config.executor_model


def redact_install_snippet(text: str) -> str:
    for key in ("DEEPSEEK_API_KEY", "MMDEV_GATEWAY_TOKEN"):
        marker = f'{key} = "'
        start = text.find(marker)
        while start != -1:
            value_start = start + len(marker)
            value_end = text.find('"', value_start)
            if value_end == -1:
                break
            text = text[:value_start] + ("<set>" if value_end > value_start else "") + text[value_end:]
            start = text.find(marker, value_end)
    return text


def executor_config_summary(config) -> tuple[str, bool]:
    provider = config.normalized_executor_provider
    if provider == "mmdev_gateway":
        ok = bool(config.mmdev_gateway_url and config.mmdev_gateway_token)
        detail = "gateway configured" if ok else "gateway missing MMDEV_GATEWAY_URL or MMDEV_GATEWAY_TOKEN"
        return f"{detail}; {config.executor_provider_reason}", ok
    if provider == "deepseek_byok":
        ok = bool(config.deepseek_api_key and config.deepseek_base_url and config.deepseek_executor_model)
        detail = (
            f"deepseek_byok configured ({config.deepseek_executor_model})"
            if ok
            else "deepseek_byok missing DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, or DEEPSEEK_EXECUTOR_MODEL"
        )
        return f"{detail}; {config.executor_provider_reason}", ok
    return f"unknown executor_provider: {config.executor_provider}", False


def build_strong_client(config):
    provider = config.normalized_strong_model_provider
    if provider == "openai":
        if not config.openai_api_key:
            raise typer.BadParameter("OPENAI_API_KEY or openai_api_key is required")
        mode = (config.openai_api_mode or "responses").strip().lower()
        if mode == "responses":
            return OpenAIResponsesClient(config.openai_api_key, config.openai_base_url)
        if mode == "chat_completions":
            return OpenAIChatCompletionsClient(config.openai_api_key, config.openai_base_url)
        raise typer.BadParameter("OPENAI_API_MODE/openai_api_mode must be 'responses' or 'chat_completions'")
    if provider == "claude":
        if not config.claude_api_key:
            raise typer.BadParameter("CLAUDE_API_KEY or claude_api_key is required")
        return ClaudeMessagesClient(config.claude_api_key, config.claude_base_url)
    raise typer.BadParameter("strong_model_provider must be 'openai' or 'claude'")


def build_executor_client(config):
    provider = config.normalized_executor_provider
    if provider == "deepseek_byok":
        if not config.deepseek_api_key:
            raise typer.BadParameter("DEEPSEEK_API_KEY or deepseek_api_key is required")
        if not config.deepseek_base_url:
            raise typer.BadParameter("DEEPSEEK_BASE_URL or deepseek_base_url is required")
        return DeepSeekChatClient(config.deepseek_api_key, config.deepseek_base_url)
    if provider == "mmdev_gateway":
        if not config.mmdev_gateway_url:
            raise typer.BadParameter("MMDEV_GATEWAY_URL or mmdev_gateway_url is required")
        if not config.mmdev_gateway_token:
            raise typer.BadParameter("MMDEV_GATEWAY_TOKEN or mmdev_gateway_token is required")
        return MMDevGatewayClient(
            config.mmdev_gateway_url,
            config.mmdev_gateway_token,
            country=config.mmdev_gateway_country,
            entity=config.mmdev_gateway_entity,
        )
    raise typer.BadParameter("executor_provider must be 'deepseek_byok' or 'mmdev_gateway'")


@app.command()
def init(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    mmdev_dir = init_state_dir(workdir)
    typer.echo(f"Initialized {mmdev_dir}")


@app.command("init-global")
def init_global(overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing global config template.")) -> None:
    path = init_global_config(overwrite=overwrite)
    typer.echo(f"Global config: {path}")
    typer.echo("Edit this file once; new projects can reuse it without copying API keys.")


@app.command()
def status(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    typer.echo(f"Workdir: {config.workdir}")
    typer.echo(f"Initialized: {config.mmdev_dir.exists()}")
    typer.echo(f"Global config: {global_config_path()} ({global_config_path().exists()})")
    typer.echo(f"Executor provider: {config.normalized_executor_provider}")
    for note in config.executor_provider_notes:
        typer.echo(f"Executor note: {note}")
    typer.echo(f"Executor model: {config.executor_model}")
    typer.echo(f"Tasks: {(config.mmdev_dir / 'tasks.json').exists()}")
    typer.echo(f"Git: {git_status_short(config.workdir, 10)}")
    statuses = task_statuses(config.mmdev_dir)
    if statuses:
        typer.echo("Task statuses:")
        for row in statuses:
            typer.echo(f"- {row['task_id']}: {row['status']} ({row['title']})")


@app.command()
def doctor(
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    api: bool = typer.Option(False, "--api", help="Send minimal requests to configured model APIs."),
) -> None:
    config = load_config(workdir)
    result = run_doctor(config, check_api=api)
    typer.echo(format_doctor(result))
    if not result.ok:
        raise typer.Exit(code=1)


@app.command()
def plan(requirement: str, workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    strong_provider = strong_model_provider_label(config)
    strong_model = config.planner_model
    append_run_event(
        config.mmdev_dir,
        {
            "event": "cli.plan.start",
            "strong_provider": strong_provider,
            "strong_model": strong_model,
            "requirement_chars": len(requirement),
        },
    )
    try:
        typer.echo(f"Strong model (plan): provider={strong_provider}, model={strong_model or '<unset>'}")
        client = build_strong_client(config)
        project_plan = create_plan(requirement, config, client)
        path = write_plan(config.mmdev_dir, project_plan)
        typer.echo(f"Wrote {path}")
    except Exception as exc:
        append_run_event(
            config.mmdev_dir,
            {
                "event": "cli.plan.finish",
                "outcome": "error",
                "error_type": type(exc).__name__,
                "strong_provider": strong_provider,
                "strong_model": strong_model,
                "requirement_chars": len(requirement),
            },
        )
        raise
    append_run_event(
        config.mmdev_dir,
        {
            "event": "cli.plan.finish",
            "outcome": "success",
            "strong_provider": strong_provider,
            "strong_model": strong_model,
            "requirement_chars": len(requirement),
        },
    )


@app.command()
def run(
    task_id: str,
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    isolation: str = typer.Option("none", help="Isolation mode: none or worktree."),
    checkpoint: bool = typer.Option(True, "--checkpoint/--no-checkpoint", help="Create a local recovery checkpoint before running."),
) -> None:
    config = load_config(workdir)
    plan_data = load_plan(config.mmdev_dir)
    task = find_task(plan_data, task_id)
    client = build_executor_client(config)
    if isolation not in {"none", "worktree"}:
        raise typer.BadParameter("isolation must be 'none' or 'worktree'")
    if checkpoint:
        record = create_checkpoint(config, f"before-run-{task_id}", source="run")
        typer.echo(f"Checkpoint: {record.id}")
    active_config = prepare_worktree(config, task_id) if isolation == "worktree" else config
    result = execute_task(task, active_config, client)
    typer.echo(result.model_dump_json(indent=2))


@app.command("do")
def do_task(
    requirement: str,
    allowed_file: list[str] | None = typer.Option(None, "--allowed-file", "-f", help="Relative file the executor may modify. Repeat for multiple files."),
    acceptance: list[str] | None = typer.Option(None, "--acceptance", "-a", help="Acceptance criterion. Repeat for multiple checks."),
    title: str | None = typer.Option(None, "--title", help="Short task title."),
    goal: str | None = typer.Option(None, "--goal", help="Concrete executor goal. Defaults to requirement."),
    context: str = typer.Option("", "--context", help="Extra bounded context for the executor."),
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    checkpoint: bool = typer.Option(True, "--checkpoint/--no-checkpoint", help="Create a local recovery checkpoint before running."),
) -> None:
    files = allowed_file or []
    if not files:
        raise typer.BadParameter("at least one --allowed-file is required")
    config = load_config(workdir)
    init_state_dir(config.workdir)
    doctor_result = run_doctor(config, check_api=False)
    blocking = [
        check
        for check in doctor_result.checks
        if check.name in {"workdir", "git", "executor-config"} and check.status == "fail"
    ]
    if blocking:
        typer.echo(format_doctor(doctor_result))
        raise typer.BadParameter("tokenpatch is not ready; fix failed workdir/git/executor-config checks first")
    task = DevTask(
        task_id="task-001",
        title=title or "tokenpatch task",
        goal=goal or requirement,
        context=context or requirement,
        allowed_files=files,
        forbidden_changes=[],
        acceptance_criteria=acceptance or ["The requirement is implemented within the allowed files."],
        validation_commands=[],
        complexity="low",
        recommended_executor="cheap",
        max_attempts=1,
    )
    plan = ProjectPlan(
        project_summary=requirement,
        assumptions=["Host coding assistant supplied a bounded tokenpatch CLI task."],
        risks=[],
        tasks=[task],
    )
    tasks_path = write_plan(config.mmdev_dir, plan)
    typer.echo(f"Wrote {tasks_path}")
    checkpoint_record = None
    if checkpoint:
        checkpoint_record = create_checkpoint(config, f"before-do-{task.task_id}", source="do")
        typer.echo(f"Checkpoint: {checkpoint_record.id}")
    refresh_memory(config)
    client = build_executor_client(config)
    execution = execute_task(task, config, client)
    refresh_memory(config)
    report_path = write_final_report(config.mmdev_dir)
    payload = {
        "ok": True,
        "status": "executed" if not execution.needs_human_input else "needs-human-input",
        "tasks_path": str(tasks_path),
        "checkpoint": checkpoint_record.model_dump() if checkpoint_record is not None else None,
        "execution": execution.model_dump(),
        "report_path": str(report_path),
        "metrics": build_metrics(config.mmdev_dir, window="all").get("summary", {}),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def validate(task_id: str, workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    plan_data = load_plan(config.mmdev_dir)
    task = find_task(plan_data, task_id)
    result = validate_task(task, config)
    path = write_validation_result(config.mmdev_dir, result)
    typer.echo(f"Wrote {path}")
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def review(task_id: str, workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    strong_provider = strong_model_provider_label(config)
    strong_model = config.reviewer_model
    append_run_event(
        config.mmdev_dir,
        {
            "event": "cli.review.start",
            "task_id": task_id,
            "strong_provider": strong_provider,
            "strong_model": strong_model,
        },
    )
    try:
        typer.echo(f"Strong model (review): provider={strong_provider}, model={strong_model or '<unset>'}")
        plan_data = load_plan(config.mmdev_dir)
        task = find_task(plan_data, task_id)
        validation = read_validation_result(config.mmdev_dir, task_id)
        client = build_strong_client(config)
        result = review_task(task, validation, config, client)
        path = write_review_result(config.mmdev_dir, result)
        typer.echo(f"Wrote {path}")
        typer.echo(result.model_dump_json(indent=2))
    except Exception as exc:
        append_run_event(
            config.mmdev_dir,
            {
                "event": "cli.review.finish",
                "outcome": "error",
                "error_type": type(exc).__name__,
                "task_id": task_id,
                "strong_provider": strong_provider,
                "strong_model": strong_model,
            },
        )
        raise
    append_run_event(
        config.mmdev_dir,
        {
            "event": "cli.review.finish",
            "outcome": "success",
            "task_id": task_id,
            "strong_provider": strong_provider,
            "strong_model": strong_model,
        },
    )


@app.command()
def report(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    path = write_final_report(config.mmdev_dir)
    typer.echo(f"Wrote {path}")
    payload = build_metrics(config.mmdev_dir, window="all")
    typer.echo("")
    typer.echo(format_savings_snapshot(payload))


def format_savings_snapshot(metrics_payload: dict) -> str:
    summary = metrics_payload.get("summary", {})
    economics = metrics_payload.get("patch_economics", {})
    lines = [
        "Savings Snapshot:",
        f"- Savings ratio: {float(summary.get('savings_ratio', 0.0)):.2f}%",
        f"- Estimated savings: {float(summary.get('estimated_savings', 0.0)):.6f}",
        f"- tokenpatch actual cost: {float(summary.get('estimated_cost', 0.0)):.6f}",
        f"- All-strong baseline estimate: {float(summary.get('baseline_cost', 0.0)):.6f}",
        f"- Applied patches: {int(economics.get('applied_patches', 0) or 0)}",
        f"- Cost per applied patch: {float(economics.get('cost_per_applied_patch', 0.0)):.6f}",
        f"- Savings per applied patch: {float(economics.get('savings_per_applied_patch', 0.0)):.6f}",
        f"- Savings ratio per applied patch: {float(economics.get('savings_ratio_per_applied_patch', 0.0)):.2f}%",
    ]
    if summary.get("baseline_uses_default"):
        lines.append("- Baseline: default frontier baseline ($5/1M input, $25/1M output)")
    return "\n".join(lines)


@app.command()
def metrics(
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    window: str = typer.Option("all", "--window", help="Metrics window: all or <N>h/<N>d (e.g. 24h, 7d, 30d)."),
    pretty: bool = typer.Option(True, "--pretty/--compact", help="Pretty JSON output."),
    out: Path | None = typer.Option(None, "--out", help="Write metrics JSON to a file path."),
    csv_dir: Path | None = typer.Option(None, "--csv-dir", help="Write grouped metrics CSV files to a directory."),
    csv_prefix: str | None = typer.Option(None, "--csv-prefix", help="Optional prefix for exported CSV filenames."),
    csv_meta: bool = typer.Option(False, "--csv-meta", help="Also write a summary meta CSV (requires --csv-dir)."),
    push: str | None = typer.Option(None, "--push", help="POST metrics JSON to this URL."),
    push_token: str | None = typer.Option(None, "--push-token", help="Optional Bearer token for --push."),
    push_timeout_seconds: int = typer.Option(20, "--push-timeout-seconds", help="HTTP timeout for --push."),
) -> None:
    config = load_config(workdir)
    try:
        payload = build_metrics(config.mmdev_dir, window=window)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if csv_prefix is not None and csv_dir is None:
        raise typer.BadParameter("--csv-prefix requires --csv-dir")
    if csv_meta and csv_dir is None:
        raise typer.BadParameter("--csv-meta requires --csv-dir")
    if csv_dir is not None:
        for path in write_metrics_csvs(payload, csv_dir, prefix=csv_prefix):
            typer.echo(f"Wrote {path}")
        if csv_meta:
            typer.echo(f"Wrote {write_metrics_meta_csv(payload, csv_dir, prefix=csv_prefix)}")
    if push is not None:
        try:
            status_code = push_metrics(payload, push, token=push_token, timeout_seconds=push_timeout_seconds)
        except Exception as exc:
            typer.echo(f"Failed to push metrics: {exc}")
            raise typer.Exit(code=1)
        typer.echo(f"Pushed metrics to {push} (status {status_code})")
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + ("\n" if pretty else ""), encoding="utf-8")
        typer.echo(f"Wrote {out}")
        return
    typer.echo(text)


@app.command("export")
def export_task(
    task_id: str,
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    apply: bool = typer.Option(False, "--apply", help="Apply exported worktree patch to the main worktree."),
) -> None:
    config = load_config(workdir)
    path = export_worktree_diff(config, task_id, apply_to_main=apply)
    typer.echo(f"Wrote {path}")
    if apply:
        typer.echo("Applied patch to main worktree")


@app.command()
def auto(
    requirement: str,
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    isolation: str = typer.Option("none", help="Isolation mode: none or worktree."),
    checkpoint: bool = typer.Option(True, "--checkpoint/--no-checkpoint", help="Create a local recovery checkpoint before running."),
) -> None:
    config = load_config(workdir)
    strong_provider = strong_model_provider_label(config)
    planner_model = config.planner_model
    reviewer_model = config.reviewer_model
    executor_model = executor_model_label(config)
    append_run_event(
        config.mmdev_dir,
        {
            "event": "cli.auto.start",
            "strong_provider": strong_provider,
            "planner_model": planner_model,
            "reviewer_model": reviewer_model,
            "executor_provider": config.executor_provider,
            "executor_model": executor_model,
            "isolation": isolation,
            "requirement_chars": len(requirement),
        },
    )
    try:
        typer.echo(f"Strong model (plan): provider={strong_provider}, model={planner_model or '<unset>'}")
        typer.echo(f"Strong model (review): provider={strong_provider}, model={reviewer_model or '<unset>'}")
        typer.echo(f"Executor model: provider={config.executor_provider}, model={executor_model or '<unset>'}")
        planner_client = build_strong_client(config)
        executor_client = build_executor_client(config)
        reviewer_client = build_strong_client(config)
        if isolation not in {"none", "worktree"}:
            raise typer.BadParameter("isolation must be 'none' or 'worktree'")
        if checkpoint and isolation == "none":
            record = create_checkpoint(config, "before-auto", source="auto")
            typer.echo(f"Checkpoint: {record.id}")
        result = run_auto(requirement, config, planner_client, executor_client, reviewer_client, isolation=isolation)
        typer.echo(result.model_dump_json(indent=2))
    except Exception as exc:
        append_run_event(
            config.mmdev_dir,
            {
                "event": "cli.auto.finish",
                "outcome": "error",
                "error_type": type(exc).__name__,
                "strong_provider": strong_provider,
                "planner_model": planner_model,
                "reviewer_model": reviewer_model,
                "executor_provider": config.executor_provider,
                "executor_model": executor_model,
                "isolation": isolation,
                "requirement_chars": len(requirement),
            },
        )
        raise
    append_run_event(
        config.mmdev_dir,
        {
            "event": "cli.auto.finish",
            "outcome": "success",
            "strong_provider": strong_provider,
            "planner_model": planner_model,
            "reviewer_model": reviewer_model,
            "executor_provider": config.executor_provider,
            "executor_model": executor_model,
            "isolation": isolation,
            "requirement_chars": len(requirement),
        },
    )


@app.command()
def web(
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    host: str = typer.Option("127.0.0.1", help="Host for local web console."),
    port: int = typer.Option(8787, min=1, max=65535, help="Port for local web console."),
) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - import guard
        raise typer.BadParameter("web console requires uvicorn; install with: python -m pip install -e \".[gateway]\"") from exc
    from mmdev.web_console import create_web_app

    config = load_config(workdir)
    typer.echo(f"Starting tokenpatch web console at http://{host}:{port}")
    uvicorn.run(create_web_app(config.workdir), host=host, port=port)


app.command(name="ui")(web)


@app.command()
def setup(
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    host: str = typer.Option("127.0.0.1", help="Host for local setup page."),
    port: int = typer.Option(8787, min=1, max=65535, help="Port for local setup page."),
) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - import guard
        raise typer.BadParameter("setup page requires uvicorn; install with: python -m pip install -e \".[gateway]\"") from exc
    from mmdev.web_console import create_web_app

    config = load_config(workdir)
    url = f"http://{host}:{port}/setup"
    typer.echo(f"Starting tokenpatch setup at {url}")
    typer.echo("Configure executor credentials here; Codex/Claude/Cursor keep using their own strong model settings.")
    uvicorn.run(create_web_app(config.workdir), host=host, port=port)


@app.command()
def mcp(workdir: str | None = typer.Option(None, help="Project root for MCP tools. Defaults to current directory.")) -> None:
    from mmdev.mcp_server import run_stdio_server

    run_stdio_server(default_workdir=workdir)


@app.command("mcp-config")
def mcp_config(
    workdir: str | None = typer.Option(None, help="Project root to place in the generated MCP config."),
    format: str = typer.Option("json", "--format", help="Output format: json or markdown."),
) -> None:
    config = load_config(workdir)
    package_root = Path(__file__).resolve().parents[1]
    launcher_path = default_codex_config_path().parent / "tokenpatch_mcp_launcher.py"
    payload = {
        "mcpServers": {
            "tokenpatch": {
                "command": sys.executable,
                "args": [str(launcher_path)],
            }
        }
    }
    instruction = (
        "When the user starts with tp: or tp：, asks to use tokenpatch, save tokens, run a low-cost executor, "
        "or make a safe AI coding change, prefer tokenpatch_auto. Strip only the tp prefix and preserve the rest "
        "as the requirement. You are the strong planning model: choose a narrow allowed_files list and acceptance "
        "criteria, then let tokenpatch execute safely with its configured cheap executor. Use tokenpatch_plan and "
        "tokenpatch_run_task only when the user explicitly asks for step-by-step control."
    )
    if format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if format != "markdown":
        raise typer.BadParameter("--format must be json or markdown")
    typer.echo("# tokenpatch MCP Config")
    typer.echo("")
    typer.echo("```json")
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    typer.echo("```")
    typer.echo("")
    typer.echo("Recommended agent instruction:")
    typer.echo("")
    typer.echo("```text")
    typer.echo(instruction)
    typer.echo("```")
    typer.echo("")
    typer.echo(f"Launcher package root: {package_root}")
    typer.echo(f"Launcher project workdir: {config.workdir}")


@app.command("install-codex")
def install_codex(
    workdir: str | None = typer.Option(None, help="Project root to expose to Codex through tokenpatch MCP."),
    config_path: Path | None = typer.Option(None, "--config-path", help="Codex config.toml path. Defaults to ~/.codex/config.toml."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the change without writing config.toml."),
    command: str = typer.Option("tokenpatch", "--command", help="Command Codex should run for tokenpatch."),
    dynamic_workdir: bool = typer.Option(False, "--dynamic-workdir/--fixed-workdir", help="Omit --workdir so Codex launches tokenpatch in the active project when possible."),
    python_module: bool = typer.Option(True, "--python-module/--script-command", help="Use the current Python executable with -m mmdev.cli instead of relying on tokenpatch being in PATH."),
    launcher: bool = typer.Option(True, "--launcher/--no-launcher", help="Install a Codex-specific Python launcher that does not depend on PATH, cwd, or editable install."),
) -> None:
    config = load_config(workdir)
    package_root = Path(__file__).resolve().parents[1] if python_module else None
    launcher_path = default_codex_config_path().parent / "tokenpatch_mcp_launcher.py" if launcher and python_module else None
    result = install_codex_mcp(
        project_workdir=None if dynamic_workdir and not launcher else config.workdir,
        package_root=package_root,
        config_path=config_path or default_codex_config_path(),
        dry_run=dry_run,
        command=sys.executable if python_module else command,
        dynamic_workdir=dynamic_workdir,
        python_module=python_module,
        launcher_path=launcher_path,
    )
    typer.echo(f"Codex config: {result.config_path}")
    typer.echo(f"Changed: {result.changed}")
    if result.backup_path is not None:
        typer.echo(f"Backup: {result.backup_path}")
    if result.launcher_path is not None:
        typer.echo(f"Launcher: {result.launcher_path}")
    if result.skill_path is not None:
        typer.echo(f"Skill: {result.skill_path}")
    if result.agents_path is not None:
        typer.echo(f"Instructions: {result.agents_path}")
    if dry_run:
        typer.echo("Dry run; no files were modified.")
    typer.echo("")
    typer.echo(redact_install_snippet(result.snippet).rstrip())
    typer.echo("")
    if result.launcher_path is not None:
        typer.echo("Launcher mode is enabled; Codex does not need tokenpatch in PATH or an editable install.")
    elif dynamic_workdir:
        typer.echo("Dynamic workdir mode is enabled; Codex should launch tokenpatch from the active project directory.")
    typer.echo("")
    typer.echo("For Codex App, open Settings -> MCP Servers -> tokenpatch -> Environment variables.")
    typer.echo("DeepSeek BYOK:")
    typer.echo("  MMDEV_EXECUTOR_PROVIDER=deepseek_byok")
    typer.echo("  DEEPSEEK_API_KEY=your-deepseek-key")
    typer.echo("  DEEPSEEK_BASE_URL=https://api.deepseek.com")
    typer.echo("  DEEPSEEK_EXECUTOR_MODEL=deepseek-v4-pro")
    typer.echo("Hosted gateway:")
    typer.echo("  MMDEV_EXECUTOR_PROVIDER=mmdev_gateway")
    typer.echo("  MMDEV_GATEWAY_URL=https://api.tokenpatch.com")
    typer.echo("  MMDEV_GATEWAY_TOKEN=your-tokenpatch-token")
    if result.skill_path is not None:
        typer.echo("Codex Skill is installed; it tells Codex to call tokenpatch before direct edits.")
    if result.agents_path is not None:
        typer.echo("Codex global instructions are installed; they tell Codex to call tokenpatch before direct edits.")
    typer.echo("Restart Codex App, then ask: tp: implement ... Only modify <files>.")


@app.command("install-cursor")
def install_cursor(
    workdir: str | None = typer.Option(None, help="Project root where .cursor/rules/tokenpatch.mdc should be installed."),
    rules_path: Path | None = typer.Option(None, "--rules-path", help="Custom Cursor rule path. Defaults to <workdir>/.cursor/rules/tokenpatch.mdc."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the rule without writing files."),
    python_command: str = typer.Option(sys.executable, "--python-command", help="Python executable Cursor should use for CLI fallback."),
) -> None:
    config = load_config(workdir)
    result = install_cursor_rules(
        workdir=config.workdir,
        rules_path=rules_path,
        dry_run=dry_run,
        python_command=python_command,
    )
    typer.echo(f"Cursor rule: {result.rules_path}")
    typer.echo(f"Changed: {result.changed}")
    if result.backup_path is not None:
        typer.echo(f"Backup: {result.backup_path}")
    if dry_run:
        typer.echo("Dry run; no files were modified.")
    typer.echo("")
    typer.echo(result.rule_text.rstrip())
    typer.echo("")
    typer.echo("For Cursor App:")
    typer.echo("1. Open this project in Cursor.")
    typer.echo("2. Ensure Agent mode can run terminal commands.")
    typer.echo("3. Ask: tp: implement ... Only modify <files>.")
    typer.echo("")
    typer.echo("Executor credentials can stay in Cursor MCP env settings, process env, or ~/.tokenpatch/config.toml.")


@app.command("install-claude-code")
def install_claude_code_command(
    workdir: str | None = typer.Option(None, help="Project root where .mcp.json and .claude/CLAUDE.md should be installed."),
    mcp_path: Path | None = typer.Option(None, "--mcp-path", help="Custom Claude Code .mcp.json path. Defaults to <workdir>/.mcp.json."),
    memory_path: Path | None = typer.Option(None, "--memory-path", help="Custom Claude Code memory path. Defaults to <workdir>/.claude/CLAUDE.md."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print planned setup without writing files."),
    python_command: str = typer.Option(sys.executable, "--python-command", help="Python executable Claude Code should use for tokenpatch MCP."),
) -> None:
    config = load_config(workdir)
    package_root = Path(__file__).resolve().parents[1]
    result = install_claude_code(
        workdir=config.workdir,
        package_root=package_root,
        mcp_path=mcp_path,
        memory_path=memory_path,
        dry_run=dry_run,
        python_command=python_command,
    )
    typer.echo(f"Claude Code MCP config: {result.mcp_path} (changed={result.mcp_changed})")
    typer.echo(f"Claude Code memory: {result.memory_path} (changed={result.memory_changed})")
    typer.echo(f"Claude Code launcher: {result.launcher_path}")
    if result.mcp_backup_path is not None:
        typer.echo(f"MCP backup: {result.mcp_backup_path}")
    if result.memory_backup_path is not None:
        typer.echo(f"Memory backup: {result.memory_backup_path}")
    if dry_run:
        typer.echo("Dry run; no files were modified.")
    typer.echo("")
    typer.echo("Claude Code can now use tokenpatch in this project.")
    typer.echo("Ask: tp: implement ... Only modify <files>.")
    typer.echo("Executor credentials can stay in Claude Code MCP env, process env, or ~/.tokenpatch/config.toml.")


@app.command("bootstrap")
def bootstrap(
    workdir: str | None = typer.Option(None, help="Project root to prepare for tokenpatch."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show planned setup without writing files."),
    install_codex_app: bool = typer.Option(True, "--codex/--no-codex", help="Install Codex App MCP, Skill, and global instructions."),
    install_cursor_app: bool = typer.Option(True, "--cursor/--no-cursor", help="Install Cursor project rule."),
    install_claude_code_app: bool = typer.Option(True, "--claude-code/--no-claude-code", help="Install Claude Code project MCP config and memory."),
    init_project: bool = typer.Option(True, "--init/--no-init", help="Initialize .mmdev in the project."),
    codex_config_path: Path | None = typer.Option(None, "--codex-config-path", help="Codex config.toml path. Defaults to ~/.codex/config.toml."),
    cursor_rules_path: Path | None = typer.Option(None, "--cursor-rules-path", help="Cursor rule path. Defaults to <workdir>/.cursor/rules/tokenpatch.mdc."),
    claude_mcp_path: Path | None = typer.Option(None, "--claude-mcp-path", help="Claude Code .mcp.json path. Defaults to <workdir>/.mcp.json."),
    claude_memory_path: Path | None = typer.Option(None, "--claude-memory-path", help="Claude Code memory path. Defaults to <workdir>/.claude/CLAUDE.md."),
    python_command: str = typer.Option(sys.executable, "--python-command", help="Python executable apps should use for tokenpatch CLI/MCP fallback."),
) -> None:
    config = load_config(workdir)
    package_root = Path(__file__).resolve().parents[1]
    executor_detail, executor_ready = executor_config_summary(config)

    typer.echo(f"tokenpatch bootstrap for {config.workdir}")
    typer.echo(f"Executor config: {executor_detail}")
    if not executor_ready:
        typer.echo("Executor is not ready yet. Configure DeepSeek BYOK in the app MCP env, process env, or ~/.tokenpatch/config.toml.")
    typer.echo("")

    if init_project:
        if dry_run:
            typer.echo(f"Would initialize: {config.mmdev_dir}")
        else:
            mmdev_dir = init_state_dir(str(config.workdir))
            typer.echo(f"Initialized: {mmdev_dir}")

    if install_codex_app:
        target_codex_config = codex_config_path or default_codex_config_path()
        launcher_path = target_codex_config.parent / "tokenpatch_mcp_launcher.py"
        codex_result = install_codex_mcp(
            project_workdir=config.workdir,
            package_root=package_root,
            config_path=target_codex_config,
            dry_run=dry_run,
            command=python_command,
            dynamic_workdir=False,
            python_module=True,
            launcher_path=launcher_path,
        )
        typer.echo(f"Codex config: {codex_result.config_path} (changed={codex_result.changed})")
        if codex_result.launcher_path is not None:
            typer.echo(f"Codex launcher: {codex_result.launcher_path}")
        if codex_result.skill_path is not None:
            typer.echo(f"Codex skill: {codex_result.skill_path}")
        if codex_result.agents_path is not None:
            typer.echo(f"Codex instructions: {codex_result.agents_path}")
        if codex_result.backup_path is not None:
            typer.echo(f"Codex backup: {codex_result.backup_path}")

    if install_cursor_app:
        cursor_result = install_cursor_rules(
            workdir=config.workdir,
            rules_path=cursor_rules_path,
            dry_run=dry_run,
            python_command=python_command,
        )
        typer.echo(f"Cursor rule: {cursor_result.rules_path} (changed={cursor_result.changed})")
        if cursor_result.backup_path is not None:
            typer.echo(f"Cursor backup: {cursor_result.backup_path}")

    if install_claude_code_app:
        claude_result = install_claude_code(
            workdir=config.workdir,
            package_root=package_root,
            mcp_path=claude_mcp_path,
            memory_path=claude_memory_path,
            dry_run=dry_run,
            python_command=python_command,
        )
        typer.echo(f"Claude Code MCP config: {claude_result.mcp_path} (changed={claude_result.mcp_changed})")
        typer.echo(f"Claude Code memory: {claude_result.memory_path} (changed={claude_result.memory_changed})")
        typer.echo(f"Claude Code launcher: {claude_result.launcher_path}")
        if claude_result.mcp_backup_path is not None:
            typer.echo(f"Claude Code MCP backup: {claude_result.mcp_backup_path}")
        if claude_result.memory_backup_path is not None:
            typer.echo(f"Claude Code memory backup: {claude_result.memory_backup_path}")

    if dry_run:
        typer.echo("Dry run; no files were modified.")
    typer.echo("")
    typer.echo("Restart/open your coding app. You can keep using Codex, Cursor, or Claude Code as your strong model.")
    typer.echo("If tokenpatch MCP tools are not visible, the installed app guidance will use tokenpatch CLI fallback.")
    typer.echo("")
    typer.echo("Smoke test:")
    typer.echo("tp: modify the page title to TokenPatch Bootstrap Test. Only modify index.html.")
    typer.echo("")
    typer.echo("For metrics/report:")
    typer.echo("tp: show metrics and report. Do not modify source files.")


@checkpoint_app.command("create")
def checkpoint_create(
    label: str = typer.Argument("manual"),
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
) -> None:
    config = load_config(workdir)
    record = create_checkpoint(config, label, source="manual")
    typer.echo(record.model_dump_json(indent=2))


@checkpoint_app.command("list")
def checkpoint_list(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    records = list_checkpoints(config.mmdev_dir)
    for record in records:
        typer.echo(f"{record.id}\t{record.created_at}\t{record.source}\t{record.label}\t{record.status_summary}")


@checkpoint_app.command("diff")
def checkpoint_show_diff(
    checkpoint_id: str,
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
) -> None:
    config = load_config(workdir)
    typer.echo(checkpoint_diff(config.mmdev_dir, checkpoint_id))


@checkpoint_app.command("restore")
def checkpoint_restore(
    checkpoint_id: str,
    workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory."),
    yes: bool = typer.Option(False, "--yes", help="Actually restore tracked files. Without this flag restore is dry-run."),
    allow_head_mismatch: bool = typer.Option(False, "--allow-head-mismatch", help="Restore even if current HEAD differs from checkpoint base."),
) -> None:
    config = load_config(workdir)
    result = restore_checkpoint(config, checkpoint_id, yes=yes, allow_head_mismatch=allow_head_mismatch)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@memory_app.command("refresh")
def memory_refresh(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    memory = refresh_memory(config)
    typer.echo(f"Wrote {memory_markdown_path(config.mmdev_dir)}")
    typer.echo(memory.model_dump_json(indent=2))


@memory_app.command("show")
def memory_show(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    memory = load_memory(config.mmdev_dir)
    if memory is None:
        raise typer.BadParameter("missing project memory; run tokenpatch memory refresh")
    typer.echo(render_memory_markdown(memory))


if __name__ == "__main__":
    app()
