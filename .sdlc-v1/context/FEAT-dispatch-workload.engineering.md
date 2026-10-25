# 工程上下文：FEAT-dispatch-workload 派工与证据减量

## 当前有效方案

### 架构设计

**关联产品上下文**：[REQ-dispatch-workload.product.md](REQ-dispatch-workload.product.md)；绑定范围、AC 和观察计划以该文件为准。
**工程上下文**：`.sdlc-v1/context/FEAT-dispatch-workload.engineering.md`。
**已确认需求**：产品文件中的用户原话及已批准规则、AC-1～AC-10；无未决产品选择。
**创建日期**：2026-10-25。**状态**：主 Agent 已接受，作为本次实施的当前有效方案。

#### 背景

在 `codex/sdlc-dispatch-evolve`、基线 `db023de9d64aeb92ddb1e064e88bdaf9353e49f3` 的隔离源码中修改技能规则。实施合同保留在本次本地工作区，未随源码分发；本方案完整描述实施约束，不依赖仓外文档补齐必须行为。后续发布授权见产品上下文的“发布授权补充”。

只读分析发现：现行 stage-agent-protocol 规定逐阶段派发；Codex adapter 尚无阶段模型映射；small-project-context 把同一 CLI 拆为两个 Task。`lifecycle_state.py:1445` 的 `next` 仅查看已登记 Task，部分登记即可返回 build。当前全局 `next` 更指向旧 `FEAT-branch-registration` 的 ship，而本目标 projection 已 ready、尚无 Feature；该旧目标不在本次授权内。现有 PROJECT 含历史版本、计数和证据，只能按来源适用性使用，不能冒充本候选通过。

#### 架构与组件

- **权威编排协议**：`skills/sdlc/references/stage-agent-protocol.md` 定义准备批次、接受/恢复、稳定索引刷新、证据适用和紧凑交付规则。状态仍只由主 Agent 通过现有 CLI 维护；不新增执行器、文件格式或状态字段。
- **入口与阶段方法**：router 与阶段技能只提供批次入口、阶段职责和协议引用，不复制完整规则。Build 提供真实增量与实际 project_candidates；Onboard 仍由原指定写者负责。
- **宿主适配**：`runtime-adapters/codex.md` 区分专业视角卡与模型角色，映射 Sol/xhigh 准备、规划、接受及独立 Review，同一 Terra/xhigh Build/修正、另一位 Terra/xhigh 独立 Validate、Terra Ship。核心协议只描述职责与独立性，不硬依赖 Codex 或模型名；不可用时如实披露现有 fallback。
- **上下文与证据**：既有 PRODUCT/ENGINEERING/PROJECT/TASK 和小项目示例保留核心章节/顺序；规则、AC 映射和证据各写一处，其余精确引用。PROJECT 为稳定索引；实际结果放工程记录/state。各组件覆盖统一见“需求覆盖”。

#### 关键设计决定

1. **复用现有协议和 CLI**：现有 JSON state、canonical stage result、上下文与 Git 已覆盖状态和恢复需求，只扩展派工/接受约定；不引入依赖或替代运行时，无迁移及供应链成本。外部检索不适用，仓内资产已足够。
2. **合并派工、逐项接受**：同一准备执行者按 Backlog→Spec→Plan 生成候选与有序原有结果块，不新增批次 schema 或持久化结果。仅合格小项目采用；复杂接口/迁移/并发、产品/原型未决、授权缺口和未解决选择仍按对应常规阶段处理。本 Feature 落地前遵循现行分阶段协议；结构 evolve 沿用现有 Requirement/Feature 与工程上下文，局部 evolve 无记录的例外不能扩至结构改动。
3. **完整价值与共享写入边界决定 Task**：本 Feature 一个完整 Task，由同一 Terra 完成实现、必要检查与修正；真实中途结果通过原消息能力展示，不结束 Task。更大项目仍按独立价值拆分。修复 brief 先由 Sol 给出已证实不变量和相关代表边界，保留原失败史与现有停止规则；不新增全项目穷举要求。

#### API / 接口契约

公共 CLI、参数语义、state_version=3/schema、roles/modes 字典均不改。每个候选继续返回 canonical `stage/status/artifacts/evidence/context_updates/unresolved_items/requested_transitions`；状态仅为原有三种，不添加字段。brief 预填已核对 operation、确切长参数和已知 ID，结果填实际值或精确证据引用，不能用别名、猜值、未来占位替代。

