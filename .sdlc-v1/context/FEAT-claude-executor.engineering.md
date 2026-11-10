# 工程上下文：FEAT-claude-executor 可选 Claude 执行适配与入口收敛

## 当前有效方案

### 架构设计

**关联产品上下文**：`.sdlc-v1/context/REQ-claude-executor.product.md`

**工程上下文**：`.sdlc-v1/context/FEAT-claude-executor.engineering.md`

**已确认需求**：产品正文的 confirmed 条目、RULE-1～RULE-6、SCN-1～SCN-10、AC-1～AC-10。主 Agent 已接受 Spec 并将 Requirement 实际标为 ready；产品正文仍有“Spec 候选”措辞时，以本阶段 brief 与当前 projection 的接受事实为准，不修改产品文件。

**创建日期**：2026-11-10。

**状态**：Plan 已由主 Agent 接受；Feature/Task 进度以 state 为准，实际检查见后文证据。

#### 背景

沿用产品 NEED-001、DEC-001～DEC-002 的方向，执行包内适配及配套入口收敛。只在主源码仓库管理生命周期，配套仓库既有 Dreaming 与无关改动保持原样。本文明确双仓版本绑定和 csd 等待/销毁边界，因此比单仓纯文案计划稍详细；产品规则、canonical schema 与停止协议仍只引用原定义。

| 仓库简称 | 实际 worktree / 分支 | 起始业务基线 |
|---|---|---|
| 主仓 | `/Users/mac/hansen_agent_team/workspace/20261110-claude-execution-consolidation/sdlc-pilot`；`codex/claude-execution-adapter` | `5480d8d3f17d74e2579121dda8fa8053e3b137f1` |
| 配套仓 | `/Users/mac/hansen_agent_team/workspace/20261110-claude-execution-consolidation/agent-team`；`codex/consolidate-claude-delegation` | `5124fe112500a78d8a6fc44d661921657ed97f6b` |

以上绝对路径仅是本次执行绑定，不进入可分发的适配参考。主仓实际插件元数据为 `4.3.3`；project.md 中 `2.0.0` 等版本/测试数字是历史事实，不能作为当前工具版本。配套驱动固定上游为 `obra/claude-session-driver@d97d1eb0a904546ed059b0a33dd5d4aa3e199c9a`，bundle、hooks 和 LICENSE 的归属/hash 见其 `UPSTREAM.md`。

#### 架构与组件

##### 包内可选执行参考与既有路由

- **职责**：新增 `skills/sdlc/references/runtime-adapters/claude-cli.md`；只把现有阶段合同映射到真实 csd 命令与观察能力，不实现新的执行控制器。
- **接入**：`skills/sdlc/SKILL.md` 在编排入口提供明确 opt-in 引用；`runtime-adapters/codex.md` 说明当前任务明确选择并授权外部 Claude 时，由主 Agent 直接使用该参考替代该次原生 child 派发。原有默认模型/职责表与原生路径不改；不能先派一个 native stage child 再让它启动 CLI worker。
- **接口**：输入是现有 stage brief 和主 Agent 已决定的执行绑定；输出是现有 canonical result 与可核对文件证据。引用 `stage-agent-protocol.md` 与 `templates/TASK.md`，不另存合同模板或结果格式。
- **覆盖**：RULE-1、RULE-3～RULE-5；AC-2～AC-6。

##### 公共会话驱动与旧入口清理

- **职责**：配套 `.agents/skills/driving-claude-code-sessions/SKILL.md` 的 trigger/开头说明区分普通独立委托与已有 SDLC；保留现有 Claude/Codex/Pi 驱动能力及命令说明。对 tracked 工作只导航到当前 SDLC/包内适配，不复制阶段流程。
- **接口**：通过实际 skill discovery 或主 Agent 显式提供并核对的安装路径查找 `scripts/csd`；从实际安装的 sdlc 包查找协议/阶段/lifecycle CLI。不得推导个人 hansen 路径、历史 workspace 或要求用户全局同名目录。
- **归属**：`UPSTREAM.md` 将 SKILL 从“unmodified”改为明确本地路由/授权说明修改；保留上游 revision、bundle/hooks/LICENSE 及现有 wrapper。删除旧技能三个文件和审计文档活动链接；不搬运旧 collector 的个人路径 fallback。
- **覆盖**：RULE-1～RULE-2；AC-1、AC-3～AC-4、AC-7、AC-10。

##### Usage 与验证入口

