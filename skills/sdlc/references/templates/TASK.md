<!--
Optional stage or Task brief. Insert it into the Feature's
.sdlc-v1/context/<feature-id>.engineering.md or pass it to a sub-agent.
It is not a separate runtime file and does not hold progress.
-->

## Task: <task-id> — <title>

```yaml
feature_id: <feature-id>
task_id: <task-id>
stage: <build>
branch: <branch>
depends_on: [<task-id>]
write_scope: [<repository-relative paths>]
context_refs: [<project/product/engineering paths>]
expected_artifacts: [<paths or observable outcomes>]
completion_conditions: [<checks>]
allowed_transitions:
  - operation: set-task-status
    required_arguments: [feature-id, task-id, status]
    optional_arguments: [at]
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
- In orchestrated mode, do not edit `.sdlc-v1/state.json` or run lifecycle mutations; request them in the result for the main Agent.
- Record durable design decisions in the Feature engineering context.

### Result

```yaml
stage: <stage>
status: <completed | blocked | failed>
artifacts:
  changed_files: []
evidence:
  commands: []
context_updates:
  product: []
  feature: []
  project_candidates: []
questions: []
requested_transitions:
  - operation: <lifecycle_state command>
    arguments: {<exact-long-option-without-leading-dashes>: <value>}
```
