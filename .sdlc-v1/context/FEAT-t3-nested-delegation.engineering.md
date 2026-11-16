# 工程上下文：FEAT-t3-nested-delegation — T3 按需多层合同与 Desktop 兼容

## 当前有效方案

### 架构设计

**关联产品上下文**：[REQ-t3-nested-delegation.product.md](REQ-t3-nested-delegation.product.md)

**工程上下文**：`.sdlc-v1/context/FEAT-t3-nested-delegation.engineering.md`

**已确认需求**：产品上下文的 confirmed 条目、REQ-001–REQ-009、AC-001–AC-018；本次 brief 指定的 settled interfaces。

**创建日期**：2026-11-16

**状态**：Plan 候选，待原主 Agent 接受；本文件不登记 Feature 或 Task，不改变生命周期。

#### 背景

本 Feature 更新文档型编排合同，使 T3 执行者在产品规定的条件内进行局部协调，同时保留原主 Agent 的唯一状态写入和最终接受职责。产品规则与验收例子的唯一正文仍在产品上下文；本方案只决定修改位置、适配方式、单写者实施顺序和验证方式。没有业务服务、UI、调度器实现或持久化格式迁移。

本次亲自核对 `product-projection`：`REQ-t3-nested-delegation=ready`、`feature=null`、依赖 `REQ-t3-stage-dispatch`；`verify-acceptance` 的 `spec_ready` 为 `match`，内容指纹为 `c4f9a2f58e918559fae9d06c7ed1df207a3b6bcebead6623aaee2d3f644a90d6`。原主 Agent 接受 Spec 的事实由 brief 和当前 state 提供；产品正文中仍保留的“候选”标签不构成重新捕获或改写产品的理由。旧 Requirement 与 `FEAT-t3-stage-dispatch` 均为 released，旧通过记录只说明历史，不证明本次能力。

方向来源沿用产品 U1/U2 和本次 Plan brief；没有新增产品选择。项目级约束采用工作仓 `AGENTS.md -> CLAUDE.md` 的维护契约和现行阶段协议：单一状态实现、协议唯一正文、adapter 只适配、普通 Git 协作。确认范围限本 Feature 已确认变化，不由本 Plan 批准其他长期规范。`project.md` 仍是较早的 a034dc6 / 2.0.0 索引：当前两处插件文件的三个版本值实际均为 7.0.1，快速检查已包含八组测试；旧索引的版本、测试数和发现链接不是当前证据，也不作为推迟本 Task 的新依赖。该预存索引缺口不在本次写范围内。

#### 架构与组件

##### 权威阶段协议

- **职责**：在 `skills/sdlc/references/stage-agent-protocol.md` 内集中表达 T3 条件扩层的适用范围，并将既有 brief、结果、独立检查、等待/取消、资源和失败规则应用到每一层。Desktop 默认行为继续由其既有 native 适配表达。
- **接口**：继续使用原有 brief 与 canonical result；获准的直接上级只能产生待原主 Agent 接受的候选，不能取得 lifecycle 控制权。具体修改见下文文件清单。
- **覆盖**：REQ-001–REQ-003、REQ-005–REQ-009。

##### 宿主适配与使用入口

- **职责**：router、T3 adapter、Codex adapter 的 T3 引言、TASK 使用说明和 README 都引用上述权威适用范围；不各自维护一套允许条件，也不复制 T3 通用 native/delegate/background 工具路由表。
- **接口**：实际宿主指令负责当次工具选择；项目配置提供 provider/model/options。T3 adapter 仅保留选中机制需要的句柄、配置证据、跟随 `next` 和取消映射等适配说明。Codex native 正文、模型表及发现说明逐项保护。
- **覆盖**：REQ-001、REQ-003、REQ-004、REQ-006、REQ-007。

##### 静态合同检查与人工场景核对

- **职责**：复用 `scripts/test_scenarios.py` 的 `T3ChildContractTest` 和 `scripts/validate-skills`，检查共享引用、有效锚点、必要形状及已知冲突反例；人工按产品 AC 逐例检查语义、归属和允许的后续动作。
- **接口**：检查只返回测试结果；不创建生产策略解释器、Agent 运行器、结果目录或新状态 schema。确定性脚本、人工合同走查与真实运行分别归因。
- **覆盖**：REQ-001–REQ-009；仅覆盖各自的静态或合同范围。

稳定部分是现有生命周期、brief/result、接受与资源协议；真实变化是 T3 条件扩层和受保护的 Desktop native 两种宿主语义。复用既有 adapter 边界即可，不引入插件系统、配置 DSL 或新的策略 runtime。原型、页面及视觉图不适用；以下有序说明已能表达控制流。

#### 关键设计决定

##### 决定 1：在现有协议内增加 T3 限定小节

新增 `### T3 layer boundary`（锚点 `t3-layer-boundary`）作为允许条件、逐层授权子集和局部协调边界的唯一说明位置。协议 §1 的默认层级、Runtime selection、§2 的修正职责、§4 的候选汇总使用必要引用协调，不保留互相冲突的无条件禁令。逐层 brief 继续在现有 `authorization`、`settled_interfaces`、`dependencies`、`completion_conditions`、`required_verification` 和必要补充中写明具体目标、可读来源、revision/写范围、总预算分配、汇总位置、停止及收尾责任；不增加必填字段、固定口令、统一层数或数值上限。

允许条件本身引用产品 REQ-001/002；进一步派工的权限不能由上级工具能力、模板说明或通用“继续”产生。原主 Agent 命名的有限层级和原有总体约束逐层收窄；必需剩余额度、资源归属或写入互斥无法核实，只停止依赖的新启动。下级的 allowed transitions 不能比原 brief 更宽，任何层都只返回请求，由原主 Agent 核对原允许清单并执行。

候选替代项是仅删除各处禁令，或新建通用编排控制器；前者丢失条件与职责，后者增加第二运行时和状态源，均不采用。覆盖 REQ-001、REQ-002、REQ-005、REQ-008。

##### 决定 2：宿主选择与 Desktop 正文分开保护

Runtime selection 说明宿主实际合同优先，不再承诺所有 T3 都由同一种机制派发。只有选中的宿主路径需要 T3 app-owned child 时才加载该适配，不套 native 包装、不用顶层线程替代 child。若宿主要求 native，而实际环境属于产品 H1 的 2026-11-11 本机 T3-hosted Codex / `openai_token_sharing` 故障范围，报告机制冲突；不尝试已知可能污染历史的 native 操作，也不静默换机制或模型。故障事实在权威协议记录一次，其他位置引用；没有当前修复或全平台故障结论。

`codex.md` 只修改 `## Interface map` 之前的 T3 引言，明确下方 native 映射只适用于支持且获准的 native 宿主；从该标题开始到 EOF 的正文保持字节一致。T3 小 review finding 自修窄例外只在协议 §2 定义：必须有当前 T3 宿主明确要求、原写者交还和所属写入终止证据；保留必要检查、适用独立复审和失败历史。它不适用于 Desktop，也不把整项实现交给主 Agent。覆盖 REQ-003、REQ-004、REQ-006。

##### 决定 3：可实施合同先落地，运行证据严格限域

本 Task 的交付是合同、使用文档和必要的确定性检查；本地实现与本地检查不依赖模型实验。获准的新多层路径、当前 run 配置、取消级联、真实资源终止和 Desktop 行为均无运行证据，不安排探针或演练。后续若有人需要 live 通过声明，须在当时授权、能力和预算内取得相应证据；此需求不预授这种授权，也不删除相关验收义务。覆盖 REQ-004、REQ-007、REQ-008。

#### 时序与数据流

1. 原主 Agent 读取当前 projection、产品与工程接受依据，命名有界目标、汇总位置和总授权/预算；只有它接受 Plan 并登记 Task。
2. 对某次 T3 任务，执行者按权威小节核对是否明确要求进一步派工、宿主是否允许和必要路由/权限是否成立。缺条件时直接完成合同内可执行部分并返回影响范围。
3. 获准直接上级通过原 brief 形成下级授权子集，指定本层写者、必要独立检查和资源责任。它不改全局方案、产品决定或 state；本 Feature 的实现 Task 自身无须再派工。
4. 下级执行自身合同，沿原句柄遵循宿主等待、恢复和取消指令；只在自己也收到明确任务且全部条件成立时才有更深协调资格。
5. 下级返回 canonical 候选。直接上级在既有 `evidence.commands.result`、`revision`、`workspace_status`、`unresolved_items` 等字段内保留实际执行者、上下文、文件、命令/exit 和未知项，汇总时不把自己称为实际检查者，不替下级证据改写结论或丢失请求顺序。
6. 所有中间结果仍待原主 Agent 接受。原主 Agent 核对实际 diff、当前候选、独立性、配置证据、资源和原允许清单后决定接受或拒绝；只有它执行 mutation。
7. 部分失败只停止依赖的接受/启动；取消回执、任务终止、所属写进程终止和资源释放分别核对。§5 的历史失败计数与唯一诊断使用事实沿层传递，未知历史不当作零。写者/终止未知时不接管同范围，共享或未知归属资源不清理。

