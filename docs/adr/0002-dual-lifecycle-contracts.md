# ADR-0002: Separate Product Design and Software Delivery Lifecycles

- Status: accepted
- Date: 2026-08-04
- Updated: 2026-08-05

## 背景 / 问题

sdlc-pilot 当前以一条 Feature 主线同时承载产品塑形、领域/行为设计、技术规格、实现和验证。尽管已有多个阶段 skill，产品与工程内容仍集中在 monolithic spec、重复的阶段协议和带执行流程的 role cards 中，导致上下文加载偏大、方法职责含混，并且 control 无法证明 plan 实现的是哪一版获批产品意图。

## 决策

目标架构由一个 façade、两个 canonical 生命周期和三个正交能力组成：

- `sdlc` 仅负责 preflight、context resolve、路由、兼容和 handoff；它不是生命周期，也不是已知精确入口时的强制依赖；
- `sdlc-product-design` 以 BDD 与战略 DDD 为主，产出 Requirement 级、内容寻址、不可变且可审批的 ProductContract；
- `sdlc-software-delivery` 以 SDD 与 TDD 为主，消费固定的 ProductContract revision，产出 Feature 级 EngineeringSpec、Plan、实现和 Evidence。
- `sdlc-onboard`、`sdlc-backlog`、`sdlc-ship` 分别保持项目画像、需求集合和发布能力的正交边界。

两条生命周期只通过带 stable criterion IDs 的 versioned contracts 和显式 ChangeRequest 交换状态。BDD/DDD/SDD/TDD 的完整方法和角色动作保存在 lifecycle phase Playbook；角色卡只保存稳定专业视角。每个阶段由机器可读 PhaseContract 绑定输入、方法模块、required/conditional roles、obligations、输出、完成断言、Evidence 和转换语义。

执行体系分三层：Engine code 执行确定性解析、校验、采证和状态转换；versioned Policy 声明阶段、模块、角色和义务；Playbook + typed attestation 承载产品、领域和架构语义。Policy 编译为内容寻址 PolicyManifest，并按 product authoring run / software contract generation 固定其 hash；中途变化必须显式迁移。Resolver 生成 ContextManifest + ObligationManifest，required obligation 不得静默消失，unknown selector 必须请求分类。

模型/用户提交的 intent 只能请求选择或转换，不能自报客观完成。`tests_passed`、`approved`、`review_complete` 必须分别从 runner Evidence、有效 ApprovalHead 和当前 Feature fence 上的 review attestation 派生；review attestation 必须由配置的 reviewer policy 创建，并完整引用当前通过的 Evidence。语义充分性仍由具名角色的 typed attestation 承担。

Approval principal/role 由 authority-mode-specific adapter 解析并按 authorization/assurance policy 检查，caller 不能自报。每个 lifecycle run 通过 CAS-controlled ObligationHead 指向最新 immutable obligation revision；输入变化先重新 resolve 并单调合并义务。`contract_model` 只允许受审计的 `legacy → dual-lifecycle-v1` 升级，禁止 dual Requirement/Feature 降级绕过合同链。

合同 bundle 使用完整 SHA-256 identity；Approval 使用每 subject 唯一的 CAS-controlled head；Feature 通过 monotonic contract generation 使旧 Plan/Task/Evidence 不能在合同变更后重新成为当前证据。

迁移分两批：第一批以 shadow/compatibility 方式抽取 modules/PhaseContracts、编译 PolicyManifest、生成 Context/Obligation Manifests 并做旧行为 parity，旧阶段入口仍是 canonical；第二批完成 mixed-v1/v2 control、canonical transition reducer、Approval/ChangeRequest 和旧客户端 fail-closed 后，才激活两个新 canonical 入口。

Phase 1 的 Policy/Context/Obligation/transition 结果只用于比较和测量，权威 mutation 仍走现有 control；Phase 2 后旧 adapters 才统一进入新的 Obligation 和 transition 管道。ContextManifest 与 ObligationManifest 按单向引用生成，避免 content-addressed hash cycle。

Phase 1 另有不可跨越的 compatibility boundary：preview 记录只写入 `.sdlc/preview/<run-id>/`，并带
`scope=preview`。它们不能更新 legacy STATE、不能作为 control Evidence/Approval/Review/Ship 的输入，也不能
阻断旧路径的 mutation；unknown 或 incomplete preview obligation 只产生诊断。`legacy-composite-v1` 只把 legacy
spec approval observation 映射为 legacy plan rendering，绝不伪装为 EngineeringSpec 或 dual approval。无语义
intent 的 legacy 调用只重放旧 diff/glob 技术路由，语义选择保持 advisory。

每个 preview run 固定 PolicyManifest；中途变更只能经 CAS-protected、具名 actor/reason 的 preview policy
migration 完成。旧 canonical entry 保持默认路径，直到 deterministic direct/driver/resume parity matrix 完成，且后续
真实 baseline/candidate 行为 Eval 获得单独授权。