- **职责**：主仓 `README.md` 是全局 usage 入口，以自然语言示例导航到包内详细参考。说明 actor、显式选择/授权、依赖/参数来源、支持范围、正常结果与缺口/超时/取消恢复；产品 SCN 与验收映射只留在本工程上下文和验证证据中，不把内部需求编号引入用户操作流程，不复制规格或记录 secret。
- **验证资产**：`docs/testing.md` 增补本次无 provider fixture 的一次性定义与适用范围；复用现有 `scripts/validate-skills`、`scripts/test_scenarios.py` 及驱动 `scripts/verify-plugin-layout`，不新增 runner、自动结果接受器或仅匹配文案的行为测试。
- **覆盖**：SCN-1～SCN-10；AC-1～AC-10 的实际检查导航。

#### 关键设计决定

##### 决定 1：复用 csd 与 canonical 协议，仅增加按需参考

| 评估项 | 当前证据与选择 |
|---|---|
| 相近实现 | 主仓已有 Codex runtime adapter、TASK 模板与唯一阶段协议；配套旧适配有绑定/证据职责，但三份文件重复解释阶段流程，collector 含历史个人路径 fallback。 |
| 现有依赖 | 当前 csd help 和 bundle 支持所需 launch、send/converse、wait、读取、status、stop；现有 wrapper、hook/layout fixture 足以复用。无能力缺口要求新增代码。 |
| 选择 | **复用现有实现**：写一个包内 reference，引用原模板；证据采集由既有 Git/CLI/日志命令完成，主 Agent 核实，不移植 collector。 |
| 未采用 | 整体复制旧技能会重复协议并保留错误路径；另建 runner/包装 CLI/结果解析器会增加当前产品不需要的接口和状态。未引入外部依赖，无需扩大上游调研。 |
| 条件 | 若实施发现真实能力缺口，原实现者返回可复现缺口与既有方案不足，交主 Agent 更新方案；不能为了让文案测试通过临时增加生产代码。 |

只读 decision-context 查询仅复核“外部运行成功不等于 SDLC 验收”的既有边界；命中的后台平台资料没有本地接入验证，未采用任何平台候选或新增产品要求。原型不适用，复用结论为无需原型资产。

##### 决定 2：源码保持一项完整交付，验证固定双仓版本

两仓入口与适配是同一产品结果，使用一个 Task、同一 Terra implementer 串行实施及修正；不按仓库或单次检查拆派工。现行 lifecycle 只记录主仓 validation commit；配套仓的**实际业务 commit** 在既有验证记录中一并绑定，主 Agent 在 Validate/Review/Ship 前核对这一对提交。任一仓相关源码、测试、配置或语义义务变化，都必须判断并补足受影响独立验证，不能只凭主仓 hash 未变复用结论。没有跨仓事务或第二状态源。

#### API / 接口契约 *(Feature 暴露 API 或 CLI 表面时包含)*

公共 lifecycle CLI、state schema、stage-result schema 均不变；csd 参数以当前安装的 `help` 和固定上游源为准。新参考只提供以下映射及差异，不另定义工具 API：

| 阶段需要 | csd 映射与边界 |
|---|---|
| 启动当前有界执行 | 主 Agent 在完整 brief、worktree/branch/HEAD/任务绑定和适用授权均明确后，使用 `launch --harness claude`；保存实际返回 shim。本次实现/验证不执行该命令。 |
| 首次派工及同合同修正 | 沿用该 shim 的 `converse --with-turn` 或 `send`；同一实现者负责修正。合同实质变化仍用现行完整 `supersedes` 规则；不能把 csd 当作原生 `send_message` 或额外代理层。 |
| 等待与结果读取 | `converse` 超时 exit 1 不停止 worker。保留原 turn 的事件基线；`wait-for-turn` 默认只等待调用后的新 turn-end，已有 turn 已结束时读取原结果，仍运行时等待同一 turn（可用现有 `--after-line`），不重发任务。按现有 csd 可核对状态处理 CLI 超时，不把它扩展成 native Agent 树轮询。 |
| 观察 | 使用绑定 shim 的 `status`、`read-events`、`read-turn`；unknown/gone 等观察值不等于已验收/已安全释放。CLI exit 0 与转发文本均不验证 canonical 语义或 artifact。 |
| 停止/取消 | `stop` 会清理 meta/events/shim，必须先保留必要证据；核对任务归属后才操作该会话，并按现行资源规则核实收尾。禁止全局 prune/pkill、无关停止及超时后 stop/relaunch。 |

一次性 csd consent 与当前任务/provider/绕过权限提示授权是不同事实；只在已获适用授权时才允许建立 consent。上游支持 adopt 不代表该阶段允许采用未知旧会话；缺少可核实任务绑定时交主 Agent 决策，不用它绕过停止/恢复限制。上述现象的 provider-free 验证与 live 未测边界见实施计划，不承诺本轮验证真实 Claude 进程控制。

