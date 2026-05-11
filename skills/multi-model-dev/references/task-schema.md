# Task Schema

`mmdev plan` writes `.mmdev/tasks.json` as a `ProjectPlan`.

## ProjectPlan

Required shape:

```json
{
  "project_summary": "string",
  "assumptions": ["string"],
  "risks": ["string"],
  "tasks": []
}
```

## DevTask

Each task must include:

```json
{
  "task_id": "task-001",
  "title": "string",
  "goal": "string",
  "context": "string",
  "allowed_files": ["relative/path.ext"],
  "forbidden_changes": ["string"],
  "acceptance_criteria": ["string"],
  "validation_commands": ["python -m pytest"],
  "complexity": "low|medium|high",
  "recommended_executor": "cheap|strong",
  "max_attempts": 2
}
```

Rules:

- `allowed_files` must be relative project paths.
- Do not allow `..` or absolute paths.
- `acceptance_criteria` must be behavior-oriented and verifiable.
- `validation_commands` must be known local commands, not open-ended shell operations.

Cost reporting is configured separately in `.mmdev/config.toml` with per-1M-token pricing fields for planner, reviewer, executor, and optional all-strong baseline comparison.
