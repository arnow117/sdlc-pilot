# Stage agent protocol

> updated: 2026-10-03

This is the sole authority for SDLC stage orchestration. It adds an execution
convention only: lifecycle state remains `state_version=3`; it creates no event
runtime, message service, task inbox, local result store, or behavioral-evaluation
loop. `lifecycle_state.py`, ordinary Git history, and the existing Markdown
contexts retain their current roles.

## 1. Authority, modes, and layer boundary

- In **orchestrated mode**, the main Agent owns goal understanding, work
  decomposition, cross-module decisions, integration acceptance, lifecycle
  mutations, and `.sdlc-v1/state.json`. It calls `next`, dispatches the bounded
  stage work, verifies the child's evidence, applies valid transitions, and calls
  `next` again.
- Actual stage work, including a small implementation task, is performed by the
  dispatched child. The main Agent does not treat a brief as completed work.
- The default hierarchy is one layer: **main Agent → one child Agent**. A child
  must not fan out, create another lifecycle, or delegate its contract. The main
  Agent may request one or more independent, bounded read-only analyses when it
  records the reason, boundary, and aggregation point first. A further execution
  layer requires the same record. Every layer returns a summary before the main
  Agent proceeds; no level expands itself beyond the hierarchy the main Agent named.
- **Standalone mode** means an independently direct invocation with no current main
  Agent orchestration. Once the main Agent orchestrates a Feature or stage, every
  stage skill invocation inherits orchestrated mode, even if called directly. It
  cannot use standalone mode to bypass child execution or main acceptance. This
  protocol does not change any CLI, Spec/Plan/Build/Validate/Review/Ship stage, or
  state schema.
- If the runtime cannot create a child, the main Agent performs the same steps
  serially inline and discloses that fallback. An inline pass is not an
  independent review.

Before Spec becomes Plan, the main Agent chooses bounded analysis by domain,
existing module, or key risk. One analysis is the default; it may fan out
independent read-only analysis only when the actual need warrants it. Each analysis
returns current-state evidence, reuse recommendations, interface needs, risks, and
unresolved decisions. Those notes are inputs only: they do not write the unified
Plan, change scope, or authorize implementation. The main Agent resolves conflicts
and records the one effective unified Plan.

## 2. Dispatch contract

Every child receives a complete current brief. Use
[`templates/TASK.md`](templates/TASK.md) as a message shape when useful; it is an
optional prompt template, never a stored task card or another progress record.

The brief includes all of the following:

- Feature ID and Plan Task ID when tracked; for `/sdlc evolve`, state that no
  lifecycle ID applies.
- Goal, explicit out-of-scope work, and the current user authorization.
- Settled interfaces and relevant context references. For cross-client/server
  work, record API/DTO inputs and outputs, identity/permission source, persistence
  owner, version compatibility, retry/cancellation/recovery behavior, composition
  paths, and an observable acceptance scenario before implementation.
- Write scope, dependencies, branch/worktree constraints, completion conditions,
  and required verification.
- `allowed_transitions`: the ordered lifecycle operation allow-list for this brief.
  Use `[]` when no lifecycle mutation is allowed. For every allowed operation, list
  the exact required and optional long option names emitted by that operation's
  current `--help` output.
- Required result contents: changed files, actual commands with exit results,
  tested revision and workspace status, unresolved items, requested transitions,
  and any context-update proposal.

Use the current complete brief when dispatching. A material interface, scope, or
evidence-backed change to the solution, execution method, or verification strategy
first updates the effective Plan, then the main Agent sends a complete replacement
brief marked `supersedes`; it does not splice a changed contract into an earlier
brief. This protocol overrides the optional `TASK.md` direction to use
`supersedes` only after a material scope or interface change: an evidence-backed
material recovery change requires a complete `supersedes` brief even when scope and
interfaces are unchanged. A routine clarification may use a native follow-up
message only when it does not change the contract.

The child completes ordinary implementation choices and necessary checks without
asking for approval at each step. It stops for a material missing decision,
interface conflict, authorization gap, or write-scope conflict. A runtime with
child capability still uses one child for a small actual work item; only the stated
inline fallback applies when that capability is absent.

The same implementer owns implementation, necessary tests, and corrections until
the work item is accepted. A replacement needs an independently verifiable
deliverable, settled dependencies and write scope, or an explicit reason such as an
unavailable runtime; unfinished edits or missing tests alone are not enough. A
child never edits `.sdlc-v1/state.json` or calls lifecycle mutation commands in
orchestrated mode.

New children receive minimal relevant context. In Codex, request `fork_turns="none"`
when supported, use the repository's configured model/role routing, and report the
actual runtime limitation instead of assuming a role file changed a loaded model.
Messages add a new constraint, correction, blocker resolution, or result; do not
send acknowledgements, progress polls, or repeated “continue” requests. While a
child runs, the main Agent does independent work or uses an event-aware wait
(normally 60 seconds where supported); a timeout alone does not trigger a new
dispatch or status query.

