# Canonical dual-lifecycle runtime

直接调用者显式选择 `--authority dual-lifecycle-v1`，或 façade 已读取并固定
`.sdlc/lifecycle.json=dual-lifecycle-v1` 时加载本文件。legacy profile 下的旧命令继续使用固定 legacy runbook；
没有 profile 的既有 artifact 必须先迁移，不能凭 ledger 存在性切换；`preview` 继续只写 `.sdlc/preview/<run-id>/`。

## Authority and transport

canonical state 只存在于目标仓库的 `.sdlc-control/dual-lifecycle/ledger.json`。所有状态转换都通过：

```sh
python3 <sdlc-pilot-root>/scripts/dual_ledger.py --repo <target-repo> status
python3 <sdlc-pilot-root>/scripts/dual_ledger.py --repo <target-repo> apply \
  --expected-sha <exact-current-snapshot-sha-or-absent> \
  --idempotency-key <stable-request-id> \
  --intent-file <canonical-intent.json>
```

`status` 返回当前 snapshot identity。每次 `apply` 都必须回显这个 identity；冲突时重新读取状态、保留
原 intent，并由调用者决定是否重试。不要直接编辑 ledger JSON，也不要把 Markdown、STATE 或模型自报的
`approved/tests_passed/review_complete` 当成转换依据。

读取时优先使用 projection，而不是 `status --include-snapshot`：

```sh
python3 <sdlc-pilot-root>/scripts/dual_ledger.py --repo <target-repo> \
  feature-projection --feature-id <feature-id>
```

该输出只含当前 Feature 的 fence、Task 摘要、当前通过 Evidence refs、review attestation ref 和 ChangeRequest refs；
不返回合同正文、组件字节或历史 runner/release receipt。提交 `submit_feature_review` 时直接使用其中的
`review_evidence_refs`，不要自行从 Markdown 或旧 Evidence 猜测。需要产品侧视图时使用本文件末尾的
`product-projection`。

首次进行 canonical approval 前，目标仓库必须已有严格 JSON 的
`.sdlc-control/dual-lifecycle/authority.json`。可从
[`dual-authority.example.json`](dual-authority.example.json) 复制结构并替换实际 principal、roles 与 policy；
该文件属于 local-serial runtime authority，不应提交到源码。ledger 只从该文件解析 principal/policy，拒绝
intent 中的 identity、role、policy 或 predecessor。公开 intent 使用 `request_approval`，而非内部的
`apply_approval`；ChangeRequest 的 accept/reject/cancel 同理使用由 authority config 派生的决定操作。Feature
review 需要额外配置唯一的 `subject_type=feature_review`、`scope=feature` policy，并使用
`submit_feature_review`；内部 `review_feature` 不能由普通调用方提交。

intent 必须含 `operation` 和该 operation 的完整结构化输入。`lifecycle_reducer.py` 是唯一的状态规则
实现；ledger 负责 strict JSON、CAS、幂等、event 与 snapshot 的原子持久化。

产品合同、PROFILE snapshot 与 EngineeringSpec 的注册请求必须同时带 bundle 和原始 `components`；ledger 会保存
其不可变 artifact envelope，并在采用或查询 readiness 时重新校验。只提供 SHA 或 Markdown 引用的请求会被拒绝。

## Product design sequence

产品侧只写 ProductDefinition / ProductContract / Approval：

```text
register_requirement (optional product metadata)
→ create_product_definition
→ start_product_definition
→ submit_product_contract
→ request_approval
→ adopt_product_contract
```

`ProductContract` 必须是不可变 bundle，具有完整 SHA-256 identity，包含稳定的 `OUT-*`、`SCN-*`、
`RULE-*`、`TERM-*`、`NFR-*` 等引用。BDD/DDD 的语义判断以具名 attestation 留痕；审批身份和角色由
approval adapter / authorization policy 验证，不能由调用方声明。

批准新 ProductContract 只影响未来 Feature claim。正在交付的 Feature 要采用新版本时，必须有该
Feature 的 accepted product ChangeRequest，并通过 `adopt_feature_product_contract` 原子完成采用和失效。

## Software delivery sequence

软件交付只写 Feature / EngineeringSpec / DeliveryPlan / Task / Evidence / ChangeRequest：

```text
claim_feature
→ register_profile_snapshot
→ register_engineering_spec
→ request_approval
→ adopt_engineering_spec
→ activate_delivery_plan
→ transition_task / execute_task_evidence
→ validate_feature
→ submit_feature_review
→ publish_feature
```

每个 delivery intent 都必须携带当前 `fence`：ProductContract approval、EngineeringSpec approval、
DeliveryPlan 与 `contract_generation` 的完整 tuple。当前 tuple 变化、approval revoke、accepted blocking
ChangeRequest 或过期 CAS 都会拒绝后续 Task、Evidence、验证、评审和发布写入。

`activate_delivery_plan` 是唯一能同时绑定当前 EngineeringSpec 与完整 Task 集合的操作。`plan.md` 只是
由 immutable DeliveryPlan 渲染的兼容视图；不能反向解析为 plan 输入，也不能靠编辑 checkbox 改状态。

