# 工程上下文：FEAT-bundled-prototype 统一原型入口与分发

## 当前有效方案

主 Agent 已接受本方案，并按用户 2026-10-21 最新明确指示取消旧入口与图书馆测试产物兼容。进度只取自 `state.json`。

### 架构设计

**关联产品上下文**：`.sdlc-v1/context/REQ-bundled-prototype.product.md`
**工程上下文**：`.sdlc-v1/context/FEAT-bundled-prototype.engineering.md`
**已确认需求**：产品上下文 NEED-001、NEED-002、NEED-003、CON-001；命名与触发规则为该上下文标明的工程默认。
**创建日期**：2026-10-21
**状态**：主 Agent 已接受；2026-10-21 已授权提交、发布、更新本地技能和真实触发验证

#### 背景

用户希望通过 `/sdlc` 驱动首次设计和后续迭代，保留独立原型能力，并已明确不保留旧兼容入口或图书馆测试 demo。

原实施分支 `main`，HEAD `0c6ebdc104cccf7d6fa97b65618f35ddedf4c847`。现有未提交改动全部保留；原脏工作区保持不变；发布使用下述独立工作树。方向来源为本次产品上下文及现有 README/CLAUDE 的轻量、可移植、按需加载约定。

源技能位于父工作区 `.claude/skills/product-prototype/`，共 13 个普通文件。插件元数据已声明 `skills: ./skills/`，基线版本为 3.0.0；当前发布按 minor 升级至 3.1.0，同步三处版本和 CHANGELOG。

#### 架构与组件

##### 包内规范原型技能

- **职责**：`skills/sdlc-prototype/` 承接入口、agents 元数据、8 份 references、3 份通用状态 assets，继续支持 create/iterate/inspect 和 client/platform/both。
- **接口**：本地发现名称 `sdlc-prototype`；插件身份 `sdlc-pilot:sdlc-prototype`。独立工作不先启动 SDLC；已跟踪工作仍服从当前 stage。
- **覆盖**：REQ-001/002/003。

##### SDLC 内置协作适配

- **职责**：`skills/sdlc/references/integrations/product-prototype.md` 保持 SDLC 选择策略、阶段边界及证据归属的唯一来源；保留文件名减少无意义改名，不保留旧技能兼容入口。
- **接口**：router、product-design/spec/plan、design 角色及 canonical handoff 引用包内相对路径；不发现或安装外部 product-prototype。
- **覆盖**：REQ-001/004。

##### 旧入口及测试产物清理

- **职责**：迁入并核对完整能力后，移除父工作区 `.claude/skills/product-prototype/` 与 `.agents/skills/product-prototype` 发现链接；不建立 wrapper、资源 symlink 或第二份维护源。
- **接口**：用户明确允许清理 `workspace/20261020-library-prototype/` 测试产物。先确认目录仅包含此前生成的 demo；若发现其他用户内容则保留并报告。仅停止可核实归属于该 demo 的服务，不停止共享服务。
- **覆盖**：REQ-003。

#### 关键设计决定

##### 决定 1：完整迁移，不保留旧名兼容

- **复用证据**：现有 13 个文件已经提供方法与状态实现；插件目录发现和 README 安装循环会包含新目录。用户最新指示取消旧路径兼容需求。
- **决定**：复用现有实现，修改名称、提示词及必要接入文本；通用 runtime 三文件字节不变。移除旧源和发现链接；图书馆 demo 不再用于迁移验收。
- **替代项**：外部可选依赖不满足单包目标；双份复制形成重复维护；兼容 wrapper 已被用户明确取消。
- **取舍**：旧名不再支持。新独立命令仍受宿主索引/安装方式影响，本轮更新已授权的本地安装；未实际验证前不声称宿主已加载。
- **覆盖**：REQ-001/002/003。

##### 决定 2：首次默认设计，后续按受影响范围迭代

- **决定**：首次 UI/交互设计无充分已确认基线时默认调用；实质信息架构、导航、核心旅程、角色、状态反馈或跨端联动变化时评估并更新受影响范围。复用有效基线；尊重明确跳过；后端、普通实现、文案或小样式变化不强制原型。
- **取舍**：只在 adapter 维护完整策略；不永久维护全量第二套 UI。
- **覆盖**：REQ-001/004。