## 3. Planning, implementation, integration, and review

### Plan

Plan contents are the current solution, task boundary, interfaces, dependencies,
execution and verification strategy, and acceptance strategy. Update them for a
material design change or when genuinely new causal localization evidence requires
a different solution, execution method, or verification strategy. Product
requirements remain in the Requirement product context. Dispatch records,
reminders, debug notes, and rerun logs do not belong in a Plan. A recovery update
must change the actual solution, execution method, or verification strategy;
supporting trace evidence stays in the existing evidence section and must meet
section 5. `/sdlc evolve` uses its authorized brief instead of creating a Plan or
lifecycle state.

For implementation, split work by independently acceptable units, not by a fixed
frontend/backend/domain pattern. Agree shared implementation interfaces first;
serial execution is required while one of those interfaces or a dependency remains
unresolved. This does not prevent the main Agent from first obtaining independent,
read-only Spec-to-Plan analysis. The main Agent may allow parallel implementation
work only after verifying all of these conditions:

1. the interface is stable;
2. write scopes do not overlap;
3. each unit has independent acceptance and verification; and
4. existing branch/worktree isolation can keep runtime resources separate.

Each implementer runs its own necessary tests. The main Agent performs integration
acceptance on the integrated revision.

### Integration and acceptance

The main Agent selects bounded integration checks from the relevant user journeys,
recovery/concurrency behavior, and permission isolation; it may use a small set or
run them serially instead of mechanically splitting roles. A child supplies
reproducible evidence and coverage gaps; the main Agent chooses the repair order.
Review is read-only with respect to implementation. When the runtime can create an
actually independent reviewer, the main Agent dispatches one after implementation.
If it cannot, it records a serial fallback and never labels it independent.

Validate is also read-only with respect to implementation. Ship may prepare release
and smoke evidence, but external effects and release mutations remain with the
main Agent after the required user authorization.

After a child returns, the main Agent verifies the declared diff, required checks,
revision, workspace state, and lifecycle-request contract before accepting it.
Missing or failed required verification prevents acceptance. On stage completion,
the main Agent stops or releases the child when the runtime offers that control;
otherwise it discloses the limitation. The next stage reads the accepted summary
and necessary references, not the prior conversation or a running-agent state.

## 4. Results, transitions, and correction

A child returns a handoff message in this shape. The English status is paired with
its required Chinese meaning.

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

A nonempty ordered request uses only this brief's `allowed_transitions`:

```yaml
requested_transitions:
  - operation: <lifecycle_state command>
    arguments:
      <exact-long-option-without-leading-dashes>: <value>
```

Only the main Agent accepts a result. A child never reports `completed`; it returns
`awaiting_acceptance` only when its completion conditions and necessary checks are
satisfied. `incomplete` and `blocked` explain what remains or what prevents it.
Historic `completed` or `failed` messages are evidence to reinterpret, not a state
schema migration or an alternative state transition.

`requested_transitions` stay ordered. Before every lifecycle request, the main
Agent compares it with this brief's `allowed_transitions`: operation, required
arguments, and unknown arguments must all match. It creates that allow-list from
`lifecycle_state.py <operation> --help` before dispatch and lists each operation's
actual required and optional long option names. The main Agent fixes `--repo` to
the target repository; a child result cannot provide or override it. It preserves
the CLI's existing scalar and repeated-option value semantics, neither dropping nor
inventing values. A request that is CLI-legal but not allowed for this stage is
rejected just like a missing or unknown argument: state remains unchanged and the
complete result returns to the same child for correction. Only then does the main
Agent execute the existing CLI.
For validation, a non-passing result may request the existing
`record-validation --result fail` under the established validation-attribution
rules; it records non-passage and does not advance the stage. If the CLI rejects
that record because its preconditions are not met, stop dispatch for that Feature;
do not use an earlier passing validation to continue review or ship.

