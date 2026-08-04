---
title: SDLC control plane protocol
scope: shared execution ledger, branch binding, immutable evidence
schema-version: 1
updated: 2026-08-04
---

# SDLC control plane protocol

This reference is the single protocol used by `sdlc`, `sdlc-backlog`, `sdlc-plan`,
`sdlc-build`, `sdlc-validate`, `sdlc-review`, and `sdlc-ship`. Stage skills do not
invent their own Git transactions or lifecycle rules.

## 1. Execution modes

| Mode | Authority | Concurrency guarantee |
|---|---|---|
| `shared-control` | remote `sdlc-control` branch under `.sdlc-control/` | active claims are unique across clones through non-force fast-forward push competition |
| `local-serial` | local control worktree under `.sdlc-control/` | one local orchestrator; no cross-clone uniqueness claim |
| `legacy` | `.sdlc/STATE.md` plus the existing requirement tree | read-compatible behavior only; absence of control data never creates or migrates it |

`STATE.md` is a feature-session cache. In `shared-control` and `local-serial`, the
control records are authoritative whenever they disagree with local STATE.

## 2. Record layout and identity

All frontmatter is a strict, flat schema: scalar values and inline scalar lists
only. Every record contains `schema_version: 1` and `record_type`. Multiline action,
acceptance criteria, command, and output live in the Markdown body.

```text
.sdlc-control/
├── requests/<request-id>.md
├── requirements/<domain>/<subdomain>/<leaf-id>.md
├── claims/<leaf-id>.md
├── features/<feature-id>.md
├── features/<feature-id>/plans/<plan-content-id>.md
├── tasks/<feature-id>/<plan-revision>/<task-id>.md
└── evidence/<feature-id>/<task-id-or-_feature>/<tested-sha>/<evidence-id>.md
```

`evidence-id` is the first 16 hexadecimal characters of the canonical record
content SHA-256. IDs and paths must reject absolute paths, `..`, and path separators
inside a single ID.

## 3. Writers and transitions

| Operation | Single writer | Atomic record set |
|---|---|---|
| intake | backlog orchestrator | request + requirement leaf + `source_request` |
| deliver/claim | driver through the control adapter | active claim + feature |
| approved plan registration | plan orchestrator | immutable plan commit, then feature + tasks referencing that commit SHA |
| build/integration | feature integration orchestrator | task status, branch binding, source tip, merge method, resulting integration SHA, task evidence |
| validate | validation orchestrator | feature evidence tested at current feature integration HEAD |
| review | review orchestrator | reviewed HEAD and verdict; code edits invalidate prior validation |
| ship/retire | ship/backlog orchestrator | release evidence, leaf `shipped`, claim `released`, feature `shipped` |
| task agent | none | business code and local test output only; never STATE or control records |

Task lifecycle:

```text
waiting -> ready -> claimed -> in_progress -> awaiting_verification -> verified
   |          |          |          |                  |
   +----------+----------+----------+------------------+-> blocked -> waiting|ready
awaiting_verification -> in_progress
any nonterminal -> abandoned|superseded
```

Only tasks in the current `plan_revision` count. `superseded` tasks are excluded;
`abandoned` tasks prevent feature validation.

## 4. Git transaction protocol

Every shared write is prepared from an explicit `expected_control_sha`:

1. fetch `sdlc-control` and create an isolated control worktree at that SHA;
2. load and lint the complete snapshot;
3. apply one logical record transition and commit only `.sdlc-control/**`;
4. push `HEAD:sdlc-control` without force;
5. on rejection, fetch and re-evaluate the operation instead of replaying it blindly.

For claim competition, create the feature branch only after the control push wins.
If another active claim now owns the leaf, return its owner and feature ID and stop.
`claimed_base_sha` is the business feature base; `expected_control_sha` is the
control transaction base.

Plan registration uses two commits because a record cannot contain the SHA of its
own commit: commit A stores the immutable content-addressed plan; commit B creates
revision-scoped Task records whose `plan_revision` is commit A's SHA. A replan writes
a new plan artifact, supersedes nonterminal Tasks from the prior current revision,
and may reuse Task IDs because their paths include `plan_revision`.

## 5. Task branches and integration

`write_set` accepts repository-relative POSIX files or directory prefixes ending in
`/`; no globs, absolute paths, or `..`. Two sets overlap on exact match or directory
prefix coverage.

A task may use `execution_mode: task_branch` only when all conditions hold:

1. every `depends_on_tasks` task is `verified`;
2. its write set does not overlap another active task;
3. `interfaces_fixed: true` and shared interfaces have one declared owner;
4. `runtime_isolated: true`;
5. fewer than three task branches are active for the feature and no serial task is active.

Otherwise use `execution_mode: serial` on the feature branch. A serial task and task
branches are mutually exclusive. Task branches start from the current feature
integration HEAD. Integration is serialized; after rebase/squash/merge and targeted
retest, record both the task source tip and the resulting feature `integration_sha`.

The task worktree's read-only `TASK.md` records execution mode, feature/task/branch
identity, plan revision, control ref, and the control base SHA used for assignment.
It must not contain Feature STATE, and the Task agent never advances the control base.

## 6. Evidence and freshness

Evidence scope is `task | feature | release` and records are immutable. Identical
content is idempotent; an existing path with different content is an error. Task
verification requires passing task evidence whose `tested_sha` equals that task's
resulting `integration_sha`. Retire requires passing release evidence for the current
Feature integration SHA; merging a branch is not release evidence.

Freshness is derived, not manually assigned:

| Value | Meaning |
|---|---|
| `missing` | no passing evidence or no integration SHA |
| `fresh` | current HEAD equals the tested integration SHA, or later changes do not intersect the task write set |
| `stale` | later changes intersect the task write set |
| `unknown` | SHA is unreachable/not an ancestor or Git comparison failed |

A feature becomes `validated` only when it has a current plan with at least one Task,
all current non-superseded tasks are verified,
none is abandoned, and passing feature evidence has `tested_sha` equal to both the
recorded integration SHA and actual feature HEAD. `shipped` is written only from a
successful release/retire transaction, never inferred from `STATE.stage`.

Review writes `review_status`, `reviewed_sha`, reviewer, report refs, and timestamp to
the Feature record. Release requires `review_status: pass` at the current integration
SHA. Review fixes are registered as a new plan revision/remediation Task and repeat
build → validate → review; code edits never advance the Feature ledger directly.

## 7. Portable adapter contract

Resolve the installed `scripts/control.py` path; do not assume it exists in the target
repository. Operations emit JSON and use exit codes `0` success, `1` invalid schema or
transition, `2` missing input/path, and `3` concurrent-state conflict. Skills call the
adapter rather than editing control frontmatter directly. Every mutation requires
`--repo-root`, `--expected-control-sha`, and an explicit execution mode; raw
`--control-root` access is read-only. `register-plan` is the two-commit orchestration.

Architecture rationale: [`ADR-0001`](../../../docs/adr/0001-sdlc-control-branch.md).