#### API / 接口契约

- `/sdlc` 保持现有生命周期判断及一个主阶段；原型是阶段方法，不增加 stage/schema/CLI。
- product-design/spec 在 brief 指定的 `.sdlc-v1` 外目录探索原型；plan 记录复用及迭代范围；build 更新已计划资产；validate/review 对实现只读；主 Agent 独占 state/transition。
- confirmed、观察、假设、未决事项保持分离；原型证据不能替代生产持久化、并发、认证/授权验证。
- `.sdlc-v1` 外受跟踪原型资产变化需要新的业务验证基线；仅上下文语义变化遵循既有 evidence applicability。
- 插件包内引用必须可搬迁且不逃逸到父工作区；残缺时报告包装缺口，不下载外部旧技能。

#### 风险与取舍

| 风险 | 影响 | 缓解 |
|---|---|---|
| 迁移遗漏 | 新包缺少方法或资源 | 核对原 13 文件和未变资产 hash，隔离副本检查全部内部引用。 |
| 误清理测试以外内容 | 损失用户文件或影响共享服务 | 先核对明确目录和内容，仅清理此任务生成产物与已核实专属服务。 |
| 新命令尚未被索引 | 用户找不到独立入口 | 文档区分包内方法调用与宿主发现刷新，不假称已安装或已发布。 |
| 无关脏改动 | 污染交付或伪造正式验证 | 限定写范围，不提交或处理其他改动，不记录正式 pass。 |

#### 需求覆盖

| 规格需求 | 设计覆盖 |
|---|---|
| REQ-001 | 包内技能、adapter、首次与迭代策略。 |
| REQ-002 | create/iterate/inspect 及终端 profile，独立模式。 |
| REQ-003 | 单一规范源、旧入口及测试产物清理。 |
| REQ-004 | 既有阶段、confirmed 和证据契约。 |

### 实施计划

**关联产品上下文**：`.sdlc-v1/context/REQ-bundled-prototype.product.md`
**关联设计**：本文架构设计
**已确认需求**：NEED-001/002/003、CON-001
**创建日期**：2026-10-21
**状态**：主 Agent 已接受

#### 背景

一个完整 Task 交付包内原型能力、路由、文档和旧入口清理；不拆出无法独立验收的修补工作。

#### 目标 / 非目标

- **目标**：单包方法、明确路由、独立模式、清理已取消保留的旧入口及 demo、相称验证。
- **非目标**：新 stage/schema/CLI、生产功能、JavaScript 行为修改、无关功能或脏改动、无关旧 Feature 的 ship。

#### 技术栈

现有 Markdown/YAML、插件目录发现；Bash/Python 检查与 Node 状态测试。无新依赖。

#### 实施层决定

同一 Terra worker 迁移、编辑、核对后清理，并完成必要检查；主 Agent 接受结果后独立只读评审。没有运行时行为变化，不做浏览器回归，不为文案添加匹配措辞的机械测试。

#### 风险 / 取舍

沿用架构风险表。完整包可移植性与宿主命令实际发现是不同证据；未刷新插件不能写成真实调用成功。

#### 实施阶段

1. 记录源文件和 hash，完整迁入 canonical，更新身份及包内接入；覆盖 REQ-001/002/003。
2. 更新 adapter/router/阶段/design/handoff；覆盖 REQ-001/004。
3. 核对后移除旧源、发现链接和已授权 demo；更新 README 与相关 Unreleased；覆盖 REQ-001/002/003。
4. 执行 V1—V4，返回事实及正式验证缺口；覆盖全部需求。

#### 需求覆盖

| 验收 | Task/设计 | 计划验证 |
|---|---|---|
| 故事1.1 首次设计 | TASK-bundled-prototype / 决定2 | V1/V4 首次请求走查。 |
| 故事1.2 实质迭代 | 同 Task / 决定2 | V1/V4 导航、角色、跨端变化走查。 |
| 故事1.3/1.4 小改、跳过、复用 | 同 Task / 决定2 | V4 排除与基线复用走查。 |
| 故事2.1 单包 | 同 Task / 包内规范源 | V2/V3 移动副本、引用解析和资产检查。 |
| 故事2.2 独立模式 | 同 Task / 直接入口 | V1/V4；宿主刷新后真实调用尚未执行则列缺口。 |
| 故事2.3 无兼容层 | 同 Task / 清理 | V2 文件完整性及旧入口/测试目录不存在。 |
| REQ-004 | 同 Task / 阶段与证据契约 | V4 语义走查，不新增状态或生产能力。 |

