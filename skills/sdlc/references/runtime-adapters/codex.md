# Codex runtime adapter

> distilled-from: session:sdlc-codex-compat-2026-06-17
> updated: 2026-08-10

This reference maps portable SDLC behavior onto Codex capabilities. Core lifecycle semantics do not depend on a particular agent runtime.

## Interface map

| SDLC need | Codex implementation | Fallback |
|---|---|---|
| User choice | Use structured input when exposed and appropriate | Numbered plain-text choices |
| Independent subwork | Use multi-agent tools for concrete disjoint tasks | Run the same steps sequentially |
| Parallel reads | Parallelize read-only repository inspection | Sequential `rg`/`sed`/`git` reads |
| File edits | Use `apply_patch` for manual edits; use project scripts for defined mechanical changes | Avoid ad hoc shell writes |
| Long visual review | Use the available web review workflow | Plain-text findings |
| Non-interactive execution | Stop when a missing decision would change behavior or accept risk | Report the required input |
| Independent model check | Use another available model only when it is genuinely independent | Perform a separate inline pass |

## Stage and Task agent work

The canonical behavior is [`stage-agent-protocol.md`](../stage-agent-protocol.md).

1. The main Agent owns `next`, lifecycle mutations and `.sdlc-v1/state.json`; Stage and Task Agents never edit that file.
2. Dispatch one Stage Agent with a self-contained brief, verify its artifacts and evidence, apply its ordered requested transitions, then call `next` again.
3. Read-only exploration can run in parallel. Write work needs disjoint paths, explicit interfaces and isolated runtime resources; otherwise continue serially.
4. Give review to a fresh Agent separate from the implementer when possible. If unavailable, run the review serially and disclose that fallback.
5. When multi-agent tools are unavailable, perform the same stage inline. SDLC behavior must not depend on a particular runtime.

The optional brief/result structure is in `templates/TASK.md`. It can be embedded in the Feature engineering context or passed directly to a sub-agent; it is not a separate progress file.

## User choices

When structured input is unavailable, use:

```text
我需要你选一个：
  1) 选项 A — 说明
  2) 选项 B — 说明
回复编号即可。
```

- Ask only when the choice materially changes scope, behavior or external effects.
- In non-interactive execution, do not guess risk acceptance; report the missing decision.
- Do not run two active feedback channels at once.

## Handoff

Progress is already queryable through `lifecycle_state.py`. A handoff message should be a short projection, not another stored record:

```text
Requirement: <id> (<status>)
Feature: <id> (<status>)
Branch: <branch>
Validation commit: <sha or none>
Product context: <path>
Engineering context: <path>
Next action: <stage and concrete task>
```

Cross-machine handoff also states the Git remote/ref to pull. Do not duplicate this message inside `state.json`.

## Discovery

For repository-local Codex discovery, maintain `.agents/skills/sdlc*` symlinks pointing to the writable source or installed skill directories. Verify their targets after adding or changing links. A new Codex session may be required before discovery refreshes.