主 Agent 固定 `--repo`；阶段执行者只在明确写边界内写上下文/源码，不执行 lifecycle mutation。准备批次可写 product 与 engineering 候选的权限必须预先授予，不能默认为跨文件权限；本次只有主 Agent 接受后才执行 start-feature/add-task。已有 ready/Feature 沿用实际记录，不重复 capture/start。未知 ID 只能在前序接受后从准确返回值取得再形成合法请求。

#### 时序与数据流

1. 主 Agent 先绑定用户明确的目标 Requirement/Feature，并核对 projection、实际 root/branch/HEAD 与当前上下文。全局 next 指向他项不能证明本项前置条件，也不能启动他项；本次不得 Ship 旧 Feature。未解决的多候选选择不能靠批次跳过；已有明确目标则继续核对本目标合法步骤，无须重问范围。
2. 合格输入一次派发准备执行者，返回有序候选块；Plan 接受前仍完成所需只读风险分析。产品决定必须有用户确认或明确委托来源；发现必答项或原型待确认时停在该边界，后续候选不生效。
3. 主 Agent 按块核对 artifact/evidence、前置条件、用户决定、当前版本与 allowed_transitions；按原 CLI 顺序执行，逐项形成已接受前缀。任何接受/操作失败立即停止后缀；不为批次引入原子事务。
4. 恢复只读对账 state/context/Git 与原结果，确定首个未接受阶段/未应用操作，保留已成功 capture/ready/start/add-task，不重复重放。结果不确定时先查实际状态，不能从错误退出断言没写入。确认原写者交回或停止后才恢复同一写边界，保留实际分支身份约束。
5. start 或部分 add-task 成功后，即使 next 指向 build/validate，主 Agent 仍将有效 Plan 的全部 Task ID、标题边界和依赖与实际 projection 对账，补齐未登记项后才执行。不依赖 CLI 感知 Markdown 中尚未登记的 Task；不新增字段或登记服务。
6. Build 在原授权内持续完成一个完整 Task；中途里程碑给实际入口、命令、版本、范围和缺口，不请求 done 或正式交回。真实稳定事实未变时返回 `project_candidates: []`；有变化才交指定 Onboard 写者更新受影响事实。

这些有序步骤已覆盖分支与恢复条件，不另画重复图。

#### 横切质量设计

- PROJECT 保留 `unit/coverage/e2e/typecheck/lint/build` 六个键，只放已验证命令或 `none`；planned/NOT_RUN 写正文。稳定入口、配置、环境、资源、surface、长期来源及其历史出处可保留；测试数、覆盖率、当前候选版本和 Feature 阶段不复制进去。代码修复或 HEAD 变化本身不触发刷新。
- 检查按目的与相关输入复用：完整 coverage 实际执行同一 suite 可兼作 unit；提交前后内容/环境等价则核对版本归属，不因 Git 身份出现重跑。源码、测试、runner、配置、环境、相关 README 契约变化，失败、缺证据或独立阶段义务仍要求对应实际检查。Build PASS 不替代独立 Terra 对当前候选的实际 Validate。
- 优先已有真实 subprocess/旅程资产；首轮有缺口才补一次，后续复用或只补新边界。错误 probe 保留失败归因后局部重跑。不能把文案关键词检查当编排行为证明，也不能把 fixture 演练当真实模型实跑。
- Ship 只读取当前批准源、最新正式验证/评审段、README 和授权/交付条件，保留来源/内容核对、源码分发的新解包目录 smoke 或既有已授权部署目标的实际版本 health/smoke，以及正式 commit 关联。等待时可准备只读引用，批准后使用确切版本；最终汇总引用一次记录的证据，不复制全 suite/coverage 或整份工程史，是否换交付执行者按职责选择。

#### 需求覆盖

下表 Task 均为 `TASK-dispatch-workload`，是本方案唯一 AC→设计→Task→计划检查映射；实际结果见下文“验证记录（实际）”。