#### 风险与取舍

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 把 T3 例外扩到 native 默认路径 | 改变 Desktop 默认职责或层级 | 限定适用文字、保护 Codex native 全部正文；命令 C3 加人工逐项核对 |
| 局部协调变成第二接受/状态控制者 | 越权或丢失实际证据 | 协议明确原主 Agent 身份；合同案例检查中间候选与请求子集，state/runtime 源码不改 |
| 只改文案让 token 测试变绿 | 不能证明授权判断或行为 | 测试只称结构/反例检查；AC 逐例人工核对，live 项明确 NOT_RUN |
| 只看 child 结束就重叠接管 | 未终止写入或资源被误清理 | 复用现行等待、资源与失败协议，逐项记录未知，不引入自动级联假设 |
| 未提交技能会被发现入口立即读取 | 本机消费到尚未接受的合同 | 改前核对真实来源和写者；报告当前未提交范围；不更改发现链接、安装或声称已发布 |

#### 需求覆盖

下表是本方案唯一的“产品验收 → 设计/契约 → Task → 计划验证”关联；AC 原始给定/当/则仍只在产品上下文维护。

| 产品规则 / 验收 | 设计与检查输入 | Task | 计划验证与期望观察 |
|---|---|---|---|
| REQ-001；AC-001、AC-002 | 决定 1；同一 brief 只增删明确 A→B 要求，另给通用“继续”和明确禁止版本 | TASK-t3-nested-contract | 人工按协议找到允许、直接执行及缺口分支；C1 只证明引用可达，不启动执行者 |
| REQ-002；AC-004、AC-005 | 决定 1；A 只获准 B 检查 X，另给 B→C、越界写和剩余额度未知版本 | TASK-t3-nested-contract | 不能把祖先权限或总额度复制给下层；不虚构统一层数/预算；检查未知只阻断依赖启动 |
| REQ-003；AC-003、AC-010、AC-012 | 决定 2；host deny、工具缺失、必需配置不符；分别给合法 native、app-owned 和 H1 冲突合同 | TASK-t3-nested-contract | 逐案指向当次宿主合同与具体缺口；H1 冲突不得试跑或静默换路径；不产生通用 T3 工具路由表 |
| REQ-005；AC-006 | 时序 5–6；B 返回命令/exit、revision、文件与两个有序请求，A 汇总候选 | TASK-t3-nested-contract | 保留实际执行归属和顺序；拒绝超出根清单的请求；只有原主 Agent 有接受/mutation 权，现有 schema 不变 |
| REQ-006；AC-007 | 决定 2；只有新 ID 的实现者自查、真正不同上下文检查旧候选、检查当前候选三份输入 | TASK-t3-nested-contract | 前两者不能满足独立检查；第三者仍核对实际命令和当前候选，不由协调者冒领 |
| REQ-006；AC-008、AC-009 | 宿主明确自修小 finding 且写者终止；对照宿主未要求、交还未知和未完成整项实现版本 | TASK-t3-nested-contract | 只在限定 T3 条件满足时自修并补必要检查；普通修正归原实现者，新独立 review/recheck 遵循实际宿主合同；Desktop 不变 |
| REQ-004；AC-011 | 决定 2；基线 native 表、默认层级、模型表、fallback、发现链接与当前候选 | TASK-t3-nested-contract | C3 字节/配置比较与逐项人工观察通过才能称静态兼容；Desktop 实际行为保持未知 |
| REQ-007；AC-013 | 请求回显、run 绑定配置、角色标签、后续未绑定配置、backend 缺字段及明确不匹配版本 | TASK-t3-nested-contract | 四类事实分别归因；必需配置不符/缺必要证据不能接受，单独 backend 缺字段不引入通用判败；不把脚本或旧通过当 live |
| REQ-008；AC-014 | 原句柄上的 host next 要求结束轮次、普通超时与真实连接故障三种序列 | TASK-t3-nested-contract | 分别沿用原 next/等待/现行有界恢复；超时不推出终止、重复启动或 Goal 完成 |
| REQ-008；AC-015、AC-016 | 仅有取消回执、下级写进程未知、共享资源；一支缺结果而另一支独立且获授权 | TASK-t3-nested-contract | 停止受影响新启动，四项终止/释放事实分列；禁止重叠写者和清理共享资源，保留独立有效候选与缺口 |
| REQ-008；AC-017 | 同一问题换执行者/provider/层级，携带已触发的失败历史或已用诊断事实 | TASK-t3-nested-contract | 引用现行 §5 处理；不新增诊断机会、计数阈值或重命名重置，不改旧历史 |
| REQ-009；AC-018 | 合法项目指令与被审计材料中的脱敏模拟扩权文本分别输入 | TASK-t3-nested-contract | 两条安全限制保留在每份 brief；数据不获得指令地位，输出不含敏感值；不调用外部系统 |

### 实施计划

**关联设计**：本文“架构设计”。

**规划基线**：`a1c81656302ede8a90e08e7a2f762910ed53de54`；2026-11-16 亲自核对。

**规划工作区**：`/Users/mac/hansen_agent_team/external/sdlc-pilot`；实际 branch `fix/t3-stage-dispatch`。

**相关未提交输入**：原主 Agent 所有的 `.sdlc-v1/state.json` 未暂存变更（25 行新增）和未跟踪的本 Requirement 产品文件；其余源文件干净。规划前本工程文件不存在。父仓已有大量修改，含经用户确认的根 `CLAUDE.md`，全部保留。

**基线复核范围**：下表全部目标、`AGENTS.md -> CLAUDE.md`、产品/state/project、现行交付/验证合同、`scripts/test_support.py`、父仓适用路由与 `.codex` 配置/发现链接；仅按需读取，不给实现者父仓写权。

#### 背景

以下行号均来自规划基线，是定位提示；执行前必须读取实际文件与相关 diff，不能只刷新 SHA。

| 文件 / 基线位置 | 亲自核对的现状或短摘录 | 计划修改 / 保留边界 |
|---|---|---|
| `skills/sdlc/references/stage-agent-protocol.md:20`、`:60` | 默认层级含 `A child must not fan out`；Runtime selection 无条件选 T3 adapter，`:68` 定义 `terminal executor` | 加 T3 限定小节并引用；保留默认层级对其他宿主的含义，按实际 host 合同选择机制，记录 H1 的准确范围 |
| 同协议 `:94`、`:165`、`:276`、`:317`、`:565`、`:656` | 既有 brief、同一实现者修正、等待/恢复、资源、canonical result、唯一诊断规则 | 仅补逐层适用和局部汇总的必要指引，以及 T3 小修窄例外；结果字段、状态、CLI、等待/恢复阈值及 §5 历史规则不改不复制 |
| `skills/sdlc/SKILL.md:14` | `受托执行者不得嵌套派工` | 替换为共享小节引用；其余状态路由、阶段选择和默认规则不改 |
| `skills/sdlc/references/runtime-adapters/t3-code.md:3`、`:10`、`:15` | main 直接 T3 child、首次 delegate 前 capabilities、`terminal executor` | 引用适用范围；工具选择由实际 host 决定，capabilities 仅在宿主要求且选中 delegate 时适用；保留 selected-task 的 next、句柄、模型证据与 task_cancel 适配，不复制通用路由 |
| `skills/sdlc/references/runtime-adapters/codex.md:10`–`:18` | T3 限定引言同时写 `its children must not delegate further` | 只改标题 `## Interface map` 之前的 T3 段，链接共享范围及 H1；后续 native 正文字节不变 |
| `skills/sdlc/references/templates/TASK.md:15` | `T3 child 为终端执行者` | 改成按共享小节填写当次条件与有限边界的说明；YAML brief/result 字段、安全限制不改，不新设 `delegation_depth` 等参数 |
| `README.md:45`–`:67` | SCN-t3-stage-dispatch usage 入口含终端禁令与旧故事导航 | 保留旧场景 ID/标题锚点，增加 `SCN-t3-nested-delegation` 当前故事导航与产品引用，删除当前使用中的冲突禁令；不回写旧产品/工程历史 |
| `scripts/test_scenarios.py:425`–`:501` | `T3_CONTRACT_PATHS`、`T3_REQUIRED_TOKENS` 强制 adapter/template 终端 token；`t3_child_contract_errors` 只查文档形状；临时副本反例检查源文件未变 | 扩展同一检查及现有 T3 测试类，改查共享引用/有效锚点和明确冲突反例；保留顶层旧肯定路径反例。它仍非语义决策器或 live oracle |
| `scripts/validate-skills:271`–`:311`、`:404`–`:444` | 阶段结构与引用检查；明示 shape only；快速检查运行 test_scenarios 等八组测试 | 复用现有入口，无须新增脚本或变更 runner；必要检查放回已有测试类，不增加重复 token 列表 |
| `docs/testing.md:65`–`:85` | 按改动选择确定性检查、人工合同走查和另行授权的真实演练 | 仅更新当前 T3 检查行及相关说明，映射本次场景范围/限制；历史实测记录和历史计数不改，不复制产品 AC 全文 |
| `CHANGELOG.md:8` | 最新正式说明为 7.0.1 | 新增待发布说明，准确标注条件式新能力及静态/运行证据边界；旧版本条目不回写 |
| `.claude-plugin/plugin.json`、`marketplace.json` | plugin version、marketplace metadata.version、插件 entry.version 三处均为 7.0.1 | 当前 Task 不升版、不宣称已发布；未来确有发布授权时，兼容新增能力按 minor 在当时版本上决策并同步三处，不借本 Plan 固定 tag 或预授 release |

