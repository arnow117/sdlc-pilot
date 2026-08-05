---
name: sdlc-product-design
description: >
  产品设计生命周期：用 BDD 与战略 DDD 澄清问题、行为、领域、体验和产品质量。
  默认显式调用是 Phase 1 preview；只有携带 --authority dual-lifecycle-v1 的调用才写 canonical ProductDefinition/
  ProductContract/Approval ledger。两者都不替代既有 sdlc-spec 的默认 legacy 路由。
---

# sdlc-product-design

在产品侧澄清“为什么做、给谁做、外部行为和约束是什么”。阶段选择、角色义务和完成条件由固定的
PolicyManifest / PhaseContract 决定；本 skill 不维护第二份规则。

## Phase 1 边界

只在调用者明确选择 preview 后运行。先确认以下输入均可识别：目标仓库、`lifecycle_run_id`、固定的
`policy_manifest_id`、请求意图，以及要解析的 phase/operation。缺任一项时只报告诊断，不补猜状态。

- 所有新输出仅能写到 `.sdlc/preview/<run-id>/`，并固定 `scope=preview`。
- 不创建或修改 `.sdlc-control/`，不修改 `.sdlc/STATE.md`，也不改 legacy `.sdlc/spec.md`、`.sdlc/plan.md`。
- preview 的 Context、Obligation、attestation 和 phase intent 都不能供 control、validate、review 或 ship 消费。
- legacy spec 只能作为观察输入；它不是 `ProductContract`，更不能被转换为 `EngineeringSpec` 或 dual approval。
- `unknown` / `needs_classification` 只形成待澄清项，不能改变 legacy 路由、退出状态或权威写入。
- 在飞 preview 若必须采用新 PolicyManifest，只能调用
  `migrate-preview-policy(expected_head, old_policy_manifest_ref, new_context_manifest, new_policy_manifest, actor, reason_ref)`：
  runtime 以 expected-head CAS 写入迁移审计，并按新 policy 重新生成未完成义务。任何 policy ref 不匹配都停止执行。

既有 `/sdlc spec` 仍是 Phase 1 的 canonical 路径。本 skill 不主动从 driver 接管它；只有 runtime 的显式
shadow 调用才可以并行生成 preview 诊断。

## 执行协议

1. 读取 `../sdlc/references/lifecycles/product-design.md`，并按 PolicyManifest 选中的 module anchor 加载最小正文。
2. 从 PhaseContract 取得 `phase_contract_ref`、输入契约、role obligations 和 completion assertions；不要从文件路径推断业务意图。
3. 执行选中的 BDD / DDD / 体验 / 质量方法，保留 `SCN-*`、`TERM-*`、`RULE-*`、`EXP-*`、`NFR-*`、`EVAL-*` 的稳定 ID。
4. 语义结论使用具名 typed attestation，至少绑定 actor、subject、scope、claim、evidence refs、policy 和 phase ref。它是输入，不是机械完成事实。
5. 输出 preview-only phase intent、选中模块、待澄清项和适用的 preview attestation；不提交 transition，不更新任何批准或合同 head。

## 产物语义

Phase 1 可以产生候选产品定义、结构报告或 parity diagnostic，但必须保留 `scope=preview`。产品批准只能在
后续 canonical control 已实现时由授权流程写入；当前最多记录 `legacy_approval_observation`，它只服务于
compatibility 比较，不能完成 approval obligation。

详情和稳定 anchors 见
[`product-design.md`](../sdlc/references/lifecycles/product-design.md)。产品 owner / 领域专家的长期判断视角见
[`product-owner.md`](../sdlc/references/roles/product-owner.md) 与
[`domain-expert.md`](../sdlc/references/roles/domain-expert.md)。

## Canonical authority 模式

只有调用者明确给出 `--authority dual-lifecycle-v1` 时进入此模式；它不能从 preview、legacy spec、文件路径
或旧 STATE 猜出。先读取
[`dual-lifecycle-runtime.md`](../sdlc/references/dual-lifecycle-runtime.md)，并以 ledger `status` 的 exact snapshot
SHA 作为这次 intent 的比较对象。

产品侧按 `create_product_definition → start_product_definition → submit_product_contract → request_approval →
adopt_product_contract` 顺序提交独立、可重试的 intent。每个 intent 有稳定 idempotency key；CAS 冲突后重新读取
状态，不重放过期上下文。`register_requirement` 只保存产品级依赖元数据，不能被工程任务状态替代。

成功采用后，ProductDefinition 的 current tuple 才可供未来 `claim_feature` 使用。新合同不会自动修改在途 Feature；
要采用它必须通过 Feature 级 accepted ChangeRequest 和 `adopt_feature_product_contract`。产品侧只读取交付投影，
不能直接变更 Task、Evidence、validation、review 或 release。
