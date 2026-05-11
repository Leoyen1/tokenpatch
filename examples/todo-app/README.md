# Example Todo App

Small Python project for testing tokenpatch end to end.

## Run tests

```bash
python -m pytest
```

## Suggested tokenpatch demo task

```bash
tokenpatch auto --workdir examples/todo-app "为 todo 列表增加按 completed 状态筛选"
```

## Offline scripted demo

Run the fake-model demo from the repository root:

```bash
python examples/todo-app/scripts/run_fake_demo.py
```

It copies this example into `.mmdev-demo/todo-app`, initializes Git, runs the full worktree-isolated workflow with fake planner/executor/reviewer clients, exports the approved patch, and writes a final report. It does not require API keys.

For safer demos, initialize Git and use worktree isolation:

```bash
git init
git add .
git commit -m "initial todo app"
tokenpatch auto --isolation worktree "为 todo 列表增加按 completed 状态筛选"
tokenpatch export task-001
```

Expected planner shape:

- one low-complexity task
- `allowed_files` should include `todo_app/todos.py` and `tests/test_todos.py`
- validation command should be `python -m pytest`

The current app already supports listing all todos. The intended demo change is to add an optional `completed` filter to `list_todos`.

If you want to test later commands without calling the planner model, copy `tasks.example.json` to `.mmdev/tasks.json` after `tokenpatch init`, then run:

```bash
tokenpatch run task-001
tokenpatch validate task-001
tokenpatch review task-001
tokenpatch report
```
