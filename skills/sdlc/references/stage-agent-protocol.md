# Stage agent protocol

> updated: 2026-10-22

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
  protocol does not change any CLI, Spec / planning (`plan`) / Build / Validate / Review / Ship stage, or
  state schema.
- If the runtime cannot create a child, the main Agent performs the same steps
  serially inline and discloses that fallback. An inline pass is not an
  independent review.

Before Spec enters the planning stage (`plan`), the main Agent chooses bounded analysis by domain,
existing module, or key risk. One analysis is the default; it may fan out
independent read-only analysis only when the actual need warrants it. Each analysis
returns current-state evidence, reuse recommendations, interface needs, risks, and
unresolved decisions. Those notes are inputs only: they do not write the unified
current effective solution, change scope, or authorize implementation. The main
Agent resolves conflicts and records the one current effective solution.

## 2. Dispatch contract

Every child receives a complete current brief. Use
[`templates/TASK.md`](templates/TASK.md) as a message shape when useful; it is an
optional prompt template, never a stored task card or another progress record.

The brief includes all of the following:

- Feature ID and Task ID when tracked; for `/sdlc evolve`, state that no
  lifecycle ID applies.
- Goal, explicit out-of-scope work, and the current user authorization.
- Settled interfaces and relevant context references. For cross-client/server
  work, record API/DTO inputs and outputs, identity/permission source, persistence
  owner, version compatibility, retry/cancellation/recovery behavior, composition
  paths, and an observable acceptance scenario before implementation.
- Write scope, dependencies, branch/worktree constraints, completion conditions,
  and required verification.
