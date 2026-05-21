from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable

from mmdev.checkpoint import checkpoint_diff, create_checkpoint, list_checkpoints, restore_checkpoint
from mmdev.config import init_state_dir, load_config
from mmdev.doctor import format_doctor, run_doctor
from mmdev.executor import execute_task, find_task, load_plan
from mmdev.git_utils import git_status_short
from mmdev.memory import load_memory, refresh_memory, render_memory_markdown
from mmdev.metrics import build_metrics
from mmdev.planner import create_plan, write_plan
from mmdev.reporter import generate_report, write_final_report
from mmdev.schemas import DevTask, ProjectPlan
from mmdev.state import task_statuses


JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], str | None], Any]


def run_stdio_server(default_workdir: str | None = None, *, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
    reader = stdin or sys.stdin.buffer
    writer = stdout or sys.stdout.buffer
    while True:
        message = read_message(reader)
        if message is None:
            break
        response = handle_message(message, default_workdir)
        if response is not None:
            write_message(writer, response)


def handle_message(message: dict[str, Any], default_workdir: str | None = None) -> dict[str, Any] | None:
    if "id" not in message:
        return None
    request_id = message.get("id")
    try:
        method = str(message.get("method", ""))
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "initialize":
            return success(request_id, initialize_result())
        if method == "tools/list":
            return success(request_id, {"tools": [tool_to_mcp(spec) for spec in tools()]})
        if method == "resources/list":
            return success(request_id, {"resources": []})
        if method == "resources/templates/list":
            return success(request_id, {"resourceTemplates": []})
        if method == "tools/call":
            name = str(params.get("name", ""))
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            return success(request_id, call_tool(name, arguments, default_workdir))
        if method == "ping":
            return success(request_id, {})
        return error(request_id, -32601, f"method not found: {method}")
    except Exception as exc:
        return error(request_id, -32000, str(exc), {"traceback": traceback.format_exc(limit=5)})


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "tokenpatch", "version": "0.1.0"},
    }