Nonconvergence triggers, bounded diagnosis, evidence requirements, recovery, and
reporting are defined only in [section 5](#5-evidence-git-and-mandatory-stop). The
main Agent follows that procedure before further execution; it does not resend the
same reminder.

## 5. Evidence, Git, and mandatory stop

Reuse verification only when the relevant code, configuration, environment, and
tested revision still match. Evidence names the command, exit result, revision, and
relevant workspace/configuration facts. A changed input, missing evidence, failed
check, or stage-specific requirement requires appropriate new verification.

After a complete change segment passes its required checks, commit it on the
Feature branch when existing authorization permits. A partial checkpoint commit
must say that work remains incomplete. Merge to the release branch or main line
only after the overall acceptance and the authorization required for that release.
This does not authorize push, merge, or an external release by itself.

For this procedure, a delivery segment is the affected work for one problem and
acceptance objective; it does not include unrelated deliverables merely because
they share a Feature. Two consecutive implementation or correction attempts on
that problem which satisfy no acceptance condition and add no genuinely new causal
localization evidence require a mandatory stop of blind changes and repetitive
dispatch for that segment. The same stop applies to two redispatch/review/retest
cycles that repeat work with unchanged inputs, no new finding, and no required
lifecycle check.

Preserve the attempt count, failure evidence, and one bounded-diagnosis allowance
through evidence-backed Plan updates, complete `supersedes` briefs, renamed or
split tasks, and implementer replacement. None starts a new segment or erases the
history. If resumed work for the same problem and acceptance objective reaches a
nonconvergence trigger after that allowance has been used, stop and report; do not
label it a new segment to obtain another diagnosis. Independent work already
authorized and outside the affected segment may continue.

Stop new dispatch, interrupt active Agents for that segment when the runtime can,
and cancel only identified task-owned test/build jobs when safe. Preserve the
working tree and recovery evidence; never reset Git, delete data, stop shared
services, create a second progress store, or advance lifecycle state.

Unless an active user pause or stop, approval refusal, or required authorization
prevents it, the main Agent may run one—and only one—bounded diagnosis within the
existing authorization. Before it starts, state a falsifiable hypothesis, limited
minimal discriminating experiment(s), an explicit finite time limit, and a
side-effect boundary. Do not repeat an identical failed action, append hypotheses
or experiments indefinitely, or restart the time limit by rephrasing the
diagnosis. A diagnosis does not permit a paused CI push or bypass any other
external-operation authorization.

Genuinely new causal localization evidence must be observed and reproducible, and
must reduce the candidate cause set—for example, isolate input, configuration,
code, or environment while ruling out an alternative. A renamed task, changed Plan
wording, or added logging without an observed cause-narrowing result is not
localization evidence. Reproducible trace output that eliminates an alternative is
localization evidence.

If the diagnosis produces that evidence, first update the effective Plan's actual
solution, execution method, or verification strategy. Then, under the existing
authorization and without step-by-step approval, send the same implementer a
complete replacement brief marked `supersedes`. The brief records the material
recovery and required verification change. It preserves prior attempts rather than
using the revised Plan to justify a third identical retry. A diagnosis is not
permission to bypass release or main-merge authorization, model-consuming or
destructive-operation authorization, required tests or review, or lifecycle state
ownership.

If the diagnosis exhausts its time limit, finds no localization evidence, or
requires a missing user decision or new permission, stop the affected segment and
report the trigger; completed and unfinished work; hypothesis, experiment, and
result; failure count; interruption result or runtime limitation; the precise
missing evidence, decision, or permission; and the next action. A used allowance
does not suppress a first successful evidence-backed recovery. Only a later renewed
nonconvergence trigger for the same segment after that allowance was used stops and
reports under this paragraph without another diagnosis. Await user direction after
that report, while independent work already authorized and outside the affected
segment may continue. A child `blocked` result is local to its work item, not a
whole Goal status: follow actual Goal-tool preconditions and never clear, recreate,
falsely resume, or falsely complete a Goal to evade them. A timeout, elapsed time,
token use, necessary verification, or an independent review alone does not trigger
this stop.

## 6. Context and checkpoints

Product behavior, scenarios, and rules belong in the Requirement product context.
Feature design, task boundary, interfaces, dependencies, and acceptance strategy
belong in the effective Plan section of the engineering context. Final validation
and acceptance evidence use their existing engineering-context section or a
reference. Keep those sections distinct. Do not put a current handoff or a stream
of dispatch/debug/rerun notes in the Plan.

The effective Plan is authoritative for the current solution; `state.json` is
authoritative for lifecycle progress; Git history and the actual working-tree code
are authoritative for what is present. An on-demand checkpoint is allowed only for
pause, cross-conversation recovery, or execution-environment change. Its only path is
`.sdlc-v1/checkpoints/<feature-id>.md`; use
[`templates/CHECKPOINT.md`](templates/CHECKPOINT.md). There is at most one per
Feature, it has at most 60 lines, and only the main Agent creates, updates, or
deletes it. A child may return a candidate, but never writes the checkpoint. It has
exactly these five sections:

1. `定位` — Feature, branch, HEAD, workspace, Plan Task;
2. `已确认` — main-Agent accepted work, commands, results, versions;
3. `未完成` — active, unaccepted, failed, or blocked work;
4. `下一步` — first action, completion condition, necessary verification, and
   constraints that must remain;
5. `必要引用` — only the required state, Plan, context, Git, code, or evidence
   references.

The checkpoint is not a Spec, Plan, chat transcript, full log, state replacement,
or credential, private material, or unnecessary local-path store. On recovery,
first verify branch, HEAD, and workspace. If the recorded version differs,
reassess the evidence before continuing. The main Agent updates the single file in
place; Git preserves its history. The main Agent deletes it when the Feature
completes.