#### 时序与数据流 *(跨组件的控制/数据流不直观时包含)*

1. 主 Agent 按现有路由确定阶段和执行者；只有当前明确选择且授权 Claude 时按需读取新参考，否则沿用原生路径。普通独立委托直接使用公共驱动，不初始化 SDLC。
2. 依现有协议形成完整 brief，核对绑定后直接控制一个 CLI worker；同一原生阶段 child 不再开 CLI worker。
3. 读取结果与实际文件/检查证据，按产品 SCN-4～SCN-5 接受或交原实现者修正。原主 Agent 单独处理允许的状态请求与后续独立阶段。
4. 超时、未知状态、纠偏、取消与恢复按 SCN-6～SCN-8 和现行协议分支处理；先保留证据，再作允许且核实归属的销毁操作。

有序说明足以表达本次单控制者映射，不引入新时序协议或强制图示。

#### 横切质量设计 *(性能 / 安全 / 可用性影响设计时包含)*

能力与授权检查仅位于 opt-in 分支；包内 reference 不在原生加载路径执行外部工具。安装路径及参数由使用者当前解析来源提供，不含凭证或个人路径。新 Markdown 交叉链接由现有检查覆盖；驱动上游文件以固定基线 diff/hash 核对。临时 fixture 只操作其专属目录，不启动 Claude/tmux/provider，不修改 HOME/全局配置；既有标准测试启动的 loopback 资源按原测试清理约定核对，不停止共享资源。

#### 风险与取舍 *(设计存在实质风险时包含)*

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 说明被当作模型/权限切换授权 | 意外消耗或绕过路由 | opt-in 入口与 SCN-1～SCN-3 的独立语义核对；无 provider 任务运行。 |
| csd 超时或 stop 被误解 | 重复派工、结果丢失 | 当前源行为映射；专属事件 fixture 验证 wait 基线，证据先于销毁，取消仅作合成场景评审。 |
| 两仓证据混版 | 仅主仓 pass 掩盖配套变化 | 固定实际 commit 对；主 Agent 分阶段核对两仓业务差异，按变化重验。 |
| 删除旧入口影响当前链接或历史 | 悬空发现、误删日志 | 精确目标扫描，先交付新入口后删活动文件；保留历史快照/其他 worktree。 |

#### 需求覆盖

唯一完整 AC → 设计 → Task → 检查关联见下方“实施计划 / 需求覆盖”；以上组件的覆盖引用只用于定位。

### 实施计划

**关联产品上下文**：`.sdlc-v1/context/REQ-claude-executor.product.md`

**关联设计**：本文“架构设计”。

**已确认需求**：同上；**创建日期**：2026-11-10；**状态**：Plan 已接受。

#### 背景

两仓边界已明确，计划只修改 Markdown/发现入口并删除旧适配代码，不新增生产代码。所有以下检查和交付动作均为 planned/NOT_RUN，除“实际记录”明确注明的 Plan 只读查询外，不作为 Build/Validate 通过证据。

#### 目标 / 非目标

目标是完成产品 AC-1～AC-10；非目标唯一见产品 OUT-001。当前 Task 不运行真实外部执行者，不改发布版本元数据，不升级上游，不触碰配套 Dreaming 或其他技能。

#### 技术栈

Markdown/YAML、现有 Python 标准库检查、Git；配套现有 Bash wrapper 与 Node CJS bundle 只复用、不改写。没有新增依赖、数据库或前端。无新增生产代码时，文档使用静态/fixture/独立语义核对；不为 Markdown 或未改的 vendor 代码虚构新增覆盖率。

#### 实施层决定

选择一项纵向 Task `TASK-claude-execution-consolidation`；同一 Terra 负责两仓实现、必要检查与修正。先接通可查看的参考/入口，再清理与完整验证。Build 完成与独立 Validate/Review、主 Agent 最终验收、Ship 是不同完成条件，不能用里程碑提前标记 Task done。

#### 风险 / 取舍

| 风险 | 可能性 / 影响 | 计划处理 |
|---|---|---|
| 文案断言冒充控制行为测试 | 中 / 高 | 不新增匹配措辞的伪行为测试；区分实际 csd 文件/事件操作、合成输入的独立决策评审和 live NOT_RUN。 |
| 验证时业务树脏或输入变化 | 中 / 高 | 主 Agent 先准备 tracked context/state 与两仓实际业务 commit，业务树干净；独立 Validate 在固定 pair 上实跑，变化后按适用性重验。 |
| 双仓 main 推送部分成功 | 低 / 中 | 不宣称原子交付、不 force/reset；保留已成功远端事实，在原授权内核对并完成另一仓，真正冲突/授权缺口如实报告。 |

