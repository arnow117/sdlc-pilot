---
mode: e2e
triggers: ["*.tsx", "*.vue", "*.css", "components/**", "**/api/**", "**/handlers/**", "*.server.*", "**/*.swift", "*.kt", "mobile/**", "ios/**", "android/**", "e2e/**", "*.spec.*", "*.e2e.*", "e2e.config.*"]
distilled-from: [design-review, devex-review, web-api-reverse-engineering, browse, playwright-mcp, tester-army/e2e]
---

# Validate mode: e2e

e2e 从真实用户视角验证受改动影响的旅程。Web、OpenAPI 和 App 可以组合运行；详细证据写入当前 Feature 的研发上下文，不生成独立 SDLC 报告。

## 输入与记录位置

- `.sdlc-v1/project.md` 的 surface map、启动命令和测试入口。
- 当前产品上下文的关键用户旅程与验收条件。
- 当前 `.sdlc-v1/context/<FEAT>.engineering.md` 的设计、测试策略和已知限制。
- 当前 Git diff。

结果追加到研发上下文的 `## Validation` / `### E2E`。测试框架产生的截图、trace、video 或 request/response 文件可以保留在项目原有测试产物目录，并在该小节引用；这些文件是证据附件，不保存进度。

## 选择范围与模态

范围：

| scope | 用途 |
|---|---|
| feature | 只验证本次改动直接影响的旅程，默认 |
| iteration | 验证本次迭代累积影响的旅程 |
| full-chain | 明确要求全链路检查时使用 |

模态：

| 改动 | 模态 |
|---|---|
| Web 页面、组件、样式、路由 | Web |
| API、handler、service | OpenAPI |
| iOS、Android、移动端 | App |

一次改动可触发多个模态。不要扫描与当前 Feature 无关的全站历史。

## 旅程推导

按以下优先级建立“名称 / 入口 / 步骤 / 期望终态”清单：

1. 产品上下文的验收条件和关键用户旅程。
2. 路由表或 OpenAPI paths。
3. Git diff 触达的页面、组件、端点或移动页面。
4. 项目文档中的产品入口。

每条核心旅程至少检查成功、错误和空态；不适用时在研发上下文说明原因。

## Web