- For a Feature whose registered development branch must change, use the authoritative
  [branch-registration migration contract](lightweight-runtime.md#51-开发分支登记迁移).
  The main Agent first receives or stops the same Feature's active writer, records
  the actual worktree/root/HEAD and execution purpose, and dispatches a complete
  replacement brief after migration. Other Features retain their existing parallel
  eligibility; the protocol adds no worker registry.
- `allowed_transitions`: the ordered lifecycle operation allow-list for this brief.
  Use `[]` when no lifecycle mutation is allowed. For every allowed operation, list
  the exact required and optional long option names emitted by that operation's
  current `--help` output.
- Required result contents: changed files, actual commands with exit results,
  tested revision and workspace status, unresolved items, requested transitions,
  and any context-update proposal.

Use the current complete brief when dispatching. `supersedes` replaces an earlier
dispatch brief only after a material change to scope, settled interfaces, the
current effective solution, execution method, or verification strategy. An
evidence-backed material recovery change also requires it, even when scope and
interfaces are unchanged; section 5 still preserves the failure history and attempt
limits. The main Agent first updates the current effective solution, then sends a
complete replacement brief instead of splicing a changed contract into the earlier
one.

A replacement brief remains complete for current execution: preserve the current
authorization, write scope, interfaces, completion conditions, required
verification, and allowed transitions. State the material change briefly and use
precise existing `context_refs` to the relevant requirement, design, or evidence
sections. Do not repeat the product text, entire solution, conversation, failure
logs, or prior brief. Replacing a brief does not delete the child's existing
messages; do not resend that history or create a history store. A routine
clarification, local correction, or repair already within the existing acceptance
scope uses a short native follow-up instead. If it materially changes the listed
contract, send the replacement brief.

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
(normally 60 seconds where supported). Waiting and recovery follow the rule below.

### Waiting and recovery

An ordinary wait keeps the original dispatched child's event mailbox as its target.
If a wait returns only its normal timeout, with no new result, actual blocker or
execution error, or user request, and the original handle has not been established
as terminated or missing, wait on that same child again within the host's actual
single-wait limit. Do not finish the work turn or return a final solely for that
timeout; do not start Goal continuation, redo recovery, inspect the runtime tree,
poll or message the child, replace it, or create a checkpoint. This rule applies
whether or not a Goal exists. A timeout is not evidence that the child is still
running.

Give necessary user-facing commentary while waiting. For a user question, answer
briefly from the evidence already available and then resume the same wait unless
the user explicitly pauses, stops, or cancels the work. Honor an explicit
pause/stop under the existing protocol; this rule cannot continue it. Treat actual
execution or tool errors by their observed facts: they are not ordinary timeouts
and do not automatically count as nonconvergence under section 5.

Only an actual runtime restart or connection failure permits one authoritative
runtime-tree check. Continue waiting only when that check confirms the original
child is still executing and its event mailbox can wait. If it returns an existing
result, including one not yet accepted, resume the existing result-acceptance
process. If it confirms the handle is missing or the child has terminated without
a result, first reconcile the original lifecycle status or projection, the
current effective solution and relevant context, and necessary Git evidence for unaccepted
work and its writer; then apply the existing replacement-brief and authorization
rules. If the runtime cannot be queried, or a retained handle's current execution
state cannot be confirmed, report that environment limitation: unknown is neither
termination nor a reason to blindly wait or dispatch a second executor. A user
status question uses known evidence and does not by itself start this recovery.

Dispatch records, lifecycle `in_progress`, checkpoints, and historical handoffs do
not prove real-time child liveness. The current effective solution remains
authoritative for the present design; historical evidence remains separate. Read
only the current, relevant parts when recovery needs them, rather than reloading
all historical changes to the current effective solution or handoffs.
This rule adds no schema, ledger, or runtime service.

### Interaction while work is active

While an actual stage child or long-running command is executing, the main Agent
may answer a user question, clarify a later decision, or do independent work that
does not interfere with the active writer's scope. A normal question or feedback
does not pause the child, redispatch its work, or turn a status request into a
liveness check. Answer status questions from the evidence already known, then
resume the original work.

Send a routine clarification or correction that remains within the current
acceptance scope as a short native follow-up only to the affected current
executor. For a material change to the contract, the main Agent first updates the
one current effective solution, then sends the affected executor a complete
replacement brief marked `supersedes`, following the existing writer-handoff and
review rules. Do not let an old and replacement writer edit the same work, and do
not use feedback to bypass independent review. `/sdlc evolve` keeps its existing
authorized-brief exception because it has no lifecycle engineering context.

An explicit user pause, stop, or cancellation takes precedence and is handled by
the existing pause, recovery, and authorization rules. If the host has no
asynchronous execution capability, execute serially with the available configured
child and role routing. Only a runtime that cannot create a child uses the section
1 serial inline fallback and discloses it; absence of asynchronous execution or
intermediate messaging is not absence of child capability. Do not promise that
work will continue after the conversation ends, that a persistent background
worker exists, or that the host will wake itself later.

### Continuation within existing authorization

After the main Agent accepts a stage result, applies only its allowed lifecycle
transition, and reads `next`, it continues to the next Task or stage when the
user's existing authorization covers that objective. Completing one stage, an
ordinary wait timeout, a user question, or an early increment does not itself
require a new “continue?” request or end the orchestration.

This continuation remains bounded by the original objective and external-impact
boundary. Authorization for one stage does not authorize an entire Feature, and
authorization for one Feature does not authorize another. Do not consume or
enable external services, commit, push, publish, or deploy without the existing
authorization required for that action. `needs_selection`, an unresolved material
decision, a missing external authorization, an explicit pause or stop, missing or
failed evidence, and the mandatory nonconvergence rule still stop progression.
The same stage owner keeps its implementation, tests, and corrections until the
main Agent accepts the result; ordinary repairs already inside the accepted
contract do not create an additional user-approval step.

### Earliest real increment

The current effective solution and its Task order should put the smallest runnable
core user journey first. Identify only the dependencies that journey actually
needs, and validate an external dependency that determines feasibility early when
the required access and budget are already authorized. Unrelated foundation work,
full research, and every cross-cutting concern do not block that first increment.
For an internal capability with no user interface, use a reproducible experiment,
CLI result, or contract result instead of inventing a UI. If no independently
showable increment exists, record the concrete dependency that prevents one.

When Build has a stable, evidence-supported increment that a user can inspect, it
reports its entry point or artifact reference, actual verification scope, tested
revision and workspace facts, and remaining gaps to the main Agent without adding
a result field or progress store. The main Agent promptly presents that stable
increment and those facts to the user while the existing authorized work continues;
this presentation requires no separate trial confirmation, approval, or lifecycle
transition. It does not mark an unfinished Task done, replace Validate, Review, or
Ship, or make a mock or prototype a production-path pass. If a real provider,
device, or other dependency is unavailable, say so; a mock-only result is not a
real pass.

## 3. Planning, implementation, integration, and review

### Planning stage (规划阶段) and current effective solution (当前有效方案)

The existing runtime stage `plan` is the planning stage (规划阶段). The current
solution held in its engineering context is the current effective solution
(当前有效方案). It contains the task boundary, interfaces, dependencies,
execution and verification strategy, and acceptance strategy. Update it for a
material design change or when genuinely new causal localization evidence requires
a different solution, execution method, or verification strategy. Product
requirements remain in the Requirement product context. Dispatch records,
reminders, debug notes, and rerun logs do not belong in the current effective
solution. A recovery update must change the actual solution, execution method, or
verification strategy; supporting trace evidence stays in the existing evidence
section and must meet section 5. `/sdlc evolve` uses its authorized brief instead
of creating a current effective solution or lifecycle state.

For implementation, split work by independently acceptable units, not by a fixed
frontend/backend/domain pattern. Agree shared implementation interfaces first;
serial execution is required while one of those interfaces or a dependency remains
unresolved. This does not prevent the main Agent from first obtaining independent,
read-only analysis from Spec into the planning stage. The main Agent may allow
parallel implementation work only after verifying all of these conditions:

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
If it cannot, it records a serial fallback and never labels it independent. Review
input scope, procedure and record content are owned by
[`sdlc-review`](../../sdlc-review/SKILL.md#review-input-and-scope).

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

### Results for corrections and other issues

A simple successful first pass keeps the concise result format above. When the same
acceptance objective returns for correction, or another issue affects the completion
judgment, the result briefly states whether acceptance has progressed, moved
backward, or not progressed, with its evidence. It distinguishes work required for
acceptance from a follow-up that does not block acceptance through the existing
`evidence`, `unresolved_items`, and `context_updates` sections; it adds no YAML
fields, a fixed list of status values, counters, per-tool reports, or a separate
store. Compatibility, security, correctness, and recovery requirements cannot be
described as follow-ups to avoid a necessary check.

For a batch of review or user opinions, use
[`receiving-feedback.md`](receiving-feedback.md) for the canonical handling and
recording discipline. The nonconvergence rule and its history preservation remain
solely in [section 5](#5-evidence-git-and-mandatory-stop): a correction label,
another issue, or `supersedes` brief does not change that rule.

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
through evidence-backed current effective solution updates, complete `supersedes` briefs, renamed or
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
code, or environment while ruling out an alternative. A renamed task, changed solution
wording, or added logging without an observed cause-narrowing result is not
localization evidence. Reproducible trace output that eliminates an alternative is
localization evidence.

If the diagnosis produces that evidence, first update the current effective solution's actual
solution, execution method, or verification strategy. Then, under the existing
authorization and without step-by-step approval, send the same implementer a
complete replacement brief marked `supersedes`. The brief records the material
recovery and required verification change. It preserves prior attempts rather than
using the updated solution to justify a third identical retry. A diagnosis is not
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

### Context prose and evidence applicability

The lifecycle CLI does not automatically interpret a semantic change to product or
engineering-context prose, or invalidate an earlier validation because that prose
changed. A current business commit that is unchanged is therefore neither proof that
the evidence still covers the current requirements nor proof that it does not.

Before reusing validation for review or ship, the main Agent compares the current
binding requirements and current effective solution with what the recorded evidence
actually covered. If a changed requirement, design, contract, environment fact, or
planned verification creates an obligation the evidence did not cover, it must use
the existing planning, build and validation actions and their permitted lifecycle
transitions before advancing. If the change does not affect coverage, record the
reason in the existing context and retain the evidence reference. Do not invent an
automatic state transition, context-prose detector, cache, or new evidence store.

## 6. Context and checkpoints

Product behavior, scenarios, and rules belong in the Requirement product context.
Feature design, task boundary, interfaces, dependencies, and acceptance strategy
belong in the current effective solution section of the engineering context. Final validation
and acceptance evidence use their existing engineering-context section or a
reference. Keep those sections distinct. Do not put a current handoff or a stream
of dispatch/debug/rerun notes in the current effective solution.

The current effective solution is authoritative for the present design;
`state.json` is authoritative for lifecycle progress; Git history and the actual working-tree code
are authoritative for what is present. An on-demand checkpoint is allowed only for
pause, cross-conversation recovery, or execution-environment change. Its only path is
`.sdlc-v1/checkpoints/<feature-id>.md`; use
[`templates/CHECKPOINT.md`](templates/CHECKPOINT.md). There is at most one per
Feature, it has at most 60 lines, and only the main Agent creates, updates, or
deletes it. A child may return a candidate, but never writes the checkpoint. It has
exactly these five sections:

1. `定位` — Feature, branch, HEAD, workspace, Task ID;
2. `已确认` — main-Agent accepted work, commands, results, versions;
3. `未完成` — active, unaccepted, failed, or blocked work;
4. `下一步` — first action, completion condition, necessary verification, and
   constraints that must remain;
5. `必要引用` — only the required state, current effective solution, context, Git, code, or evidence
   references.

The checkpoint is not a Spec, current effective solution, chat transcript, full log, state replacement,
or credential, private material, or unnecessary local-path store. On recovery,
first verify branch, HEAD, and workspace. If the recorded version differs,
reassess the evidence before continuing. The main Agent updates the single file in
place; Git preserves its history. The main Agent deletes it when the Feature
completes.