#### 实施阶段

1. **当前 Task 的最早可检查增量**：完成主仓 `claude-cli.md`、router/Codex 映射、README usage 及配套驱动开头路由/UPSTREAM；使用两仓文件入口、`csd help` 和本地引用检查展示“原生默认保留、显式外部执行可找到正确合同”。这是文档/CLI 契约增量，无 provider 实跑；原 Terra 随即继续清理与全部检查，不请求 done。覆盖 AC-2～AC-4、AC-7；设计：三个组件。
2. **同一 Task 的完整实现**：清理下节确切旧文件及审计活动链接，按 `docs/testing.md` 补齐一次性 fixture 定义；CHANGELOG Unreleased 记录可选能力、兼容性和真实链路未测边界。完成 Build 必要检查，保留源文件可读性与 diff 范围证据。覆盖 AC-1～AC-8、AC-10。
3. **固定候选后独立验证/评审**：主 Agent 使用现有授权准备两仓业务提交；在工程验证记录写入两个实际 SHA，业务 worktree 干净，主仓 state/context tracked、state 未 staged 且无冲突。新的独立 Terra Validate 实际运行下列检查与代表性场景；独立 Sol Review 只读核对两仓完整 diff、usage/参数来源与证据。Build 检查不能替代它们。发现实现问题交原 Terra 修正，相关候选变化后重验。
4. **已评审源码交付**：主 Agent 依当前 Ship 协议将被接受内容集成至两个 main，复核实际远端、并发变化与无关脏改；主仓 origin 为 GitHub `arnow117/sdlc-pilot`，配套 origin 为 Gitee `arnow117/hansen_agent_team`。先推主仓使新包内参考存在，再推配套清理；以两次实际 main SHA/远端核对完成 AC-9，不创建 tag/Release/marketplace 发布。仅 `.sdlc-v1/**` 证据提交可按现行规则续接；业务差异或新验证义务必须补足验证。

**检查与 fixture 定义**：Build implementer 在本上下文完成相称自检，不启动子 Agent 或 CLI worker；固定候选后的独立 Validate 在自己的上下文实跑适用检查并核对场景，不能把 Build 自检标成独立结果。

- 主仓：`bash scripts/validate-skills`、`git diff --check`；该既有脚本覆盖技能/frontmatter、本地引用及现有确定性测试。无需修改该脚本来断言新参考某一句措辞；新参考通过路由链接进入其现有引用检查范围。
- 配套仓：`bash .agents/skills/driving-claude-code-sessions/scripts/verify-plugin-layout`、`.agents/skills/driving-claude-code-sessions/scripts/csd help`、`git diff --check`；对修改的 SKILL frontmatter/name/description、相对本地引用及当前入口做结构核对，并与基线比较保护的 vendor 文件/归属。核对引用不能代替语义场景。
- **实际无 provider 事件 fixture**：复用现有 verify-plugin-layout 的专属临时目录、meta 与 emit-event 配方；生成本地 Stop 事件，使用真实 `csd --worker <fixture> read-events` 读取。对已有 turn-end，`wait-for-turn 1` 应因默认基线在末尾而超时 exit 1；同一输入加 `--after-line 0` 应取得已有事件 exit 0。对比 fixture meta/events 内容，确认读取/等待没有销毁或重发任何会话。本 fixture 不 launch、不发送模型 prompt、不执行 stop，不声称测得真实 converse 超时/取消；后两者用固定 bundle 源检查和合成场景核对。
- **实际文件/结果 fixture 与独立场景核对**：复用 `templates/TASK.md` 的现有格式以及 `test_scenarios.py` 的隔离 Git/证据适用性准备方法；保持实际 repo HEAD、artifact 与检查 log 可核对，形成有效、删去必要检查证据、换成不适用业务 revision 三个输入，交独立验证者按 SCN-4～SCN-5 区分接受/拒收，核对 fixture state 前后不变。不要写一个总返回预设答案的“验收器”；等价输入证据复用仍按 RULE-4，不能用任意 hash 不同制造反例。
- **独立决策场景**：按产品 SCN-1～SCN-3、SCN-6～SCN-8 给定受控输入（无外部工具、缺授权/能力、仍运行/已结束/未知、同实现者修正、已取消与共享资源），验证者基于当前 usage/reference 记录应采取动作、不得采取动作和保护对象。状态/过程为 synthetic，不接触真实 session；核对无 nested CLI worker、重复派工、隐式 consent、越权停止和限制重置。SCN-9/SCN-10 另以实际文件/远端事实检查，不用这些合成决策替代。
- 单次 fixture 定义维护在 `docs/testing.md`，运行记录仅写既有工程验证章节或引用；每次使用新的专属可丢弃输入，保留必要失败证据后清理。既有 `test_scenarios` reference/oracle 只是 fixture 方法，不等于真实 Agent/独立阶段通过；本轮真实 Claude/provider 链路始终 `NOT_RUN`。

