# Software delivery lifecycle playbook

本文件保存软件交付方法，不定义阶段选择、角色基数、skip 语义或状态转换；这些规则只能来自
`references/policies/{modules,phases,roles}.json` 的编译结果。每个 `playbook-anchor` 是 policy 可引用的稳定文本。

## Phase 1 preview 约束

所有结果只写 `.sdlc/preview/<run-id>/` 并带 `scope=preview`。不得写 `.sdlc-control/`、legacy STATE、legacy
spec/plan 或业务代码；preview ref 不能作为 control、validate、review、ship 的输入。缺产品/工程契约、
policy 或语义意图时返回诊断或 `needs_classification`，不要猜测。

若 runtime 提供 argv-only 的安全 Evidence runner，可以运行明确的诊断性测试并保存 preview Evidence；它不注册
control Evidence、不修改实现、不执行部署/发布/回滚副作用。

<!-- playbook-anchor: delivery.engineering-spec -->
<!-- playbook-anchor: delivery.module.core-sdd -->
<!-- playbook-anchor: delivery.module.engineering-spec -->
## engineering-spec

Obligation refs: `obl.delivery.engineering-spec.trace`, `obl.delivery.engineering-spec.design`.

1. Canonical 输入是获批 ProductContract revision、PROFILE snapshot 和 repository base SHA。逐条把产品 criterion
   映射到 `ARCH-*`、`API-*`、`DATA-*`、`REL-*`、`SEC-*`、`TEST-*` 工程 criterion。
2. 明确目标 surface、接口兼容性、数据/迁移、可靠性、安全、可观测性、回滚和测试策略；每个取舍都连到上游
   criterion 或风险。
3. legacy `.sdlc/spec.md` 只能作为兼容观察，不是 EngineeringSpec。Phase 1 可以生成工程规格诊断候选，
   但不能创建 EngineeringSpec record、批准或下游输入。

<!-- playbook-anchor: delivery.module.architecture -->
### architecture（条件模块）

Obligation ref: `obl.delivery.architecture.design`.

当跨 surface、公共接口、数据模型或 blast radius 较高时，定义组件边界、接口 owner、兼容策略、数据流和 ADR
候选。把运行时约束和回滚路径写成可验证的工程 criterion，而不是泛化架构叙述。

<!-- playbook-anchor: delivery.module.tactical-ddd -->
### tactical-ddd（条件模块）

Obligation ref: `obl.delivery.tactical-ddd.mapping`.

当上游 `RULE-*` 需要领域模型表达时，映射 aggregate、value object、domain event、ACL 和持久化边界。它实现
产品侧的领域规则，不重新划定产品侧 bounded context。

<!-- playbook-anchor: delivery.module.reliability -->
### reliability（条件模块）

Obligation ref: `obl.delivery.reliability.design`.

仅在 `NFR-*`、资金/一致性风险或 `availability_critical` 存在时加载。选择 timeout、retry、幂等、隔离、
降级、容量、观测、恢复和演练机制，并把每项映射到 NFR 与 failure evidence。

<!-- playbook-anchor: delivery.plan -->
<!-- playbook-anchor: delivery.module.planning -->
## plan

Obligation ref: `obl.delivery.plan.delivery-plan`.

1. 只消费获批 EngineeringSpec。若没有获批 ref，停止在诊断，不能由 legacy spec 或 preview candidate 补位。
2. 输出 `DeliveryPlan`：静态 Task DAG、每项 write set、interface owner、依赖、criterion refs、测试/证据边界和
   execution mode。它不重复 ProductContract 或 EngineeringSpec 正文，也不保存 Task 运行状态。
3. 小改动仍保留 trace：计划可编译成单个 Task，但该 Task 仍绑定 EngineeringSpec criterion 和明确 evidence。

<!-- playbook-anchor: delivery.implement -->
<!-- playbook-anchor: delivery.module.implementation-tdd -->
## implement

Obligation ref: `obl.delivery.implement.tdd`.

1. 对可执行行为使用 RED → GREEN → REFACTOR：先让与 criterion 绑定的测试失败，再实现最小变更、最后重构并
   采集 command / exit code / tested SHA 等机械事实。
