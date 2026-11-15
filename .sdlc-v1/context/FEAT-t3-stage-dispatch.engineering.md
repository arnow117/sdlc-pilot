# 工程上下文：FEAT-t3-stage-dispatch — 按宿主能力调度独立阶段

## 当前有效方案

### 架构设计

**关联产品上下文**：`.sdlc-v1/context/REQ-t3-stage-dispatch.product.md`
**工程上下文**：`.sdlc-v1/context/FEAT-t3-stage-dispatch.engineering.md`
**已确认需求**：产品正文的 NEED、CON、DEC、REQ-001–REQ-007、AC-001–AC-018；来源及范围以该正文为准。
**创建日期**：2026-11-15
**状态**：进度唯一以 `state.json` 为准。

#### 背景

本 Feature 修复已定位的运行时选择、等待和局部停止措辞，使获授权的 T3 主 Agent 能直接派发独立 child 阶段，同时保留模型职责、必要验证、单写者和主 Agent 接受。只修改技能合同、适配说明、使用说明及必要回归，不实现调度服务或修改 T3 宿主。

长期方向来自产品确认日志 U1–U3 和本次委托；不把旧 `project.md` 的版本、测试数或安装链接描述当作当前验证。适用的项目级架构约束为目标 `AGENTS.md` 的“维护原则”“状态与上下文约定”，确认来源为当前已加载项目指令；上层 `AGENTS.md` 的模型职责与交接规则也适用。检查方式为完整 diff 的路径/职责检查、现有 CLI 和确定性回归，以及实际阶段证据核对；本计划不批准其他长期规范。

产品无 `depends_on`。当前分支携带 Security 的未发布实现是 Git 集成事实，不构成产品依赖，也不是修改其验收的授权。

本文比小项目示例长，必要增量是两种宿主路径、四层模型证据、十八个 AC 的证据边界和未发布基线的集成风险；产品判据与协议原文仍通过引用保留唯一来源。

#### 架构与组件

##### 共享阶段协议

- **职责**：`skills/sdlc/references/stage-agent-protocol.md` 保持唯一的派工、brief/result、接受、状态所有权、恢复和非收敛规则。改正 runtime selection 和 waiting/continuation 的适用范围；四层模型证据通过既有 `evidence`、`unresolved_items` 和 context 表达，不新增字段。
- **接口**：现有 stage brief → canonical result → 主 Agent 核对 → 有序 allow-list CLI。保留现有 stage/status、CLI、验收指纹和所有必要接受条件。
- **覆盖**：REQ-001–REQ-007。

##### 运行时适配器

- **职责**：`runtime-adapters/t3-code.md` 映射主 Agent 的 `delegate_task`、实际返回的 `next`、任务句柄和 `task_cancel`；`codex.md` 保留符合配置的原生路径，并明确 T3 托管 Codex 不使用 native 控件。两个 adapter 引用同一协议，不复制第二套接受规则。
- **接口**：能力、当前授权、项目路由和完整 brief → 所选宿主支持的 child 调用。T3 的顶层 thread 仅用于用户明确要求的新会话，不作为阶段 child 的替代品。不增加宿主 API，不假定旧顶层 thread API 的幂等参数、唤醒或 settlement 能力适用于 child task。
- **覆盖**：REQ-001–REQ-005；REQ-006 的执行边界。

##### 入口、模板与回归

- **职责**：`skills/sdlc/SKILL.md` 只导航；`templates/TASK.md` 在既有字段/补充中明确终端执行者限制和证据引用；`README.md` 是唯一全局 usage 入口。`scripts/validate-skills`、`scripts/test_scenarios.py`、`docs/testing.md` 复用现有检查、临时仓库和证据边界。
- **接口**：README 的稳定场景导航到产品故事、共享协议和 adapter；参数分别来自当前宿主工具合同、项目路由与 stage brief，不在 README 复制参数 schema 或敏感配置。
- **覆盖**：REQ-001–REQ-007；SC-004。

#### 关键设计决定

##### 决定 1：扩充现有合同，复用现有执行与状态实现

| 可行候选 | 当前证据与覆盖 | 决定及代价 |
|---|---|---|
| 复用协议、扩充 T3 adapter 和现有检查 | 已有单层执行、canonical result、allow-list、资源和非收敛合同；T3 文档错误地限于 Claude/top-level；现有测试可承接回归 | **采用：复用现有实现。** 集中修正少量合同，保留 native；需人工判断和一次当前候选真实 child 阶段，字符串检查不能代替行为证据。 |
| 只改 T3 adapter | router、Codex adapter、协议仍限定 Claude；通用 timeout 和 stop 措辞仍冲突 | 不采用；调用入口仍会误选，不能覆盖 REQ-004/REQ-007。 |
| 新建调度器、状态表或模型运行器 | 现有宿主已提供 child 和等待/取消；产品明确不需要另一 runtime | 不采用；无已确认缺口支持其成本，违背 CON-003。 |

依次核对了当前文件、标准库测试设施和宿主已加载的工具合同；无新增库、安装、外部检索或供应链变更。复用项目 MIT 文件；未引入第三方实现。没有原型输入或 UI，原型复用和 Web/App 验证不适用。

##### 决定 2：共享接受合同，按宿主选择控制方式

真实变体为 T3 child 和支持 native 的宿主；稳定核心是阶段职责、完整 brief、主 Agent 单写 state、必要检查及有序接受。差异只落在 adapter 的创建、等待、恢复和取消控件。当前 T3 主 Agent 直接使用 child task；受托者直接完成其合同，不能嵌套派工。保留 native adapter 的可用路径，不把本机订阅错误推广为所有 Codex 宿主不能使用 native。

沿用现有 Markdown adapter 扩展边界；不引入策略类、配置 DSL、持久化模型或 schema 迁移。覆盖 REQ-001、REQ-002、REQ-005、REQ-006；代表检查见下表 AC-001–AC-004、AC-012–AC-013。

##### 决定 3：分别报告行为、配置、后端与可接受范围

四层证据的唯一判据引用产品 REQ-003，不在模板重复一张判定表。协议说明如何在现有结果中记录来源、run/时段及未知；adapter 只说明其可取得的事实。只见请求、继承标志未解析、生效配置缺失、明确配置不符、`executedModel=null` 必须区分。普通功能结果不因单独缺后端字段被统一改判；必需模型/角色合规未知仍不满足对应接受条件。

`vibe_host.py` 的 live producer/judge 非空后端要求及 `vibe_test.py` 的 strict/可比较规则保持原样。本 Feature 不修改这些实现、测试合同或 Security 验收。覆盖 REQ-003；以现有严格反例及 AC-005–AC-009 检查边界。

#### API / 接口契约

没有公共 lifecycle CLI 或状态格式变化。沿用 `state_version=3`、原 stage/status 和 canonical brief/result；不得新增模型证明字段、Goal 镜像、结果文件或运行记录协议。宿主可观察的 task/run/thread 与请求、生效配置、实际后端事实留在原生记录和现有工程证据中，不把不同 ID 当作执行了检查的证明。

主 Agent 在首次 `delegate_task` 前按实际宿主合同核对 capabilities、provider/model/options 和授权；后续遵从该宿主的重新核对条件。请求使用完整 provider/model/options；缺失或不符时报告受影响范围。目录无匹配不等于额度耗尽，不能据此换模型。

#### 时序与数据流

以下有序说明覆盖 AC-001、AC-010–AC-018；详细接受和非收敛判据继续引用阶段协议，避免另建状态机。

