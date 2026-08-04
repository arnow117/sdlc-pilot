<!--
  TASK.md is local identity for a task worktree. It is read-only after creation.
  A task worktree must not contain `.sdlc/STATE.md`; the feature orchestrator owns STATE.
-->

# SDLC Task Context: <task-id>

execution-mode: shared-control | local-serial
feature-id: <feature-id>
task-id: <task-id>
feature-branch: <feature-branch>
task-branch: <task-branch>
worktree: <absolute-worktree-path>
branch-base-sha: <feature-integration-head-at-creation>
plan-revision: <control-plan-commit-sha>
control-head: <control-sha-used-to-create-this-context>
control-ref: <sdlc-control in shared-control; local ref/path in local-serial>
control-base-sha: <expected control SHA for the Task assignment>
owner: <agent-or-user>

## Allowed write set

- <repo-relative-file-or-directory-prefix>

## Contract

- Read the immutable plan and this task's action/acceptance criteria before editing.
- Edit only the allowed write set. If another file is required, stop and report it.
- Run the task's RED/GREEN tests and report exact commands, output, and task branch HEAD.
- Do not edit `.sdlc/STATE.md`, `.sdlc-control/**`, or another task record.
- Do not merge, rebase onto a moving feature branch, or mark the task verified.
