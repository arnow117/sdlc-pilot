<!--
恢复检查点。仅用于暂停、跨会话恢复或执行环境变化；路径：.sdlc-v1/checkpoints/<feature-id>.md。
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