1. 主 Agent 只读核对所选目标的 projection、验收指纹、Git、授权与路由；未接受或必要证据不足，只暂停依赖该结论的动作。
2. 主 Agent 形成完整 brief，选择适用 adapter，直接派发一个阶段 child。T3 请求带终端执行者限制；不同上下文、路由和 write scope 均待证据核实。
3. 宿主 `next` 要求结束本轮时按要求交还控制，保留原绑定；不轮询、sleep、发消息催问或重复派工。没有该要求且只是普通 timeout 时，按该宿主指引等待同一句柄，不推断活跃、终止或 Goal 完成。lifecycle `next` 只选阶段，与宿主 `next` 分开。
4. 只有实际连接故障、重启、派发结果不确定等事实才触发有界恢复：核对原句柄、已有结果、state/context/Git 和写者；先接受既有结果或恢复未应用部分，不猜幂等键，不重复已成功操作。
5. 获授权取消/替换 T3 child 时使用 `task_cancel`；取消回执、任务终止、所属写入进程终止和专属资源释放分别核对。状态不明不启动同范围接替者，不对 childThread 调用 `t3_thread_interrupt`，不处理共享资源。
6. 主 Agent 核对 canonical result、完整 diff、命令/exit、版本、必要检查、独立性及 allow-list 后才接受和执行 CLI。必要验证失败或缺证不进入依赖它的正式 Review/Ship；按现行归因处理 fail。若 fail 被 CLI 拒绝，保留“停止该 Feature 调度”，不能沿用旧 pass；可做不违反此限制的只读澄清及同目标其他合法独立工作。
7. 已授权独立工作必须同时满足无证据依赖、无写者冲突、依赖已就绪、权限/预算仍有效；没有这样的工作就报告最小恢复输入。用户停止和非收敛限制优先。阶段被接受后继续授权内的必要工作；当前轮次、child 状态和单阶段完成均不决定 Goal 状态。

#### 风险与取舍

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 宿主工具合同变化或当前会话仍加载旧说明 | 再次误选 API、错误等待或重复写者 | 在实际派工时按当前工具定义核对；明确候选加载范围，不承诺不存在的恢复/唤醒能力。 |
| 请求回显冒充生效配置或 backend | 必需模型职责被绕过 | 四层证据分开；缺失标未知、明确不符不接受；run 绑定的可用事实由主 Agent 核对。 |
| 局部继续措辞被用于越过 fail/用户停止 | 旧通过继续进入 Review/Ship | 保留 Validate 的既有拒绝限制，加入独立工作与不得继续的成对场景。 |
| 未发布 Security 基线被整体合入 main | 未满足的旧义务被“顺带发布” | 使用下述集成与发布检查；本 Requirement 不豁免 Security，也不改其上下文或状态。 |
| 静态检查被宣传为 live 调度、取消或资源回收通过 | 验收覆盖被夸大 | 区分确定性脚本、文档合同走查、实际阶段；未发生的 live 分支写未观察。 |

#### 需求覆盖

本表是唯一的“当前 AC → 设计/契约 → Task → 计划验证”关联。所有行对应完整 Task `TASK-t3-stage-dispatch-core`；这些是计划，不是已通过结果。验证方式：**S** 为结构/链接/禁止旧路径的确定性检查；**F** 为现有本地临时仓库 fixture 的真实 CLI/文件断言；**D** 为按产品场景对当前文档和动作序列的人工合同走查；**L** 为加载当前候选的真实 T3 阶段及主 Agent 接受证据。S/F/D 均不能证明未运行的 Agent 行为或宿主能力。

| AC | 设计/契约与计划检查 | 证据适用范围与缺口 |
|---|---|---|
| AC-001 | 运行时适配器；S、D、L：直接 child、完整 canonical、主 Agent 接受 | **L 必需**，优先结合后续独立 Validate；本次 Plan 及旧 H1 均不证明候选修复生效。 |
| AC-002 | 接口契约；D：分别代入工具/授权/必需路由/独立上下文缺失 | 必须报告具体影响、不静默 fallback；除自然发生且有记录外，负路径仅合同覆盖。 |
| AC-003 | 共享协议/模板；S、D，L 核对无嵌套调用及越界写入 | brief 明文禁止嵌套；仅有禁令不证明执行者遵守，L 需实际动作/结果核对。 |
| AC-004 | native adapter；S、D：保留原生接口映射与相同接受条件 | 本轮不发起 native 实验；live native 兼容未验证，不宣称 native 故障已修复。 |
| AC-005 | 决定 3；D：仅 target/角色标签 → 只报告请求 | 不凭标签推断生效配置、backend 或独立性。 |
| AC-006 | 决定 3；D，L 仅核对实际可取得事实 | 宿主生效配置需与 run/时段绑定；null 后端仍未知，功能结果与角色合规分别判断。 |
| AC-007 | 接口契约/模型职责；D：必需配置缺失与明确不符两个反例 | 受影响接受不满足；未执行真实错误路由，不请求降级也不冒充能力缺失已排除。 |
| AC-008 | 严格合同只读依赖；现有 vibe host/core 测试纳入 S 的完整入口；D | 保持缺后端字段的 live 拒绝、strict 不完整/不可比；离线测试不证明真实 live producer/judge。 |
| AC-009 | 主 Agent 接受；D：不同 ID 但未执行检查、实现者自审两个反例；L | 独立 Validate 必须实际检查当前候选；Review 保持不同只读上下文，不用本计划自读替代。 |
| AC-010 | 时序 3；D：宿主 next 明确要求本轮返回 | 动作序列无额外轮询/等待/消息/重派；L 中自然发生则记录，不能假定已经发生唤醒。 |
| AC-011 | 时序 3；D：无结束指示的普通 timeout，保持原绑定 | 与 AC-010 成对核对；timeout 不证明 liveness，不强制制造真实超时。 |
| AC-012 | 时序 4；复用 B05 的 F、D | F 证明登记恢复无重复/漏 Task；连接丢失、未知句柄与 writer 判断仅 D，live 恢复未验证。 |
| AC-013 | 时序 5；S、D：取消仅回执/终止未知/共享资源 | 检查 task_cancel 和不得重叠接管；无真实运行中取消及资源终止证据，不宣称 live 通过。 |
| AC-014 | 时序 6–7；复用 B03 并补最小 F/D 边界 | F 核对缺探针 exit 2、旧批准失效和独立 fixture 可继续；D 核对主 Agent 不把独立只读准备称正式 Review。 |
| AC-015 | 时序 7；复用 B02 的不推进反例并补 D：无独立工作、显式停止 | F 仅证明文件/状态约束；用户选择、停止和 Goal 工具前提由人工语义核对，不制造重试。 |
| AC-016 | 时序 6；F：B03 变体令前置条件不满足，CLI 拒绝 fail；D | 核对非零 exit、准确错误、state/旧记录字节未改；记录“Feature 不再调度”，旧 pass 不代表可继续。 |
| AC-017 | 时序 7；D，L 后主 Agent 按当前授权继续实际 next | 只继续本目标必要且获授权步骤；不要求为此跑一轮额外 B01，不把 Validate 接受当 Goal 完成。 |
| AC-018 | 现有协议 §5 与时序 5/7；D：既用诊断、换名/换模型、未知旧写者 | 失败历史和唯一诊断使用情况不清零；不主动触发非收敛或取消实验；live 异常分支未观察。 |

### 实施计划

