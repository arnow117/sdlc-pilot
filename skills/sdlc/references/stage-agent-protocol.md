# Stage agent protocol

> updated: 2026-09-13

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

## Execution, communication, and context budget

- Dispatch a complete bounded stage with acceptance conditions, not one file or
  test command at a time. Within the brief, the stage Agent completes ordinary
  implementation choices and necessary checks autonomously. It reports material
  blockers, contract conflicts, or completion; it does not seek approval for each
  routine step. Existing user authorization carries forward within its scope.
- Before cross-layer implementation, the main Agent records the relevant API/DTO
  inputs and outputs, identity and permission sources, persistence ownership,
  version compatibility, and retry/cancellation/recovery behavior in the existing
  engineering context. Name the affected server, client and composition paths
  and an observable acceptance scenario. Resolve material interface gaps first;
  routine implementation details remain with the implementer. Do not require a
  separate design document or this analysis for an unrelated simple edit.
- Keep implementation, its necessary tests, and corrections with the same stage
  Agent. A new implementer needs an independently verifiable deliverable, explicit
  write scope and settled dependencies, or a stated replacement reason such as
  an unavailable Agent. Missing tests and unfinished edits alone are not reasons
  to create another Agent. Independent validate/review stages remain separate.
  If two consecutive correction attempts on the same blocker satisfy no acceptance
  condition and add no evidence narrowing its cause, apply the mandatory stop
  below; changing Agent names or splitting work does not reset this condition.
- Messages between Agents must add a constraint, correct direction, resolve a
  blocker, or deliver a result. Do not send no-op acknowledgements, requests for
  progress, or repeated instructions to continue. This does not remove required
  user-facing progress updates; the main Agent uses evidence already available.
- While a stage runs, the main Agent does independent work if available. Otherwise
  use an event-aware wait, defaulting to 60 seconds where supported and waking
  early for completion, blockers, or user input. A timeout alone is not a reason
  to send a message, list Agents, query status, or invent another task; continue
  waiting after any required user-facing update. Respect runtime wait limits.
- For every newly created stage Agent, default to minimal context; when
  supported, explicitly set `fork_turns="none"` with a brief. Include the goal,
  write boundary, output format, tool guidance, relevant decisions, authorization,
  constraints, and paths to required repository/skill instructions and artifacts.
  The Agent must load missing applicable instructions before acting. Do not omit
  necessary contracts to shorten context. Without selective inheritance, provide
  the same concise brief and load only relevant files. Reuse the same Agent for
  corrections within the same stage; review independence still applies below.
  Fuller inheritance requires a stated decision that cannot be conveyed reliably
  through the brief and referenced artifacts. Use the repository's configured
  role/model routing; report runtime limitations instead of assuming that a role
  file changed an already running Agent's model.
- Collect completion evidence before review and return actionable feedback in
  one batch. Recheck affected findings after correction; do not start repeated
  reviews without changed evidence or an unresolved concern. Required lifecycle
  validate/review stages and their commit rules remain mandatory.
  Code written with missing or failing agreed checks is not a completed stage.
  Record partial work and the concrete blocker, distinguishing implementation
  failures from environment failures. Do not start review solely on a count of
  passing tests without evidence covering the completion conditions.
- Reuse command evidence only when the required checks actually ran and the
  relevant code, configuration, and environment snapshot still matches. Include
  command, result/exit code, tested revision and any relevant working-tree or
  environment details. The main Agent inspects this evidence rather than rerunning
  identical checks solely because it received a handoff. Changed inputs, failures,
  missing evidence, or stage-specific requirements require the appropriate checks;
  an old pass never substitutes for current lifecycle validation.

## Mandatory stop for non-converging execution

The condition above, or two consecutive redispatch/review/retest cycles repeating
the same work without changed inputs, a new finding, or a required lifecycle
check, requires a stop of the current delivery segment. This overrides ordinary
continuation under earlier authorization to complete all work.

Stop new dispatch and interrupt active Agents for that segment using available
runtime controls. Cancel only clearly identified task-owned test/build jobs when
safe. Preserve the working tree and recovery evidence; do not reset Git, delete
data, or stop shared database/deployment services. Do not advance lifecycle state.
Report the trigger, completed and unfinished work, interruption results and any
work that could not be stopped, and a proposed recovery approach. End the turn
and wait for explicit user direction before resuming. Read-only analysis for this
report is allowed; reassessment alone does not authorize another implementation
attempt. If interruption controls are unavailable, disclose that limitation and
do not claim running work has stopped.

Elapsed time, token count, a normal wait timeout, and required independent review
alone do not trigger this rule. This is an Agent execution instruction, not an
external watchdog or a new lifecycle state/runtime.

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

For validation only, a blocked/failed result may request `record-validation` with
`result: fail` to invalidate an older pass before pausing. The main Agent verifies
that the request is allowed by the brief and supported by the recorded failure,
blocker, or missing evidence; this records non-passage, never advances the stage.
All normal CLI preconditions apply. If recording is rejected, stop dispatch for
that Feature and resolve the precondition; do not continue review/ship using the
old pass or mutate state directly. See [validation attribution](../../sdlc-validate/SKILL.md#验证归因).

## Context routing

- Keep a compact current handoff in the existing Feature engineering context:
  branch/revision, accepted work, unresolved contracts/findings, evidence with its
  tested snapshot, and the next bounded action. Replace that summary as work
  advances; retain detailed evidence below or by reference. Recovery starts from
  this summary and authoritative state, not a replay of the entire conversation.
  A summary of earlier passes is not fresh verification of the current tree.
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
