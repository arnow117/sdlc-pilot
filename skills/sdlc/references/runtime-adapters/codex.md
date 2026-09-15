# Codex runtime adapter

> distilled-from: session:sdlc-codex-compat-2026-06-17
> updated: 2026-09-15

This reference maps the portable protocol to currently available Codex tools. It
does not define lifecycle, dispatch, result, acceptance, or checkpoint semantics;
[`stage-agent-protocol.md`](../stage-agent-protocol.md) is authoritative.

## Interface map

| SDLC need | Codex implementation | Fallback |
|---|---|---|
| Start one bounded child | `spawn_agent` with the complete current brief | Main Agent runs the stage serially inline and discloses it |
| Correct a child contract | `followup_task` with a complete `supersedes` brief after a material change | Start a later serial child only after the prior result is summarized |
| Routine clarification or constraint | `send_message` when it does not alter the brief | Include it in the next complete brief |
| Wait for a result | `wait_agent` | Use the runtime's interruptible wait |
| Stop an active child | `interrupt_agent` | Disclose that no stop control is available |
| Inspect active agents | `list_agents` only for a user status request, interruption recovery, or necessary diagnosis | Do not poll after a normal wait timeout |
| Read-only inspection | Parallel tool calls are allowed when independent | Run `rg`, `sed`, and `git` reads serially |
| File edits | `apply_patch`; use project scripts for defined mechanical changes | Avoid ad hoc shell writes |
| User choice | Structured input when exposed and appropriate | Numbered plain-text choices |
| Independent review | A fresh direct child selected by the main Agent | Serial review labeled as a fallback, never independent |

`spawn_agent`, `followup_task`, `send_message`, `wait_agent`, `interrupt_agent`,
and the limited `list_agents` use above are communication controls, not a message
system. Do not create an inbox, result directory, local state, or mandatory
task-card file around them. The main Agent uses one child for actual stage work by
default; a child never creates its own children. The main Agent, not the child,
applies the canonical protocol when it permits bounded analysis or parallel work.

[`templates/TASK.md`](../templates/TASK.md) is an optional brief/result message
shape. Pass it directly to a child; do not persist it as a Plan, task card, or
progress file.

## User choices

When structured input is unavailable, use:

```text
我需要你选一个：
  1) 选项 A — 说明
  2) 选项 B — 说明
回复编号即可。
```

- Ask only when the choice materially changes scope, behavior, or external effects.
- In non-interactive execution, do not guess risk acceptance; report the missing decision.
- Do not run two active feedback channels at once.

## Handoff and discovery

The authoritative recovery sources are the state CLI, Plan/context, and Git. A
handoff message is only a short summary; use the protocol's checkpoint only when
its pause/recovery conditions apply.

For repository-local Codex discovery, maintain `.agents/skills/sdlc*` symlinks
pointing to the writable source or installed skill directories. Verify their
targets after adding or changing links. A new Codex session may be required before
discovery refreshes.