**关联产品上下文**：`.sdlc-v1/context/REQ-t3-stage-dispatch.product.md`
**关联设计**：本文“架构设计”；已确认需求和范围引用该产品正文。
**创建日期**：2026-11-15
**状态**：进度以 `state.json` 为准；本文不代表 Build/Validate/Review 通过。
**规划基线**：`0ccd06b1f08b7922882ab28c0ec9841ef5ad1154`，2026-11-15 本地核对。
**恢复基线**：`de2c5ff5014221a92b04e60a952028361e34dc5d`，同一 root/branch；本轮入口仅工程文件追加独立失败事实和主 Agent 的 state reopen 变更，无暂存、冲突或其他路径变化。原规划基线保留为本 Feature 的增量比较基线；本轮不是重建 Feature/Task。spec_ready 为 match，plan 因工程正文变化 stale；先实质修订并由主 Agent 重新接受，不只重记哈希。
**规划工作区**：`/Users/mac/hansen_agent_team/external/sdlc-pilot`；branch `fix/t3-stage-dispatch`。入口 status 仅有主会话 `.sdlc-v1/state.json` 未暂存修改和 `.sdlc-v1/context/REQ-t3-stage-dispatch.product.md` 新文件；其他文件相对 HEAD 无修改。该工程文件为本 Plan 唯一允许的新文件。
**基线复核范围**：下方 Task 的全部写路径，直接依赖的 `AGENTS.md`、本产品和工程上下文、项目路由、`sdlc-plan`/`sdlc-software-delivery`/`sdlc-validate`、`lifecycles/software-delivery.md`、`collaboration-discipline.md`、`scripts/lifecycle_state.py`、`scripts/test_support.py`、`scripts/test_lifecycle_state.py`、`scripts/vibe_host.py`、`scripts/vibe_test.py` 及其现有测试。Security 上下文与状态由其原 owner 维护，不在本 Task 写范围。

#### 背景

规划者亲自读取并核对下列当前摘录；行号定位本基线，不要求实现者照抄或以本段替代执行前现状读取。

| 当前位置 | 已核对事实与实施意义 |
|---|---|
| `stage-agent-protocol.md:60–76`；`runtime-adapters/codex.md:10–15`；router `SKILL.md:14–15` | 只有显式 Claude 才切 T3；应改为能力、授权和项目路由选择，区分 T3 托管与原生宿主。 |
| `runtime-adapters/t3-code.md:9–25` | 旧路径用 launch/send/wait/interrupt/settle 控制顶层 thread；与当前 child 的 delegate_task/next/task_cancel 合同不同，需替换阶段执行路径，不能仅加一段互相冲突的说明。 |
| `stage-agent-protocol.md:267–295`、`:346–363`；router `:63–65` | timeout “Do not finish the work turn”及“stop progression”缺适用范围；应引用宿主 next，限定受影响接受，并保留恢复触发边界。 |
| `stage-agent-protocol.md:539–583`、`:615–630`、`:698–759` | 已有主 Agent 接受、canonical status、fail 拒绝后停止 Feature 和非收敛规则；复用并保持语义，不新增状态或诊断额度。 |
| `templates/TASK.md` 的使用说明/必带限制 | 现有模型、验证和安全限制可承载必要补充；准备批次“原生消息”用词需变为所选宿主的一次派工，不扩大单层权限或新增字段。 |
| `README.md:44–54`；`docs/testing.md:52–56` | usage 仍描述 Claude 与旧观察方式；历史 Scratch/low effort 实测明确不覆盖阶段接受、运行中取消和传输恢复，只可保留为历史事实。 |
| `scripts/validate-skills:270–302`、`:403–453` | 检查 native 控件和结果形状，未纳入 T3 child 合同；已有临时副本正/反例范式（`:145–215`、`:348–400`）可复用。完整入口会运行八组离线测试；本轮未执行。 |
| `scripts/test_scenarios.py:151–304`、`:307–422` | `prepare`、`reference`、`assert_result` 复用临时 Git、产品/工程文件和 B02/B03/B04A/B/B05；F 断言只覆盖状态/文件，不解析 Agent 语义或身份。 |
| `scripts/lifecycle_state.py:1090–1116`、`:1146–1174`、`:1910–1963` | fail 也经过 state/context/Git 前置检查；成功 fail 撤销旧批准。不能改 CLI 让拒绝消失；用 fixture 验证并保留 Feature 停止限制。 |
| `scripts/vibe_host.py:137–150`、`:195–215`；`scripts/vibe_test.py:828–885`、`:921–942` | live 路由/后端缺失、strict 完整和比较要求是真实严格合同；不将其放宽，也不外推成全部普通验证的统一失败条件。 |

未提交输入定位：产品 SHA-256 为 `b6b22862b52a75cc5e1125fa8e34a1a0501cff15d32c272ec89498e0680407f3`；入口 state 文件 SHA-256 为 `ebf295a5c22e46660e054122b08dfc673129b1efab7ded5d060dd5e703430b90`。这只定位本轮输入，不是新状态表或后续必须保持不变的 state。product-projection 返回 `ready`、`feature:null`、`depends_on:[]`；`verify-acceptance --requirement-id REQ-t3-stage-dispatch --point spec_ready` 返回 `match`，exit 0。`start-feature --help` 和 `add-task --help` 已核对，Feature/Task 计划 ID 尚未使用。

#### 目标 / 非目标

- **目标**：实现上方 AC 映射中的最小合同修复，覆盖现有入口，留下范围准确的回归和一次当前候选真实阶段证据。
- **非目标**：修改宿主、认证、模型上报、Security 的产品/工程/状态、其他 Requirement、Goal 状态机制、live/strict 合同；新增调度/测试框架；跨项目根因归纳。

#### 技术栈

Markdown/YAML frontmatter、Bash、Python 标准库、本地 Git；无数据库、前端、常驻服务和新依赖。当前项目的版本/命令以实际文件为准，不沿用 `project.md` 的旧 2.0.0/三组测试描述。

#### 实施层决定

##### 决定 1：一个完整 Task，先修合同再取真实阶段证据

候选是“同一实现者完成所有耦合文档和必要测试”或“分文件/分测试派多个写者”；采用前者。协议、adapter、模板和检查共同定义一个可独立验收的结果，没有先拆基础设施的价值。实现者负责必要检查和普通修正；后续独立 Validate/Review 仍是既有生命周期职责，不为其再创建实施 Task。覆盖 REQ-001–REQ-007；不改变产品边界。

##### 决定 2：路由和资源前提按实际事实处理

