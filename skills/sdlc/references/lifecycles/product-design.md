# Product design lifecycle playbook

> distilled-from: session:happycompany-sdlc-retro-2026-08-08

本文件保存产品设计方法，不定义阶段选择、角色基数、skip 语义或状态转换；这些规则只能来自
`references/policies/{modules,phases,roles}.json` 的编译结果。每个 `playbook-anchor` 是 policy 可引用的稳定文本。

## 对齐节奏与问题归属

产品对齐分为澄清和收敛两种工作方式。

1. 只有答案会改变产品定位、目标 outcome / actor、V1 范围、职责边界、不可逆决策或风险接受范围时，
   才逐题澄清；先读取已有 request、decision 和候选内容，不重复询问已有答案。
2. 核心边界稳定后，批量列出剩余问题、推荐默认值、依据、可逆性和归属，让用户只纠正例外。
   连续两次出现同类选择时，提炼为通用规则，不继续逐项询问。
3. 中间更新只报告新增、修改、延后和阻塞项；完整复述留到候选 ProductContract 生成时。
4. 用户已接受紧接着描述的同一动作时，不重复确认。若范围扩大、产生不可逆外部影响或 policy 要求
   正式 Approval，仍按授权和记录规则处理；自然语言认可不能替代 typed Approval。

未决项按责任归属处理：

| 内容 | 归属 |
|------|------|
| 用户结果、actor、外部可观察行为、领域不变量、V1 范围、用户可感知质量和风险接受范围 | ProductContract |
| 单个企业、能力或场景特有的 rubric、样本构成、阈值、观察周期和重大纠正规则 | 项目定义的领域评估规格（例如 Capability EvalSpec）；平台 ProductContract 只保留通用约束 |
| 存储结构、重试、隔离、幂等、容量实现和可观测性实现 | software delivery / EngineeringSpec |

不影响 ProductContract 且下游已有 owner 的问题，记录推荐默认值和归属后继续，不提前要求产品 owner
决定实现细节。

## Phase 1 preview 约束

所有结果都只能位于 `.sdlc/preview/<run-id>/` 且带 `scope=preview`。它们是诊断，不是 ProductContract、
Approval 或 control Evidence。不要写 `.sdlc-control/`、legacy STATE 或 legacy spec。语义不确定时输出
`needs_classification`，不要把缺失字段解释成 false。

<!-- playbook-anchor: product.discover -->
<!-- playbook-anchor: product.module.core -->
## discover

Obligation refs: `obl.product.discover.problem-frame`, `obl.product.discover.preservation`.

1. 把 request 收敛为问题证据、目标结果、actor、范围、非目标和成功信号；区分已有事实、假设与待验证问题。
2. 要求可观察 outcome，而不是实现方案。若已有行为不能改变，显式列出 preservation criterion。
3. 保留每个结论的来源和反例；没有证据的优先级或用户需求只能标为假设。

Preview 结果是问题框架和待澄清列表，不是需求状态或批准。

<!-- playbook-anchor: product.behavior-design -->
<!-- playbook-anchor: product.module.behavior-contract -->
<!-- playbook-anchor: product.module.behavior-bdd -->
## behavior-design

Obligation refs: `obl.product.behavior.scenario-contract`, `obl.product.behavior.example-mapping`.

1. 为每个外部可观察行为定义唯一的 `SCN-*`，包含 actor、前置条件、触发、可观察结果和失败/边界结果。
2. 对新行为、业务规则、状态转换、旅程变化或验收含糊之处使用 Example Mapping：先列规则、样例和问题，
   再把收敛的例子映射到同一组 `SCN-*`。Given-When-Then 是表达格式，不替代例子发现。
3. feature 记录目标行为；hotfix 记录 reproduction 与修复结果；remediation 或无行为变化工作记录 preservation
   criterion。三种情形都必须有至少一个可验证行为。

Preview 结果是 scenario/acceptance 候选和未决例子，不能作为测试通过或产品批准的替代。

<!-- playbook-anchor: product.domain-design -->
<!-- playbook-anchor: product.module.domain-ddd -->
## domain-design

