<!--
Optional task brief. Insert it into the Feature's
.sdlc-v1/context/<feature-id>.engineering.md or pass it to a sub-agent.
It is not a separate runtime file and does not hold progress.
-->

## Task: <task-id> — <title>

```yaml
feature_id: <feature-id>
task_id: <task-id>
branch: <branch>
depends_on: [<task-id>]
write_scope: [<repository-relative paths>]
```

### Product criteria

- <Criterion from the referenced product context>

### Engineering intent

<What this task changes and why.>

### Completion conditions

- <Observable code or behavior condition>
- <Required test or check>

### Constraints

- Do not modify files outside `write_scope` without coordinating with the Feature owner.
- Do not edit `.sdlc-v1/state.json` directly; the Feature owner updates Task status through `lifecycle_state.py`.
- Record durable design decisions in the Feature engineering context.

### Result

```yaml
changed_files: []
commands_run: []
result: <done | blocked>
notes: <summary>
```