- 通用实现首选仍为 `claudeAgent / glm-5.3-flash[1M] / {effort: xhigh}`。本 Task 的原 GLM 调用因 API 400 未实施，用户随后明确授权原实现者本 Task 使用 `codex / gpt-6.1-terra / {reasoningEffort: xhigh}`；本次恢复沿用这项授权，不把 API 400 解释成额度/限流，不扩大到其他 Task。主 Agent 复核原实现者绑定和单写者，保留其必要验证与修正职责，不创建替代实现者。
- 独立 Validate 的当前适用 Codex 映射为新上下文 `codex / gpt-6.1-terra / {reasoningEffort: xhigh}`；Review 为独立只读 `codex / gpt-6.1-sol / {reasoningEffort: xhigh}`。这不是用 Validate 角色代替未完成的实现，也不构成实现兜底已满足。
- 初次 Plan 时上游报告主会话为 Terra/max；不能把该历史配置当作恢复时的现状。计划及最终接受判断继续由符合项目职责的 Sol/xhigh 承担，唯一主 Agent 保持状态所有权。不能声称角色文件或本结果已切换任何运行会话；恢复时按实际 run 绑定复核，必需接受职责无法落实时只暂停依赖该判断的接受。
- 当前 Plan 执行上下文由宿主声明 Sol/xhigh；未读取与本 run 绑定的 backend 字段，实际后端及未被证明的内部 effort 未知。主 Agent 应用原生绑定核对上下文和生效配置；请求回显不作 backend 证明。
- 本 Plan 不发起额外模型任务、扫描、网络、安装、提交或生命周期 mutation。后续默认只使用本就必要的一个 Build、一个独立 Validate、一个 Review，串行并发 1；最早真实结果优先复用其中的独立 Validate，不为 18 个 AC 启动 18 次模型调用，也不新增取消/恢复/native 实验。纠正仍归原实现者，除非原路由/宿主合同要求合法交接。
- 真正启动前由主 Agent 在既有 brief 明确该批次数、provider/model、并发、有限时间/额度预算、write scope、原句柄、专属资源与收尾 owner，并核对既有授权是否已覆盖；本 Plan 不虚构已有的额度上限或额外实验许可。缺少的资源授权只阻止依赖它的真实运行，不能以静态走查冒充。跟随宿主 next；有限预算也不能被用作未知终止时重派同范围写者的理由。

##### 决定 3：修正版本说明，迁移同一开发期检查并实测覆盖率

独立 Validate 已定位 CHANGELOG 状态表达缺陷和 Bash 覆盖率缺证，恢复只改变下面的文案结构与检查实现/计量策略；产品、全部 AC、职责、阈值和 Security 义务不变。预计返修业务 diff 仅涉及 `CHANGELOG.md`、`scripts/validate-skills`、`scripts/test_scenarios.py`；两份插件元数据保持已准备的 7.0.1，其他已正确合同不重写。

| 路径 | 当前事实与适用性 | 决定 |
|---|---|---|
| 原 Bash 检查保留并计量 | PATH 无 kcov/bashcov；上游试装 bashcov 1.8.2 被 Ruby 2.6.10/json 依赖要求 >=2.7 拒绝。本轮未安装。coverage.py 不测 Bash；未验证的 shell xtrace/行工具不能提供可信分支分母。 | 当前不可执行。若保留新增 Bash 判断，需要已获授权且兼容的 Bash 覆盖工具/环境，并实际证明能给出本改动分支的静态分母、执行弧和遗漏弧；只有行报告的 kcov/bashcov 仍不足。不得手算或把 0 分支记成 100%。 |
| 复用现有 Python unittest/fixture | §10 已调用 `scripts/test_scenarios.py`；T3 检查本来就是仓库开发期的文档合同测试，不是交付给用户的调度/生产逻辑。该文件已有正反 oracle 和临时 fixture。离线 coverage.py 7.17.2 能测真正运行的 Python 判断。 | **采用。** 同一检查、同一标准入口、同一错误拒绝能力迁入该文件；不伪装生产逻辑、不加源文件/依赖/入口。只有候选实测达到 80% 行/70% 分支后才算补证。 |

CHANGELOG 的精确候选 diff 如下；两版本所有条目正文逐字保留，6.0.0 及以下历史不动。7.x 标题表达源码版本变更清单，不表达“未发布”或“已发布”，因此真实 Ship 前后均成立；实际发布及日期只留既有 lifecycle 与工程发布证据。保留双元数据 7.0.1，不能为文案降版本、抹去 Security 或添加伪造发布日期。

```diff
@@ -5 +5,2 @@
-## [Unreleased]
+以下 7.x 章节按源码版本汇总变更，不表示验证、评审或发布已经完成。
+实际发布状态以对应 Feature 的 lifecycle state 及发布证据为准。
@@ -7 +8 @@
-## [7.0.1] — 2026-11-15
+## [7.0.1] — 版本变更清单
@@ -18 +19 @@
-## [7.0.0] — 2026-11-15
+## [7.0.0] — 版本变更清单
```

检查迁移的精确边界以恢复基线的符号/块定位：删除 `scripts/validate-skills:271–287` 的 `check_t3_child_contract` 定义及 `:289–293` 的 if/else 调用，删除 `:426–462` 的 `t3_fixture` 创建、trap 和正反例块；保留 `:288` 的 §8 标题和 `:294` 起的其他既有检查、§1 的 T3 adapter 路径声明、§10 原有的 `test_scenarios.py` 调用。不新增 shell 分支、额外调用或覆盖率捷径；最后相对原规划基线的 Bash diff 应仅余一条 adapter 路径声明及必要注释，原有 trap 不变。实际行号由实现者读取现状复核。

在现有 `scripts/test_scenarios.py` 增加 `t3_child_contract_errors(adapter, protocol, template, readme)` 和 `T3ChildContractTest`，由同一个 helper 读取真实文件/临时副本并返回具体缺失项；不能只断言测试样本或检查文件存在。保持现有函数及 B03 两个新场景不变。helper 的完整判据沿用原 Bash：adapter 必须含 `delegate_task`、`task_cancel`、`terminal executor`、``host `next` ``、`stage-agent-protocol.md`；protocol 必须含 `runtime-adapters/t3-code.md`、``host `next` ``；template 必须含 `终端执行者`；README 必须含 `SCN-t3-stage-dispatch`、`runtime-adapters/t3-code.md`；adapter 拒绝原肯定式 ``Launch idle via `t3_thread_launch` ``，不误拒 native 映射或禁止示例。

测试至少包含：真实仓库四文件正例、真实副本正例、逐文件逐必要 token 移除全部出现的反例、追加旧肯定路径反例。每个反例从全新副本开始，断言具体错误及原文件未变，覆盖所有判据的成功/拒绝路径；保留原“缺终端执行者/旧路径/缺引用”三类反例。实现可使用标准库循环/if 和临时目录；不要引入自动调度器或以这些结果证明 live 行为。

#### 风险 / 取舍

实现前复核实际 root、branch、完整 HEAD、暂存/未暂存/未跟踪路径和相关 diff；有已接受依赖或无关变更时记录适用理由，不要求 HEAD 永远等于规划基线。相关契约、工具能力或验证策略变化时停止受影响工作，由主 Agent 更新当前有效方案并提供完整 `supersedes`。不只刷新 SHA，不以换名/新 brief 清零失败历史和唯一诊断使用情况。

非收敛规则唯一按协议 §5 和上层指令执行；本 Plan 未进行实现尝试或有界诊断，不能推断上游同段历史为零。主 Agent 派发前传递已知失败与诊断历史，未知即标未知。普通 timeout、测试失败、必要独立验证不是自动切模型或新增诊断的条件。

#### 实施阶段