现有范式可直接复用：`T3ChildContractTest.test_temporary_copies_and_each_missing_token` 用隔离副本逐项删改且断言原文未变；`test_old_affirmative_path_is_rejected_in_new_copy` 区分合法的工具名说明和肯定的旧顶层启动路径。协议引用/锚点检查可复用 `validate-skills:131` 起的 `check_arch_constraint_refs` 思路，但不复制架构规则正文或新增运行时。

#### 目标 / 非目标

目标是同步合同、入口、适配和检查，按上表消除当前 T3 条件冲突，由同一实现者完成必要测试及修正。Desktop 受保护语义必须逐项保持：native `spawn_agent`/`followup_task`/`send_message`/`wait_agent`/`interrupt_agent`/受限 `list_agents` 映射；native 默认一层及 child 不自行创建 children；主 Agent 的接受/状态职责；配置的 Sol/Terra 职责、模型/effort、独立 Validate/Review；fallback 的拓扑限制与非独立披露；用户选择与 handoff/discovery；资源终止证据要求。父仓 `.codex`、技能链接及工作仓 CLI/state schema 均不改。

非目标：父仓、旧 Requirement/Feature/历史、现有产品正文、lifecycle 源码/state、任何业务源码、新依赖/新权限/新层数常量、安装/联网/认证、模型/多层/Desktop 实验、提交/推送/发布。未来 Build 只写下文 Task 指定文件；本次 Plan 只写当前工程文件。

#### 技术栈

Markdown 为产品实现载体；既有 Python 标准库 unittest 和 Bash 检查为验证载体。无需引入依赖、安装工具、服务、浏览器或模型 API。现有 lifecycle CLI 继续是唯一状态实现，调用写操作只属于原主 Agent。

#### 实施层决定

复用评估：选择“复用现有实现”。当前协议、adapter、TASK、T3ChildContractTest、快速检查入口已覆盖结构和副作用边界；仅需扩展具体合同与反例。没有依赖清单或现成库能代替宿主指令语义判断。另建调度器/模拟决策引擎没有必要，修改 Desktop 路由不满足已确认范围；因此不联网比较、不引入第三方库。

本 Feature 只有一个完整 Task，由一个 implementer 持有全部源文件写范围，顺序完成合同、适配、README、测试和修正；不把缺失测试或小文件编辑另派给其他实现者。实现模型按适用父仓路由优先 `claudeAgent / glm-5.3-flash[1M] / effort=xhigh`，仅在已授权的明确额度耗尽/持续限流条件和完整交接成立时采用 `codex / gpt-6.1-terra / reasoningEffort=xhigh`；本 Plan 不启动、探测或切换。实际请求、生效配置和 backend 证据仍按协议区分。原主 Agent 保留最终验收；正式独立 Validate/Review 是后续阶段，不能由同一实现者的本地检查替代。本 Task 无并行实现或进一步派工需要。

#### 风险 / 取舍

单写者避免协议、模板和测试各自形成不同语义；代价是文件修改顺序串行。静态检查能快速暴露引用缺失和旧肯定路径，无法证明模型会执行正确选择；因此语义由逐例人工核对保留，真实能力不声称已验证。这个工程上下文比 5–8 KB 示例长，是因 18 个合同场景、Desktop 比较基线、原写者/资源/失败边界和正式验证限制需要可独立执行的说明，不靠删掉这些义务缩短。

#### 实施阶段

以下是同一 Task 内的步骤，不是额外 Task 或阶段授权。

1. **复核与检查预期**：读取产品、本文和实际宿主指令，核对基线/归属；把现有 T3 结构测试改为共享引用及反例要求。可以先运行 C1 看到缺少新锚点/引用的预期失败，记录失败归因；文档型合同不要求构造伪造的运行行为测试。覆盖 REQ-001–REQ-004；设计：权威协议、静态检查。
2. **核心合同与最早可检验增量**：在权威协议补适用小节，同步 router、两份 adapter 的限定文字和 TASK，令 C1 的引用/冲突反例通过；人工对照 AC-001、002、003、011，再运行 C3 证明 Desktop 受保护正文与配置未变。此时可展示真实文档合同增量及检查输出，明确其未覆盖 live；仍由同一实现者继续 Task，不请求 done。这是最早真实增量，无需 README 收尾、正式 validation commit 或模型试验作为前置。覆盖 REQ-001–REQ-007；设计：决定 1/2。
3. **完整场景与 usage**：同步 README 当前导航、docs/testing 和待发布说明；按需求覆盖表人工走查全部 18 个 AC，记录每例使用的文件位置、输入变体、预期分支、实际文案与差异。复用 B03/B05 确定性测试核对原状态/恢复基础，不能据此声称新的 Agent 多层行为已执行。覆盖 REQ-001–REQ-009；设计：三个组件。
4. **本地检查与交还**：运行 C1–C3、空白/范围检查，记录被测未提交快照、完整命令/exit 和剩余未观察项；完整 Task 本地完成后交还唯一写范围。没有 commit 授权时保留工作树，不自动 stage/commit，不以此阻止步骤 1–3。覆盖全部规则；设计：决定 3。

#### 需求覆盖

实施步骤和 Task 的覆盖以架构设计“需求覆盖”表为唯一关联；本节不再复制第二张映射。

### 工程任务

#### TASK-t3-nested-contract — 更新 T3 按需多层合同并保留 Desktop 路径

- **目标与依据**：实现上文三个组件及全部产品 AC 的静态/合同表达；单一可核查结果为“共享协议适用范围一致、Desktop native 正文和配置不变、检查与 usage 同步”。这是完整且唯一计划 Task，不带 `[P]`。
- **范围与依赖**：允许修改 `skills/sdlc/references/stage-agent-protocol.md`、`skills/sdlc/SKILL.md`、`skills/sdlc/references/runtime-adapters/t3-code.md`、`skills/sdlc/references/runtime-adapters/codex.md`（仅 Interface map 前 T3 引言）、`skills/sdlc/references/templates/TASK.md`、`scripts/test_scenarios.py`（仅现有 T3 文档合同检查/测试）、`README.md`、`docs/testing.md`（仅当前 T3 检查说明）、`CHANGELOG.md`（只新增待发布说明）。当前工程文件的必要设计/实际记录维护由原主 Agent 在未来 brief 明确写入者后处理，不能与实现者重叠。禁止改其他文件、父仓、旧上下文、state/Git、CLI/schema、插件版本及发现链接。Task 的 `depends_on=[]`；Requirement 只保留已存在的 released 依赖，不新增 Requirement/Task 依赖。开始条件为原主 Agent 接受本 Plan，并按请求顺序登记 Feature 和这一个 Task。
- **实施与检查**：依本文实施步骤 1–4；文件/符号与基线摘录见背景清单，命令见 C1–C3。实现前按协议复核 actual root/branch/full HEAD、基线到当前的相关 diff、暂存/未暂存/未跟踪输入及项目配置；只读验证不能冒充完成实现。
- **完成条件**：唯一权威适用范围及引用无矛盾；18 例人工对照各有实际文案/分支证据且没有新增权限/全局数值；C1/C2 均 exit 0 且预期反例确实被拒绝；C3 exit 0 且 Desktop 逐项人工核对一致；`git diff --check` exit 0；实际 diff 只在上述范围并保留既有输入。安全限制、字段、失败历史、资源归属及独立检查职责全部保持。完成声明只涵盖本地合同实现，不能写成正式 validation、live/Desktop 回归或发布通过。
- **测试安排**：在既有 `T3ChildContractTest` 扩展 `T3_CONTRACT_PATHS` 与 `t3_child_contract_errors`，覆盖 router/Codex 引言等消费者对同一 `#t3-layer-boundary` 的有效引用。临时副本分别删引用、改错锚点、恢复原无条件 T3 终端禁令、加入旧肯定顶层路径，要求对应结构错误；合法的 scoped Desktop 禁令、工具名引用和未知能力说明不能被词语黑名单误拒。保留原文未变断言。测试中不实现一套真假授权算法供自己断言，也不把出现 `allowed_transitions` 等 token 当作语义正确。C2 已含本文件与 B03/B05 回归，无须为格式再重跑同一全套。若新增/修改可执行检查逻辑，新增分支须有成功/拒绝/错误用例，并遵守 correctness 的现有覆盖率约定；本仓无自定义阈值时默认 80% 行、70% 分支，工具未证实可用则报告未验证，不能假定或安装。本次 Plan 未运行覆盖率统计，模块探针缺口见实际记录，不将 Markdown token 数当覆盖率。
- **停止条件**：产品 fingerprint 不再 match；旧目标不再 released 或新目标已被其他人登记；相关代码/配置漂移改变本方案关键契约；保护 Desktop 语义必须修改受保护正文；需要新增字段、统一层数、扩大写权或试跑已知 native 故障；实现/验证所需事实缺失且无已接受等效方式；同范围写者/终止归属不明。只停止依赖部分并返回事实，由原主 Agent 按现行协议处理。非收敛次数与唯一诊断继续沿用 §5，本 Task 不新增阈值或重置失败历史。
- **维护注意**：保留当前产品及已发布旧状态；同一 implementer 持续负责必要测试和普通修正。T3 宿主明确要求的原主 Agent 小 finding 自修只按权威限定条件交还写者后处理；新独立 review/recheck 依实际宿主合同。必要的真实运行缺口进入既有记录，不能通过降格为 follow-up 消除接受条件。