### 工程任务

**输入**：当前产品上下文和本有效方案。
**测试**：现有状态测试、结构、包内引用、语义走查；不依赖图书馆产物。
**组织方式**：单一完整 Task，由同一 worker 实施、验证和修正。

#### 格式：`[ID] [P?] [Story] 描述`

`TASK-bundled-prototype [US1/US2]` 内置原型能力并统一路由，清理旧入口及测试 demo；串行。

#### 路径约定

本仓为 `/Users/arnow117/hansen_agent_team/workspace/20260603-sdlc-pilot`；父工作区为 `/Users/arnow117/hansen_agent_team`。

#### 阶段 1：用户故事 1/2 - 统一入口及分发

- **写范围**：本仓 `skills/sdlc-prototype/**`、`skills/sdlc/SKILL.md`、`skills/sdlc-product-design/SKILL.md`、`skills/sdlc-spec/SKILL.md`、`skills/sdlc-plan/SKILL.md`、`skills/sdlc/references/roles/design.md`、`skills/sdlc/references/integrations/product-prototype.md`、`README.md`、相关 `CHANGELOG.md` Unreleased；父工作区旧 `.claude/skills/product-prototype/`、`.agents/skills/product-prototype`、`workspace/20261020-library-prototype/` 清理；本工程上下文实际记录。
- **禁止改动**：state、runtime 三文件行为、其他生产代码、插件元数据/版本、AGENTS/CLAUDE/soul/user、无关脏改动、全局链接。已有 build/validate/protocol/runtime-adapter/TASK 改动必须原样保留。
- **完成条件**：完整能力单包可读、独立与阶段调用一致、无旧名兼容层，V1—V4 通过，文档准确说明命令发现条件与实际未验证范围。
- **V1**：本仓 `bash scripts/validate-skills`、`git diff --check`；canonical `python3 /Users/arnow117/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/sdlc-prototype`。
- **V2**：13 文件完整性、三资产原 hash 比较；检查旧源/发现链接/demo 已移除，无残留调用要求。若发现未授权内容则保留并报告，不能扩大清理。
- **V3**：复制实际插件分发内容到本轮临时目录，保留 symlink 语义；检查本地引用存在且 resolve 不逃逸；在副本运行 `node --test skills/sdlc-prototype/assets/shared-state/runtime.test.cjs`（原有五项）。只清理本轮临时副本。
- **V4**：按产品故事走查首次、实质迭代、小改、跳过/复用、独立任务、已跟踪任务；检查阶段/confirmed/演示边界。README 提供全局 usage 和故事导航，引用方法表与 adapter，不增加 CLI 参数。源规则走查不能写成实际宿主自动触发 E2E。

#### 依赖与执行顺序

主 Agent 接受有效方案后先登记 Feature，再登记 Task；真实 branch main，不 checkout。无并行实现。

#### 执行策略

Terra worker 完整实施并返回命令、版本、工作树与缺口。正式 validation 需要实现 commit、tracked 上下文与干净业务树；当前无 Git 授权，且存在他人脏改动，本轮不伪造 pass。

#### 说明

既有授权覆盖用户明确要求的目录迁移与 demo 清理，不需再次确认；不授权清理其他文件或共享服务。本轮用户已明确授权 commit/push/release；外部操作仅由主 Agent 执行。修正沿用同一 segment 和既有停止条件；无全局 reset/clean。

#### 本轮发布与真实使用验证