Obligation refs: `obl.product.domain.model`, `obl.product.domain.sufficiency-attestation`.

1. 仅在术语冲突、复杂不变量、跨子域 ownership、重写或跨边界规则出现时加载战略 DDD。
2. 建立 `TERM-*`、`RULE-*` 和上下文图；对每个规则说明 owner、输入、例外、可观察后果和与 `SCN-*` 的关联。
3. 分析 bounded context 的职责、公开语言、集成关系和 anti-corruption boundary。不能因实现目录相邻就合并领域边界。

需要领域充分性的结论必须使用 `domain-model-sufficient` typed attestation；它不能由 schema 检查代替。

<!-- playbook-anchor: product.experience-design -->
<!-- playbook-anchor: product.module.experience-design -->
## experience-design

Obligation refs: `obl.product.experience.constraints`, `obl.product.experience.sufficiency-attestation`.

1. 仅在 IA、journey、交互、可访问性或 design-system 约束变化时加载本段。
2. 写出 `EXP-*`：入口、关键步骤、成功/失败/空态、恢复路径、辅助技术和不可接受体验。
3. 让体验约束引用相关 `SCN-*`，避免把视觉偏好伪装成无来源的工程任务。

体验充分性是语义判断，使用具名 attestation，并保留其依据与适用范围。

<!-- playbook-anchor: product.quality-design -->
<!-- playbook-anchor: product.module.product-eval -->
<!-- playbook-anchor: product.module.quality -->
## quality-design

Obligation refs: `obl.product.quality.nfr-contract`, `obl.product.quality.eval-contract`.

1. 对用户可观察质量目标定义 `NFR-*`：SLO、容量、合规、数据完整性、恢复目标和不可接受结果。
2. 对 AI 或非确定性输出定义 `EVAL-*`：任务边界、数据集来源、rubric、阈值、失败样本和人工复核要求。
3. 只定义产品结果与风险接受范围；冗余、重试、降级、容量实现和观测设计属于软件交付侧。
4. 标记敏感数据、信任边界或合规风险时，建立可追溯的 `SEC-*` 风险与验收 criterion；交付侧必须把它们落实为独立的安全 review 和 runner Evidence，而不是把安全当成可选备注。

没有质量或 AI 风险信号时不要补造模块；有信号但阈值未知时保持 `needs_classification`。

<!-- playbook-anchor: product.product-validation -->
<!-- playbook-anchor: product.module.product-validation -->
## product-validation

Obligation refs: `obl.product.validation.structural-check`, `obl.product.validation.semantic-attestation`.

1. 检查所有选择的 `SCN-*`、`TERM-*`、`RULE-*`、`EXP-*`、`NFR-*`、`EVAL-*` 是否唯一、可追溯且没有悬空引用。
2. 区分机械结构检查和语义判断。机械检查只报告 ID、引用、覆盖和输入完整性；产品充分性由具名角色提交
   `product-semantic-pass` 或相应 typed attestation。
3. 把开放问题、风险、缺失证据和不适用模块明确列出。不要用“未发现问题”替代结论依据。

Phase 1 的 validation 输出只能是 preview 报告和 attestation 候选，不能使任何 approval obligation 完成。

<!-- playbook-anchor: product.product-approval -->
<!-- playbook-anchor: product.module.approval -->
## product-approval

Obligation refs: `obl.product.approval.decision`.

1. 固定候选内容、来源和 policy/phase refs，供授权人判断 approve、reject 或 revoke 的对象边界。
2. 判断记录必须指出 subject、决策、actor、授权依据、证据 refs、风险接受范围和时间；决策语义不能从自然语言
   “looks good” 推断。
3. Phase 1 只能保存 `legacy_approval_observation` 或 preview approval diagnostic。它们不能成为 Approval、
   不得更新 approval head，也不得让下游 software delivery 视为已批准输入。

## Typed attestation 最小信息

每份语义结论至少包含 `type`、`subject_ref`、`scope`、`actor`、`claim`、`evidence_refs`、
`policy_manifest_ref`、`phase_contract_ref` 和 `issued_at`。runtime 负责校验引用、身份和新鲜度；本 playbook
只规定结论应解释的产品语义。
