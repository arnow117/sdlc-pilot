# T3 Code MCP runtime adapter

Read this adapter only when the protocol's
[runtime selection](../stage-agent-protocol.md#runtime-selection) chooses T3 for
the current dispatch. It is the complete T3 execution path, without a local driver
or terminal-automation fallback. The public skill is optional for this package;
the mapping below is sufficient for SDLC stage execution.

This reference maps explicitly selected and authorized Claude Code execution through the connected T3 Code MCP to the existing [stage protocol](../stage-agent-protocol.md) and [brief/result template](../templates/TASK.md). The main Agent directly controls the executor, checks its result and owns lifecycle mutations. Do not insert a native stage child, use T3 delegation/workflows to create another orchestration flow, or treat a completed run as acceptance. Existing model, role and independence constraints still apply; a Claude invocation or instance label is not proof of the actual role or model. Independent bounded delegation uses the public `driving-claude-code-sessions` entry without requiring a Feature.

## Select and bind

Require current task, provider, workspace and runtime permissions. Connect through the host's native MCP/OAuth and T3 Sharing & access; never store credentials in the repository. If access, tools, a registered project or required permissions are missing, report the gap without silently changing executor, broadening permissions or using a privileged host CLI. A new or reloaded host session may be needed for new tools. The native SDLC path does not require T3.

Read `t3_environment_read` and `orchestrator_capabilities`. Bind the environment, project and checkout/worktree, selected provider instance, model and options, runtime and interaction modes, and current brief (including revision, write scope and ownership). Scratch is for appropriate disposable work, not a substitute for a repository task. Launch idle via `t3_thread_launch` with an explicit title, project and `workspaceStrategy` (or `scratch: true`), `modelSelection`, modes and stable `clientRequestId`; then verify the binding with `t3_thread_read`. Send the brief via `t3_thread_send` with `mode: "queue"` for the next turn. Retain the environment, `threadId`, exact `runId` and request IDs. An ambiguous launch/send reply can be retried with the same `clientRequestId`, not a new worker.

## Observe and accept

Use bounded `t3_thread_wait` on the exact run, with `untilDelegatedWorkSettled: true` when relevant; read messages or activity with bounded pagination via `t3_thread_read`. Timeout or transport loss is an observation failure, not a stop: continue observing the same run without resending or launching another. Rely only on actual host-supported signaling, not an inferred wakeup. Send corrections to the same available implementer; `auto`, `steer` and `restart` have different effects. Do not use restart, `freshContext` or replacement to reset failure, stop or diagnosis history. Material contract changes follow the existing complete `supersedes` rule.

The main Agent checks the canonical result, actual files, commands and exit codes, worktree and revision against the brief. A transport acknowledgement or completed run is not acceptance. Required independent Validate and Review remain separate, and the main Agent checks and executes any permitted transition request.

## Interrupt and settle

Follow the existing protocol for cancellation, recovery, single-writer handoff and nonconvergence. For authorized cancellation, interrupt the bound active run with `t3_thread_interrupt` and verify its actual terminal state; an idle thread is unaffected. After terminal work, request settlement using `t3_thread_organize` with `action: "settle"`. Then read the task-bound status to confirm it is settled and has no active or pending work, and independently verify task-owned resource release. A receipt or timeout does not prove settlement. If status is unsatisfied or unobservable, report it and follow the existing control protocol; do not repeatedly settle on that basis. Never stop shared services or delete unrelated resources. A timeout alone is not a reason to interrupt or relaunch.