def tools() -> list[ToolSpec]:
    workdir_prop = {"type": "string", "description": "Project root. Defaults to tokenpatch mcp --workdir or current directory."}
    return [
        ToolSpec(
            "tokenpatch",
            "Use this first when the user starts with 'tp:' or 'tp：', says 'use tokenpatch', asks to save tokens, or asks tokenpatch to implement a bounded coding change. For tp-prefixed requests, strip only the prefix and preserve the rest as the requirement. If allowed_files are provided, tokenpatch runs the configured low-cost executor, checks patch boundaries, and returns usage/cost metrics. If allowed_files are omitted, it asks for a safe file scope instead of editing.",
            schema(
                {
                    "requirement": {"type": "string", "description": "User's coding requirement."},
                    "title": {"type": "string", "description": "Optional short task title."},
                    "goal": {"type": "string", "description": "Optional concrete implementation goal. Defaults to requirement."},
                    "allowed_files": {"type": "array", "items": {"type": "string"}, "default": [], "description": "Relative files tokenpatch may modify. Required for execution."},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "default": [], "description": "Checks the change must satisfy. Defaults to a simple requirement check."},
                    "forbidden_changes": {"type": "array", "items": {"type": "string"}, "default": []},
                    "validation_commands": {"type": "array", "items": {"type": "string"}, "default": []},
                    "context": {"type": "string", "default": ""},
                    "mode": {"type": "string", "default": "safe"},
                    "workdir": workdir_prop,
                },
                required=["requirement"],
            ),
            tool_tokenpatch,
        ),
        ToolSpec("tokenpatch_init", "Initialize .mmdev local state.", schema({"workdir": workdir_prop}), tool_init),
        ToolSpec("tokenpatch_status", "Show initialization, tasks, git status, and task statuses.", schema({"workdir": workdir_prop}), tool_status),
        ToolSpec(
            "tokenpatch_doctor",
            "Run local configuration checks without calling model APIs.",
            schema({"workdir": workdir_prop}),
            tool_doctor,
        ),
        ToolSpec(
            "tokenpatch_checkpoint_create",
            "Advanced: create a local recovery checkpoint before risky AI edits.",
            schema({"label": {"type": "string", "default": "manual"}, "workdir": workdir_prop}),
            tool_checkpoint_create,
        ),
        ToolSpec("tokenpatch_checkpoint_list", "Advanced: list local recovery checkpoints.", schema({"workdir": workdir_prop}), tool_checkpoint_list),
        ToolSpec(
            "tokenpatch_checkpoint_diff",
            "Read the tracked-file patch saved in a restore point.",
            schema({"checkpoint_id": {"type": "string"}, "workdir": workdir_prop}, required=["checkpoint_id"]),
            tool_checkpoint_diff,
        ),
        ToolSpec(
            "tokenpatch_checkpoint_restore",
            "Restore tracked files from a restore point. Defaults to dry-run unless yes=true.",
            schema(
                {
                    "checkpoint_id": {"type": "string"},
                    "yes": {"type": "boolean", "default": False},
                    "allow_head_mismatch": {"type": "boolean", "default": False},
                    "workdir": workdir_prop,
                },
                required=["checkpoint_id"],
            ),
            tool_checkpoint_restore,
        ),
        ToolSpec("tokenpatch_memory_refresh", "Advanced: refresh compact local project context without model calls.", schema({"workdir": workdir_prop}), tool_memory_refresh),
        ToolSpec("tokenpatch_memory_show", "Advanced: show compact local project context.", schema({"workdir": workdir_prop}), tool_memory_show),
        ToolSpec(
            "tokenpatch_auto",
            "Use this when the user starts with 'tp:' or 'tp：', or asks tokenpatch to do a coding task cheaply. The host coding assistant supplies allowed_files and acceptance criteria; tokenpatch runs the cheap executor, checks the patch, and reports usage/cost metrics.",
            schema(
                {
                    "requirement": {"type": "string", "description": "User's coding requirement."},
                    "title": {"type": "string", "description": "Short task title."},
                    "goal": {"type": "string", "description": "Concrete implementation goal for the executor."},
                    "allowed_files": {"type": "array", "items": {"type": "string"}, "description": "Relative files the executor may modify."},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "description": "Checks the change must satisfy."},
                    "forbidden_changes": {"type": "array", "items": {"type": "string"}, "default": []},
                    "validation_commands": {"type": "array", "items": {"type": "string"}, "default": []},
                    "context": {"type": "string", "default": ""},
                    "mode": {"type": "string", "default": "safe"},
                    "workdir": workdir_prop,
                },
                required=["requirement", "goal", "allowed_files", "acceptance_criteria"],
            ),
            tool_auto,
        ),
        ToolSpec(
            "tokenpatch_plan",
            "Use the configured strong model to create .mmdev/tasks.json from a requirement.",
            schema({"requirement": {"type": "string"}, "workdir": workdir_prop}, required=["requirement"]),
            tool_plan,
        ),
        ToolSpec(
            "tokenpatch_run_task",
            "Run a low+cheap task through the configured low-cost executor and report usage/cost metrics.",
            schema(
                {
                    "task_id": {"type": "string"},
                    "checkpoint": {"type": "boolean", "default": True},
                    "workdir": workdir_prop,
                },
                required=["task_id"],
            ),
            tool_run_task,
        ),
        ToolSpec("tokenpatch_report", "Generate and return the final tokenpatch report.", schema({"workdir": workdir_prop}), tool_report),
        ToolSpec("tokenpatch_metrics", "Return tokenpatch metrics JSON.", schema({"window": {"type": "string", "default": "all"}, "workdir": workdir_prop}), tool_metrics),
    ]


def schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def tool_to_mcp(spec: ToolSpec) -> dict[str, Any]:
    return {"name": spec.name, "description": spec.description, "inputSchema": spec.input_schema}


def call_tool(name: str, arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    for spec in tools():
        if spec.name == name:
            result = spec.handler(arguments, default_workdir)
            return {"content": [{"type": "text", "text": tool_text(result)}]}
    return {"isError": True, "content": [{"type": "text", "text": f"unknown tool: {name}"}]}


def tool_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2)


def config_from_args(arguments: dict[str, Any], default_workdir: str | None):
    return load_config(arguments.get("workdir") or default_workdir)


