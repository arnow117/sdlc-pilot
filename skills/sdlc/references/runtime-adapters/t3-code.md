# T3 Code MCP runtime adapter

Apply the shared [stage protocol](../stage-agent-protocol.md) and its
[runtime selection](../stage-agent-protocol.md#runtime-selection). This adapter
maps an authorized main Agent's direct T3 child task, for any supported provider;
it does not alter role, model, verification, authorization or state ownership.

## Select and dispatch

Check the current host tool contract, permissions, project routing and task budget.
Before the first `delegate_task`, call `orchestrator_capabilities` as required by
the host; repeat only under its stated conditions. Request the full provider,
model and options required by the project and bind the authorized workspace,
revision, write scope, dependencies and complete canonical brief. The child is a
terminal executor: explicitly prohibit nested executors and controllers. Record
available original task/run handles and binding evidence. If tools, authorization,
required routing or an independent context are unavailable, report the specific
gap and stop the dependent dispatch; do not silently switch provider or mechanism.
A top-level thread is only for a user explicitly requesting a new thread, never a
substitute for a stage child.

## Observe, accept and recover

Follow the running delegate's actual host `next`. If it requires ending the turn,
return without polling, sleep, extra messages or redispatch; a turn ending is not
Goal completion. An ordinary timeout without that instruction follows the host's
same-handle waiting guidance and proves neither liveness nor termination. Recover
only from actual restart, connection failure or ambiguous dispatch: inspect the
available original handle and existing result, state/context and Git as needed.
Do not assume an idempotency key, wakeup or settlement API. Unknown writer status
forbids a concurrent replacement in the same scope.

For a routine in-scope implementation correction, use the host-supported message
or continuation control for the same implementer, subject to current host rules.
Where supported and allowed, `t3_thread_send` may continue that implementer; a
send to a finished child can start a new task, whose returned handle must be kept.
New independent reviews or rechecks use a new `delegate_task`, not a thread send.
Preserve writer exclusivity and failure history across either path.

The main Agent checks the canonical result, actual diff, commands and exit codes,
revision, required checks, independence and allowed transitions before acceptance.
Separate requested configuration, run-bound host-effective configuration, observed
behavior and backend model; null or absent backend is unknown, not proof of the
requested model. Apply the project's required evidence and any stricter contract;
do not invent a universal backend-field requirement for ordinary checks. A child
completion or distinct identifier does not prove independent checks were executed.

## Cancel and release

For an authorized child cancellation use `task_cancel`, never `t3_thread_interrupt`
on its child thread. A cancellation receipt, task termination, task-owned writing
process termination and exclusive resource release are separate facts; verify each
using available evidence before handoff. Unknown termination prevents overlapping
writers. Do not stop shared services or infer resource release from task completion.
Preserve failure and nonconvergence history through any recovery or replacement.