- **当前授权**：用户明确要求“提交并发布到 sdlc-pilot，再更新本地技能，实际验证 /sdlc 首次设计和后续迭代触发”。此前不提交/不发布/不安装的限制已被本次授权替代；历史未执行记录仍为当时事实。
- **实际工作树**：`/Users/arnow117/hansen_agent_team/workspace/20261021-sdlc-pilot-release`，开发分支 `codex/bundled-prototype-release`，创建基线 HEAD `0c6ebdc104cccf7d6fa97b65618f35ddedf4c847`。原工作区其他修改不纳入本次提交。
- **Feature 登记迁移**：同一 Feature 前一实现者已完成并返回待验收，无活动写入者；当前工作树用于准备同一 Feature 的最终发布。由主 Agent 执行 `migrate-feature-branch --feature-id FEAT-bundled-prototype --expected-branch main --branch codex/bundled-prototype-release --expected-head 0c6ebdc104cccf7d6fa97b65618f35ddedf4c847 --reason '同一原型整合迁入独立发布工作树，保留原目录无关修改'`。这是登记修正，不改变 Task 或验证结论。
- **发布范围**：原型整合文件与相关状态上下文，三处 3.1.0 版本、该版本 CHANGELOG；排除 stage-agent-protocol/build/validate/runtime-adapter/TASK 的他人修改及 happycompany catalog。发布目标为 `origin/main`、`v3.1.0` tag 和公开 GitHub Release。
- **实际使用验证**：在临时测试项目串行执行两个 `/sdlc` 请求，模型 `gpt-6.1-sol`、xhigh；实际采用同一独立原生会话和同一产品项目完成首次设计与增量迭代，不声称第二次是全新会话。原 CLI 路径因 ChatGPT 账号接口明确拒绝此模型（400）而不能执行，保留失败日志；使用当前原生运行时支持的模型，不替换为其他模型。只指定 `sdlc` 入口，不指定原型 helper 或其路径；第一轮做含移动端/后台的新产品设计，第二轮在已有设计中增加取消预约及跨端反馈。检查实际工具事件是否加载已安装的包内 helper、是否产生/更新交互产物和场景映射、既有 baseline 是否复用；不能只靠最终文本自述。它验证 Codex 执行时的技能入口路由，不能外推为 CLI 账号可用、跨新会话发现或桌面 App 菜单操作成功。为测试实际阶段编排，允许主 Agent → 独立验收 Agent（SUT）→ 单一有界 stage Agent；理由是需要实际运行已安装入口，而非让当前维护者按预期重现结果；主 Agent 最终汇总工具读取及产物证据。
- **范围与收尾**：只有两个串行模型会话，无购买或计费设置变更；CLI 路径每轮最多 15 分钟；原生运行时路径包含产品规格、单一阶段执行和浏览器收尾，首次原生运行包括规格与完整双端制作；已观察到 7 份源码、共享状态动作和测试资产已产生，有验收进展且无实现失败，首次总窗口据此调整为最多 35 分钟（至 08:10 UTC，含浏览器收尾）；第二轮只允许原有流程的有界迭代，预算25分钟。测试项目只作临时验证，保留必要日志/哈希/截图等证据，不长期维护 demo。仅处理本轮归属明确的进程。若首次设计或迭代触发失败，按实际证据回到同一实现者修正，不伪造通过。
- **发布准备 Task**：`TASK-bundled-prototype-release`，输出三处 3.1.0 元数据、准确版本说明和可提交插件包，完成条件为相称检查通过。原实现 Task 已完成且 CLI 不允许 done 回退，故新增本次授权产生的独立发布准备交付，不重置原 segment 的失败/修正历史。
- **顺序**：准备并提交最终源版本 → 提交版本上的结构/状态测试及独立正式评审 → 安装本地候选并完成两轮实际使用验证 → 独立正式评审 → 推送 main/tag → 从远端核对及更新本地插件 → 发布公开 Release 并记录 release。测试证据更新仅写 `.sdlc-v1/**`；若修改插件源码，重新提交并验证对应版本。

## 实现记录（实际）