`e2e:Web` 强制使用 [tester-army/e2e](https://github.com/tester-army/e2e) 的 CLI runner 和 Web engine，
执行已提交的测试，验证当前 scope 内受影响的 Web 用户旅程。这里的 SDLC `e2e` 是验证方式，
`tester-army/e2e` 是执行框架；不新增阶段、validate mode 或 lifecycle state 字段。
项目已有 Playwright、Cypress 或其他浏览器套件可作补充，但通过这些套件不能免除本节要求。

### 阶段职责

| 阶段 | 职责与交付 |
|---|---|
| Onboard | 在 `project.md` 记录框架与 Node / 浏览器版本、启动与测试入口、工程资产与产物位置、模型 provider 的凭据来源、测试身份及准备缺口；不安装或改测试 |
| Plan | 将验收条件映射到旅程、期望终态和业务断言；明确 URL / 环境、浏览器与 viewport 范围、前置状态、数据清理、模型预算、重试、缓存及证据归档策略；缺少配置、fixture、覆盖或 CI 准备时列入 Build Task |
| Build | 按有效 Plan 准备下节的工程资产与产物管理，运行并检查成功、错误及空态；需要共享缓存时检查录制动作并随测试提交，记录实际执行入口与归档位置 |
| Validate | 独立运行当前集成 commit 的已提交测试，核对覆盖和证据，按下文归因；不修改实现、测试、配置、断言或已审查录制，缺覆盖返回 Build |

阶段 Agent 和主 Agent 的派工与状态权限仍遵循 [stage-agent-protocol.md](../stage-agent-protocol.md)。e2e 自带的 Skill、MCP 和
探索能力可辅助准备测试或定位失败；探索结论、生成测试和交互操作不能替代已提交测试的实际回归执行。

### 工程资产与运行产物

测试资产留在目标工程的测试目录；`.sdlc-v1/` 只保存既有项目上下文、Feature 证据摘要与 lifecycle state。
以下是框架默认路径示例；已有工程可沿用目录约定，并在 `project.md` 记录实际位置，不要求重排现有测试。

| 文件或目录 | 内容与管理方式 |
|---|---|
| `package.json` 与对应 lockfile | 固定 `e2e`、Web engine 及所需 provider 依赖，提供实际验证过的测试入口；纳入 Git |
| `e2e.config.ts` / `e2e.config.mts` | 目标、浏览器、模型、超时、缓存与报告配置；纳入 Git，凭据只引用环境变量或项目已有的凭据来源 |
| `tests/*.e2e.ts` 与相关 fixture / cleanup | 产品旅程、确定性业务断言、测试数据及状态准备 / 清理；纳入 Git，不把脚手架示例通过当作业务验收 |
| `.gitignore` | 忽略已安装的依赖目录、运行报告、截图 / trace、日志与临时会话；纳入 Git，使用自定义产物路径时同步维护 |
| `.e2e/cache/` | 动作回放，默认忽略；是否共享提交及审查方式遵循下文的模型与缓存约束 |
| `.e2e/report.json`、`junit.xml` 等报告 | 运行产物，不纳入 Git；JUnit 等按实际 reporter 配置产生，在研发上下文引用归档证据 |
| `.e2e/artifacts/` 及其他启用的日志 / trace / video 输出 | 运行证据，不纳入 Git；必要证据归档后使用稳定引用，不能只引用下次会覆盖的本地路径 |
| `.e2e/sessions/` | 临时登录会话，不纳入 Git，也不作长期证据；正常由框架在运行结束时清理 |
| 项目既有 CI 配置 | 有 CI 时按 Plan 接入测试任务与产物归档，纳入 Git；保留 runner 退出结果，失败时也保留已有报告与日志 |

Build 复用项目包管理器与既有配置，检查脚手架产生的 diff；保留已有测试脚本、依赖和 Agent 配置，
入口冲突时选择独立脚本名并记录，不因初始化覆盖其他套件。provider / 模型沿用有效 Plan，不能直接接受脚手架默认值。
框架自带 Agent Skill 与 MCP 客户端配置是可选辅助，按项目约定接入，不作为 CLI 验收的前提。

输出目录与缓存目录独立配置；移动输出目录不会自动移动缓存。归档或清理仅处理当前运行所属的产物，
不能覆盖其他任务的证据或删除共享录制；产物与版本控制约定在 Build 完成，Validate 不临时修改 `.gitignore` 来满足工作树检查。
框架原始报告不写入 `state.json`，不另建 SDLC 状态、runner 或结果数据库。

### 执行与业务断言

1. 执行前确认依赖、浏览器、启动入口、必要身份和模型配置可用；打开真实入口并记录初始状态。
   核对站点实际运行的构建 / 部署版本与被测 commit 的关系，不能用当前 HEAD 为旧服务结果背书。
2. 用已提交测试中的 `agent.act` 执行明确业务目标，也可使用确定性 locator 操作；不要求每一步调用模型。
   Agent 根据当前界面选择操作路径可以用于验收，但不能替代验收条件或自行放宽期望终态。
3. 每条核心旅程的最终业务结果必须有确定性断言，例如确切的状态、业务字段或持久化结果。
   `agent.assert`、视觉判断和截图可补充证据，不能单独证明必要业务结果；“页面出现”不等于目标完成。
4. 对照 Plan 核对实际收集和运行的旅程、目标与结果。总体退出成功不能掩盖必要用例被过滤、跳过、未收集、
   中断或缺失断言；重试才通过的用例记录为 flaky，并按 Plan 的质量要求判断，未约定时保持未通过。
5. 检查 console error、关键 network request、适用的错误态、空态、键盘操作、响应式和无障碍要求。
   使用确定性等待，不用裸 sleep。框架尚不支持的必要检查可用 Playwright 等工具补充，并分别记录；
   核心旅程无法由指定框架执行时保持未通过，不自动用其他套件结果替代。

### 模型与缓存

- Plan 明确 provider / 模型、步骤与超时预算、并发和重试上限，以及允许的测试环境、身份和操作范围；
  凭据值不写入产品 / 研发上下文。框架的环境标签不代表已获得该环境的操作授权。
- Build 可以按 Plan 生成或更新缓存；共享录制作为测试资产检查动作、输入和目标后纳入版本控制。
  Validate 显式使用 `read-only` 缓存，不能只依赖 CI 默认值；报告和证据产物写入测试产物目录。
- 是否启用 strict 缓存由 Plan 明确。严格模式拒绝失效录制，但不保证零模型调用；新步骤、重试及回放缺口
  仍可能实时执行，`agent.assert`、`agent.waitFor`、`agent.extract` 也不使用动作回放缓存。
- 允许实时执行时记录实际模型与缓存情况；超出既有预算或外部操作授权时保持未通过并报告缺口。
  Validate 不关闭 strict、刷新录制或改断言来获得通过。

### 证据与归因

结果按下文统一格式写入研发上下文，并引用框架的 `report.json`、已配置的 JUnit 和适用的 trace、screen / screenshot
等附件。记录实际命令、退出码、执行时间、测试 / 配置路径及版本、URL、浏览器 / viewport、被测构建 / commit、
必要旅程覆盖、模型调用 / usage、缓存回放或实时接管以及各次失败与重试结果。未使用模型或缓存时明确写明。
身份流程使截图不可用时，说明原因并保留可用的文本、trace 或业务断言证据；必要视觉证据不足时保持未通过。
重跑前保留旧失败证据，避免框架清理输出后只剩成功结果。
核对报告的运行时间、用例和目标与本次命令记录一致；测试启动前失败、收集失败或零用例等情况可能保留旧输出，
不能把旧报告的通过结果算作本次通过。缺少本次报告时保留此次退出码和日志，按下文归因并保持必要验证未通过。

按 [验证归因](../../../sdlc-validate/SKILL.md#验证归因) 判断，不能只按 runner 退出码转换：

- 模型拒绝凭据、配额或外部依赖缺口已确认时记录 `ENV_BLOCKED`，不据此重做产品实现。
- 业务断言失败且原因可定位时记录 `IMPLEMENTATION_FAILED`；原因未确认时记录 `INCONCLUSIVE`。
- 缓存失效、Agent 未完成、自动化能力不足或截图 / 报告缺失，本身不能证明产品有错；记录具体缺口，
  由主 Agent 决定补测试、解决环境或补证据。所有必要检查实际通过后才可汇总为 `PASS`。

框架行为以项目固定安装版本附带的文档和实现为准；在线 [CI](https://e2e.tester.army/docs/ci)、
[缓存](https://e2e.tester.army/docs/cache) 和 [调试](https://e2e.tester.army/docs/debugging) 文档作为检索入口。
项目具体命令在目标工程实际运行后写入 `project.md`，
不在本参考猜测 CLI 参数或复制另一套 runner。

## OpenAPI

1. 优先从 OpenAPI/Swagger 生成请求与断言；没有规范时，从真实 Web 流量和路由实现推导。
2. 验证状态码、响应 schema、关键业务字段、认证和错误格式。
3. 生产或共享环境只执行只读或幂等请求。
4. 创建、更新、删除用例只在隔离测试环境运行；否则标记未运行并给出人工步骤。
5. 保留必要的 request/response 摘要，脱敏后写入研发上下文。

## App

`e2e:App` 强制使用 Maestro CLI 执行已提交的 Flow，验证当前 scope 内受影响的移动端用户旅程。
项目已有的移动自动化可作为补充，但不能替代本节要求；已有套件通过、项目测试命令或 surface map
指定了其他工具，都不能免除 Maestro 验证。

1. 在 Plan / Build 中将产品验收条件映射到 Maestro Flow，明确目标平台、前置状态、测试数据和清理方式。
   优先复用满足这些条件的既有 Maestro Flow；覆盖缺失时返回 Build 补充测试，Validate 不修改 Flow 或实现。
   Flow 及其引用的 subflow、脚本、配置和 fixture 必须纳入被测 commit，不能用临时或被忽略的测试资产为该版本背书。
   凭据使用工程既有的外部来源，运行报告 / 截图等产物不纳入 Git，必要证据归档后在研发上下文引用。
2. 执行前确认 Maestro 版本、设备或模拟器、App 构建与安装状态、测试环境及所需身份。确认已安装的 App
   来自本次被测实现版本，记录构建产物标识和设备 / OS；不能用当前 HEAD 为旧 App 构建的结果背书。
3. 使用 Maestro CLI 实际运行选定 Flow，检查最终业务结果和适用的错误态、空态。MCP 可用于探索、编写 Flow
   和定位失败，但交互操作或生成 Flow 本身不能替代 CLI 回归执行。
4. 关键验收条件使用确定性断言。AI 断言可作补充；参与验收的 AI 断言必须显式设置 `optional: false`，
   不能用默认可选步骤或成功截图代替必要的业务断言。
5. 按下文统一格式保留实际命令、退出结果、Flow 路径、配置、被测版本及日志 / 截图等证据，绑定到当前
   Feature 的研发上下文。单元、原生测试及其他移动套件仍按测试策略运行，其结果分别记录。
6. Maestro、设备、构建、身份或平台支持不足时，按验证归因记录未执行、受阻或证据不足，App 必要验证保持
   未通过；不自动切换其他工具并标为通过。缺少 App 验证不影响其他模态的真实结果，但不能推进需要 App
   验收的 Feature 到验证通过。

## 失败处理

e2e 负责取证与归因，不在验证阶段自动修实现。恢复路径遵循
[验证归因](../../../sdlc-validate/SKILL.md#验证归因)：

1. 收集可用的 console、network、trace、snapshot、runner 或设备日志，记录期望、实际、复现步骤与可定位的文件位置。
2. 已确认的环境 / 身份 / 配额缺口按 `ENV_BLOCKED` 解决环境，原因未明或证据不足按 `INCONCLUSIVE` 补充定位和证据；
   两者均保持必要验证未通过，不直接推断产品实现有错。
3. 确认需要修改实现、测试、配置或指南时返回 `sdlc-build` 做有界修复；产品规则或验收条件缺口交由主 Agent 处理。
4. 环境 / 证据缺口解决或修复提交后，重新运行受影响旅程和必要回归，不能沿用受阻或失败前的通过结论。

视觉问题可保留 before / target / after 证据；功能问题保留失败断言与修复后断言。不要强制“一条问题一次提交”，正常按当前 Feature 的 Git 工作流组织提交。

## 必要条件

e2e 通过需要：

- scope 内所有核心旅程都运行到终态。
- 成功路径断言通过。
- 适用的错误态和空态符合预期。
- 未运行部分明确标为 `PARTIAL` 或 `INFERRED`。
- 未解决的核心旅程失败为零。

每个结论标记：

- `TESTED`：在被测目标上实际运行并观察。
- `PARTIAL`：运行过，但受数据、凭证或环境限制。
- `INFERRED`：未运行，只能静态推断。

必要旅程为 `PARTIAL`、`INFERRED` 或未执行时，整体保持未通过；明确不适用的检查记录理由。
环境或凭证不足时，结果是受限或失败，不伪造通过。

## 写入研发上下文

统一遵循 [sdlc-validate 的验证归因](../../../sdlc-validate/SKILL.md#验证归因)，在下列小节记录每项检查的
outcome、分类依据、执行时间和脱敏环境信息；混合问题分开记录。这里的覆盖/质量指标不替代验证归因。


在 `.sdlc-v1/context/<FEAT>.engineering.md` 更新：

~~~markdown
## Validation

### E2E — <commit>

Scope: feature | iteration | full-chain
Modalities: Web, OpenAPI, App
Target: <URL / API base / device>

| journey | modality | result | method | evidence |
|---|---|---|---|---|
| <name> | Web/OpenAPI/App | PASS/FAIL/PARTIAL/SKIPPED | TESTED/PARTIAL/INFERRED | <observed result and artifact ref> |

Failures: <none or reproduction + source location>
Unverified: <none or limitation + manual steps>
~~~

同一 commit 重跑时更新对应小节。E2E 正文和进度只使用研发上下文与 lifecycle state；截图放项目原有测试产物目录。

## 状态更新

e2e 不直接编辑 `state.json`。所有选定验证方式结束后，`sdlc-validate` 根据合并结果调用一次 `record-validation`。后续评审与发布分别只由 `record-review` 和 `record-release` 更新机器状态。

## 常见错误

- 只走 happy path。
- 把 DOM 存在当作用户目标完成。
- 失败只写现象，没有复现步骤或源码定位。
- 在真实环境执行破坏性 API。
- 没有设备工具却把 App 结论标成 `TESTED`。
- 将截图或测试产物当作另一份进度来源。