全部 Task 集合只有上述一个 ID、上述精确标题、空依赖。主 Agent 执行 `start-feature` 后须登记该 Task 并核对 feature projection 的 ID/标题/依赖；即使 `next` 已提示 Build，也不省略登记。第一个可开始的 Task 即本 Task；后续阶段依授权进入 `sdlc-build`，本 Plan 结果不授权它自行开始。

以下命令分开执行，不把多条退出状态压成一条。C1/C2 的完整执行属于未来 Build/独立 Validate 的计划检查，本次 Plan **NOT_RUN**；已读取其代码/入口，不伪称先前全套通过。

**C1 — 有界文档合同测试（未来计划）**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -B -m unittest test_scenarios.T3ChildContractTest
```

期望 exit 0；真实仓库引用通过，每个临时副本反例出现精确错误，合法限定说明通过，源文档字节未变。这只是文档检查器的执行结果。Plan 只实际执行过其中 `test_real_repository_contract`，见实际记录。

**C2 — 仓库必要检查（未来计划）**

```bash
PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills
git --no-optional-locks diff --check
git --no-optional-locks diff --name-only HEAD
git --no-optional-locks status --short --untracked-files=all
```

期望快速检查 exit 0，八组现有测试（含本 Task 修改的合同检查）通过，空白检查 exit 0；后两条需要人工对照 write scope 和既有 state/product，不以 exit 0 自动证明范围正确。现有测试会在隔离临时目录构造 Git fixture、部分本地 loopback stub，并按既有测试机制清理；不启动外部模型。不得在目标或父仓执行测试 fixture 的 Git 写操作。若未来 brief 连隔离 fixture 也禁止写入/测试启动，则报告该局部检查前提，不静默绕过；这不影响其他已授权静态工作。

**C3 — Desktop 和相关配置静态保护（已在 Plan 基线上执行；Build 后重跑）**

```bash
python3 -B - <<'PY'
from pathlib import Path
import hashlib
import subprocess

root = Path.cwd()
base = "a1c81656302ede8a90e08e7a2f762910ed53de54"
relative = "skills/sdlc/references/runtime-adapters/codex.md"
baseline = subprocess.check_output([
    "git", "--no-optional-locks", "show", f"{base}:{relative}"
], cwd=root).decode("utf-8")
current = (root / relative).read_text(encoding="utf-8")
marker = "## Interface map\n"
assert baseline.split(marker, 1)[1] == current.split(marker, 1)[1], "Desktop native body changed"
expected = {
    ".codex/config.toml": "6202abc51d6ec3d39a9314ed64d6c62c6f8e090933c005b210dcc4182ea5696e",
    ".codex/agents/worker.toml": "ff8445ed00f514637742b19c2d826325d6e4b9985292b7f770ea74e2dd6d7dac",
    ".codex/agents/reviewer.toml": "8f83625499ff538019bef9eb09f4e73bff3547c539344b09d324ff5a88090669",
}
parent = root.parent.parent
assert parent == Path("/Users/mac/hansen_agent_team"), "different execution environment"
for name, digest in expected.items():
    assert hashlib.sha256((parent / name).read_bytes()).hexdigest() == digest, name
    assert not (root / name).exists(), f"unexpected local override: {name}"
for relative in ("scripts/lifecycle_state.py", "scripts/backlog.py", "scripts/board.py"):
    before = subprocess.check_output([
        "git", "--no-optional-locks", "show", f"{base}:{relative}"
    ], cwd=root)
    assert before == (root / relative).read_bytes(), relative
print("PASS: Desktop native body, configured files and lifecycle implementation unchanged")
PY
```

基线实际路由：父仓 primary Sol/xhigh、worker Terra/xhigh、reviewer Sol/xhigh；工作仓无本地 `.codex` 覆盖。另需比较父仓 `.agents/skills/sdlc*` 的 12 个既有相对链接，全部仍为 `../../.claude/skills/<same-name>`；本次未发现 `~/.codex/skills` 或 `~/.claude/skills` 中匹配 `sdlc*` 的条目，不能沿用旧 project 的 11+11 声明。C3 是本机路径绑定的静态比较，不证明已加载角色或真实 backend；环境迁移先核对对应配置与发现来源，不能直接刷新摘要。Build 的源码 diff 审查还须确认协议中 Desktop 默认语义没有被 T3 例外覆盖。

## 实现记录（实际）

- 本次只创建当前工程候选；尚未执行 TASK-t3-nested-contract，没有改合同源码、测试、README 或版本文件。
- 依次读取父仓 soul/user/AGENTS、工作仓 AGENTS、Plan/软件交付/阶段协议及其适用模板、skill-maintainer、project/product；按范围读取当前 adapters、router、README、测试/验证和版本事实。没有读取上游兼容方案线程来替代本 Plan，没有调用下级执行者。

## 验证记录（实际）

本节是 **Plan 输入核对**，不是独立 Validate 或实现通过。下列命令在上述工作仓执行，均 exit 0；读取命令只证明相应当前文本可读。

| 实际命令 / 检查 | 观察结果 |
|---|---|
| `git --no-optional-locks rev-parse HEAD`；`git --no-optional-locks rev-parse --show-toplevel --abbrev-ref HEAD HEAD` | 完整 HEAD 与 root/branch 如规划基线；后一个命令对两个 HEAD 参数均输出分支名，SHA 以第一个命令为准 |
| `git --no-optional-locks status --short --untracked-files=all`；`git --no-optional-locks diff --stat -- .sdlc-v1/state.json` | 初始仅 state 未暂存和产品未跟踪；state 为 25 行新增，工程候选初始不存在；业务源文件干净 |
| `python3 -B scripts/lifecycle_state.py --repo . product-projection --requirement-id REQ-t3-nested-delegation` | ready、feature null、原依赖存在 |
| `python3 -B scripts/lifecycle_state.py --repo . verify-acceptance --requirement-id REQ-t3-nested-delegation` | spec_ready match；current/expected 均为前述 c4f9a2… 指纹 |
| `python3 -B scripts/lifecycle_state.py start-feature --help`；`python3 -B scripts/lifecycle_state.py add-task --help` | required/optional 与 brief 完全一致；start-feature 没有 title；add-task 的 depends-on 为逗号分隔 scalar |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -B -m unittest test_scenarios.T3ChildContractTest.test_real_repository_contract` | 1 test / OK；只读运行当前文档形状检查，不是新合同或 live 行为通过 |
| `bash -n scripts/validate-skills`；`git --no-optional-locks diff --check` | shell 语法和初始已跟踪 diff 空白检查通过 |
| `python3 -B -`（AST parse lifecycle_state/test_scenarios/test_support） | 三份当前脚本 AST 可解析；无 pycache 或文件写入 |
| `python3 -B -`（Desktop/Codex body 与配置/CLI 比较、定向发现链接 inventory） | native 正文及相关实现与基线相同；配置摘要与上述 C3 相同，发现链接只读列举；不是 Desktop 运行回归 |
| `python3 -B -`（只读工作树/parent/state/index 快照） | 241 个 tracked/untracked 条目纳入排除本候选的比较基线；旧 REQ/FEAT 均 released；state 内容 SHA-256 为 `24e191cdb831499e037ca4010ae6ae910fc52fc0404a002b2f7b287539178be3`；产品内容 SHA-256 等于 spec 指纹；父仓既有 diff/index 留存内存摘要，未复制正文 |

尚未运行：完整 C1/C2、覆盖率、全部新 AC 的实现后合同走查、正式独立 Validate/Review、新多层/取消/资源/Desktop 实验。当前宿主声明本执行者为 `gpt-6.1-sol / xhigh`；没有另行取得 run 绑定回包或 backend 身份证明，不将声明、角色文件或摘要当实际后端证据。

另行只读核对 `python3 -B -m coverage --version` 返回 exit 1：当前默认 Python 为 3.15，未安装 coverage 模块。没有安装、遍历其他模型或启动实验。需要对修改的可执行检查逻辑给出数值覆盖率时，须先提供可核实的已有覆盖率工具/执行环境与命令；当前不能承诺默认 80%/70% 已满足，也不能把工具缺口当实现失败。该缺口只影响依赖数值覆盖率的验证/接受，不阻止本地编辑、确定性测试和合同检查，不在本方案新增包依赖或安装授权。