#### 需求覆盖

所有行的实施 Task 均为 `TASK-claude-execution-consolidation`；后续 Validate/Review/Ship 由现有阶段承担，不另建实施 Task。

| 当前 AC | 设计/契约 | Task 范围与计划检查 |
|---|---|---|
| AC-1 | 公共驱动与清理、SCN-9 | 删除三文件和审计活动链接；当前引用及精确发现目标检查。 |
| AC-2 | 包内可选参考、决定 1 | router → reference/TASK 链接、无新增系统 diff 核对、标准检查。 |
| AC-3～AC-4 | RULE-1 映射、SCN-1～SCN-3 | 独立路由/授权场景；驱动普通委托与原生默认兼容检查。 |
| AC-5 | 现有 canonical/证据接口 | 三个实际文件输入、等价输入边界及独立阶段义务核对。 |
| AC-6 | csd 差异与 RULE-5 | 实际事件/wait fixture、源行为核对及 SCN-6～SCN-8 独立合成场景。 |
| AC-7 | 维护组件/上游归属 | 两仓标准/格式/引用检查；UPSTREAM 与受保护 bundle/hooks/LICENSE 基线比较。 |
| AC-8 | 版本 pair 与验证边界 | 独立 Validate/Review 记录实际命令/exit/范围，真实模型 NOT_RUN 明示。 |
| AC-9 | 决定 2、RULE-6 | Task 准备两仓可提交内容与 Unreleased；评审后 Ship 核对双 main 内容、实际远端 SHA 和未额外发布。 |
| AC-10 | 双仓绑定、OUT-001 | 仅主仓生命周期；最终两仓 diff、Dreaming/其他技能/元数据/历史保护核对。 |

### 工程任务

**输入**：本文设计与实施计划、已接受产品规则；**测试**：文档改动可先实施后做上述相称检查，不添加措辞镜像测试；**组织方式**：一个完整 Task，单写者、两仓串行。

#### 格式：`[ID] [Story] 描述`

`TASK-claude-execution-consolidation` [US1、US2、US3]：接入可选 Claude 包内执行参考，收敛配套公共委托入口并完成必要检查。标题用于 add-task：`收敛 Claude 委托入口并接入可选执行适配`。无 Task 依赖、无并行 Task。

#### 路径约定

- **主仓可写**：新增 `skills/sdlc/references/runtime-adapters/claude-cli.md`；修改 `skills/sdlc/SKILL.md`、`skills/sdlc/references/runtime-adapters/codex.md`、`README.md`、`docs/testing.md`、`CHANGELOG.md`。后续阶段 brief 可授权更新本文实际记录；产品与 state 不属 implementer 写入范围。
- **配套可写**：修改 `.agents/skills/driving-claude-code-sessions/SKILL.md`、同目录 `UPSTREAM.md`、`planner/20261105-skills-audit.md`；删除 `.agents/skills/claude-rnd-orchestrator/SKILL.md`、`references/worker-contract.md`、`scripts/collect-evidence`（后两项在该旧技能目录下）。审计只更新被本次决定取代的当前建议/活动链接，历史统计明确保留历史口径，不改其他技能行。
- **发现检查**：重新以 lstat/readlink 检查两仓/当前项目的 `.claude/skills`、`.agents/skills`、`.codex/skills` 及用户三个同类 root；精确匹配旧技能目标而非全局清理悬空链接。Plan 未发现目标别名，旧技能实体仍位于配套源码的 `.agents`；不搬迁公共技能或补造全局链接。若出现经过核实属于本次旧入口的别名，由主 Agent 在授权清理范围内处理；意外文件/目标冲突先报告，不覆盖。独立 worktree 的旧版本不清理。
- **禁止改动**：主仓生命周期实现/模板/阶段协议、版本元数据；配套 bundle、hooks、LICENSE、wrapper/verify 脚本、Dreaming state、其他技能、用户偏好及无关脏改。若实际缺口要求突破此范围，先交主 Agent 收敛，不自行扩写。

#### 阶段 1：准备（共享基础设施）

核对给定两仓绑定、当前工作树与 accepted 上下文；确认完整 Task 已登记。无需新 worktree/分支/依赖/服务。不得将 `branch` 登记当成 checkout 指令。