| 产品 AC | 设计/契约 | Task | 计划验证 |
|---|---|---|---|
| AC-1、AC-2 | 准备批次；接口与时序 1～5 | TASK-dispatch-workload | 实际 CLI 正常顺序、部分失败恢复不重复创建、Task 未完整登记时 next 提前指向 build；未决产品/needs_selection/旧目标排除的语义走查。 |
| AC-3、AC-4 | 完整 Task；时序 6；PROJECT 稳定索引 | TASK-dispatch-workload | 场景走查：真实增量不改状态、代码修复稳定事实不变返回 []、实际命令变化才刷新；fixture 前后状态比对。 |
| AC-5、AC-6 | 同输入证据和旅程资产复用 | TASK-dispatch-workload | 走查完整 suite 兼证、内容等价绑定、变化/失败重验与 probe 归因；独立 Terra 实际检查当前候选并记录输入适用性。 |
| AC-7 | Codex 模型映射；精确结果；原修正纪律 | TASK-dispatch-workload | 核对模型角色/专业视角隔离与 help 参数；缺项/别名拒绝、已证实修复边界和失败历史保留。 |
| AC-8～AC-10 | 紧凑交付；兼容与授权边界 | TASK-dispatch-workload | 结构检查、diff/范围核对、批准源与授权走查、未提交快照独立评审；CLI/schema/版本元数据/旧项目不变，正式绑定 pending。 |

### 实施计划

**关联产品上下文**：同上。**关联设计**：上述架构设计。**已确认需求**：同上。**创建日期**：2026-10-25。**状态**：主 Agent 已接受。

#### 背景

按唯一需求覆盖表完成内部技能/使用说明更新；全局 usage 入口为 README，操作参数权威仍是现有 CLI help，详细编排行为引用 protocol，不另造 story 或参数源。

#### 目标 / 非目标

目标是让现有文件规则实际减少准备派工、Task 交接、无事实变化 Onboard 及重复证据对象。非目标完整沿用产品“范围外”：特别是不改脚本运行时、不动旧项目，不提交发布或启动模型实跑。

#### 技术栈

Markdown/YAML、现有 Bash 检查和 Python 标准库 CLI；无新依赖、数据库或服务。无 UI/原型资产。

#### 实施层决定

文档/协议改动先编辑，再运行已有结构与行为检查；不添加镜像文案或关键词断言测试。复用 `scripts/test_lifecycle_state.py` 的临时仓库/subprocess 模式组织隔离 CLI 演练，不更改 lifecycle 实现。演练资产只组织一次，独立验证在新 fixture 中执行同一资产，后续仅补新缺口；临时目录仅存合成数据和必要证据，禁止对本源码创建 commit、安装插件或访问旧项目。

#### 风险 / 取舍

| 风险 | 影响与处理 |
|---|---|
| 批次候选被当成已接受阶段，或部分登记后提前执行 | 必须执行时序 1～5 的逐项核对；CLI 演练明确显示 next 的能力边界，不能宣称 CLI 自动强制这些语义。 |
| 多处规则互相冲突或专业卡被当成模型角色 | protocol 单一权威，入口/模板只引用；Codex adapter 集中模型映射，独立评审核对最终 diff。 |
| 复用放宽独立性/重验，或未提交快照冒充正式通过 | 独立 Terra 实际验证；分开工作区证据与正式 commit 记录，禁止借旧 PASS 推进。 |
| 仍生成同样对象却宣称提速 | 按产品观察计划核对实际对象减少；本轮模型实跑 NOT_RUN，不承诺六/十二轮为固定上限或实测速度。 |

#### 实施阶段

1. 同一 Task 先修改权威协议、router/adapter 和必要入口；最早可检验结果是协议候选及临时 CLI 的正常顺序/失败恢复结果，由 Terra 提供实际命令、版本与状态前后值供查看，不据此 done。覆盖见唯一映射表。
2. 同一 Terra 继续同步确有冲突的阶段方法、模板/示例/README，CHANGELOG 写 Unreleased；保留核心章节/顺序，不复制背景、AC 或证据，不做机械裁字返工。
3. 实现者运行 `bash scripts/validate-skills`、`git diff --check` 并核对完整 diff。另一位 Terra 对最终未提交候选实际执行必要结构/临时 CLI 场景检查与语义走查；Build 已有 PASS 仅作输入，不能替代这次实际独立验证。只读 Sol 独立评审最终 diff 和适用证据。新修改/失败重验受影响检查，其余相同输入证据按目的复用。

### 工程任务

**输入**：上述架构设计、实施计划与产品规格。**测试**：按唯一映射和实施阶段 3；计划命令均为 NOT_RUN。**组织方式**：一个完整 Task、同一实现者持续负责，不新增基础设施或并行写者。

#### 路径约定

下列均为本隔离 repo 的相对路径。其他项目、插件缓存、全局配置与历史上下文只读；不重写当前 `.sdlc-v1/project.md` 或其他 Requirement/Feature 的记录。

#### 用户故事：减少同一小项目的重复工作

