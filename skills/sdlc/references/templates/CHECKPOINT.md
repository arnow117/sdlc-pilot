<!--
恢复检查点。仅用于暂停、跨会话恢复、执行环境变化，或批准型重记的预写；
路径：.sdlc-v1/checkpoints/<feature-id>.md。
全文不超过 60 行，原位更新，Feature 完成后删除。只有主 Agent 可以创建、更新或删除；子 Agent 只能返回候选。
不要记录凭据、私密信息、不必要本地路径、聊天记录、Spec、当前有效方案全文或完整日志。
权威来源：../stage-agent-protocol.md#6-context-and-checkpoints
-->

# 恢复检查点：[填写：Feature ID]

## 定位

- Feature / branch / HEAD / workspace：[填写：恢复前必须核对的实际值；不确定写 `unknown`。]
- Task ID：[填写：当前 Task；没有则 `none`。]

## 已确认

- [填写：主 Agent 已接受的工作、实际命令与结果、已验证版本；没有写“尚未确认：原因”。]

## 未完成

- [填写：进行中、未接受、失败或受阻的工作和直接原因；没有写 `none`。]

## 下一步

- [填写：第一步操作、完成条件、必要验证和不能改变的约束；不要把预期结果写成已通过。]

## 必要引用

- [填写：恢复所需的 state、当前有效方案、上下文、Git、代码或证据路径；没有写 `none`。]

<!--
批准型重记预写时，在既有五节内补充下列事实，不新增章节：
- 定位：实际工作树、branch、HEAD、Requirement/Feature 身份和必要 Task；登记前的 spec_ready
  重记写明 Feature 尚未登记，并保存实际 Requirement 投影。
- 已确认：核准的验收点、路径集合及每个路径的 context-v1 digest、相关 validation/交付 commit。
- 未完成：待执行或结果仍待核对的重记及顺序；保留待恢复的旧 Review。
- 下一步：对应操作和读回条件。
- 必要引用：原快照、原批准正文、权限，以及实际旧评审的决定、reviewer 和证据。
原位追加简要条目，不覆盖既有未完成事项；无法在限制内无损保存时暂停该次重记。
-->