1. **核心修复和必要回归**：执行下述完整 Task。先核对边界，再集中改协议/T3/native 引用、usage、文档检查和最小场景变体；最后同步 CHANGELOG 与两份插件元数据。没有额外初始化 Task。覆盖 REQ-001–REQ-007；设计为三个组件。
2. **最早可检验结果及正式验证**：Build 候选提交且必要前提满足后，由主 Agent 直接派发本就必要的独立 T3 Validate，明确加载该候选的 protocol/adapter/router/产品/工程文件，实际检查并产生 canonical result；主 Agent 核对其原生绑定、diff、命令和适用模型配置后接受。child 只报告候选和实际观察，不声称自己已被接受；主 Agent 核对这次真实阶段过程并作出 AC-001 的接受判断后，才处理其合法验证请求，不要求 child 预先证明尚未发生的主 Agent 接受。**这次当前候选加载后的真实 child 阶段及接受，才是计划中的最早可观察结果。**记录实际入口、候选 revision、工作区、原句柄/输出位置、接受结论及缺口；它不等于 Feature、Review 或发布完成。若该必要阶段未能合法运行，SC-001 仍缺证，不把本 Plan、旧 H1 或 F/D 当作替代。覆盖 AC-001、AC-003、AC-006、AC-009、AC-017；其他 live 分支只记录自然发生的覆盖。
3. **评审、集成与交付**：独立 Validate 通过并接受后才正式 Review；再按下方发布与观察安排集成和 Ship。主 Agent 现有授权覆盖的步骤连续推进，不因阶段完成新增逐阶段确认；路由/证据/用户停止限制继续有效。覆盖 REQ-006–REQ-007。

共享检查均为 **NOT_RUN（本 Plan 只读）**，命令来源已从当前脚本/指南核对：

| 计划检查 | 期望结果及范围 |
|---|---|
| `python3 -B scripts/test_scenarios.py` | exit 0；原有六场景和新增最小变体的正/反例通过，只证明本地文件/CLI 合同。开发中按变更定向运行，不机械地与完整入口重复。 |
| `bash scripts/validate-skills` | exit 0、`RESULT: PASS`；现有结构/引用和八组离线测试、新增有界合同检查通过。此脚本包含前一命令及严格 vibe 回归；不启动真实模型或扫描。 |
| 下方离线 coverage 命令及增量计量 | 候选上的实际执行仍 NOT_RUN。两次计量均要求行 >=80%、分支 >=70%，非零分母且报告遗漏项；不是 `coverage report` 的合并百分比，也不是 fixture 业务 `cli.py` 的旧覆盖率。 |
| `git diff --check` | exit 0；格式无 whitespace 错误；新文件另读取确认，不能把未跟踪文件未进入 diff 当作已检查。 |
| `python3 scripts/lifecycle_state.py --repo . verify-acceptance --feature-id FEAT-t3-stage-dispatch --point plan` | 主 Agent 接受并登记 Plan 后应 exit 0、`match`；此前不伪造 Feature 或快照。Validate/Review/Ship 引用其他接受点时同样核对，match 不代替语义覆盖。 |
| D 合同走查与 L 真实阶段 | 逐项记录上方 AC 表的对应结果/缺口；只有实际观察满足相应判据才报告该范围通过。不能命令化的路由/授权/独立工作判断由主 Agent 与独立阶段提供证据并核对。 |

覆盖率命令候选（**尚未运行候选测试**；仅工具 version/help 与 JSON 字段本轮已核对）：在仓库 root 执行，临时数据在 checkout 外，原始 JSON/数据保留到主 Agent 接受证据后再按归属清理。默认标准入口使用 Python 3.15.2；当前离线 uv 环境为 Python 3.12.16/coverage.py 7.17.2，两种环境分别记录，不冒称相同。以下覆盖率运行同时执行完整 scenario 单元套件，不为报告格式再重复该同环境套件；完整 `validate-skills` 仍独立必跑。

```bash
set -eu
T3_COVERAGE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/t3-stage-coverage.XXXXXX")
export T3_COVERAGE_DIR
PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-project --with coverage python -B -m coverage run --rcfile=/dev/null --branch --include='*/scripts/test_scenarios.py' --data-file="$T3_COVERAGE_DIR/.coverage" scripts/test_scenarios.py
PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-project --with coverage python -B -m coverage json --rcfile=/dev/null --data-file="$T3_COVERAGE_DIR/.coverage" -o "$T3_COVERAGE_DIR/coverage.json"
python3 -B - <<'PY'
import ast
import json
import os
from pathlib import Path
import re
import subprocess

path = Path("scripts/test_scenarios.py")
baseline = "0ccd06b1f08b7922882ab28c0ec9841ef5ad1154"
diff = subprocess.run(
    ["git", "diff", "--no-ext-diff", "--unified=0", baseline, "--", str(path)],
    check=True, capture_output=True, text=True,
).stdout
changed = set()
for start, count in re.findall(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.M):
    first = int(start)
    changed.update(range(first, first + max(int(count or "1"), 1)))
tree = ast.parse(path.read_text(encoding="utf-8"))
scope = set(changed)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        body = set(range(node.lineno, node.end_lineno + 1))
        if body & changed:
            scope.update(body)
report = json.loads((Path(os.environ["T3_COVERAGE_DIR"]) / "coverage.json").read_text())
assert report["meta"]["branch_coverage"], "branch measurement missing"
data = report["files"][str(path)]
assert not (set(data["excluded_lines"]) & scope), "changed code excluded"

def require_threshold(label, item, lines):
    hit = set(item["executed_lines"]) & lines
    missed = set(item["missing_lines"]) & lines
    arcs_hit = {tuple(arc) for arc in item["executed_branches"] if arc[0] in lines}
    arcs_missed = {tuple(arc) for arc in item["missing_branches"] if arc[0] in lines}
    line_total = len(hit | missed)
    branch_total = len(arcs_hit | arcs_missed)
    print(label, "lines", len(hit), "/", line_total,
          "branches", len(arcs_hit), "/", branch_total,
          "missing_lines", sorted(missed), "missing_branches", sorted(arcs_missed))
    assert line_total > 0 and branch_total > 0, "empty denominator is not 100%"
    assert len(hit) * 100 >= line_total * 80, "line coverage below 80%"
    assert len(arcs_hit) * 100 >= branch_total * 70, "branch coverage below 70%"

require_threshold("all changed Python functions and module lines", data, scope)
helper = data["functions"]["t3_child_contract_errors"]
require_threshold("T3 contract checker", helper, scope)
PY
```

上述增量范围包含相对原基线所有新增/修改函数的完整函数体、两个 B03 新方法、新 helper 与 fixture 方法及变动的模块行，不能只选最易覆盖的新增行。helper 再单独核对，避免大量测试行掩盖真正检查逻辑的遗漏分支。不加 `no cover`/`no branch` 或排除规则，不引用历史 CLI 14/14、3/4 代替本次报告。最终新增 Bash 只有路径声明时，按 correctness 的无逻辑配置分类说明行/分支数值**不适用（仅文件清单数据，无新增控制逻辑）**；应以 baseline→候选完整 diff 和标准入口实际经过该声明为证据，不记“0/0=100%”，也不声称原 Bash 覆盖率检查通过。这是删除原新增控制逻辑后对实际改动面的重新判定，不是豁免旧分支。若残留/新增 Bash 判断，则此 Python 报告不覆盖它，必须补可信 Bash 计量或返回未通过。

本改动无 Web/App 旅程、后端接口或持久化格式变化，不新增 E2E、数据库迁移和编码/路径 fuzz。安全视角核对不泄露信息、不执行被审计内容及现有权限边界；是否存在适用的必要扫描由后续阶段按现行风险合同判断，既不强制新扫描也不豁免 Security 本身的必要项。

#### 需求覆盖

实施顺序与验证引用唯一使用上方 AC 关联表；一个 Task 覆盖全部已确认规则，后续独立阶段补充正式证据，不重复建设映射或状态表。

### 工程任务

**输入**：本文架构设计、实施计划及关联产品正文。所有 Task 登记完成后才能 Build；本计划集合只有以下一项，状态不写在 Markdown 复选框中。