- 已将原 `product-prototype` 的 13 个文件迁入 `skills/sdlc-prototype/`。只改名、metadata/default prompt 和 canonical handoff；其余方法与 reference 保持源内容。三个通用状态资产 SHA256 均保持：runtime.js `92fbf3708ffeafd0443dad65868e98e92b290c5dfa9ad3683d9abe2562332762`；runtime.test.cjs `3e2eb1002c5f1143f88b26bdc3616371a0827073bc5166332830f7291527ca4e`；example.html `86318b081d82802336c7368d5e2f32460e236aeba23f027cc5985ee8c97c8b1a`。
- adapter 现为包内 `sdlc-prototype` 的唯一选择策略来源；router 仍路由一个主阶段，原型是 helper。product-design、spec、plan 和 design 角色只引用该策略；README 说明 `/sdlc` 的首次/迭代选择、独立入口和宿主发现条件，未声称当前运行时已加载新前缀。
- 已在迁入和核对后清理父工作区旧 `.claude/skills/product-prototype/`、`.agents/skills/product-prototype` 发现链接，以及确认只含本 Task 生成物的 `workspace/20261020-library-prototype/`；未停止或修改共享服务。

## 验证记录（实际）

- 迁移前基线：`bash scripts/validate-skills` exit 0，11 个技能、30 lifecycle + 7 backlog + 36 contrast 测试通过；`git diff --check` exit 0；原技能 quick_validate exit 0。
- 原图书馆 17 项检查在旧方案下通过，仅为历史基线；按最新用户指示，不再作为本轮交付或迁移条件。
- 2026-10-21 清理预检：`lsof -nP -iTCP:4173 -sTCP:LISTEN` exit 1 无监听者；demo 文件列表为本轮已知生成源码、HTML、预览图、设计/产品/验证文档及测试。实现者随后核对目录内容并完成限定清理；未停止服务。
- V1：迁移后 `bash scripts/validate-skills` exit 0（12 个 SKILL.md、30 lifecycle + 7 backlog + 36 contrast 测试通过）；`git diff --check` exit 0；canonical quick_validate exit 0。
- V2：迁入前后均为 13 个文件；仅 SKILL.md、agents/openai.yaml 和 references/handoff.md 按设计变化；三项状态资产 hash 匹配。旧源、发现链接和 demo 目录已不存在。
- V3：复制实际插件根目录（保留符号链接语义、不含 `.git`）到隔离临时包，检查 README、CLAUDE 和 skills 的 67 份 Markdown 本地引用均存在且 resolve 不逃逸；在副本运行 `node --test skills/sdlc-prototype/assets/shared-state/runtime.test.cjs`，5 项通过。
- V4：走查首次无 confirmed baseline、实质 IA/导航/核心旅程/角色/状态反馈/跨端变化、普通小改、明确跳过/充分复用、独立任务与已跟踪任务；adapter、stage 边界和 README 一致。此为规则/文档走查，不是浏览器 E2E 或正式生产 validation。
- 正式 lifecycle validation 仍缺实现 commit、tracked contexts 和干净业务工作树；本轮未写入 validation 结果。

## 评审记录（实际）

- 主 Agent 已接受实现与本地验证证据，通过 CLI 将 TASK-bundled-prototype 设为 done；本 Feature 的下一阶段为 validate，未写入正式 validation/review/release。
- 独立只读预评审 `/root/review_bundled_prototype`：未发现阻塞或其他可操作问题，也未发现有证据支持的重复实现或可避免工程债。首次设计、增量跨端迭代、小样式、明确跳过、独立任务和 tracked build 改规则六类场景与当前阶段边界一致。
- 评审定向核对 16 份 Markdown 的 88 个本地链接，全部存在且无包外逃逸；README 新增三处 fragment 匹配真实标题。源码文档范围在评审开始与结束保持不变；canonical SKILL SHA256 为 `eb2ad97eda2a2a9807582881c3674ee0494cec1385080da8f1f832c70c9cb203`，adapter 为 `525404ab6200844fae9f0397c2daceb7c7a77abd3bc7b4f56336182243f90861`。
- 主 Agent 对原 13 文件 hash 清单独立比对：无缺失，仅 SKILL.md、agents/openai.yaml、references/handoff.md 发生预期变化；8 个已记录的无关文件/元数据 hash 全部保持。旧源、发现链接和 demo 均已不存在。
- 此为未提交工作树的本地预评审，不是 lifecycle review approved；宿主刷新后的新命令发现、自动路由 E2E 与浏览器交互未执行。