#### 阶段 2：基础（故事所需前置条件）

无额外基础设施；直接从上述实施阶段 1 的现有协议与 csd 入口开始。

#### 阶段 3：用户故事 1～3 的完整实现（优先级：P1）

同一 Task 按实施阶段 1→2 完成全部路径。完成条件：AC-1～AC-8、AC-10 的实现/本地证据范围齐全，AC-9 的源码交付准备就绪，所有 Build 必要检查通过且剩余独立 Validate/Review/Ship 明示；只请求 Task 实现完成，不把准备当作 Feature 已发布。实现问题仍交同一 Terra 修正。

#### 阶段 N：收尾与横切关注点

按实施阶段 3→4 完成独立阶段和授权交付；任何 source 改动回原实现者，不由只读验证/评审者修文件。回滚使用普通 Git 的有界 revert/修复提交与已核实发现链接恢复，不 reset/force push，不清历史/共享数据；双仓已有部分成功时先核对实际提交和影响，再决定必要补救，不假称原子回滚。

#### 依赖与执行顺序

Task 无其它 Task 依赖。主 Agent 先接受本计划、依次 start-feature/add-task，再派一个 Terra。两仓相关写入不并行分派；完整 Task 检查结束后固定实际业务 commit 对，独立 Validate → 独立 Review → Ship。当前 Plan 不执行这些 mutation、实现或外部动作。

#### 执行策略

最早增量位置与检查见“实施阶段 1”；展示只是实际文档/CLI 合同进度，同一 Task 继续完成。源代码检查及双仓提交使用现有授权，主 Agent 承担生命周期 mutation、集成接受与最终 main push 核对，不增加逐阶段确认。只有真实范围/授权缺口或既有停止条件才暂停；真实 provider 运行仍不在本轮授权内。

#### 说明

后续 brief 的 context_refs 引用本产品文件与本工程文件，不复制完整规则。授权、两次无进展停止及一次诊断限制等仍唯一遵循现行协议；改 Task/worker 名不产生新额度。

## 实现记录（实际）

- **状态**：Build 已由主 Agent 接受；Task 已完成，未启动 provider。实际文件范围见 Git diff：主仓接入参考、入口、usage、fixture 定义和 Unreleased；配套仓修改公共驱动路由及归属，删除旧三文件并更新审计中的活动建议。
- **Task**：`TASK-claude-execution-consolidation`；只有主 Agent 可修改生命周期状态。源码候选 commit 对在固定提交后由主 Agent 核对；本记录不宣称独立阶段或发布完成。

## 验证记录（实际）

- **Build 自检，2026-11-10**：主仓 `3f04cb466d6b0cfecbe95e8347d81c3200f6c2d9` 加本次工作树改动，配套仓 `5124fe112500a78d8a6fc44d661921657ed97f6b` 加本次工作树改动；Node v26.13.0、Python 3.15.2、Git 2.56.0、Bash 3.2.57。标准 `bash scripts/validate-skills` 首次 exit 1：沙箱禁止绑定 127.0.0.1，Hallmark 12 项中 9 项 setup 为 `PermissionError`；其余四组 40、7、5、36 项通过。以获准的沙箱外本机 loopback 重跑同一命令 exit 0，五组共 100 项通过，测试自建临时服务并按测试清理。两仓 `git diff --check` exit 0。
- 配套仓 `bash .agents/skills/driving-claude-code-sessions/scripts/verify-plugin-layout`、`.../scripts/csd help` 均 exit 0；Ruby YAML frontmatter/name/description 和两文件相对 Markdown 链接检查均 exit 0。可选 `quick_validate.py` exit 1，因为当前 Python 没有 `yaml` 模块；未安装依赖，以上 YAML 检查及主仓标准检查为实际结构证据，不把可选命令写成通过。固定上游 bundle、hooks、manifest、LICENSE、wrapper 与 verify 脚本对配套基线无 diff；`shasum -a 256` 五项均与 UPSTREAM 一致。精确发现目标扫描在两隔离 worktree 无旧入口；原工作区存在独立实体目录，已报告主 Agent，不改其他 worktree。
- **无 provider 事件 fixture**：按 `docs/testing.md` 执行；`read-events` exit 0 读到 stop，默认 `wait-for-turn 1` exit 1 超时，`--after-line 0` exit 0 读到同一 stop，`cmp` 确认 meta/events 不变，整体 exit 0。首次脚本在 zsh 中误用只读变量 `status` 导致 exit 1；改为 `wait_exit` 后在全新专属目录完成。固定 bundle 源只读核对 `cmdConverse` 超时返回 1，`cmdStop` 调用 `removeWorker` 清理 meta/events/shim 等；这不是 live 进程测试。
- **结果 fixture 自检**：隔离 Git 版本 A `841e1132473347ce8595f7ac06a2b5d7c7d2d520` 的 artifact 为 `expected`，对应实际 `test "$(cat artifact.txt)" = expected` exit 0；版本 B `07fbed1351545fe034f6865e111eb21b03b1f990` artifact 为 `changed`，旧检查不覆盖 B。三份 TASK 形状输入按实际文件核对：A 的完整候选可接受；缺命令证据和以 A 日志声称 B 的候选拒收，state 前后 `cmp` 相同。首次检查命令在 zsh 中的变量冒号展开使 `git show` 失败；全新 fixture 使用 Bash 和 `${revision}:artifact.txt` 后 exit 0。不同 SHA 本身不是拒绝等价输入的依据。
- **合成场景自检**：原生无外部依赖、普通独立任务不创建 Feature；缺能力/授权报告而不启动或隐式 consent。仍运行等待原 turn，已结束读取结果，未知报告不推断终止；缺证据交同一实现者，取消时保留证据并仅处理核对归属的资源，恢复保留停止、授权、失败和诊断限制。以上是实现者依据文档作的决策核对，不是独立执行。
- **缺口**：独立 Validate/Review 和双 main 交付尚待执行；真实 Claude/provider/tmux launch、converse、stop 与模型任务 `NOT_RUN`。上述自检不证明模型身份、独立性或真实资源回收。