#### 用户故事 1–3：正确派发、准确证据、有限停止（P1）

**TASK-t3-stage-dispatch-core — 修复阶段调度合同并完成必要回归与使用说明**

- **目标与依据**：交付一份能一致指导 T3 child 与 native 的完整候选修复；覆盖 REQ-001–REQ-007/上方全部 AC 关联。实现阶段完成不代表已获得 L 或整个 Feature 验收。
- **范围与依赖**：无前置 Task，产品 `depends_on:[]`。允许修改且仅修改：`skills/sdlc/references/stage-agent-protocol.md`、`skills/sdlc/references/runtime-adapters/t3-code.md`、`skills/sdlc/references/runtime-adapters/codex.md`、`skills/sdlc/SKILL.md`、`skills/sdlc/references/templates/TASK.md`、`README.md`、`scripts/validate-skills`、`scripts/test_scenarios.py`、`docs/testing.md`、`CHANGELOG.md`、`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`。工程上下文仅由主 Agent 协调指定的唯一上下文写者更新，Build 返回必要候选，不自行与其并写。
- **禁止改动**：`scripts/lifecycle_state.py`、现有 strict/live 实现与测试合同、Security 产品/工程/状态、其他 context、认证与宿主、模型配置和发现链接；不在目标仓库新建文件、状态、依赖或服务。现有测试建立专属临时仓库/fixture 的行为按测试隔离范围执行，不反写目标 repo。若确需其他路径，停止相关工作并返回有证据的最小缺口，不自行扩大。
- **实施与检查**：
  1. 按共享规划/恢复基线复核 root/branch/HEAD、实际输入、路由和工具合同；沿用实施层决定 2 的本 Task Terra/xhigh 明确授权并确认写范围互斥。读取上述 file:line 的现状，不从旧摘要认定未漂移。
  2. 集中修正协议的 runtime selection、普通 timeout/host next、恢复和 continuation；检查 preparation batch、routine correction/review 等处的“native”专属措辞，只在确有同类误导时改为所选 adapter 的控制方式。子执行者限制明确，不借协议原先的可选层级说明允许本 T3 child 嵌套派工。
  3. T3 adapter 的阶段路径以 delegate_task/next/task_cancel 替换旧 launch/send/interrupt/settle 控制；只有当前工具实际支持且符合授权时才引用相关参数/读取能力，不编造幂等或自动唤醒。保留 top-level 的独立用户请求边界，保留 native 控件映射和项目路由限制。模板/router 只做必要补充与引用。
  4. README 原“可选的 Claude 执行者”入口调整为运行时路径说明，使用稳定场景 ID `SCN-t3-stage-dispatch`，链接本产品三个故事和共享协议/adapter。说明 actor、权限/能力/路由前提、参数来源、正常结果、失败/未知/停止后的恢复及支持范围；不复制 AC 或工具参数 schema。`docs/testing.md` 同步选择与证据边界，保留旧 Scratch 实测的历史身份。
  5. 按实施层决定 3，将新增 T3 helper/调用/fixture 从 Bash 迁入已运行的 Python unittest；现有 §8 其他检查和 §10 入口保留。对真实文件与临时副本运行同一 helper，保留并补全必要 token 的正反例，拒绝旧 top-level 肯定路径、漏终端限制或必要引用，保留 native/禁止示例。完成下方真实增量及 helper 覆盖率计量；只声称文档合同形状检查。
  6. 复用 `prepare`/`reference`/`assert_result`，保留原 B02/B03/B04A/B/B05 的边界。新增的 F 只覆盖已识别缺口：B03 fail 成功时旧批准失效；fail 因业务工作树不干净被拒时，实际 CLI 非零并保留原 state/业务内容；使用另一个独立临时 fixture 的已授权操作验证无跨仓污染。不要修改原 B03 的允许范围来偷偷增加工作，也不构造“自动调度器”来证明 Agent 会选择独立工作。其选择、用户停止、模型和等待/恢复分支按 D 走查，保留正反动作序列，不持久化第二结果格式。
  7. 保留当前 plugin、marketplace metadata/plugins 的 7.0.1 及两版本全部说明，按实施层决定 3 的精确候选 diff 改为无发布日期的 7.x 变更清单；不得写本修复或 Security 已发布，也不把永久“未发布”留到 Ship 后。Ship 只记录实际交付证据，不为改状态再动 CHANGELOG/元数据；若集成时内容/版本确有变化，主 Agent 先核对证据适用性，必要时补 Build/Validate/Review，不能在验证后静默修改。
- **完成条件**：允许范围内完整 diff 与设计一致；S/F 的正例和代表性错误反例实际执行；完整 `validate-skills` exit 0、`RESULT: PASS`，`git diff --check` exit 0；D 对全部 AC 留下范围准确的结论/缺口；README 导航、参数 owner、失败恢复和版本一致。返回实际命令、exit、完整 HEAD/未提交快照、工作区、路径与未决项，由主 Agent 检查后才请求 Task done。L 由后续必要独立阶段完成，是 Feature 验收义务，不要求 Build 为等 L 人为新增执行者或构造依赖环。
- **测试安排**：文档/配置先修再查适用；新增 CLI/合同变体先确认代表性错误结果会被断言拒绝，再与正例一起通过。范式引用 `validate-skills:145–215,348–400` 和 `test_scenarios.py:425–499`。完成条件同时包含实施层决定 3 的真实覆盖率阈值与遗漏项报告，及 CHANGELOG 两版本条目完整/无发布误报/7.0.1 三处版本一致的 diff 走查。完整入口包含既有 lifecycle、vibe host/core、Security 依赖探针回归；不重复实现这些严格判据。独立 Validate 在新候选干净业务树上重跑标准入口与覆盖率，不用本次 Plan 或 Build 结果代替；archive/内容检查绑定最终候选，不把 de2c 的报告当作新包通过。
- **停止条件**：本 Task 已明确授权的实现路由不可用且无进一步合法授权；相关现状推翻关键摘录/工具假设；需要修改禁止路径、产品或 Security 验收；必需上下文不可读/归属未知；要求新的模型/外部权限；旧写者终止或互斥不能证实；必要验证无合法可执行方式。按协议只停止依赖该事实的工作；fail 被拒时保留停止整个该 Feature 调度的既有特例，不能以本段继续实施。非收敛与唯一诊断沿用原历史。
- **维护注意**：不新增 stage schema 或测试框架，不用字串命中替代语义判断；所有未观察 live 分支留缺口。实现者承担本 Task 的必要测试与修正，主 Agent 不另派人补其漏测。相关产品/模型/验证契约实变时返回负责 owner，不自行重定义。

#### 依赖与执行顺序

顺序为主 Agent 接受 Plan → `start-feature` → 登记完整一项 `add-task` → 核对 Feature projection 的 ID/标题/空依赖 → 路由前提满足后 Build。即使 lifecycle `next` 提前指向 Build，也先完成集合核对。无候选并行任务；后续独立 Validate、Review、Ship 使用当前生命周期，不作为第二套 Task 进度。

本轮为已存在 Feature/Task 的恢复，不重走上述初次登记：主 Agent 接受修订后的有效方案 → 仅以本 brief 允许的 `start-feature ... --refresh-acceptance` 重记 plan → 复核 match 和原 Task `in_progress` → 给原实现者完整 `supersedes`。不请求 add-task、再次 reopen 或任何新状态。本工程文件的证据追加也会影响指纹，主 Agent 在依赖接受点前仍按现有 CLI 和语义适用性规则核对。

