<!--
可选的派工消息结构。直接发送给子 Agent；它不是持久化的 Task 卡、inbox、结果文件、当前有效方案章节或第二份进度记录。
使用前阅读阶段协议；复制到消息后删除本注释，避免来源相对路径进入目标仓库。

权威来源：../stage-agent-protocol.md
-->

## 派工：[填写：stage] / [填写：工作项]

用一份完整消息写清目标、范围、已定接口、写入边界、完成条件和必要验证。只列已获授权的 lifecycle transition；没有时保留空列表。

```yaml
stage: <onboard|backlog|product-design|spec|plan|build|validate|review|ship|evolve>
feature_id: <feature-id or not-applicable>
plan_task_id: <task-id or not-applicable>
goal: "[填写：当前要达成的可观察结果]"
out_of_scope: ["[填写：本次未授权或明确不做的工作]"]
settled_interfaces: ["[填写：已定 API/DTO/所有权/兼容性决定]"]
context_refs: ["[填写：项目/产品/工程上下文路径]"]
write_scope: ["[填写：允许写入的仓库相对路径]"]
dependencies: ["[填写：已解决的前置条件或外部依赖]"]
completion_conditions: ["[填写：可检查的完成结果]"]
required_verification: ["[填写：验收前必须执行的命令或证据]"]
expected_result: [changed_files, commands, revision, workspace_status, unresolved_items]
authorization: "[填写：已存在的授权，以及排除的外部操作]"
supersedes: <brief identifier or none>
allowed_transitions:
  [] # no lifecycle mutation for this brief
# 主 Agent 读取 `<operation> --help` 后，才可以列出已允许的请求：
# - operation: <lifecycle_state command>
#   required_arguments: [<exact-required-long-option-name>]
#   optional_arguments: [<exact-optional-long-option-name>]
# `--repo` 由主 Agent 固定，子 Agent 不能提供或覆盖。
```

仅在阶段协议定义的实质 contract 变化时使用 `supersedes`：
[stage-agent-protocol.md](../stage-agent-protocol.md#2-dispatch-contract)。替换消息仍须完整，简短说明变化，并用 `context_refs` 指向已有细节和证据。

## 子 Agent 结果

结果应报告实际改了什么、运行了什么、在哪个版本验证、工作区状态和未解项。只有主 Agent 接受结果；子 Agent 不使用 `completed`。

```yaml
stage: <stage>
status: <awaiting_acceptance | incomplete | blocked> # 待验收 | 未完成 | 受阻
artifacts:
  changed_files: []
evidence:
  commands:
    - command: <actual command>
      exit_code: <integer>
      result: <short observed result>
  revision: <tested commit or uncommitted snapshot>
  workspace_status: <git status summary>
context_updates:
  product: []
  feature: []
  project_candidates: []
unresolved_items: []
requested_transitions:
  [] # no lifecycle mutation requested
```

当完整 brief 已允许非空且有序的请求时，使用现有 CLI 值格式；不要新增字段或重新定义标量/重复值语义。

```yaml
requested_transitions:
  - operation: <lifecycle_state command>
    arguments:
      <exact-long-option-without-leading-dashes>: <value>
```