2. 预期 RED 是 TDD 的正常输入，不加载 debugging。只有 `unexpected_failure`、`regression` 或 `runtime_error`
   才选择 debugging。
3. 文档、纯声明配置或纯视觉调整必须选择明确替代 Evidence，而不是笼统跳过测试。

<!-- playbook-anchor: delivery.module.static-check -->
<!-- playbook-anchor: delivery.module.contract-check -->
<!-- playbook-anchor: delivery.module.visual-regression -->
### 替代 Evidence（条件模块）

Obligation refs: `obl.delivery.implement.static-check`, `obl.delivery.implement.contract-check`,
`obl.delivery.implement.visual-regression`.

`static-check` 适用于可解析的文档或配置规则；`contract-check` 适用于 schema/API/声明一致性；
`visual-regression` 适用于仅视觉调整。每个替代项都要有执行命令、输入 scope、预期结果和当前 SHA，不能把
“无需 TDD”当结论。

<!-- playbook-anchor: delivery.module.debugging -->
### debugging（条件模块）

Obligation ref: `obl.delivery.debugging.hypothesis-loop`.

固定现象与复现、列出可证伪假设、用最小实验收集证据、修复后回到相应 criterion 的测试与验证。不要在调试
循环中绕过规格差异；发现业务规则缺失时提出 ChangeRequest 返回产品侧。

<!-- playbook-anchor: delivery.validate -->
<!-- playbook-anchor: delivery.module.validation-review -->
## validate

Obligation refs: `obl.delivery.validate.mechanical-evidence`, `obl.delivery.validate.trace-freshness`.

1. 在当前 integration SHA 上运行适用的 correctness、contract、E2E、reliability 或 eval 检查，并记录 runner
   产生的 exit code、输出摘要、工具版本和 tested SHA。
2. 检查 Evidence 与 product/engineering/task criterion 的 trace、输入新鲜度、覆盖缺口和不支持的风险主张。
3. 模型或调用方写出的 `tests_passed`、`approved`、`review_complete` 不是 Evidence；机械事实只能由 runner、Git
   或 canonical record 派生。

Phase 1 只可形成 preview evidence diagnostic，不能更新 Feature evidence 或完成权威 validation。

<!-- playbook-anchor: delivery.review -->
## review

Obligation ref: `obl.delivery.review.independent-verdict`.

独立 reviewer 针对当前 diff、合同、计划、Evidence 和风险作出语义判断，输出可定位 finding、风险接受或
需要返工的原因。review 不修正实现，也不把自报结论升级为通过结果。Phase 1 的任何 review 结论仅为 preview
attestation，不能写 review status。

<!-- playbook-anchor: delivery.release-candidate -->
## release-candidate

Obligation ref: `obl.delivery.release-candidate.readiness`.

构造 readiness package：reviewed SHA、适用 Evidence、发布步骤、观测指标、告警、回滚条件和责任人。它不执行
部署、发布或回滚；这些副作用只属于正交的 `sdlc-ship`。Phase 1 只产生不可消费的 preview readiness diagnostic。

<!-- playbook-anchor: delivery.compatibility.legacy-composite-v1 -->
## legacy-composite-v1

Obligation ref: `obl.delivery.compatibility.legacy-composite`.

这是 Phase 1 唯一的 `spec → plan` 兼容桥。输入只能是已批准的 legacy `.sdlc/spec.md` 与
`legacy_approval_observation`，输出只能是 preview 目录中的 legacy plan rendering / parity diagnostic。
它不得创建或标记 EngineeringSpec、DeliveryPlan、Task、Evidence 或 Approval，不得完成 dual approval，
不得覆盖 legacy `.sdlc/plan.md`、STATE 或 control。

## Typed attestation 最小信息

每份语义结论至少包含 `type`、`subject_ref`、`scope`、`actor`、`claim`、`evidence_refs`、
`policy_manifest_ref`、`phase_contract_ref` 和 `issued_at`。runtime 校验引用、身份、独立性和新鲜度；本 playbook
只规定需要说明的工程判断。