## 发布与观察记录（实际）

- **产品观察计划引用**：产品上下文“发布后观察计划（SDLC 补充）”。
- **技术发布准备**：在 `codex/bundled-prototype-release` 独立工作树将 `.claude-plugin/plugin.json.version`、`.claude-plugin/marketplace.json` 的 metadata.version 和 plugins[0].version 统一准备为 `3.1.0`；CHANGELOG 新增 2026-10-21 的 3.1.0 原型能力、首次/迭代选择、独立模式与旧名迁移记录。README 当前版本说明同步为 3.1.0。
- **实际结果、反馈证据与缺口**：尚未 commit、push、tag、创建 GitHub Release、更新本地技能或执行两轮 CLI 实际使用验证；这些外部动作和后续验证由主 Agent 按本轮授权继续完成。

- 2026-10-21 分支登记迁移成功：main → codex/bundled-prototype-release，HEAD 0c6ebdc104cccf7d6fa97b65618f35ddedf4c847，实际根为当前发布工作树。尝试将已完成 Task 改回 in_progress 被 CLI 以 invalid-task-transition:done->in_progress 拒绝，state 未改变；按当前实际新增发布准备 Task，不改状态实现。

- CLI 真实启动失败证据：codex-cli 0.147.0，指定 gpt-6.1-sol/xhigh，17.3 秒退出 1，响应 The gpt-6.1-sol model is not supported when using Codex with a ChatGPT account。未执行产品设计。参数互斥的先前预启动失败也保留于临时 evidence 目录。未切换模型，采用当前原生运行时独立验收。


### 2026-10-21 提交版本检查与安装事实

- 实现提交：`981a849f7dc1247b7bb9c034b5d5c4d44845aa9e`，分支 `codex/bundled-prototype-release`。提交共 26 文件，仅原型整合、三处版本、版本说明和相关上下文/状态；原源码工作树中其他修改保持原状。
- 该提交上 `bash scripts/validate-skills` exit 0：12 个技能、30 lifecycle + 7 backlog + 36 contrast 测试通过；`node --test skills/sdlc-prototype/assets/shared-state/runtime.test.cjs` exit 0，5/5；`git diff --check` exit 0。业务工作树干净。
- `codex plugin marketplace add <发布工作树> --json` 与 `codex plugin add sdlc-pilot@sdlc-pilot --json` 均 exit 0；插件身份 `sdlc-pilot@sdlc-pilot`，版本 `3.1.0`，安装目录为 `~/.codex/plugins/cache/sdlc-pilot/sdlc-pilot/3.1.0`。
- 已将用户级 Codex/Claude 以及父项目 `.agents/skills/` 的 12 个 SDLC 入口统一到该安装包；逐文件核对 78 个 skills/metadata 文件与提交版本相同。安装不依赖原源码中的未提交修改。
- 首次原生验收最初发现父项目旧链接优先于全局入口，识别后已切换为安装包；主 Agent 随后修正项目级链接。此为本地安装发现问题，不改插件源码。两轮产品验收结果待补充。

- 当前 Codex 宿主的技能目录已实际出现 `sdlc-pilot:sdlc-prototype`，入口指向用户级 sdlc-prototype；本轮记录宿主发现已成功，不等同于 CLI 账号模型可用。

- 原生SUT首轮已报告实际浏览器提交失败/重试、同编号批准/驳回与备注、待办2→1→0、筛选空态、取消无副作用、重置fixture通过；输入焦点和375×640底栏问题已由同一实现者修正并复验。首轮在baseline/服务收尾时遭遇 Selected model is at capacity，尚无最终交接；保留产物并恢复同一会话收回证据，不换模型、不重新生成产品，不把运行时错误写成实现失败。


### 实际使用：首次设计（已接受）

