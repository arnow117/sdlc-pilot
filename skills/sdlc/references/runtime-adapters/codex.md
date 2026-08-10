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

## Multi-agent work

1. Fan out only concrete tasks that can proceed independently.
2. Read-only exploration can run in parallel even when writes cannot.
3. Write tasks need disjoint repository paths, explicit interfaces and isolated runtime resources.
4. Each Task receives a self-contained brief containing Feature ID, Task ID, branch, dependencies, write scope and completion conditions.
5. Task agents do not edit `.sdlc-v1/state.json`; the Feature owner updates status through `lifecycle_state.py`.
6. Task agents return changed files, commands run, result and source commit.
7. The Feature owner integrates one Task at a time and reruns checks on the resulting commit.
8. If independence becomes false, continue serially on the Feature branch.

The optional brief structure is in `templates/TASK.md`. It can be embedded in the Feature engineering context or passed directly to a sub-agent; it is not a separate progress file.

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