### 独立 Validate（实际，2026-11-10 14:20–14:23 +08）

执行者为独立于 Build 的 Validate 上下文；测试时主仓 HEAD `18edb0e586c1d57252ec7d9dbef4eda3ed929f17`（基线 `5480d8d3f17d74e2579121dda8fa8053e3b137f1`），配套仓 HEAD `29f022aea423f4f6f796e756ce0c5c56838f5429`（基线 `5124fe112500a78d8a6fc44d661921657ed97f6b`）；两仓业务工作树干净，主仓 tracked state 未暂存、无冲突，Task 为 done。环境 Python 3.15.2、Node 26.13.0、Git 2.56.0、Bash 3.2.57；没有安装依赖。

- 主仓 `bash scripts/validate-skills` 沙箱外本机 loopback exit 0，结构及引用检查和 40、7、5、36、12 项测试共 100 项通过；Hallmark 输出一次 Python HTTPError ResourceWarning，测试仍全部通过。测试的临时 HTTP server 使用随机 loopback 端口，源码在 close 中 shutdown/join/server_close；命令退出后 `ps -ax -o pid=,command= | rg '[t]est_hallmark_catalog.py|[s]cripts/validate-skills' || true` exit 0、无对应进程，未操作共享服务。两仓 `git diff --check`、各自基线到 HEAD 的 `git diff --check <baseline> HEAD` 均 exit 0。
- 配套仓 `bash .agents/skills/driving-claude-code-sessions/scripts/verify-plugin-layout` 与 `.agents/skills/driving-claude-code-sessions/scripts/csd help` 均 exit 0；`PYTHONPATH=/Users/mac/.cache/uv/archive-v0/s3Toi1vTz0UMC1P5 python3 -B /Users/mac/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/driving-claude-code-sessions` exit 0，输出 Skill is valid。Python 对驱动 SKILL 和 UPSTREAM 的相对 Markdown 链接检查 exit 0；主仓标准检查覆盖包内引用。上游 manifest、hooks、两个 bundle 与 LICENSE 的 `shasum -a 256` 与 UPSTREAM 五个值一致；`git diff <配套基线> HEAD -- .../dist .../hooks .../.claude-plugin .../LICENSE .../scripts .sdlc-v1 .agents/skills/dreaming` exit 0 且无差异。UPSTREAM 明示 SKILL 本地修改。曾误在配套仓执行主仓基线 diff，exit 128 bad object；随后在正确主仓重跑相同范围 exit 0，属于工作目录错误，不是实现失败。
- 依据 `docs/testing.md` 在新 `CSD_WORKER_DIR` 生成 Stop，实际 `csd --worker fixture read-events` exit 0；`wait-for-turn 1` exit 1 且输出 timeout，`wait-for-turn 1 --after-line 0` exit 0 读取已有 stop；两次 `cmp` 均 exit 0，meta/events 不变，整体 fixture exit 0，专属目录由 trap 删除。只读固定 bundle：`cmdConverse` 等待失败返回 1；`cmdStop` 调 `removeWorker` 删除 meta/events/shim 等。均不证明 live 进程的超时或资源回收。
- 独立准备的隔离 Git 结果 fixture：A `5635f2ade3c44025cb7aa2eac4d2844ea6f6b7a6` 内容 expected、工作树干净，实际 `test "$(cat artifact.txt)" = expected` exit 0、日志可读；B `f3ce8e058c7e3374a8870499e243e62910d701c7` 业务 artifact 改为 changed 并提交、工作树干净。按 TASK canonical 字段准备三份结果并读取实际 artifact、日志和版本：A 完整结果可接受；A 缺命令证据应退回同一实现者；B 引用 A 的旧检查不覆盖 changed，应退回。不同 SHA 本身不是拒收等价输入的理由。fixture `cmp state.before repo/state.json` exit 0，专属临时目录已删除。首次隔离 fixture 未在切换至 B 前打印 A 的工作树状态，因此以第二个新 fixture 补齐该观测；两次均未修改产品 state。以上是本地合成结果，不是 live Agent 运行。
- 独立场景判断（synthetic）：SCN-1/2 原生保持默认且无需外部工具，普通外部独立委托无需 Feature；SCN-3 缺能力或任务/provider/权限绕过授权时报告缺口，不 launch、grant consent、静默替换或从 native child 再套 CLI；SCN-4/5 使用上述文件/检查证据并由主 Agent 管状态与接受。SCN-6 原 turn 仍运行时等待同一 turn，已结束时按旧基线读取结果，未知时报告未知、不重派；SCN-7 合同内纠偏交同一可用实现者，替换不得重置失败历史或已用诊断额度；SCN-8 取消后停止新工作，保留证据与工作树，只处理核实归属资源；恢复须遵守明确停止、授权和单写者约束，不清理共享会话或数据。

