# Example Todo App

Small Python project for tokenpatch end-to-end demos.

## Run tests

```bash
python -m pytest
```

## CLI demo sequence

```bash
tokenpatch init --workdir examples/todo-app
tokenpatch auto --workdir examples/todo-app "为 todo 列表增加按 completed 状态筛选"
tokenpatch report --workdir examples/todo-app
```

## Web demo sequence (recommended for first-time users)

```bash
tokenpatch web --workdir examples/todo-app
```

Open [http://127.0.0.1:8787/onboarding](http://127.0.0.1:8787/onboarding) and confirm the checklist first.

Then open [http://127.0.0.1:8787](http://127.0.0.1:8787):

1. Paste requirement text
2. Click `Plan Tasks`
3. Click `Run task-001`
4. Click `Generate Report`

## Offline scripted demo

Run from repository root:

```bash
python examples/todo-app/scripts/run_fake_demo.py
```

It copies this example into `.mmdev-demo/todo-app`, initializes Git, runs fake planner/executor/reviewer workflow with worktree isolation, exports patch, and writes final report. No API keys required.

## Expected planner shape

- one low-complexity task
- `allowed_files`: `todo_app/todos.py`, `tests/test_todos.py`
- validation command: `python -m pytest`