`activate_delivery_plan` 会把每个 Task 的 `execution_mode` 与 `evidence_strategy` 固定到当前 generation。canonical
runner 执行完整声明的 `tdd`、`static-check`、`contract-check` 与 `visual-regression` strategy（`argv` 与仓库相对
`cwd`）；typed attestation 仍是语义输入，不能由调用方临时换一个命令作为 canonical Evidence。`execute_task_evidence` 只接受与该 Task 完全一致的
`argv` 和 `cwd`，从实际退出码与 timeout 派生结果，随后将完整 receipt、tuple 与 trace 原子写入。

runner 启动前会记录当前工作区指纹，结束后再次计算。执行期间若变更 tracked 或非 ignored 的 untracked
源码，Evidence 或 release 不会写入；用于发布的 build artifact 应放在 Git ignored 的输出目录，不能依赖执行命令
修改源码来通过检查。`publish_feature` 同样必须产生当前 tuple 的 release receipt。两者的内部 reducer operation
不接受普通调用方自建的 `result`、receipt ref 或 release ref。发布还要求当前 generation 已验证、review 已批准且
不存在 blocking ChangeRequest。

在调用外部 runner 或发布命令前，ledger 会 fsync `.sdlc-control/dual-lifecycle/execution.json`。若命令失败、超时、
工作区指纹不一致或进程在 ledger 持久化前中断，该 journal 会保留，后续写入和相同 key 的重试都会返回 recovery-required。
这是为了避免不确定的外部副作用被静默再次执行；维护者必须先核对目标环境和 ledger，再按项目的运维恢复流程处理。
唯一的自动清理情形是：同一 idempotency key 已有完全匹配、已持久化的 ledger event，却在清理 journal 前中断；
同 key 重试会验证该 event 并清除 journal，但不会再次运行命令。

`submit_feature_review` 创建的是不可变、内容寻址的 semantic review attestation：reviewer identity、role、
authorization policy、当前 Feature fence、decision、rationale 与 Policy/Context refs 都由 ledger 绑定。其
`evidence_refs` 必须精确等于当前 Feature 全部通过的 Evidence；因此它可以证明“谁基于哪一版实现和哪些测试结果
给出结论”，但不会把语义质量判断伪装为 runner 的客观输出。

两个公开执行请求的最小形状如下；`fence` 必须是当前 Feature 的完整 tuple。`cwd` 和 `artifact_path` 都是目标仓库
下的相对路径，ledger 会拒绝绝对路径、上跳路径和符号链接逃逸。

```json
{
  "operation": "execute_task_evidence",
  "feature_id": "FEAT-001",
  "task_id": "TASK-001",
  "fence": { "contract_generation": 0, "...": "current tuple" },
  "argv": ["python3", "-m", "pytest", "-q"],
  "cwd": ".",
  "timeout_seconds": 60,
  "policy_manifest_ref": "<sha256>",
  "context_manifest_ref": "<sha256>",
  "tool_version": "pytest-8",
  "at": "2026-08-05T10:00:00Z"
}
```

```json
{
  "operation": "publish_feature",
  "feature_id": "FEAT-001",
  "fence": { "contract_generation": 0, "...": "current tuple" },
  "release_target": { "environment": "staging", "target_type": "container", "target_ref": "registry.example/app" },
  "actual_release_artifact": { "artifact_type": "oci-image", "artifact_ref": "registry.example/app:1.2.3" },
  "artifact_path": "dist/release.tar",
  "argv": ["./scripts/deploy-staging"],
  "cwd": ".",
  "timeout_seconds": 60,
  "policy_manifest_ref": "<sha256>",
  "context_manifest_ref": "<sha256>",
  "tool_version": "deploy-adapter-v1",
  "at": "2026-08-05T10:00:00Z"
}
```

```json
{
  "operation": "submit_feature_review",
  "feature_id": "FEAT-001",
  "fence": { "contract_generation": 0, "...": "current tuple" },
  "decision": "approve",
  "evidence_refs": ["<every-current-passing-evidence-id>"],
  "rationale_ref": "<sha256>",
  "policy_manifest_ref": "<sha256>",
  "context_manifest_ref": "<sha256>",
  "at": "2026-08-05T10:00:00Z"
}
```

调用方不能传 `result`、`tested_sha`、`code_sha`、runner/release receipt、`release_sha` 或 artifact SHA。前者由
runner 的实际过程结果推导；后者由 ledger 读取当前 Git revision 和 artifact bytes 后生成。review request 也不能
传 reviewer identity、role、policy 或已有 attestation；它们只从 authority config 和当前 ledger state 派生。

## Product projection and compatibility

`product-projection` 是产品侧的只读交付视图：

```sh
python3 <sdlc-pilot-root>/scripts/dual_ledger.py --repo <target-repo> \
  product-projection --leaf-id <requirement-id>
```

它不授予 claim 或发布权限；ready queue 必须调用 reducer 的 product readiness。delivery transition 不得
改写 ProductDefinition 或 Requirement 的产品状态。旧 control、legacy STATE、固定 runbook 和 preview
输出与 canonical ledger 相互隔离。