- 独立原生会话只收到 `/sdlc` 与社区会议室预约的第一次产品设计请求，没有指定 helper。它按已安装 `~/.codex/skills/sdlc/SKILL.md` → `sdlc-product-design/SKILL.md` → `sdlc-prototype/SKILL.md` 及其 references 执行，使用单一 Terra stage worker 创建产品正文和双端交互原型。
- 实际产物在临时项目 `workspace/20261021-sdlc-prototype-smoke/project/`：`.sdlc-v1/context/REQ-001.product.md` 与 `prototype/` 的 HTML、CSS、app/domain、共享 runtime 和测试。版本 v0.1，产品正文 SHA256 `a6060dae3848f1e29a9558ee5ad4978c65622fbad592140a86ccbfd712fcdf1e`。index `ec86e3a32664b2df943606090c544214a5fc6fea50ea8c3a873c78f5ac88c329`；app `b19b566d5c4dc4dde9ebfa955286de63389e8eec92b8e8277029cc14cc92bc70`；domain `8930b598970797d4dccc431627cebfbbe03eb513d5e58b26c5ae8f276d664ced`；styles `aa811204868f6fce0474b5b19619b5254001d4e6d4af2f05eaa690d8034bb545`。
- 实际命令：`node --test prototype/domain.test.cjs` exit 0（6/6），`node --test prototype/runtime.test.cjs` exit 0（5/5），`node --check prototype/app.js` exit 0。主 Agent 独立执行合并命令 `node --test prototype/domain.test.cjs prototype/runtime.test.cjs` exit 0（11/11），前后源码 hash 不变；runtime 与安装包原件一致。无外部依赖扫描 exit 1 无匹配为预期结果。
- 浏览器实际覆盖：无时段校验、连续输入、模拟失败保留及重试生成 BK-003/待审核、后台批准、居民同编号/状态/备注；另完成 BK-001 驳回、待办2→1→0、筛选空态、取消处理不变、reset恢复2条fixture。输入焦点、375×640底栏、标题层级与底栏对比问题由同一实现者修正并复验，未改插件源码。主 Agent已查看实际批准截图。README缺失测试路径已补全并真实运行。
- 原生会话在最后交接时的容量错误已在同一会话恢复，未换模型、未重建产品；上述产物和有效证据保留。专属HTTP服务 PID27080/session45741已退出0，8765无监听；测试tab关闭、viewport恢复。
- 限制：仅本地同页面内存联动，不证明真实身份、持久化、并发、外部服务、真机或人类可用性。占用/身份/审核政策等仍open，测试Requirement保持captured，没有进入生产研发或发布。主Agent仅执行其capture，SUT未自行mutation state。
- v0.1完整文件基线保留于本轮测试 evidence/first-design-baseline.json 与只读 first-design-snapshot，供第二轮比较；不作为第二份产品权威正文或长期业务demo。

### 实际使用：后续迭代（已接受）

- 同一独立原生会话第二次只收到 `/sdlc` 与“本人待审核预约可取消、后台同步且不得再批准”的产品意图，没有点名原型 helper。会话新读取已安装的 `sdlc-spec/SKILL.md`，复用已加载的 router/product-design/prototype 方法与同一 Terra worker，在原路径更新设计和原型至 v0.2；未新增生命周期阶段、Feature 或 Task。
- 实际变更为原型 domain/app/styles/domain.test/README 及同一权威产品正文。主 Agent 对 v0.1 保存快照做 diff 与 SHA-256 比较：index、runtime、runtime.test 完全不变；样式只增加取消确认区和已取消标签，原导航与批准/驳回保留。新增 SCN-010～013 对应取消、权限、跨端投影和过期操作。
- 最终 SHA-256：domain `edacbc681e1cef1e562182783850e59fb0252b2cfaf3393eb7526f69cbd53605`；app `6a7658a712e2bc67b30d89ab77357e657ddc45a0bb43bddbb659361ab4cbaec5`；styles `2f3a4ff740975c2e70b33d050eb1f9ce419cd977bf6f43f7e0551bbd87318075`；domain.test `89c27aafde8c4f86c2fd8486cd3272e2914372d8836ea2a67d55eebd16a352f4`；产品正文 `0cb32b3ffe0fc19b8038b8f2fa4614cbe64da3ba0c9f65b85ea3c70c5e3fce1d`。完整比较保留于临时 evidence/iteration-result.json。
- 同一实现者实际执行 `node --test prototype/domain.test.cjs` exit 0（9/9，原6条保留，新增3条）；变更 JS 的 `node --check` exit 0；原 runtime 及其测试字节未变，复用已接受的5/5证据。离线扫描无匹配（rg exit1预期）；设计检测 exit0，沿用原两项审美 warning。测试调用 UI 的同一 reducer/selectors，不以隐藏状态注入冒充浏览器点击。
- 浏览器实际覆盖375×640居民001取消确认/保留/确认取消、列表及详情同编号已取消/新增历史；1440×1000后台待办0、已取消筛选1条、详情无批准/驳回按钮、待审核筛选0条。原已批准002与重置后驳回001均无取消入口，原驳回流程正常；切端清除确认区，reset恢复fixture。非本人、错误角色、重复取消及取消/审批先后顺序由同一动作层测试覆盖，不声称真实并发。
- 主 Agent已查看实际后台已取消截图并审阅 domain/app/test 增量差异，接受 v0.2。新截图与检测JSON未覆盖 v0.1证据。专属HTTP PID44126/session24464 Ctrl-C退出0，主Agent复查8765无监听；Chrome测试tab关闭、viewport恢复。
- 结论范围：证实已安装3.1.0在Codex原生会话内，经 `/sdlc` 的首次设计和同项目后续迭代均使用包内原型能力并完成真实交互交付。并未证实CLI账号模型可用、全新迭代会话发现、桌面菜单点击、生产认证/持久化/并发或真人可用性。临时业务demo不进入插件包或发布仓库。

