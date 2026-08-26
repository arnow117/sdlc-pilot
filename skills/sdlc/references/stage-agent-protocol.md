# Stage agent protocol

> updated: 2026-08-26

This is the canonical protocol for running an SDLC stage through a sub-agent. It
adds an execution convention only: lifecycle state remains `state_version=3`,
and no event runtime, behavioral evaluation, or retrospective loop is created.

## Modes and state ownership

- **orchestrated mode**: the main Agent (Feature owner) calls `next`, dispatches
  one stage Agent, verifies its returned evidence, applies lifecycle mutations,
  then calls `next` again.
- **standalone mode**: a stage skill is invoked directly. Its existing lifecycle
  commands continue to apply.
- In orchestrated mode, the main Agent alone owns `.sdlc-v1/state.json`. Stage
  Agents must not edit it or execute lifecycle mutation commands.
- Default execution is one stage Agent at a time. Nested or parallel Task/review
  work is allowed only when write scopes and interfaces are actually independent.

If the runtime cannot create sub-agents, the main Agent executes the same stage
serially inline and discloses that fallback. The protocol is never a runtime
dependency.

## Brief

Before dispatching, the main Agent supplies only the information needed for the
current stage:

```yaml
stage: <onboard|backlog|product-design|spec|plan|build|validate|review|ship>
requirement_id: <optional>
feature_id: <optional>
task_id: <optional>
branch: <branch>
context_refs: [<project/product/engineering paths>]
write_scope: [<repository-relative paths>]
expected_artifacts: [<paths or observable outcomes>]
completion_conditions: [<checks>]
allowed_transitions:
  - operation: <lifecycle_state command>
    required_arguments: [<exact-long-option-without-leading-dashes>]
    optional_arguments: [<exact-long-option-without-leading-dashes>]
```

The brief also states user decisions already made, constraints, and whether an
external action is authorized. A stage Agent stops and reports rather than
guessing a missing material decision. Before dispatch, the main Agent obtains
this contract by running `lifecycle_state.py <operation> --help` for each
operation relevant to the current stage. It lists only allowed operations and
their exact long-option names; the main Agent supplies its own target-repository
argument and does not expose it as a stage result field.

## Result and main-Agent advance

Every stage Agent returns this minimal result; it is a handoff message, not a
new stored progress record.

```yaml
stage: <stage>
status: <completed|blocked|failed>
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
    arguments: <command arguments>
```

`requested_transitions` is ordered and may contain multiple mutations; planning
commonly requests `start-feature` followed by one or more `add-task` calls.
Each `arguments` key is an exact CLI long-option name with leading `--` removed.
It must not contain a business-only field such as `title` for `start-feature`.
Use arrays only for an option that the CLI explicitly accepts repeatedly; do not
invent a list representation for a scalar or comma-separated option.

The main Agent verifies the real diff, declared artifacts, command evidence,
completion conditions, and that the stage Agent did not change `state.json`.
Before applying a transition, it checks the operation against `allowed_transitions`,
checks all required arguments are present, and rejects unknown argument keys. On
a mismatch it neither drops nor invents values and does not modify state; it
returns the result to the same stage Agent for correction. It relays unanswered
questions, applies only verified requested transitions with `lifecycle_state.py`,
then calls `next`. It pauses instead of advancing when `next` returns
`needs_selection`, a user decision or external authorization is needed, the
result is blocked/failed, or evidence is missing.

## Context routing

- Product behavior, scenarios, and business rules update the Requirement product
  context.
- Feature-specific design, implementation, validation evidence, and decisions
  update the Feature engineering context.
- A cross-feature rule that is useful to this target repository is returned as a
  `project_candidates` item. The main Agent proposes an explicit durable project
  document or `AGENTS.md`/`project.md` index update; it does not silently promote
  the rule.
- Only an explicitly cross-project, reusable SDLC improvement is a proposal for
  `/sdlc evolve`.

## Review and external effects

When available, review is assigned to a fresh Agent separate from the
implementer. Without that capability, the main Agent runs the same review
serially and records the fallback in the result. Validate and review are
read-only with respect to implementation. Ship may prepare evidence, but the
main Agent obtains required user authorization and performs external effects.