候选文件首次格式检查发现 8 行 Markdown 行末空白（`git diff --no-index --check` exit 3），已移除。首次只读候选审查脚本 exit 1，是逐项 AC token 断言遇到表格中的省略前缀；后续改为完整 AC 引用并重验。该脚本的 token 检查只确认引用清单齐全，不证明合同语义或行为。

修正后 `python3 -B -` 候选审查脚本 exit 0：本文件是普通 UTF-8 文件、无行末空白、本地 Markdown 链接存在、模板顺序正确、仅一个 Task 标题且 18 个 AC 均有显式引用；同时实际执行了本文 C3 的 Python 内容并通过。`git --no-optional-locks diff --no-index --check /dev/null .sdlc-v1/context/FEAT-t3-nested-delegation.engineering.md` 返回 exit 1 且无输出：`--no-index` 对新文件内容差异采用 exit 1，不能记成 exit 0；空白无误另有前述脚本证据。最终 `spec_ready` 重查仍 match，工作树仅新增本工程候选，原 state/product 状态保留。

正式 validation 仍要求所有 Task 完成、实现已提交且 `.sdlc-v1/**` 外工作树干净，state 已 tracked/未 staged/无冲突，当前 product/engineering context 已 tracked/无冲突。用户目前没有授权 commit；因此可以先完成本地实现、C1/C2/C3 和人工检查，再由原主 Agent 在具体 diff 与证据可供审阅时处理缺少的提交授权。不得自动 stage/commit 或请求 record-validation pass，不用旧 released 证据代替。即使正式前置条件未满足，也不能倒推本地实现/检查不可开始；未来必要真实使用证据仍须单独判断和保留缺口。


### 2026-11-16 独立 Validate：提交 440529683647c2b04f0741791d07fc8ed8a23309

本轮由不同于实现者的新执行上下文实际运行；此处结论仅覆盖已接受的离线合同范围，候选待原主 Agent 验收。`t3_thread_configure({})` 只读返回本 run 的 host-effective `codex / gpt-6.1-terra / reasoningEffort=xhigh`，`executedModel`、实际 backend 和内部 effort 未返回，均未知。环境为 macOS Darwin 25.6.0 arm64，标准 Python 3.15.2，已有 `../../.venv/bin/python` 为 Python 3.12.16、coverage.py 7.17.2。未联网、安装、认证或启动真实模型、Desktop 或多层实验。

起始 2026-11-16T10:32:46Z：`git rev-parse --show-toplevel`、`git branch --show-current`、`git rev-parse HEAD`、`git status --porcelain=v1 --untracked-files=all`、`git ls-files --stage -- .sdlc-v1/state.json .sdlc-v1/context/REQ-t3-nested-delegation.product.md .sdlc-v1/context/FEAT-t3-nested-delegation.engineering.md`、`git diff --cached --name-status`、`git ls-files -u` 与 `git diff --check` 均 exit 0；工作仓根、分支和 HEAD 符合 brief，工作树与 index 干净、无 unmerged，三个指定文件 tracked。`python3 scripts/lifecycle_state.py feature-projection --feature-id FEAT-t3-nested-delegation` 和 `python3 scripts/lifecycle_state.py verify-acceptance --feature-id FEAT-t3-nested-delegation` 均 exit 0：Task done、validation/review pending，spec_ready 与 plan match，validation/review fingerprint missing。起始 SHA-256：state `a2bfa5052835031ca63d5a3ba14566a913530bf2e6d15b419d3e335c560c323a`，product `c4f9a2f58e918559fae9d06c7ed1df207a3b6bcebead6623aaee2d3f644a90d6`，engineering `ae96268762ab42696c3af873dda2b7be5c1041d62938d6ae1e4da731abb8efac`。父仓起始 HEAD `1cd4525c99bcfefe265ffc564ad0dfe0fed2879a`，已有修改按 status 保留。

| 实际检查，UTC | exit / 观察 |
|---|---|
| C1 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -B -m unittest -v test_scenarios.T3ChildContractTest`，10:33:37 | 0；6 tests OK；真实引用、缺失/错误锚点、旧无条件禁令、旧顶层肯定路径、缺文件与限定 Desktop/未知能力正例。临时副本和原文不变断言仅验证文档形状。 |
| C2 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills`，10:33:22–10:34:18 | 0；八组 90+7+13+36+12+19+4+6=187 tests OK，结构/本地引用及反例通过；含 B03/B05 fixture。`HTTPError 500` 清理有 ResourceWarning，测试仍 OK。 |
| coverage：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts COVERAGE_FILE=<本轮临时路径> ../../.venv/bin/python -B -m coverage run --branch --source=scripts -m unittest -v test_scenarios.T3ChildContractTest`；`../../.venv/bin/python -m coverage json -o <本轮临时路径>/coverage.json`（同一 `COVERAGE_FILE`），10:34:28–10:34:29 | 均 0，6 tests OK；实际读取 JSON 并用 AST 定位 `t3_child_contract_errors` 460–491：行 22/22 = 100%，遗漏行 `[]`；分支 20/20 = 100%，遗漏分支 `[]`，达到 80%/70%。本轮首次错误使用 `--source=scripts/test_scenarios.py`：run 0 但警告未收集数据，JSON exit 1；属调用参数配置错误，未将其报告为通过，以上目录形式重跑取得数据。 |
| C3：执行本文 C3 的 Python 静态比较，并额外断言 marker 存在及 12 个发现链接的目标、目标存在；`python3 -B -`，10:34:55 | 0；相对 `a1c81656302ede8a90e08e7a2f762910ed53de54`，Codex adapter `## Interface map` 后正文、三份父仓配置摘要及三个 lifecycle 实现一致；工作仓无本地覆盖，12 个父仓相对发现链接一致，两个用户目录无 sdlc* 项。不是 Desktop live 证据。 |
| `git --no-optional-locks diff --check`、`git --no-optional-locks diff --name-only HEAD`、`git --no-optional-locks status --short --untracked-files=all`，10:35:37 | 各 exit 0，追加证据前业务树与整个工作树干净。`git diff a1c81656302ede8a90e08e7a2f762910ed53de54..HEAD -- .claude-plugin/plugin.json .claude-plugin/marketplace.json` 无差异；另以 Python 字节比较 exit 0，plugin 版本 7.0.1，CHANGELOG 该条在 Unreleased，未发布。 |

逐项人工对照当前产品 AC 与提交文件，以下 COVERED 仅指静态合同及对应离线 fixture，非真实执行：

| AC | 结果及对照位置 / 分支 |
|---|---|
| 001 | COVERED：protocol §T3 layer boundary 第 47–56 行要求当前任务明确要求、宿主/授权/资源允许并指定执行者和汇总点。 |
| 002 | COVERED：同处 generic continue、祖先权限无效，明确禁止优先；缺派工报告缺口。 |
| 003 | COVERED：同处 47–53、89–97 行及 runtime selection 117–130 行，缺能力/路由/授权停止依赖启动，不绕过。 |
| 004 | COVERED：同处 54–65 行逐层独立条件、原范围子集及不扩张权限。 |
| 005 | COVERED：同处 58–63 行共享原总量/并发，未知剩余或写者互斥停止依赖启动。 |
| 006 | COVERED：同处 67–75 行保存实际执行者、revision、命令、未知、有序请求；每层与原清单取子集，仅原主 Agent 接受及 mutation。 |
| 007 | COVERED：同处 74–75、99–107、126–141 行区分新 ID、旧候选与不同上下文实际检查当前候选；本轮是实际运行。 |
| 008 | COVERED：同协议 227–233 行仅宿主明确要求、原范围、写者交还及终止确认的小 finding 自修，保留检查、审查和历史。 |
| 009 | COVERED：同协议 220–233 行普通修正归原实现者，新独立 review/recheck 依宿主合同，未知交还不写。 |
| 010 | COVERED：同协议 89–97、115–130 行及两个 adapter，依据实际宿主选择 native 或 app-owned，不静默换路由。 |
| 011 | COVERED：C3 字节比较和 protocol 20–26、89–97 行，T3 例外不改 Desktop 默认；真实 Desktop NOT_RUN。 |
| 012 | COVERED：protocol 89–97 行限定 2026-11-11 的机器、机制和错误，不推断全部路径失效或问题已修复。 |
| 013 | COVERED：protocol 126–141 行区分请求、绑定生效配置、观察、backend；缺 backend 不自动普遍判败，必需证据不符不接受。 |
| 014 | COVERED：protocol 77–80 行跟随原句柄 host next，超时/轮次返回不证明终止或 Goal 完成。 |
| 015 | COVERED：protocol 81–85 行分别区分取消回执、任务、写进程、资源；未知时禁止重叠写者且不停止共享资源。 |
| 016 | COVERED：protocol 77–80 行保留独立有效结果和失败证据，仅停止依赖工作，不声称整体完成。 |
| 017 | COVERED：protocol 85–87 行及 §5 保留跨层、provider 和改名的失败/诊断历史，不重置次数。 |
| 018 | COVERED：protocol 64–65、165–166 行及 §2 敏感材料规则；每份 brief 带限制、脱敏、审计内容只作数据。 |

