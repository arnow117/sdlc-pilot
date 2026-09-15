<!--
Optional recovery checkpoint. Canonical rules:
../stage-agent-protocol.md#6-context-and-checkpoints
Path: .sdlc-v1/checkpoints/<feature-id>.md
Keep this file to 60 lines or fewer. It is updated in place and deleted when the
Feature completes. Only the main Agent creates, updates, or deletes it; a child may
return a candidate but never writes it. Do not put credentials, private material,
unnecessary local paths, chat history, a Spec, a Plan, or full logs here.
-->

# Checkpoint: <feature-id>

## 定位

- Feature / branch / HEAD / workspace: <values>
- Plan Task: <id or none>

## 已确认

- <main-Agent accepted work; command result; tested version>

## 未完成

- <in-progress, unaccepted, failed, or blocked item>

## 下一步

- <first action; completion condition; required verification; constraints that must remain>

## 必要引用

- <required state, Plan, context, Git, code, or evidence reference>