| 验收条件 | 本阶段结果 | 证据或后续义务 |
|---|---|---|
| AC-1 | 候选通过；原主工作区待 Ship 后复核 | 两候选三个旧文件删除、活动驱动/审计引用扫描无旧目标；两候选和用户三个 discovery root 精确目标不存在；对两候选、原主工作区和用户各三个 root 的所有即时符号链接按目标及解析路径扫描，旧目标匹配 0。原主工作区 `.agents/skills/claude-rnd-orchestrator` 实体仍在，隔离候选未合并时预期如此，未触碰其他 worktree。 |
| AC-2 | PASS | README、router、Codex adapter 按需引用包内薄适配，diff 未新增状态或执行系统。 |
| AC-3、AC-4 | PASS（文档与合成场景范围） | 原生默认、普通委托、明确选择/能力/授权与执行者身份按上述 SCN 判断；无真实外部链路。 |
| AC-5 | PASS（实际文件与合成结果范围） | 三个 canonical 输入、真实 artifact/log、适用版本及未变 state 如上；主 Agent 独占接受和状态。 |
| AC-6 | PASS（事件 fixture、源码与合成场景范围） | 实测 wait 基线及只读 stop/converse 源码，SCN-6～8 判断如上；live 控制和 OS 回收未测。 |
| AC-7 | PASS | 两仓标准/格式/链接检查、上游 hash 与受保护路径基线 diff 如上；改动文档与参考可读。 |
| AC-8 | 本阶段 PASS；独立 Review 待执行 | 本记录为独立 Validate 命令、双 SHA 与范围；Review 不能由此替代。真实 Claude/provider/tmux launch、converse、stop、grant-consent 和模型任务均 `NOT_RUN`。 |
| AC-9 | PENDING Ship | CHANGELOG 为 Unreleased；版本元数据无 diff。两个实际 main/远端 SHA 和无额外发布需在已授权 Ship 后核对，当前不宣称已交付。 |
| AC-10 | PASS（候选范围） | 两仓基线 diff 已核对：仅主仓记录本需求生命周期，配套 Dreaming、其他技能与上游受保护文件无改动；无历史清理。 |

本轮没有新增生产代码或改 vendor，不虚构覆盖率；上述实际检查的总体归因为 PASS（仅限已明确范围）。独立 Review 和已授权 Ship 是后续阶段，不是本轮已完成事实。

## 评审记录（实际）

- **状态**：NOT_RUN；待实现与正式验证后独立 Sol Review。
- **范围、发现与处理**：无当前实现评审结论。

## 发布与观察记录（实际）

- **产品观察计划引用**：产品上下文“发布后观察计划（SDLC 补充）”。
- **技术发布准备、实际结果、反馈证据与缺口**：NOT_RUN；待两仓实际候选、独立检查/评审与源码 main 推送核对。这里仅记录技术准备和实际结果，不复制产品指标/窗口，也不宣称插件新版发布。
