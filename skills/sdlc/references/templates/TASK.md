<!--
Optional dispatch-message shape. Pass it directly to a child. It is not a mandatory
task card, inbox, result file, Plan section, or second progress record. Canonical rules:
../stage-agent-protocol.md
-->

## Dispatch: <stage> / <work item>

```yaml
stage: <onboard|backlog|product-design|spec|plan|build|validate|review|ship|evolve>
feature_id: <feature-id or not-applicable>
plan_task_id: <task-id or not-applicable>
goal: <current intended outcome>
out_of_scope: [<work not authorized for this dispatch>]
settled_interfaces: [<API/DTO/ownership/compatibility decisions>]
context_refs: [<project/product/engineering paths>]
write_scope: [<repository-relative paths>]
dependencies: [<settled predecessor or external dependency>]
completion_conditions: [<observable results>]
required_verification: [<command or evidence required before acceptance>]
expected_result: [changed_files, commands, revision, workspace_status, unresolved_items]
authorization: <existing authorization and excluded external actions>
supersedes: <brief identifier or none>
allowed_transitions:
  [] # no lifecycle mutation for this brief
# Or, after the main Agent reads `<operation> --help`, list each allowed request:
# - operation: <lifecycle_state command>
#   required_arguments: [<exact-required-long-option-name>]
#   optional_arguments: [<exact-optional-long-option-name>]
# `--repo` is fixed by the main Agent and is never a child-provided argument.
```

Use `supersedes` only after a material scope or interface change has updated the
effective Plan and this whole brief replaces the earlier one.

## Child result

```yaml
stage: <stage>
status: <awaiting_acceptance | incomplete | blocked> # 待验收 | 未完成 | 受阻
artifacts:
  changed_files: []
evidence:
  commands:
    - command: <actual command>
      exit_code: <integer>
      result: <short observed result>
  revision: <tested commit or uncommitted snapshot>
  workspace_status: <git status summary>
context_updates:
  product: []
  feature: []
  project_candidates: []
unresolved_items: []
requested_transitions:
  [] # no lifecycle mutation requested
```

A nonempty ordered request allowed by this complete brief uses this shape:

```yaml
requested_transitions:
  - operation: <lifecycle_state command>
    arguments:
      <exact-long-option-without-leading-dashes>: <value>
```

Keep scalar and repeated values in the existing CLI format; do not invent a new one.

Only the main Agent accepts this result. The child does not use `completed`.
