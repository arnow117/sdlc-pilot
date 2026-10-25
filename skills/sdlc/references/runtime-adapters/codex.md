# Codex runtime adapter

> distilled-from: session:sdlc-codex-compat-2026-06-17
> updated: 2026-09-15

This reference maps the portable protocol to currently available Codex tools. It
does not define lifecycle, dispatch, result, acceptance, or checkpoint semantics;
[`stage-agent-protocol.md`](../stage-agent-protocol.md) is authoritative.

## Interface map

| SDLC need | Codex implementation | Fallback |
|---|---|---|
| Start one bounded child | `spawn_agent` with the complete current brief | Only when the runtime cannot create a child, use the protocol's disclosed serial inline fallback, subject to target role requirements |
| Material child-contract change | `followup_task` with the concise, complete `supersedes` brief | Start a later serial child only after the prior result is summarized |
| Routine clarification, local correction, or in-scope repair | `send_message` to an active child; use `followup_task` when an idle child needs another turn | No `supersedes`; use the next normal message |
| Wait for a result | `wait_agent` | Use the runtime's interruptible wait |
| Stop an active child | `interrupt_agent` | Disclose that no stop control is available |
| Inspect active agents | `list_agents` once only for recovery after an actual runtime restart or connection failure, as required by the protocol's waiting-and-recovery rule | A user status request uses known evidence; do not inspect after a normal timeout |
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
shape. Pass it directly to a child; do not persist it as a current effective
solution, task card, or
progress file.

## Configured model routing

Read the target repository's active Codex configuration before dispatching. The
following mapping applies only when that configuration provides these roles and
model settings; an installation of this skill alone does not provide them.

| SDLC responsibility | Codex role | Configured model and effort |
|---|---|---|
| Product decisions, Plan acceptance, lifecycle acceptance, final acceptance | primary Agent | `gpt-6.1-sol` / `xhigh` |
| Actual Backlog → Spec → Plan preparation batch | fresh Sol stage child | `gpt-6.1-sol` / `xhigh` |
| One complete Build Task and its in-scope corrections | `worker` | `gpt-5.6-terra` / `xhigh` |
| Independent Validate of the current candidate | fresh `worker` distinct from the implementer | `gpt-5.6-terra` / `xhigh` |
| Independent read-only Review | `reviewer` | `gpt-6.1-sol` / `xhigh` |
| Ship execution after the required approval | Terra execution Agent selected for the accepted delivery unit | `gpt-5.6-terra` / `xhigh` |

The main Agent explicitly requests these roles when the runtime supports them and
records any deviation from the configured model or effort. If a required Terra
implementer or independent Terra validator cannot be created, it reports that
concrete limitation and does not silently substitute Sol work or call the outcome
independent. If an independent Sol reviewer is unavailable, it likewise discloses a
non-independent fallback. Authorized read-only analysis and simple documentation
work may still continue. The portable serial fallback describes topology only when
child creation is unavailable; it does not override the target's model routing or
formal independence requirement. A specialist card such as `qa` or `security`
remains an inspection lens; it is never a substitute for the runtime role or model
assignment above.

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

The authoritative recovery sources are the state CLI, the current effective
solution, relevant project/product/engineering context, and Git. A handoff message
is only a short summary; use the protocol's checkpoint only when its
pause/recovery conditions apply.

For repository-local Codex discovery, maintain `.agents/skills/sdlc*` symlinks
pointing to the writable source or installed skill directories. Verify their
targets after adding or changing links. A new Codex session may be required before
discovery refreshes.
