# Optional Claude CLI runtime adapter

This reference maps an explicitly selected external Claude CLI worker to the
existing [stage protocol](../stage-agent-protocol.md) and its
[optional brief/result template](../templates/TASK.md). It does not define a new
schema, lifecycle, or native `spawn_agent` implementation. The main Agent owns
dispatch, acceptance and lifecycle mutations. The external CLI cannot establish
the configured model role or independence merely by being invoked.

## Select and bind

Use this path only when Claude is explicitly selected for the current task and
the applicable task, provider and permission-bypass authorizations exist. Find
`scripts/csd` through the installed `driving-claude-code-sessions` skill or a path
explicitly supplied and verified by the main Agent; find the stage protocol and
CLI in the actual installed sdlc package. Check `csd help`, Node, tmux, the
Claude executable and relevant authorization before launch. A previous one-time
`grant-consent` is not authorization for this task or other permissions; create it
only with applicable authorization. If anything is missing, report the specific
gap without launching, granting consent or silently switching executors. The
default native route needs none of these external dependencies.

The main Agent prepares the complete current brief and checks its worktree,
branch, revision, stage, write scope and task binding before directly invoking
`csd launch --harness claude <name> <cwd>`. Retain the returned shim. Where the
protocol permits N/A before a Feature exists or during evolve, use that existing
localization; do not invent IDs or initialize state for the adapter. Do not place
a native stage child between the main Agent and this CLI worker. Independent
ordinary delegation uses the public session driver and does not require SDLC.

## Dispatch and observe

Use the bound shim's `converse --with-turn <prompt> [timeout]` or `send <prompt>`
for the complete brief and in-scope corrections. The same implementer owns
corrections and checks; use the protocol's complete `supersedes` brief for a
material contract change. These commands are CLI controls, not native agent
messages. Preserve the original events line baseline for the turn before sending.

`converse` exits 1 on timeout but does not stop the worker. Inspect the bound
session with `status`, `read-events` and, when available, `read-turn`. If the
original turn has ended, obtain its existing result. If still running, wait for
that same turn without resending or launching another worker: `wait-for-turn`
defaults to the current end of the event file and waits for a future stop or
session_end; `--after-line N` uses the previously captured baseline and can see
an intervening turn-end. Unknown or gone is not proof of acceptance or safe OS
resource release. Do not infer native background or messaging guarantees from csd.

## Accept, correct and stop

The main Agent checks the canonical result against the brief, actual artifacts,
commands and exit codes, worktree and applicable revision. CLI exit 0 and relayed
text are not acceptance. Return missing, failed or wrong-version evidence to the
same available implementer; evaluate equivalent-input evidence under the existing
protocol. Required independent Validate and Review remain separate. Check ordered
transition requests against the brief before the main Agent executes any.

Follow the protocol for interruption, cancellation, recovery, single-writer
handoff and nonconvergence. Preserve the original authorization, failure history,
used diagnosis allowance and explicit stop across any replacement; changing
workers does not reset them. Do not adopt an unknown session without verified task
binding. Before an authorized stop, verify that the session and resources belong
to this task and preserve necessary evidence: `stop` removes meta, events and the
shim. Verify resource cleanup separately; cancellation or unknown status alone
does not establish that OS resources were released. Do not stop shared sessions,
prune globally, or stop/relaunch merely because of a timeout.