- **TASK-dispatch-workload**：落实编排与证据减量并同步使用说明，覆盖唯一映射表全部 AC。允许修改：
  - `skills/sdlc/references/stage-agent-protocol.md`、`skills/sdlc/references/runtime-adapters/codex.md`、`skills/sdlc/references/templates/TASK.md`。
  - `skills/sdlc/SKILL.md`；确有冲突的 `skills/sdlc-{backlog,spec,plan,build,onboard,validate,review,ship,product-design,software-delivery}/SKILL.md`，仅改入口/阶段特有责任与引用。
  - `skills/sdlc/references/templates/{PRODUCT,ENGINEERING,PROJECT}.md`，`skills/sdlc/references/lifecycles/{product-design,software-delivery}.md` 中确有冲突处。
  - `examples/small-project-context.md`、`README.md`、`CHANGELOG.md`；本工程上下文的实际记录及必要、事实支持的当前方案调整。
- **完成条件**：所有绑定 AC 的文档/契约一致，实施阶段 3 的必要检查通过且证据真实；无 runtime/CLI/schema/字典/版本元数据改动，无越界文件。完整 Task 才请求 done；独立 Validate/Review 属于后续独立职责，不由 Task 自评替代。

#### 依赖与执行顺序

Requirement 已 ready；主 Agent 接受本方案后按 start-feature→add-task 登记本次固定 ID。Task 无依赖，无并行实施；依次实现、独立验证、独立评审。修正仍归原 Terra；保持原问题失败历史和既有非收敛停止规则。

#### 执行策略

最早真实增量见实施阶段 1；后续仍在同一 Task 内继续。回滚只提出本次差异的定向撤销方案并遵循用户授权，禁止 reset/clean、清理数据或操作旧项目；本轮无部署、迁移或外部副作用。

## 实现记录（实际）

- 2026-10-25：同一 Terra 在 `db023de9d64aeb92ddb1e064e88bdaf9353e49f3`
  的未提交快照上完成 `TASK-dispatch-workload`：协议成为准备批次、逐块接受/恢复、完整 Task、稳定
  `project_candidates` 与交付证据规则的唯一权威；router、阶段入口、模板、示例、README 和 Unreleased
  仅保留对应职责或引用。Codex adapter 区分 Sol 准备子 Agent/主 Agent 接受、Terra Build/Validate/Ship
  与 Sol Review，未把专业卡当模型角色，也未改 runtime、CLI、schema、roles/modes 或版本元数据。
- 实际范围是 `CHANGELOG.md`、`README.md`、`examples/small-project-context.md`、列于本 Task 允许清单的
  `skills/sdlc/**` 文档，以及本工程上下文；未提交、未暂存。稳定入口、命令、配置、环境、资源、surface 和长期来源未变，
  本 Task 的 `project_candidates: []`。

## 验证记录（实际）

- `bash scripts/validate-skills`：exit 0（轻量运行时/引用、12 个 skill frontmatter、路由、可移植性；
  `test_lifecycle_state.py` 37 项、`test_backlog.py` 7 项、`test_contrast_check.py` 36 项均通过）。
- `git diff --check`：exit 0。已审阅当前完整 diff 的允许路径、权威引用与兼容性：未修改 runtime、公共 CLI、
  schema、roles/modes、插件版本元数据或历史上下文。
- 在一次性隔离 fixture `../evidence/dispatch-workload-cli-fixture`
  （基线提交 `1766acc20606595ac33dc3b76942c1a33ff48445`）中，现有 CLI 的 `init`、capture、ready、start-feature
  和首个 `add-task` 均 exit 0；此时 `next` 已返回 `build`。带未知依赖的第二个 `add-task` exit 2 且 projection
  没有部分写入；改为依赖第一个 Task 后 exit 0，projection 保留完整两 Task/依赖。这证明协议必须先对账并登记有效
  Plan 的全部 Task，不能跟随提前的 `next`。本轮随后只改 Markdown 合同，未改 CLI 脚本、fixture 定义或输入，因此该 CLI
  证据仍仅适用于上述状态语义。fixture 是离线演练资产，不是运行时进度或模型实跑。
- 本轮模型性能实跑为 `NOT_RUN`。`record-validation`、正式 `record-review` 与 commit 绑定仍 pending；不得引用旧
  commit 的 pass 推进状态。本轮禁止源码提交；正式记录仍受干净业务工作树和 tracked context 前置条件约束。