#### 执行策略

共享文件由一个实现者串行修改；其必要检查通过后，在既有授权允许时提交候选，并确保 state/context tracked、无冲突，state 未 staged、业务代码工作树干净，再进入独立 Validate。资源只在确需启动时按现有协议记录与收尾；普通静态工作不制造资源报告。

集成和发布安排属于主 Agent 的后续职责，不增加产品依赖或授予本 Plan 外部操作权限：

1. 本地 `main` 与 `origin/main` 均为 `3093e85725a30078f2666886766ef4175bfb1d20`，merge-base 同值；`main..0ccd06b` 有七个未合入提交，路径包括 Security 代码/上下文/状态和 7.0.0 元数据。直接合并 fix 会携带它们。本轮未 fetch，不宣称远端实时状态。
2. 默认由原主 Agent 在现有授权下分别完成 Security 的既有接受和本 Feature 的验证/评审，再串行集成 main；本 Task 不修改或代办 Security 的产品、工程和状态。不因 T3 通过替 Security 补“通过”；也不因其等待而暂停本 Feature 独立的 Plan/Build。若 Security 尚未具备合法交付证据，携带它的 main 发布暂停；独立发布 T3 所需的抽取/基线变更须由主 Agent先核对差异、影响和必要迁移，形成更新方案与完整 brief，不自动 cherry-pick、reset 或伪造依赖。
3. 集成前核对实际源/目标 refs、完整 diff、相关权限及当前文档/配置/要求；后续可联网步骤只在既有授权内由 owner 执行。合并冲突或相关代码/配置/usage/义务变化需在当前候选补相应 Build、独立 Validate 和 Review；不能只改 SHA。单纯 Git 身份变化而相关内容/环境/要求等价时，按协议记录适用理由并保留原证据，CLI 的 validation-commit/clean-tree 要求照常满足。
4. 在交付前分别核对两个目标现有证据及其接受指纹/语义适用性。T3 的 prompt 变更可能影响 Security 的执行或接受说明，是否需要补证由其原 owner 按现行合同判断；这里不改变其判据、不要求自动重扫、不把旧测试或 match 当作当前扫描通过。
5. 交付使用最终批准的实现版本；源码分发在新解包目录做内容核对和必要 smoke，确认实际加载的 adapter/router/模板/版本、必要引用及标准检查。发布/合并权限沿用既有明确授权，Ship 外部影响与 lifecycle release mutation 仍由主 Agent 控制；没有完成实际目标与所需 smoke/观察不记录 released。
6. 回滚优先恢复已知批准的整套技能/插件版本，或在原分支做有界修复并重验；不只回退一个 adapter 造成合同分裂，不清理 state/history、不自动撤销 Security 记录。外部回滚由原 owner 按授权处理。发布后观察引用产品“发布后观察计划”，不新增后台观察或额外模型实验。

## 实现记录（实际）

- **实现**：`TASK-t3-stage-dispatch-core` 的候选实现修改计划内的协议、两个 adapter、router、模板、README、测试及版本说明。执行者的结果与具体合同覆盖见[实施任务](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3A6854b167-7b46-48ec-b824-b1676240c5f4)。
- **模型与交接**：原 GLM 派工在执行前因后端模型不兼容返回 API 400，未写文件；用户随后明确授权本 Task 一次性使用 Codex Terra/xhigh。只读路由探针及实现任务的宿主配置为该路由，`executedModel` 为 null，实际 backend 未知；该错误不是额度或限流证据。
- **候选检查**：实现者在 `0ccd06b1f08b7922882ab28c0ec9841ef5ad1154` 加未提交业务 diff 上运行 `python3 -B scripts/test_scenarios.py` 和 `bash scripts/validate-skills`，均 exit 0。主 Agent 随后收紧 T3 Codex 主会话的 native 禁令、补充同一实现者返修路径并整理 7.0.1 版本说明；在该最终未提交业务 diff 上执行 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills`，exit 0，178 项测试和结构检查通过，`git diff --check` exit 0。完整检查有一条既有 HTTPError 清理 `ResourceWarning`。
- **快照与边界**：实现者交回时计划内业务 diff SHA-256 为 `503e0f23656f0a6587509561d0d07cec699d502296181c8129ca875beed398e9`；主 Agent 的上述补充后为 `4afa96a3109f74d4fa63eb1b7410e2a1bdce200f2f51302f5b9200d84ebce615`，按计划内 12 个业务路径的 `git diff` 计算。Build 检查不代替当前候选的独立 Validate；真实取消、恢复、native 兼容和资源释放未观察。

### 2026-11-15 同一 Task 返修

- 原实现者依已接受的恢复方案修改 `CHANGELOG.md`、`scripts/validate-skills` 和 `scripts/test_scenarios.py`；完整结果见[返修线程](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3A6854b167-7b46-48ec-b824-b1676240c5f4)。返修相对 `de2c5ff5014221a92b04e60a952028361e34dc5d` 的三个业务路径 diff SHA-256 为 `cd32f1c286c46dd5e4c20a7bef89d99eb560a4ab5d7a42bda07e261ea3999afd`。
- 版本说明保留两个 7.x 版本的全部条目，标题不再以日期暗示发布状态；发布情况以实际状态和证据为准。合同检查迁入既有 Python 测试入口，保留真实文件正例和逐项错误反例；相对原基线 `0ccd06b1f08b7922882ab28c0ec9841ef5ad1154`，Bash 只增加一个文件清单项，没有新增控制分支。
- `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills` 在 Python 3.15.2 下 exit 0、181 项测试通过；`git diff --check` exit 0。按恢复方案使用离线 `coverage.py 7.17.2` 与 Python 3.12.16 运行场景套件并计量真实增量：全部变动 Python 范围 82/82 行、16/16 分支，合同检查 helper 10/10 行、8/8 分支，遗漏均为空；该 Python 结果不表示 Bash 覆盖率。原始数据与 JSON 当时保存在任务专属临时目录，供主 Agent 核对。
- 以上是 Build 证据，不代替新 commit 的独立 Validate 或正式 Review；原 `de2c5ff` 未通过的记录继续保留。真实取消、恢复、native 兼容和资源释放仍未观察。

## 验证记录（实际）

- **初次规划状态（历史）**：规划输入核对已执行；当时实现和独立 Validate 均 NOT_RUN；后续实际结果见本节及实现记录。
- **被核对版本/工作区**：完整 HEAD 和入口状态见规划基线；root、branch、HEAD、status、product-projection、spec_ready 核对命令均 exit 0；结果分别为预期身份、仅已知两项输入、ready/feature null/无依赖、指纹 match。`start-feature --help`、`add-task --help` exit 0；未执行 mutation。
- **覆盖与缺口**：本轮只读核对了实际协议、adapter、README、检查实现及严格边界；未跑完整测试、F/D 验收、候选 live 实验、扫描、取消/恢复/native 实验或发布。本 Plan 不能充当 SC-001 的候选 live 证据。GLM 目录缺口和主会话 Terra/max 的职责限制待主 Agent 在依赖执行前处理；没有未决产品选择要求本 Plan 修改规格。

### 2026-11-15 独立验证 — de2c5ff5014221a92b04e60a952028361e34dc5d

- [独立验证](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Ab2f8f948-ab3d-4f28-bee6-32497538071b)在干净工作树执行 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills`，exit 0，178 项测试和结构检查通过；archive 解包、文件摘要、CLI help、README 锚点及版本一致性检查通过。Hallmark 测试有一条既有 HTTPError 清理 `ResourceWarning`。
- **IMPLEMENTATION_FAILED**：CHANGELOG 将尚未发布的 Security 与本修复置于带日期的版本标题下且 `Unreleased` 为空，容易误示已经发布，违反当前候选的状态表达要求；需要修正文案并重验。
- **INCONCLUSIVE**：本机未发现 Bash 覆盖率工具，新增脚本分支的行/分支覆盖率未计量；不能把合同反例通过当作达到默认阈值。真实取消、恢复、native 兼容及资源释放未观察；真实安全扫描 `NOT_RUN`。
- 此次 `record-validation --result fail` 已由主 Agent 按请求记录，绑定上述 commit；如因确认的实现缺陷重开 Task，现有 CLI 会清除机器状态中的验证记录，本节与原线程保留失败历史，不得以此当成通过。

