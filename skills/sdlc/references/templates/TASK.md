<!--
派工消息模板。直接发送给子 Agent；它不是持久化的 Task 卡、inbox、结果文件、当前有效方案章节或第二份进度记录。
用一份完整 brief 描述此次派工，不再复制一份相同的散文说明。复制到消息后删除本注释，避免来源相对路径进入目标仓库。

权威来源：../stage-agent-protocol.md
-->

## 派工：[填写：stage] / [填写：工作项]

### 使用说明

- `goal` 写可观察结果；`out_of_scope` 明确未授权范围；`settled_interfaces` 只写已定 API、DTO、所有权或兼容性合同。
- `context_refs` 指向当前项目、产品、工程上下文和已有证据；详细背景放在这些权威位置，不在 brief 重复粘贴。
- `allowed_transitions` 只列当前已获授权的、有序 lifecycle 请求；没有时保留空列表。`--repo` 由主 Agent 固定，子 Agent 不提供或覆盖。
- 模型选择与独立性由宿主 adapter 记录，不把 `qa`、`security` 等专业视角当作运行时角色。canonical 结果仍只使用本模板和阶段协议已有字段。
- 准备批次在同一原生消息中为每个阶段各附一份本合同；共享事实可引用，但每块保留自身的 `stage`、`write_scope` 和 `allowed_transitions`。完整规则见[阶段协议](../stage-agent-protocol.md#bounded-preparation-batch-for-small-projects)。

### 派工合同

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
expected_result: [changed_files, commands, revision, workspace_status, context_updates, unresolved_items, requested_transitions]
authorization: "[填写：已存在的授权，以及排除的外部操作]"
supersedes: <brief identifier or none>
allowed_transitions:
  [] # no lifecycle mutation for this brief
# 主 Agent 读取 `<operation> --help` 后，才可以列出已允许的请求：
# - operation: <lifecycle_state command>
#   required_arguments: [<exact-required-long-option-name>]
#   optional_arguments: [<exact-optional-long-option-name>]
# `--repo` 由主 Agent 固定，子 Agent 不能提供或覆盖。
# 请求中的 `arguments` 键只去掉当前 `--help` 长选项开头的 `--`，保留内部连字符（例如 `feature-id`、`task-id`）。
# 必填参数必须齐全，可选参数只有实际需要时才传入；不能猜别名、占位值或未知参数。
```

### 需要展开时的补充

仅在 YAML 字段不足以解释已定接口、风险、验证样例或局部限制时增加这一节；每条必须引用上面的字段或 `context_refs`，
不得再写一份完整派工正文。

| 字段或引用 | 仅补充的事实、限制或示例 |
|---|---|
| [填写：`settled_interfaces` / `context_refs` / `required_verification`] | [填写：必要细节；没有则 `none`。] |

仅在阶段协议定义的实质 contract 变化时使用 `supersedes`：
[stage-agent-protocol.md](../stage-agent-protocol.md#2-dispatch-contract)。替换消息仍须完整，简短说明变化，并用
`context_refs` 指向已有细节和证据。

## 子 Agent 结果

结果只报告实际观察到的变更和证据。只有主 Agent 接受结果；子 Agent 不使用 `completed`。

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
字段的机械排版归一、缺项更正和接受限制唯一遵循
[stage-agent-protocol.md](../stage-agent-protocol.md#4-results-transitions-and-correction)；不要用别名猜补参数或覆盖主 Agent 固定的仓库。

```yaml
requested_transitions:
  - operation: <lifecycle_state command>
    arguments:
      <exact-long-option-without-leading-dashes>: <value>
```