- 2026-10-25：与实现者不同的独立 Validate Agent 对当前未提交快照完成实际检查，结论仅限该快照为 `PASS`；
  正式 lifecycle 记录保持 pending。`bash scripts/validate-skills && git diff --check` exit 0（37 lifecycle、7 backlog、36
  contrast tests）；新的隔离合成 Git fixture 实际演练 capture/ready/start/Task 登记、未知依赖 exit 2 无部分写入、已有 ready
  Requirement/多候选选择、以及 dirty/untracked 拒绝 `record-validation`，均符合当前协议。完整命令、快照、AC 映射、
  约束与静态走查范围记录于本地工作区的 `INDEPENDENT_VALIDATE_DISPATCH_WORKLOAD.md`；它不是模型实跑、部署或
  正式 commit 绑定。现有源码工作树因未提交业务 Markdown 而不满足正式记录前置条件，本 Agent 没有调用 source
  `record-validation`、改动 state 或请求 lifecycle transition。
- 2026-10-25：两条独立 Sol 评审修正后，独立 Validate 对最终未提交快照补验 `Bounded preparation batch` 的逐阶段 brief/
  allow-list 和范围变更规则。`bash scripts/validate-skills && git diff --check` 再次 exit 0；未修改的 CLI、fixture 定义和输入
  沿用先前状态语义证据。负路径走查确认 Backlog 不可借批次消息执行 Spec/Plan mutation，缺阶段顺序/绑定在 mutation 前拒绝；
  ready/in-delivery 的实际范围变化先产生新 Requirement/依赖并停止旧后缀，captured 未绑定才使用既有 revise，合法目标只重生未接受后缀。
  这是规则推演，不是 LLM dispatch、性能实跑或新的 CLI fixture；详细补验保留在同一工作区报告中，未随源码分发。

## 评审记录（实际）

- 2026-10-25：独立 Sol 对未提交快照的只读评审发现两项有效合同缺口：准备批次需要逐阶段完整 brief 和独立权限校验，
  上游范围变化需要先按产品/Requirement 状态确定合法目标。主 Agent 以既有的 `done → todo → in_progress` 合法序列
  重开原 `TASK-dispatch-workload`；同一 Terra 在原写边界内修正，未创建新 Task、schema、CLI 或状态操作。
- 修正后 `bash scripts/validate-skills` 和 `git diff --check` 均 exit 0。CLI 脚本、fixture 定义和输入未变，既有独立
  fixture 证据仅继续适用于生命周期状态语义。该工作区评审修正与正式 `record-review` 分开；正式记录保持 pending，
  不伪造 reviewed 状态。
- 2026-10-25：同一独立 Sol 复核两项修正及独立 Terra 的最终补验，未发现未处理的必要问题；两项 P2 均已闭合。
  主 Agent 接受最终未提交快照的实现、独立验证与只读评审，原 Task 已 done。实际运行元数据确认实现者及独立验证者为
  `gpt-5.6-terra/xhigh`，独立评审者为 `gpt-6.1-sol/xhigh`。保护检查核对 7 个旧仓库、11,199 个文件路径和 171 个安装/指导文件均未变。
  该时点正式 validation/review/release 保持 pending，等待提交授权和现有前置条件；
  本次未提交快照的测试与评审通过不代表模型性能实跑或 Ship 完成。

## 发布与观察记录（实际）

- 产品观察计划引用：[工作量结果与观察计划](REQ-dispatch-workload.product.md#工作量结果与观察计划)。技术准备、反馈与实际结果待后续证据；真实模型性能对照 NOT_RUN。
- 实施阶段只交付隔离源码中的未提交改动及验证/评审结论，当时未执行 commit/push/PR/tag/release、插件升级或 Ship。
- 后续授权：用户已明确要求提交、发布并更新本机 SDLC 插件，原文及边界见产品上下文“发布授权补充”。本次声明目标为
  GitHub `arnow117/sdlc-pilot` 的公开 `v4.2.0` 源码 Release，以及本机 Codex 中该插件的安装/启用；不部署用户项目。
- 发布前远端 `main` 与最后可用版本 `v4.1.1` 均为 `db023de9d64aeb92ddb1e064e88bdaf9353e49f3`。采用兼容能力的 minor 版本，
  同步 plugin.json、marketplace metadata/entry 与 CHANGELOG；CLI/schema 无迁移。仅本 Feature 的上下文和 state 随对应源码提交。
- 发布准备：当前授权源、正式 commit 验证/评审绑定、新解包源码 smoke、远端 PR/Release 及本机安装版本核对尚待完成；
  后续实际证据追加于本节。失败时停止扩大范围，保留旧发布和工作区，提出按最后可用版本定向回退；尚未执行回滚。