def tool_init(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    mmdev_dir = init_state_dir(arguments.get("workdir") or default_workdir)
    return {"initialized": str(mmdev_dir)}


def tool_status(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    return {
        "workdir": str(config.workdir),
        "initialized": config.mmdev_dir.exists(),
        "executor_provider": config.normalized_executor_provider,
        "executor_notes": config.executor_provider_notes,
        "executor_model": config.executor_model,
        "tasks": (config.mmdev_dir / "tasks.json").exists(),
        "git": git_status_short(config.workdir, 10),
        "task_statuses": task_statuses(config.mmdev_dir),
    }


def tool_doctor(arguments: dict[str, Any], default_workdir: str | None) -> str:
    config = config_from_args(arguments, default_workdir)
    return format_doctor(run_doctor(config, check_api=False))


def tool_checkpoint_create(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    label = str(arguments.get("label") or "manual")
    return create_checkpoint(config, label, source="mcp").model_dump()


def tool_checkpoint_list(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    return {"checkpoints": [record.model_dump() for record in list_checkpoints(config.mmdev_dir)]}


def tool_checkpoint_diff(arguments: dict[str, Any], default_workdir: str | None) -> str:
    config = config_from_args(arguments, default_workdir)
    return checkpoint_diff(config.mmdev_dir, str(arguments["checkpoint_id"]))


def tool_checkpoint_restore(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    return restore_checkpoint(
        config,
        str(arguments["checkpoint_id"]),
        yes=bool(arguments.get("yes", False)),
        allow_head_mismatch=bool(arguments.get("allow_head_mismatch", False)),
    )


def tool_memory_refresh(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    return refresh_memory(config).model_dump()


def tool_memory_show(arguments: dict[str, Any], default_workdir: str | None) -> str:
    config = config_from_args(arguments, default_workdir)
    memory = load_memory(config.mmdev_dir)
    if memory is None:
        return "Local project context is missing. Run tokenpatch_memory_refresh first."
    return render_memory_markdown(memory)


def tool_tokenpatch(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    allowed_files = [str(file_name) for file_name in arguments.get("allowed_files") or []]
    requirement = str(arguments["requirement"])
    if not allowed_files:
        return {
            "ok": False,
            "status": "needs-file-scope",
            "message": (
                "tokenpatch is ready, but execution requires an explicit allowed_files list. "
                "Pick the smallest relative file list for this task, then call tokenpatch again."
            ),
            "example_arguments": {
                "requirement": requirement,
                "goal": str(arguments.get("goal") or requirement),
                "allowed_files": ["relative/path/to/file.ext"],
                "acceptance_criteria": list(arguments.get("acceptance_criteria") or ["The requirement is implemented."]),
            },
        }
    next_arguments = dict(arguments)
    next_arguments["goal"] = str(arguments.get("goal") or requirement)
    next_arguments["allowed_files"] = allowed_files
    if not next_arguments.get("acceptance_criteria"):
        next_arguments["acceptance_criteria"] = ["The requirement is implemented within the allowed files."]
    return tool_auto(next_arguments, default_workdir)


def tool_plan(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    client = build_strong_client(config)
    plan = create_plan(str(arguments["requirement"]), config, client)
    path = write_plan(config.mmdev_dir, plan)
    return {"tasks_path": str(path), "plan": plan.model_dump()}


def tool_auto(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    init_state_dir(config.workdir)
    doctor = run_doctor(config, check_api=False)
    blocking = [
        check.model_dump()
        for check in doctor.checks
        if check.name in {"workdir", "git", "executor-config"} and check.status == "fail"
    ]
    if blocking:
        return {"ok": False, "status": "blocked", "error": "tokenpatch is not ready to run.", "checks": blocking}

    task = DevTask(
        task_id="task-001",
        title=str(arguments.get("title") or "tokenpatch task"),
        goal=str(arguments["goal"]),
        context=str(arguments.get("context") or arguments["requirement"]),
        allowed_files=list(arguments["allowed_files"]),
        forbidden_changes=list(arguments.get("forbidden_changes") or []),
        acceptance_criteria=list(arguments["acceptance_criteria"]),
        validation_commands=list(arguments.get("validation_commands") or []),
        complexity="low",
        recommended_executor="cheap",
        max_attempts=1,
    )
    plan = ProjectPlan(
        project_summary=str(arguments["requirement"]),
        assumptions=["Host coding assistant supplied the structured task plan."],
        risks=[],
        tasks=[task],
    )
    tasks_path = write_plan(config.mmdev_dir, plan)
    checkpoint = create_checkpoint(config, f"before-auto-{task.task_id}", source="mcp-auto").model_dump()
    memory = refresh_memory(config)
    client = build_executor_client(config)
    try:
        execution = execute_task(task, config, client)
    except Exception as exc:
        return {
            "ok": False,
            "status": "execution-failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "tasks_path": str(tasks_path),
            "checkpoint": checkpoint,
            "memory_generated_at": memory.generated_at,
            "task_statuses": task_statuses(config.mmdev_dir),
            "metrics": build_metrics(config.mmdev_dir, window="all").get("summary", {}),
        }

    memory = refresh_memory(config)
    report_path = write_final_report(config.mmdev_dir)
    return {
        "ok": True,
        "status": "executed" if not execution.needs_human_input else "needs-human-input",
        "tasks_path": str(tasks_path),
        "checkpoint": checkpoint,
        "execution": execution.model_dump(),
        "memory_generated_at": memory.generated_at,
        "report_path": str(report_path),
        "task_statuses": task_statuses(config.mmdev_dir),
        "metrics": build_metrics(config.mmdev_dir, window="all").get("summary", {}),
    }


def tool_run_task(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    task_id = str(arguments["task_id"])
    task = find_task(load_plan(config.mmdev_dir), task_id)
    checkpoint = None
    if bool(arguments.get("checkpoint", True)):
        checkpoint = create_checkpoint(config, f"before-run-{task_id}", source="mcp-run").model_dump()
    client = build_executor_client(config)
    try:
        result = execute_task(task, config, client)
    except Exception as exc:
        return {
            "ok": False,
            "checkpoint": checkpoint,
            "task_id": task_id,
            "status": "execution-failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "task_statuses": task_statuses(config.mmdev_dir),
        }
    return {
        "ok": True,
        "checkpoint": checkpoint,
        "status": "executed" if not result.needs_human_input else "needs-human-input",
        "execution": result.model_dump(),
        "task_statuses": task_statuses(config.mmdev_dir),
    }


def tool_report(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    path = write_final_report(config.mmdev_dir)
    metrics = build_metrics(config.mmdev_dir, window="all")
    summary = metrics.get("summary", {})
    economics = metrics.get("patch_economics", {})
    return {
        "report_path": str(path),
        "savings_snapshot": {
            "savings_ratio": summary.get("savings_ratio", 0.0),
            "estimated_savings": summary.get("estimated_savings", 0.0),
            "actual_cost": summary.get("estimated_cost", 0.0),
            "baseline_cost": summary.get("baseline_cost", 0.0),
            "applied_patches": economics.get("applied_patches", 0),
            "cost_per_applied_patch": economics.get("cost_per_applied_patch", 0.0),
            "savings_per_applied_patch": economics.get("savings_per_applied_patch", 0.0),
            "savings_ratio_per_applied_patch": economics.get("savings_ratio_per_applied_patch", 0.0),
        },
        "patch_economics": economics,
        "report_text": generate_report(config.mmdev_dir),
    }


def tool_metrics(arguments: dict[str, Any], default_workdir: str | None) -> dict[str, Any]:
    config = config_from_args(arguments, default_workdir)
    return build_metrics(config.mmdev_dir, window=str(arguments.get("window") or "all"))


def build_strong_client(config):
    from mmdev.models.claude_client import ClaudeMessagesClient
    from mmdev.models.openai_client import OpenAIChatCompletionsClient, OpenAIResponsesClient

    provider = config.normalized_strong_model_provider
    if provider == "openai":
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY or openai_api_key is required")
        mode = (config.openai_api_mode or "responses").strip().lower()
        if mode == "responses":
            return OpenAIResponsesClient(config.openai_api_key, config.openai_base_url)
        if mode == "chat_completions":
            return OpenAIChatCompletionsClient(config.openai_api_key, config.openai_base_url)
        raise ValueError("OPENAI_API_MODE/openai_api_mode must be 'responses' or 'chat_completions'")
    if provider == "claude":
        if not config.claude_api_key:
            raise ValueError("CLAUDE_API_KEY or claude_api_key is required")
        return ClaudeMessagesClient(config.claude_api_key, config.claude_base_url)
    raise ValueError("strong_model_provider must be 'openai' or 'claude'")


def build_executor_client(config):
    from mmdev.models.deepseek_client import DeepSeekChatClient
    from mmdev.models.gateway_client import MMDevGatewayClient

    if config.normalized_executor_provider == "deepseek_byok":
        if not config.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY or deepseek_api_key is required")
        if not config.deepseek_base_url:
            raise ValueError("DEEPSEEK_BASE_URL or deepseek_base_url is required")
        return DeepSeekChatClient(config.deepseek_api_key, config.deepseek_base_url)
    if config.normalized_executor_provider == "mmdev_gateway":
        if not config.mmdev_gateway_url:
            raise ValueError("MMDEV_GATEWAY_URL or mmdev_gateway_url is required")
        if not config.mmdev_gateway_token:
            raise ValueError("MMDEV_GATEWAY_TOKEN or mmdev_gateway_token is required")
        return MMDevGatewayClient(
            config.mmdev_gateway_url,
            config.mmdev_gateway_token,
            country=config.mmdev_gateway_country,
            entity=config.mmdev_gateway_entity,
        )
    raise ValueError("executor_provider must be 'deepseek_byok' or 'mmdev_gateway'")


def success(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def read_message(reader: BinaryIO) -> dict[str, Any] | None:
    headers: list[bytes] = []
    while True:
        line = reader.readline()
        if line == b"":
            return None
        if line in {b"\r\n", b"\n"}:
            break
        headers.append(line.strip())
    content_length = None
    for header in headers:
        name, _, value = header.partition(b":")
        if name.lower() == b"content-length":
            content_length = int(value.strip())
            break
    if content_length is None:
        raise ValueError("missing Content-Length header")
    body = reader.read(content_length)
    if len(body) != content_length:
        raise ValueError("incomplete JSON-RPC body")
    return json.loads(body.decode("utf-8"))


def write_message(writer: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    writer.flush()
