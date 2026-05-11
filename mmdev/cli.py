from __future__ import annotations

import json
from pathlib import Path

import typer

from mmdev.config import init_state_dir, load_config
from mmdev.doctor import format_doctor, run_doctor
from mmdev.executor import execute_task, find_task, load_plan
from mmdev.git_utils import git_status_short
from mmdev.isolation import export_worktree_diff, prepare_worktree
from mmdev.models.claude_client import ClaudeMessagesClient
from mmdev.models.deepseek_client import DeepSeekChatClient
from mmdev.models.gateway_client import MMDevGatewayClient
from mmdev.models.openai_client import OpenAIResponsesClient
from mmdev.metrics import build_metrics, push_metrics, write_metrics_csvs, write_metrics_meta_csv
from mmdev.planner import create_plan, write_plan
from mmdev.reporter import write_final_report
from mmdev.reviewer import review_task, write_review_result
from mmdev.run_events import append_run_event
from mmdev.state import task_statuses
from mmdev.validator import read_validation_result, validate_task, write_validation_result
from mmdev.workflow import run_auto


app = typer.Typer(no_args_is_help=True)


def strong_model_provider_label(config) -> str:
    return config.normalized_strong_model_provider


def executor_model_label(config) -> str:
    if config.executor_provider == "mmdev_gateway":
        return config.mmdev_gateway_executor_model
    return config.deepseek_executor_model


def build_strong_client(config):
    provider = config.normalized_strong_model_provider
    if provider == "openai":
        if not config.openai_api_key:
            raise typer.BadParameter("OPENAI_API_KEY or openai_api_key is required")
        return OpenAIResponsesClient(config.openai_api_key)
    if provider == "claude":
        if not config.claude_api_key:
            raise typer.BadParameter("CLAUDE_API_KEY or claude_api_key is required")
        return ClaudeMessagesClient(config.claude_api_key, config.claude_base_url)
    raise typer.BadParameter("strong_model_provider must be 'openai' or 'claude'")


def build_executor_client(config):
    if config.executor_provider == "deepseek_byok":
        if not config.deepseek_api_key:
            raise typer.BadParameter("DEEPSEEK_API_KEY or deepseek_api_key is required")
        if not config.deepseek_base_url:
            raise typer.BadParameter("DEEPSEEK_BASE_URL or deepseek_base_url is required")
        return DeepSeekChatClient(config.deepseek_api_key, config.deepseek_base_url)
    if config.executor_provider == "mmdev_gateway":
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


@app.command()
def status(workdir: str | None = typer.Option(None, help="Project root. Defaults to current directory.")) -> None:
    config = load_config(workdir)
    typer.echo(f"Workdir: {config.workdir}")
    typer.echo(f"Initialized: {config.mmdev_dir.exists()}")
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
) -> None:
    config = load_config(workdir)
    plan_data = load_plan(config.mmdev_dir)
    task = find_task(plan_data, task_id)
    client = build_executor_client(config)
    active_config = prepare_worktree(config, task_id) if isolation == "worktree" else config
    if isolation not in {"none", "worktree"}:
        raise typer.BadParameter("isolation must be 'none' or 'worktree'")
    result = execute_task(task, active_config, client)
    typer.echo(result.model_dump_json(indent=2))


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


if __name__ == "__main__":
    app()