README 第 45–65 行链接当前产品场景并注明宿主工具合同、项目模型路由、阶段 brief 的参数来源；C1 校验新增共享锚点，C2 校验本地引用，产品链接目标实际存在。逐条人工核对仅覆盖提交的文字合同，B03/B05 是原 lifecycle fixture，不能推断多层 Agent 行为。真实多层授权/拒绝、等待/取消级联、backend 执行模型与资源释放、Desktop 运行均 NOT_RUN/未知；没有从静态检查外推 live 通过。历史测试先行失败、GLM 400 unknown model、用户授权 Terra 和未知非收敛/诊断状态保留在原记录，未重置。

资源：C1 和 C2 测试采用 `TemporaryDirectory`、C2 的 `mktemp`/EXIT trap 与独立临时 Git fixture；输出中本轮 `/var/folders/zn/9h5xx7817g1byxssf2d_8k7w0000gn/T/sdlc-arch-refs.f1jJgS` 为本轮所有。coverage 的 `t3-validate-cov-ew2brgr3` 与 `t3-validate-cov-mx8edm9c` 均确认已移除。C2 loopback stub 使用 `127.0.0.1:0`，测试 teardown 调用 shutdown/join/server_close，测试进程正常退出；无共享服务操作，未对未知资源做清理。测试进程结束和 teardown 不证明生产环境资源释放。以上离线必要检查满足；追加本段后 plan fingerprint 将 stale，须由原主 Agent 核对新旧摘要、重新接受并绑定，再处理本次 `record-validation --result pass` 请求；不得由本执行者改 state 或刷新指纹。

### 2026-11-16 独立 Validate：提交 4922c2830385600dc6f2c9b3c2ff0360e276d9f4

本轮是与实现及版本准备执行者不同的执行上下文，亲自运行下列检查，结论限当前已接受的离线合同范围。宿主声明 `codex / gpt-6.1-terra / xhigh`；本次未取得另行绑定的实际 backend 或内部 effort，均为未知。环境为 Darwin 25.6.0 arm64、Python 3.15.2；已有 `../../.venv/bin/python` 为 3.12.16，coverage.py 7.17.2。未联网、安装、认证、启动真实模型或修改 state。

起始 2026-11-16T11:34:25Z：`pwd`、`git rev-parse --show-toplevel`、`git branch --show-current`、`git rev-parse HEAD`、`git status --porcelain=v1 --untracked-files=all` 均 exit 0；root、branch、完整 HEAD 匹配 brief，工作树干净。11:35:10Z 的 `git ls-files --stage -- .sdlc-v1/state.json .sdlc-v1/context/REQ-t3-nested-delegation.product.md .sdlc-v1/context/FEAT-t3-nested-delegation.engineering.md` 显示三者 tracked；`git diff --cached --name-status`、`git ls-files -u` 输出为空。`python3 -B scripts/lifecycle_state.py --repo . feature-projection --feature-id FEAT-t3-nested-delegation` 显示唯一 Task done、Feature reviewed、release pending，旧 validation 仍绑定 440529；`python3 -B scripts/lifecycle_state.py --repo . verify-acceptance --feature-id FEAT-t3-nested-delegation` 显示 spec_ready、plan、validation、review 均 match。两条只读 CLI 执行的外层命令组 exit 0；未调用 lifecycle mutation。起始 SHA-256：state `dde05c682aaa1bf67a69720be39de22fb3ef39536b17e843c27217f3cac3472a`，product `c4f9a2f58e918559fae9d06c7ed1df207a3b6bcebead6623aaee2d3f644a90d6`，engineering `4326be6de4316830080f3e6a5fff936d88e5253b86e357779fce7ef7c4576dbd`。

| 实际检查（UTC） | exit / 实际结果 |
|---|---|
| C1 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -B -m unittest -v test_scenarios.T3ChildContractTest`，11:35:10–11:35:30 | 0；6 tests OK，含真实引用、缺文件、无效引用和旧禁令反例、旧顶层肯定路径及合法 Desktop 限定；只证明静态检查范围。 |
| C2 `TMPDIR=<本轮独立临时目录> PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills`，11:35:30–11:36:13 | 0；结构、引用、正反例及八组 90+7+13+36+12+19+4+6 = 187 tests OK，无跳过报告。`HTTPError 500` 清理出现 `ResourceWarning`，未掩盖；测试通过不证明生产资源释放。 |
| coverage `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts COVERAGE_FILE=<本轮临时路径> ../../.venv/bin/python -B -m coverage run --branch --source=scripts -m unittest -v test_scenarios.T3ChildContractTest`；同一 `COVERAGE_FILE` 下 `../../.venv/bin/python -m coverage json -o <本轮临时路径>/coverage.json`；`python3 -B -` 使用 AST 定位函数并从 JSON 统计，11:36:08–11:36:09 | 各 0；6 tests OK；`t3_child_contract_errors` 460–491 行 22/22、分支 20/20，均 100%，遗漏均为空，满足 80%/70%。实际统计对象为修改的可执行检查函数，不是整个仓库覆盖率。 |
| C3 `python3 -B -` 执行上文 C3 Python 比较，并额外断言 marker 存在、12 个父仓发现链接的目标与存在性、两个用户技能目录无 `sdlc*`，11:36:09–11:36:13 | 0；相对 `a1c81656302ede8a90e08e7a2f762910ed53de54` 的 Codex `## Interface map` 后正文、三份父仓配置摘要、三个 lifecycle 文件相同，工作仓无本地覆盖，12 个相对链接一致。Desktop 只是静态保护。 |
| `python3 -B -` 解析两个插件 JSON，断言 plugin.version、marketplace.metadata.version、唯一 `sdlc-pilot` entry.version 都是 `7.1.0`，断言 CHANGELOG 首个且唯一 `7.1.0` 章节包含 T3 与 Desktop/Codex，11:36:09–11:36:13 | 0；三个值和变更清单一致。该标题自身明示不代表验证、评审或发布完成。 |
| `git --no-optional-locks diff --check`、`git --no-optional-locks diff --name-only HEAD`、`git --no-optional-locks status --short --untracked-files=all`、`git diff --cached --name-status`、`git ls-files -u`、`git rev-parse HEAD`、`git branch --show-current`、上述三文件 `shasum -a 256`，11:37:17 | 各 0；追加证据前工作树/index 干净、无冲突，HEAD/branch 和三个摘要未变。 |

覆盖率首个拟执行的 shell 调用被执行环境以 `rm -f style commands are not permitted` 拒绝，命令未启动、无 shell exit code；随后使用 Python `TemporaryDirectory` 运行上表命令并确认自动移除，未隐藏该拒绝。此前 Plan 的默认 Python coverage 缺模块、历史首次 coverage 未收集数据/JSON exit 1、测试先行预期失败、GLM 400 和未知非收敛/诊断使用事实均保留在前文，不由本轮重置。

本轮重新读取当前产品 AC-001–018、权威协议及两个 adapter，并按上轮逐条对照表逐例核实：001–005 对应 protocol T3 boundary 的明确请求、逐层子集/额度和缺口；006–009 对应结果归属、独立性、普通修正和限定自修；010–013 对应宿主路由、Desktop 静态保护、限定历史和分层配置证据；014–018 对应原句柄、取消/写者/资源、独立结果、失败历史及敏感材料。上述各项对**已接受的静态合同范围 COVERED**，依据是本轮实际阅读、C1/C2/C3 和本节前一份逐项对照表的文件位置；这些检查不证明真实执行。`git diff 440529683647c2b04f0741791d07fc8ed8a23309..4922c2830385600dc6f2c9b3c2ff0360e276d9f4` 显示产品与合同源码未变，业务变化仅两个插件元数据文件的三处版本值和 CHANGELOG 标题，另有本 Feature 工程证据与 state 更新；故上轮具体 AC 位置对当前文本仍适用，本轮重新运行的结果不是借用上轮测试。README 的 `SCN-t3-nested-delegation` 指向当前产品规格，参数来源为宿主合同、项目路由和本阶段 brief；本轮实际按用户明确禁止再派工的 brief 自行检查并保持 `allowed_transitions: []`，仅是 AC-002 的本地实际使用例，不证明允许派工的实际路径。真实 Desktop、真实 T3 多层授权/取消级联、真实 backend/内部 effort 和生产资源释放均 NOT_RUN/未知；本轮不将静态或本地 fixture 外推为 live。

资源预检使用 `ps -Ao pid,ppid,command` 定向查看测试及临时目录相关进程；测试仅使用独立临时 fixture 和 `127.0.0.1:0` stub。`scripts/test_hallmark_catalog.py` 中服务执行 `shutdown()`、线程 `join(timeout=5)`、`server_close()`；完整测试进程 exit 0 后，本轮 C2 临时目录 `rmdir` exit 0，coverage `TemporaryDirectory` 报告已移除。11:37:02Z 以 `ps -Ao pid,ppid,command` 按本轮测试命令/临时路径过滤，未见匹配进程；未停止共享资源。该进程检查限可识别命令，不能证明未关联的未知资源或真实生产资源状态。

