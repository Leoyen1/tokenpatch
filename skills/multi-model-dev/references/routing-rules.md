# Routing Rules

Planner and reviewer use strong models.

The cheap executor is appropriate for:

- single-file or small multi-file edits
- explicit CRUD changes
- small UI edits with clear files
- tests
- docs
- repetitive code generation

Escalate to strong model or user confirmation for:

- architecture changes
- auth, permissions, or security
- migrations or persistent data changes
- concurrency or consistency
- unclear requirements
- hidden cross-module bugs
- repeated cheap-executor failure

MVP execution rule:

- `mmdev run` should only execute tasks with `complexity = low` and `recommended_executor = cheap`.
- Use `--isolation worktree` for real projects when the repository has at least one commit and the current worktree should not be modified directly.
- Hosted gateway mode should only receive structured mmdev executor tasks, not arbitrary chat prompts or OpenAI-compatible free-form traffic.