### 2026-11-15 Plan recovery — 同一 Task 的方案候选

- **输入/归属**：root `/Users/mac/hansen_agent_team/external/sdlc-pilot`，branch `fix/t3-stage-dispatch`，HEAD `de2c5ff5014221a92b04e60a952028361e34dc5d`。入口只有工程文件既有 7 行失败事实和主 Agent 的 state reopen diff；state SHA-256 `e5d35e491c7ee72528924c36328ae5afbaa59f612180f7d569985cd190cad232`，工程入口 SHA-256 `1f4d86262eddd11ef29e5e9d31650c025168144d8627dc5cad76107bce26ea3b`。主 Agent 已核对原实现者的终态；本轮未见额外路径/输入变化，未用 Git 状态推断其他进程已终止。仅本工程文件是本轮写入。
- **实际命令/结果**：`pwd -P`、`git rev-parse --show-toplevel`、`git branch --show-current`、`git rev-parse HEAD`、`git status --porcelain=v1`、`git ls-files -u`、`git diff --cached --name-only` 均 exit 0，身份匹配、无暂存或冲突；`python3 -B scripts/lifecycle_state.py feature-projection --feature-id FEAT-t3-stage-dispatch` exit 0，原 Task `in_progress`、validation pending、review/release pending、无依赖；对应 `verify-acceptance ... --point spec_ready` exit 0/match，`--point plan` exit 1/stale（原工程 expected `c853cfbe592bdb061747811da0f4b88d7df6cdd5e473a26509393b1315b3dfa1`，入口 current 为上述工程摘要，产品 match）。`start-feature --help` exit 0，确认只使用本 brief 允许的 refresh 参数；未执行 mutation。
- **工具事实**：`command -v kcov`、`command -v bashcov` 分别 exit 1；默认 Python 3.15.2 的 `find_spec("coverage")` 为 False。`PYTHONDONTWRITEBYTECODE=1 uv run --offline --no-project --with coverage python -B -m coverage --version`、`run --help`、`json --help` 均 exit 0，版本 7.17.2；同一离线环境打印 Python 3.12.16。只读核对 JsonReporter 的 `executed_lines`、`missing_lines`、`executed_branches`、`missing_branches`、`functions` 输出实现成功。不安装/联网，不运行候选业务测试，不能报告已达到覆盖率。
- **候选检查**：从本文提取 CHANGELOG patch，经 `git apply --check --unidiff-zero -` 实际检查 exit 0，未应用 patch；覆盖率命令块经 `bash -n` exit 0，内嵌 Python 经 `ast.parse` 成功，均未执行候选命令。文档编辑中的一次格式检查发现 diff 示例空白行含尾空格，修正后独立 `git diff --check` exit 0；这不是实现尝试或覆盖率结果。
- **独立证据可读性**：尝试读取上述已给定独立验证线程，宿主返回 `thread_not_found`；本轮仅以仓内保存的失败事实和当前 diff 核验，不宣称重新读到原始运行。178 项通过及解包检查均仍是 de2c 的历史证据，新候选标准检查、覆盖率及正式独立 Validate/Review/Ship 均待执行；真实取消/恢复/native/资源释放仍未观察。
- **进展及历史**：恢复候选明确修正 CHANGELOG 结构和真实计量策略，尚未修复实现或消除验证失败。保留已知原实现、主 Agent 收尾改动及一次独立失败记录；本轮无实现尝试、无有界诊断，不把 Plan 更新、工具探针或失败记录清空视作新段。连续不收敛计数及唯一诊断是否已用在现有输入中未知，主 Agent 返交原实现者时须带入原记录，未知不能写 0；命中 §5 时仍停止，不新增诊断机会。
- **模型披露**：本阶段职责要求为 `codex / gpt-6.1-sol / {reasoningEffort: xhigh}`；调用方实际 target 回包未提供，不能声称已核对其请求字段。当前宿主明确声明 Codex harness、gpt-6.1-sol/xhigh；没有本 run 的可信实际后端/内部 effort 字段，backend 未知。原实现者本 Task 的 Terra/xhigh 明确授权不变；历史配置/null 不是本轮新运行证据。
- **交接约束**：主 Agent 先语义接受本候选，再执行唯一允许的 plan refresh 并复核 match，给**原实现者/原 Task**完整 `supersedes`；带入 root/branch/完整 HEAD、两项既有输入归属、原失败/诊断历史、本节和决定 3 引用。目标为三文件返修；不动产品/state/Security/其他业务路径、不提交推送安装联网或启动额外实验，受托者为 T3 终端执行者、禁止任何嵌套执行者。沿用明确 Terra/xhigh 请求并分别报告请求/宿主/backend；无新产品决定或验收例外。必要检查为决定 3 的 helper 全正反例、增量及 helper 两组真实 80%/70% 计量、标准入口、diff/版本/CHANGELOG 完整性走查；命令失败或 Bash 残留分支未计量不得交回通过。返回 canonical 候选、实际命令/exit、完整 revision/业务 diff/状态、JSON 数据位置及未覆盖项；state 操作及后续正式独立 Validate/Review/Ship 仍由主 Agent 按各自实际 allow-list 和既有授权处理。

## 评审记录（实际）

- **历史状态**：初次独立规划评审建议接受；恢复方案的接受情况以 state 中的 plan 指纹为准，不能把旧评审当作已覆盖本轮策略变化。正式 Feature Review 尚未进行。
- **范围、发现与处理**：[独立方案评审](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Af57742ad-310a-4eff-8ea4-856c0f91998c)核对候选 SHA-256 `8e5b05a47f60988caa44643fa0286a1212a1ca9f25475b5564ba0badbe9b89ce`，未发现阻止登记的方案缺陷；后续只调整状态措辞并追加本条记录，未改变有效方案。评审请求和宿主配置为 Codex Sol/xhigh，`executedModel` 为 null，实际 backend 未知。必要正式 Review 仍须在适用独立 Validate 接受后执行。

## 发布与观察记录（实际）

- **产品观察计划引用**：`.sdlc-v1/context/REQ-t3-stage-dispatch.product.md` 的“发布后观察计划（SDLC 补充）”。
- **技术发布准备、实际结果、反馈证据与缺口**：发布/集成/远端状态刷新/解包 smoke 均 NOT_RUN；仅核对本地 refs 与元数据。后续按实施计划的集成与发布安排记录最终版本、内容核对、smoke、接受来源和真实观察范围；取消、恢复、native 与资源释放没有观察时保持未观察，不能由 child 完成推断。