本轮离线必要检查满足，建议主 Agent 按技能处理 `record-validation --feature-id FEAT-t3-nested-delegation --result pass --test-command 'PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills'`，绑定被测 HEAD；但本 brief 的 `allowed_transitions: []`，本执行者不提交正式 transition 请求、不改 state。追加此证据后工程上下文指纹将变化，主 Agent 须按现行协议核对语义适用性和重新接受/绑定需要，再决定合法操作；当前记录不代表最终接受或发布。

追加后的 11:38:17Z：`git --no-optional-locks diff --check`、`git --no-optional-locks status --short --untracked-files=all`、`git diff --stat`、`git diff --cached --name-status`、`git ls-files -u`、`git rev-parse HEAD`、`git branch --show-current` 和三文件 `shasum -a 256` 各 exit 0；仅本工程上下文未暂存变更，index 无暂存或冲突，HEAD/branch 及 state/product 摘要不变。`python3 -B scripts/lifecycle_state.py --repo . verify-acceptance --feature-id FEAT-t3-nested-delegation` exit 1：spec_ready match，plan/validation/review 均因工程证据追加而 stale；这是实际指纹结果，不是测试失败。此句继续追加证据，最终工程文件摘要交由交接结果报告。

## 评审记录（实际）

- 尚未执行独立评审。本次是受托 Plan 编写者，本 brief 禁止创建下级；自身阅读不称独立 review。原主 Agent 接受前核对完整 Task 集合、产品关联、写范围、验证范围及有序请求；如风险需要独立读计划，由原主 Agent 按实际宿主和授权安排。

### 2026-11-16 本地实现及独立预评审

- 实现候选为 `a1c81656302ede8a90e08e7a2f762910ed53de54` 加九个授权业务文件的未提交修改；业务 diff SHA-256 为 `b803b2d60cc25f7fac99c7128abeefa30e61479775f5c9a6d2578dfbeab774e4`。实现者报告其请求及宿主配置为 `codex / gpt-6.1-terra / xhigh`；`executedModel=null`，实际 backend 与内部 effort 未知。
- 标准入口 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills` exit 0，八组共 187 项通过；保留既有 HTTPError 清理 `ResourceWarning`。合同测试 C1 为 6 项通过；最终快照的检查函数经既有 coverage 环境复核为 22/22 行、20/20 分支，临时覆盖数据已清理。测试先行阶段因新合同尚未写入而有一次预期失败。
- C3 及主 Agent 的独立静态比较均通过：Desktop adapter 从 `## Interface map` 起的正文、父仓三份模型/角色配置、三个 lifecycle 实现及 12 个技能发现链接与基线一致；这不证明 Desktop 的实际运行行为。
- 独立 Sol 预评审九个业务文件，findings 为空；该评审者读取实现者原始执行记录时返回 `thread_not_found`，主 Agent 随后以对应环境和完整线程 ID 核对原始检查回执。该预评审不构成提交版本的正式 validation 或 Review。
- 原 GLM 实现器启动时返回 `400 unknown model`，未执行工具或写入；用户随后明确授权本次 Terra 接手。真实多层派工、Desktop/native、取消与资源释放行为未运行或未观察；历史失败及未知非收敛/诊断使用情况不重置。

### 2026-11-16 正式独立 Review：提交 440529683647c2b04f0741791d07fc8ed8a23309

- 独立评审覆盖自 `a1c81656302ede8a90e08e7a2f762910ed53de54` 起的九个业务文件、产品 AC-001–018 和当前方案；findings 为空，建议 `approved`。评审未发现有证据支持的重复实现或可避免工程债。
- 已对照[独立 Validate 原始记录](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A76e4319b-f48b-481f-8e05-e26664b98e8c%3Adelegate-task%3Ad8613460-416f-44d5-8fd8-fa5d28df4fd2)和当前有效方案；批准范围限文档合同与已执行离线检查。真实 Desktop、多层执行、取消级联及生产资源释放仍为 NOT_RUN/未知。
- 评审的宿主配置为 `codex / gpt-6.1-sol / xhigh`；`executedModel`、实际 backend 和内部 effort 未知。一次父仓对象查询误在工作仓执行，exit 128；随后在父仓读取成功，exit 0。首次 coverage 未收集数据及后续修正、GLM 400 和未知非收敛/诊断历史均保留。
- 本记录追加后需重新核对并绑定相关指纹；原 Review 的 transition 由主 Agent 在接受证据后处理。

## 发布与观察记录（实际）

- 产品观察计划只引用产品上下文“发布后观察计划”，不在这里复制指标、窗口、负责人或回流规则。
- 当前没有发布授权、版本调整、tag、push 或 release；没有 live 观察。未来发布前按当时明确授权、三处版本一致性、独立验证/评审、已批准内容及必要 smoke 处理，不能从本 Task 的待发布说明推导发布授权。
- 回滚原则：保留源输入和失败证据；只能在当时授权下撤销本 Feature 自有改动，不 reset/clean、不覆盖父仓或旧历史，不把共享资源停用当回滚。尚无实际发布版本需要回退。

### 2026-11-16 7.1.0 发布预检

- 上述无发布授权的记录描述的是当时状态；用户此后明确授权两个仓库 push 和发布。发布目标为 GitHub 源码与插件版本，候选实现提交为 `4922c2830385600dc6f2c9b3c2ff0360e276d9f4`。发布前远端 `main` 和 `fix/t3-stage-dispatch` 均指向 last-good 源码 `a1c81656302ede8a90e08e7a2f762910ed53de54`，其插件版本为 `7.0.1`；当时最新 GitHub Release 为 `v5.0.0`。旧源码提交保留用于恢复；如发布检查失败，停止扩大交付并保留证据，按实际情况准备恢复，不强推或清理无关改动。
- [7.1.0 独立 Review](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A76e4319b-f48b-481f-8e05-e26664b98e8c%3Adelegate-task%3Ae195b2bd-d905-4c31-8049-c7f55db7f276) 的 findings 为空，建议 `approved`；批准范围限文档合同、版本元数据和已执行的离线检查。请求与宿主配置为 Codex Sol/xhigh，实际 backend 和内部 effort 未知。
- 上述 7.1.0 Validate 记录中 C3 和版本检查的具体时段仅由执行者报告；独立核对可见该 activity 更新时间为 `11:36:29.556Z`，未独立证实所写精确时段。首个 coverage 调用被拒只有执行者记录，原始工具项不可见；后续成功检查有原始证据。真实 Desktop、T3 多层与取消级联及生产资源释放仍为 NOT_RUN/未知。

### 2026-11-16 7.1.0 Release 归档检查与 smoke（本轮）