由于 Skill、Playbook 与 Context Pack 会改变 agent 的实际指令面，迁移不能只验证确定性 resolver。固定 reference dataset 必须对 legacy baseline 与 dual-lifecycle candidate 做多次行为回归：机械契约由代码断言，产品/领域/工程语义由经人工校准的独立 evaluator 判断；任何伪造完成、遗漏 required obligation、静默跨生命周期写入或 stale Evidence 均直接失败。

## 备选与否决理由

### 继续保留八阶段，只把 SKILL.md 缩短

否决。它可以降低单文件体积，但没有改变产品合同、工程规格和控制账本的责任边界；薄 adapter 若总是加载同一批 references，也不会降低实际上下文。

### 把 BDD、DDD、SDD、TDD 各做成独立 skill

否决。方法论会变成四条重复编排链，状态、审批、产物和失败恢复重新分叉。它们应是生命周期内的条件模块和追溯协议。

### 继续靠 SKILL/role 自然语言约定阶段责任

否决。自然语言适合保存方法和语义判断，但不能可靠执行状态转换、required role/obligation、跳过审计、证据新鲜度和上下文依赖闭包。采用 PhaseContract + ObligationManifest + typed attestation：代码检查可观测谓词，角色承担语义结论。

### ProductContract 继续绑定 Feature

作为第一批迁移兼容行为接受，但不作为目标模型。Feature claim 属于工程交付 ownership；产品探索必须能够先于 claim 存在，因此目标模型把 ProductContract 绑定 Requirement，并在 claim 时复制固定 tuple。

### 一次性升级全部 control schema

否决。现有 Evidence 不可变且不能整体重写。采用 mixed record schema：历史 immutable records 保持 v1，显式升级的 Requirement、dual Feature/Task/Evidence 和新 contract records 使用 v2；旧 strict-v1 客户端因此 fail closed，新 reader 同时支持 v1/v2。配合 per-artifact format 和显式 `contract_model` 分批启用。

## 退化 / 保留

退化：

- Phase 2 激活后，公开拓扑从原有 driver + 8 阶段模型变为 1 façade + 2 lifecycle + 3 orthogonal capabilities，并额外保留 5 个 compatibility adapters；短期文件数量增加。
- 合同审批和 ChangeRequest 增加控制事务与 schema 复杂度。
- Policy/PhaseContract/Obligation schema 与 compiler 增加工程维护成本。
- 语义 intent 和 attestation 需要用户/模型明确声明，无法完全由代码自动路由或裁决。
- 纯文件默认只能提供 audit-level principal assurance；需要不可抵赖身份的环境仍须配置签名或外部认证 adapter。

保留：

- shared-control/local-serial/legacy authority 模型；
- immutable plan、Task、Evidence 与 integration SHA freshness；
- 旧命令、旧 STATE、旧 records 的读取能力；
- text_mode、Task-or-sequential、纯文件和单写者原则；
- validate modes、language packs、deploy targets 的单一事实源。

## 架构影响 / 后果

正向：

- 产品上下文与工程上下文可以独立加载、独立审批和独立恢复；
- BDD/DDD/SDD/TDD 有明确主要归属，同时保留跨生命周期 trace；
- 每个阶段的角色、动作、产物和完成责任可由代码检查，不再依赖模型记住整份流程；
- 工程实现无法静默改变产品意图，spec gap 有结构化反馈路径；
- context bytes、module/role/obligation selection、Policy identity 和 diff identity 可以被代码测量与回归。
- Skill 行为回归同时覆盖确定性契约和非确定性语义，结构减载不能用交付质量退化换取。

代价与风险：

- 需要处理 ProductContract/EngineeringSpec/Approval/ChangeRequest 的 CAS、失效与 legacy migration；
- compatibility view 可能在迁移期继续加载较多上下文，必须明确其临时性质；
- Policy 配置错误可能漏载模块或责任，必须用 compiler、唯一 rule ID、fail-closed selector、parity fixture 和 byte budget 共同约束；
- typed attestation 只能提供可审计语义结论，不能被误当成可重放的客观 Evidence；
- canonical runner 当前仅执行 DeliveryPlan 中完全固定的 TDD argv/cwd；其他 evidence strategy 先保留在 preview，后续需以同样的命令身份与 receipt 规则扩展；
- ObligationHead、Context freshness 与 Policy migration 增加 run-level CAS/reconcile 测试要求；
- baseline/candidate 多次运行和 evaluator 人工校准增加评测成本；
- mixed-v1/v2 reader、approval reducer 与 contract generation 增加控制面复杂度，必须先证明旧客户端无法绕过；
- Requirement 级产品 ownership 暂未纳入第一批实现，并发产品塑形先保持单 orchestrator。
