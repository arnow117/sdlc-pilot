---
name: sdlc-software-delivery
description: >
  软件交付生命周期：以 SDD、TDD 和按需的架构、领域、可靠性方法处理 EngineeringSpec、DeliveryPlan、实现、验证、评审和发布准备度。
  默认显式调用是 Phase 1 preview；只有携带 --authority dual-lifecycle-v1 的调用才写 canonical ledger。
  不替代既有 sdlc-plan、sdlc-build、sdlc-validate 或 sdlc-review 的默认 legacy 路由。
---

# sdlc-software-delivery

在工程侧把已定义的产品意图转为可实现、可验证、可运维的交付设计。阶段选择、角色义务和完成条件只来自
PolicyManifest / PhaseContract；本 skill 不复制这些规则。

## Phase 1 边界

只在调用者明确选择 preview 后运行。先确认目标仓库、`lifecycle_run_id`、固定的 `policy_manifest_id`、
operation、phase 和输入 artifact identity；缺失或不匹配时只返回诊断。`implement` 还必须显式给出
`evidence_strategy`（`tdd | static-check | contract-check | visual-regression`）和 `issue_class`
（`none | regression | runtime_error | unexpected_failure`）；缺失时返回 `needs_classification`，不按路径猜测。

- 所有新输出仅能写到 `.sdlc/preview/<run-id>/`，并固定 `scope=preview`。
- 不创建或修改 `.sdlc-control/`，不修改 `.sdlc/STATE.md`，不改 legacy `.sdlc/spec.md` / `.sdlc/plan.md`，不执行实现写入、部署、发布或回滚副作用。
- 若 preview runtime 提供安全 Evidence runner，只能按明确 argv / cwd / timeout 运行诊断性测试；其结果仍是不可消费的 `scope=preview` 输出。
- preview 的 Context、Obligation、Evidence、attestation 和 readiness package 不能供 control、validate、review 或 ship 消费。
- `plan`、`implement`、`validate`、`review` 的 canonical 输入是获批 `EngineeringSpec`。Phase 1 尚无此 control artifact 时，只能报告所缺条件。
- legacy spec 不是 `EngineeringSpec`。唯一兼容例外是 `legacy-composite-v1`，它只渲染 legacy plan 的 preview 诊断，不能完成 dual approval 或产生 dual record。

既有 `/sdlc plan`、`/sdlc build`、`/sdlc validate` 和 `/sdlc review` 在 Phase 1 仍是 canonical 路径；本 skill
不会从 legacy driver 自动接管它们。

## 执行协议

1. 读取 `../sdlc/references/lifecycles/software-delivery.md`，仅加载 PolicyManifest 选中的 module anchor。
2. 从 PhaseContract 取得 `phase_contract_ref`、输入契约、role obligations、机械 assertions 和语义 attestation 类型。
3. 对可用的产品合同、工程输入、PROFILE snapshot、diff identity 和风险信号做 SDD/TDD 诊断；不要用路径猜测产品语义。
4. 把语义结论写为具名 typed attestation，至少绑定 actor、subject、scope、claim、evidence refs、policy 和 phase ref；模型自报的 `tests_passed`、`approved`、`review_complete` 不是 Evidence。
5. 仅输出 preview-only phase intent、选择理由、待补输入和诊断。不得提交 transition、注册 plan、更新 task/evidence 或写 release 状态。

## `legacy-composite-v1`

该兼容操作只能显式调用，并且只读 legacy `.sdlc/spec.md` 与 `legacy_approval_observation`。输出也只能是
preview 目录中的 legacy-plan rendering / parity diagnostic。它绝不创建 `EngineeringSpec`、`DeliveryPlan`、
Approval 或 Task，也不覆盖 legacy plan。

`release-candidate` 在任何阶段都只描述 readiness package；部署、发布和回滚由正交的 `sdlc-ship` 负责，
而 Phase 1 preview 连 readiness package 也只能是不可消费的诊断副本。

详情和稳定 anchors 见
[`software-delivery.md`](../sdlc/references/lifecycles/software-delivery.md)。

## Canonical authority 模式

只有调用者明确给出 `--authority dual-lifecycle-v1` 时进入此模式。先读取
[`dual-lifecycle-runtime.md`](../sdlc/references/dual-lifecycle-runtime.md)，再用 `feature-projection` 取得当前
Feature fence、Task 摘要和 ChangeRequest refs；只在需要注册新 artifact 时读取相应的不可变输入。缺任一项时返回缺失前置输入。

工程侧只消费已经固定到 Feature 的 ProductContract tuple，并按以下顺序提交 canonical intent：

```text
claim_feature → register_profile_snapshot → register_engineering_spec → request_approval
→ adopt_engineering_spec → activate_delivery_plan → transition_task / execute_task_evidence
→ validate_feature → submit_feature_review → publish_feature
```

`activate_delivery_plan` 同时绑定 current EngineeringSpec、generation 和完整 Task 集合；Markdown plan 只能是
兼容投影。每次 Task/Evidence/validate/review/ship 都携带 exact fence。revoke、accepted blocking
ChangeRequest、CAS 冲突或 stale generation 会停止当前动作，不能退回 legacy 操作绕过。

`execute_task_evidence` 由 ledger 发起 argv-only runner，并原子保存不可变 receipt；模型自报完成、普通 Markdown、
preview Evidence 或未绑定 trace 的记录均不能推进状态。工程侧发现产品规则缺口时创建 ChangeRequest，不能静默
改写 ProductContract。产品投影是只读输出，交付状态不会写回 ProductDefinition。

canonical runner 当前只支持 DeliveryPlan 中完整声明的 `tdd` strategy，并要求请求的 `argv` 与 `cwd` 完全匹配
Task 已固化的值；`static-check`、`contract-check`、`visual-regression` 和 typed attestation 仍可用于 preview
诊断，不能临时替换为一条 canonical 命令。review 使用 `submit_feature_review`：ledger 从 authority config 解析
reviewer 与 policy，attestation 必须引用当前 Feature 全部通过的 Evidence；调用方不能直接提交内部
`review_feature`、review ref 或 reviewer identity。