- 11:59–12:02 UTC，Darwin 25.6.0 arm64、Python 3.15.2、Git 2.56.0、gh 2.103.3。工作仓 `/Users/mac/hansen_agent_team/external/sdlc-pilot`，branch `fix/t3-stage-dispatch`，HEAD/validation commit `4922c2830385600dc6f2c9b3c2ff0360e276d9f4`。起始 `product-projection`、`feature-projection`、Requirement 和 Feature 的 `verify-acceptance` 各 exit 0：Feature reviewed、release pending，spec_ready/plan/validation/review 均 match。`git diff --name-status 4922c2830385600dc6f2c9b3c2ff0360e276d9f4 -- . ':(exclude).sdlc-v1'` exit 0 无输出；status 只有事先存在的本文件和 state 未暂存修改，index 无暂存。
- `gh api repos/arnow117/sdlc-pilot/releases/tags/v7.1.0` exit 0：公开 Release <https://github.com/arnow117/sdlc-pilot/releases/tag/v7.1.0>，draft=false、prerelease=false、published_at=2026-11-16T11:57:41Z。`git ls-remote https://github.com/arnow117/sdlc-pilot.git refs/heads/main refs/heads/fix/t3-stage-dispatch refs/tags/v7.1.0 'refs/tags/v7.1.0^{}'` exit 0：两个分支均 `4922c2830385600dc6f2c9b3c2ff0360e276d9f4`，annotated tag 对象 `682c8f5672ee45a4544fcd2ad430fe4a2ddbacdc`，解引用为该 commit。前述预检记录 last-good `a1c81656302ede8a90e08e7a2f762910ed53de54` / 7.0.1；本轮未执行回滚或远端写入。
- `curl --fail --location --silent --show-error --output <临时目录>/release.tar.gz https://api.github.com/repos/arnow117/sdlc-pilot/tarball/v7.1.0` 和 `git archive --format=tar --output=<临时目录>/validation.tar 4922c2830385600dc6f2c9b3c2ff0360e276d9f4` 各 exit 0。下载归档 SHA-256 `e1b842e0913f63aeabc9109b2b6cd78e3e62bd0275835647507394fa3bfcb042`，git archive SHA-256 `181d30ba1f48adcb0c4a6e209a228576d1bf1cccd0107f95235b0b3e62fcb178`。本轮临时 Python 检查拒绝绝对/穿越路径、重复项、越界链接和特殊类型，比较去除 GitHub 顶层目录后的路径、普通文件 SHA-256 与 0777 mode、符号链接目标和目录类型，351 项对 351 项，0 差异；使用 `tarfile` 的 `data` filter 解包。比较脚本与 `shasum` 在同一 shell 调用，外层 exit 0，比较输出为 0 差异且确认解包完成；单独比较进程 exit 未由外层捕获。
- 在新解包目录检查插件 JSON 的 `plugin.version`、`marketplace.metadata.version`、唯一插件 `version` 均为 7.1.0（Python 断言与 CHANGELOG `rg` 的组合命令 exit 0）；CHANGELOG 7.1.0 条目说明 T3 条件派工及 Desktop 默认路径，并明确静态检查边界。`PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills` exit 0、RESULT PASS：八组分别 90、7、13、36、12、19、4、6 项，共 187 tests；13 项场景组含 `T3ChildContractTest`，6 项为 Security 依赖测试。hallmark 测试出现 HTTPError 500 清理 `ResourceWarning`，套件仍通过。
- 额外 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v scripts.test_scenarios.T3ChildContractTest` exit 1：`ModuleNotFoundError: No module named 'lifecycle_state'`，该调用未把 `scripts` 加入 Python 搜索路径，未运行目标测试；标准套件中相同测试文件已通过，但该单独调用的失败必须保留。按本轮“任何失败停止扩大发布”指示，本执行者停止推进并不建议当前执行 `record-release`。`PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_security_dependency.py -v` exit 0，6 tests OK；`PYTHONDONTWRITEBYTECODE=1 python3 skills/sdlc/scripts/check_security_dependency.py` exit 0，CLI `not_found`、plugin/authentication/version `not_checked`、scan `not_run`；不能据此断言真实扫描或插件不可用。`PYTHONDONTWRITEBYTECODE=1 python3 scripts/lifecycle_state.py --help` exit 0；工作仓 `git diff --check` 在追加本节前 exit 0。
- **执行边界偏差**：启动标准套件前未识别其副作用。`scripts/test_lifecycle_state.py` 等在隔离临时测试 fixture 内创建 Git 仓库、提交及执行 lifecycle mutation；这违反了本轮禁止 Git 写入/提交及 lifecycle mutation 的指令。测试不是工作仓或 GitHub 写入；该事实不由通过结果抵消。未在实际工作仓执行 Git 写入、提交或 lifecycle mutation，未向 GitHub 写入；主 Agent 应将此偏差纳入接受判断。
- 产品观察引用 `.sdlc-v1/context/REQ-t3-nested-delegation.product.md` 的“发布后观察计划”。本次只有公开 Release、源码和离线检查，无可用采用率或运行观测、反馈证据；真实多层、Desktop、取消级联、生产资源释放及真实安全扫描均 NOT_RUN/未知。建议 2026-11-17 12:00 UTC 或下次适用且获授权的交付时由原主 Agent 检查现有反馈和运行证据；不自动启动模型实验或后台服务。
- 本轮专属目录 `/tmp/sdlc-ship-v710-6y9MZD9p` 已由 Python `shutil.rmtree` 移除，退出 0 且 `exists=False`；测试进程已退出，`ps -Ao pid,ppid,command` 按本轮路径及测试命令过滤无匹配（`rg` exit 1 表示未匹配）。不据此推断未知或生产资源状态。`allowed_transitions: []`；追加本节会使工程上下文验收指纹 stale，主 Agent 须重新核对后自行决定后续操作。
- 12:02 UTC 追加后核对：`git diff --check` exit 0；`git status --short --branch; git diff --cached --name-status; git rev-parse HEAD` 命令组 exit 0，仍只有本文件和原有 state 未暂存、index 无暂存、HEAD 不变；业务树差异检查 exit 0 无输出。`verify-acceptance --feature-id FEAT-t3-nested-delegation` exit 1：spec_ready match，plan/validation/review 因本节证据追加而 stale；本行继续追加，不以先前摘要声称最终文件哈希。


### 2026-11-16 7.1.0 Release 有界补验

- 12:04–12:06 UTC，工作仓 `/Users/mac/hansen_agent_team/external/sdlc-pilot`，分支 `fix/t3-stage-dispatch`，HEAD `4922c2830385600dc6f2c9b3c2ff0360e276d9f4`。`git --no-optional-locks status --short --branch --untracked-files=all`、`git --no-optional-locks rev-parse HEAD`、`shasum -a 256 .sdlc-v1/state.json .sdlc-v1/context/FEAT-t3-nested-delegation.engineering.md` 在追加前均 exit 0；已有本文件和 state 未暂存修改，state SHA-256 `b94a2f0e055249b8df221ebf9ac3f55e027b35a7995feccce5a660b951dfd7f2`、本文件追加前 SHA-256 `944c37eaed1f6160261074d7229242f649a965f6ae272b56793cbb6944a91390`。`git --no-optional-locks diff --cached --name-status` 与 `git --no-optional-locks diff --name-only HEAD -- . ':(exclude).sdlc-v1'` 输出为空（与 `date`、`shasum` 同一命令组 exit 0）。
- `mktemp -d /tmp/sdlc-v710-recheck-XXXXXXXX` exit 0，创建 `/tmp/sdlc-v710-recheck-dh22k04a`。`curl --fail --location --silent --show-error --output /tmp/sdlc-v710-recheck-dh22k04a/release.tar.gz https://api.github.com/repos/arnow117/sdlc-pilot/tarball/v7.1.0` exit 0；`git --no-optional-locks archive --format=tar --output=/tmp/sdlc-v710-recheck-dh22k04a/validation.tar 4922c2830385600dc6f2c9b3c2ff0360e276d9f4` exit 0。下载归档 SHA-256 `e1b842e0913f63aeabc9109b2b6cd78e3e62bd0275835647507394fa3bfcb042`，本地 archive SHA-256 `181d30ba1f48adcb0c4a6e209a228576d1bf1cccd0107f95235b0b3e62fcb178`。
- 专属临时目录内建立的 `compare.py` 经 `python3 -B /tmp/sdlc-v710-recheck-dh22k04a/compare.py` **单独执行 exit 0**：去除 GitHub 单一根目录后各 351 项（109 目录、241 普通文件、1 符号链接），路径和类型、普通文件 SHA-256 及 0777 模式、符号链接目标均一致，差异 0；目录模式不是 Git 跟踪属性，未比较。脚本拒绝绝对路径、穿越、重复路径、不安全链接、非目录祖先及特殊类型，比较通过后使用 Python tarfile `data` filter 解包。
- 只读检查 `scripts/test_scenarios.py` 的 `T3ChildContractTest`、`t3_child_contract_errors` 和模块导入及 `scripts/test_support.py`、`scripts/lifecycle_state.py` 的导入路径（含 `python3 -B -` AST 顶层检查，exit 0）：六个测试只读合同文件并在 `TemporaryDirectory` 写入副本，未调用其他场景的 Git fixture、Git 或 lifecycle mutation；`test_support` 的 Git 写函数和 lifecycle 写函数虽定义但不由该测试调用。未运行完整标准套件。
- 在 `/tmp/sdlc-v710-recheck-dh22k04a/extracted/arnow117-sdlc-pilot-682c8f5`，先 `export TMPDIR=/tmp/sdlc-v710-recheck-dh22k04a/test-tmp`，随后 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -B -m unittest -v test_scenarios.T3ChildContractTest` exit 0，**Ran 6 tests, OK**。这只覆盖静态文档合同，未运行真实模型、Desktop、多层协作、取消或生产资源检查。
- 前次单独调用 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v scripts.test_scenarios.T3ChildContractTest` exit 1、`ModuleNotFoundError: No module named 'lifecycle_state'`，未运行目标测试；上述补验不抹除失败。前次标准套件的 187 项通过及其在隔离 fixture 内 Git 写入、提交和 lifecycle mutation 违反前次 brief 的执行偏差均保留在上节；本轮未重跑该套件。
- `python3 -B -` 检查本轮 `test-tmp` 余项为 `[]`，exit 0；测试进程已退出。另以 `python3 -B -` 的 `shutil.rmtree` 移除本轮专属目录，exit 0，`exists=False`；未停止共享资源。未在任何位置运行 Git 写入或提交、lifecycle mutation、远端写入、安装或实际模型；生产及未知资源状态仍未知。`allowed_transitions: []`，未请求或执行 transition；本记录不判断发布成功。

### 2026-11-16 7.1.0 源码分发验收

- [Sol 最终验收](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A76e4319b-f48b-481f-8e05-e26664b98e8c%3Adelegate-task%3A73bb0f7f-f5c7-4bf6-be16-db16d9363240)核对两轮 Ship 的原始 activity，认为源码分发证据充分，且追加记录未改变产品、有效方案或验证义务；原 Validate 和正式 Review 对 `4922c2830385600dc6f2c9b3c2ff0360e276d9f4` 仍适用。
- 首次定向命令失败及临时 fixture 内违反 brief 的 Git/lifecycle 写入仍是实际发生的偏差；本次有界补验通过且证据显示实际工作仓、index 和远端未受该偏差影响。该判断不把越界执行改写为合规，也不授权扩大后续执行范围。真实 Desktop、T3 多层与取消、生产资源及真实 Security 扫描仍未实测。
