# Review Rules

Reviewer output is a `ReviewResult`:

```json
{
  "task_id": "task-001",
  "approved": true,
  "findings": [
    {
      "severity": "low|medium|high",
      "file": "relative/path.ext",
      "line": 1,
      "message": "string"
    }
  ],
  "missing_acceptance_criteria": ["string"],
  "recommended_next_action": "approve|retry-cheap|escalate-strong|ask-human"
}
```

Interpretation:

- `approve`: task can be accepted if validation also passed.
- `retry-cheap`: retry only if the task remains low risk and the failure is local.
- `escalate-strong`: stop cheap execution and use strong-model analysis.
- `ask-human`: stop and ask the user for a decision.

Prioritize behavior, risk, acceptance criteria, and missing tests over style.