### 正式验证（当前实现提交）

- 独立 validate Agent `/root/validate_sdlc_prototype_release` 完成只读验证，主 Agent接受。实现版本 `981a849f7dc1247b7bb9c034b5d5c4d44845aa9e`；业务树干净，仅工程记录追加，无暂存/冲突。
- 单包78文件一致、13文件/3资产完整、157本地链接、安装发现和迁移清理已覆盖；独立核对首次9项快照及迭代9项hash与实际文件一致；源码及安装内容未变化。复用上述同提交78项包测试与两轮实际使用收据，不重跑相同输入。
- 已查看首次批准与两端取消实际截图，核对产品状态仍captured、open项及演示边界保持；`git diff --check`、只读lifecycle status与hash核对成功，8765无监听。未发现可操作缺陷。
- 残余范围：小改、跳过、充分复用及独立入口仅结构/语义证据；新会话迭代发现、App菜单及CLI模型可用性没有通过证据。CLI400为ENV_BLOCKED；生产身份、持久化、并发、人类研究不属于当前验证。当前产品目标未要求这些能力，未据此伪造结果。
- 主 Agent于2026-10-21执行 `record-validation --feature-id FEAT-bundled-prototype --result pass --test-command 'bash scripts/validate-skills' --commit 981a849f7dc1247b7bb9c034b5d5c4d44845aa9e`，exit0，Feature变为validated。正式review待执行。

### 正式独立评审（当前实现提交）

- 新独立 reviewer `/root/review_sdlc_prototype_release_final` 对已验证实现 `981a849f7dc1247b7bb9c034b5d5c4d44845aa9e` 完成只读 review，未发现可操作问题。主 Agent接受其结论。
- 评审核对路由/直接入口/首次与迭代选择/跳过和复用/阶段及产品权威、README story与参数来源、78安装文件/157链接、两轮各9项hash、3组12发现链接及旧入口清理。复用同提交73项仓库测试和5项runtime证据，阅读状态/失败/reset测试并查看批准及取消截图；失败重试、无副作用返回、重复/过期动作、跨端投影及reset覆盖相称。
- 本次 diff 未发现有证据支持的重复实现或可避免工程债，未发现阻塞发布的源码可读性问题。上述原生/CLI/新会话/生产证据限制保持，不扩大已验证范围。
- 入口检查 `git diff --quiet <validation-commit>..HEAD -- . ':(exclude).sdlc-v1/**'` exit0；业务树clean与diff-check exit0，只读安装字节/链接/快照hash核对exit0。仅工程上下文/state已有变动。
- 主 Agent执行 `record-review --feature-id FEAT-bundled-prototype --decision approved --by review_sdlc_prototype_release_final` exit0，Feature变为reviewed。发布目标明确为origin/main、v3.1.0及公开GitHub Release；尚未记released。
