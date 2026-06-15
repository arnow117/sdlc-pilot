# role-routing — 改动代码 → 角色卡 + validate 模式 的映射表

> 蒸馏源：本表是 sdlc-pilot 的**核心差异化**，无外部 canonical 源（见源地图 §3.1）。
> 机制原型借自 `arch-aifriendly-doctor` 的 P13 domain-aware check（git diff → 只跑该域）
> 与 P23 模块 scoped 命令；surface-map 这张表本身是净新建。
> v1 语言范围：**Python + Web(TS) + App globs**。详见 spec §6 / §6.1。

---

## 0. 这张表是什么 / 不是什么

- **是**：路由规则（glob → 角色卡 + validate 模式），属于 spec §6.1 三输入里"**rarely changes → tracked**"那一类，由蒸馏循环维护。
- **不是**：最终决策。最终决策是一个**函数**，每次进 build/validate/review 时**动态重算**：

  ```
  Decision = resolve( git-diff  ×  PROFILE.surface-map  ×  本表(routing-rules) )
  ```

  - `git-diff`：每次都变 → ephemeral，现算。
  - `PROFILE.surface-map`：项目级 surface map（模块→glob→默认角色/模式），由 `sdlc-onboard` 写入 `<repo>/.sdlc/PROFILE.md`。**优先级高于本表**（项目特化覆盖通用默认）。
  - 本表：当 PROFILE 没覆盖某条 diff 路径，或项目尚未 onboard 时的**通用兜底规则**。

- 解析结果（active roles + validate modes）**快照进 `STATE.md`**（`validate-modes:` 与 `## Active roles`），仅作 handoff/audit 记录，**不作持久事实**（下次 diff 变了就过期）。

---

## 1. 决策算法（每次进 build/validate/review 时跑）

平台无关，只用 `git diff` + 读文件。Codex 同样可跑。

```
1. 取改动文件清单：
   git diff --name-only HEAD          # 工作区相对 HEAD
   # 若已 commit 到 feature 分支，用：
   git diff --name-only <base>...HEAD

2. roles  := {} ; modes := {}
3. for path in 改动文件:
     a. 先查 PROFILE.surface-map：path 命中某 surface 的 glob？
        → 命中：并入该 surface 的 roles + modes，标记 path 已覆盖。
     b. 未命中 PROFILE：按 §2 本表规则匹配（从上到下，可命中多条，全部并入）。
     c. path 既不命中 PROFILE 也不命中本表任何具体行 → 进"未归类"集合。

4. 应用兜底 + 跨链路（§2 的 R8/B1/B2）：
     - **R8 跨链路**：统计命中了几个**不同 surface 类别**（前端 / 服务端 / 数据 / AI / 配置）。**≥2 类 或 full-chain e2e → 并入 `architect`** 视角(看接缝:全链路数据结构对齐 / 跨边界契约 / 单一事实源 / blast-radius)。
     - B1：任意 diff → 并入 qa（baseline）+ correctness。
     - B2：触及敏感面（auth/支付/密钥/用户数据/外部输入/SQL/文件系统）→ 并入 security 视角。

5. 去重 roles、去重 modes。modes 内 e2e 的子模态(Web/OpenAPI/App)分别保留。

6. 漂移检测（spec §6.1 "tracker"）：
     若"未归类"集合非空，或某 path 命中本表但 PROFILE.surface-map 里查无此 surface
     → 输出告警："architecture drifted — refresh PROFILE?" 并建议重跑 sdlc-onboard 相关部分。

7. 写回 STATE.md：validate-modes / Active roles / Changed-files snapshot。
```

降级说明（可移植铁律 §10 rule 3）：

- **并行角色评审**（review 阶段一角色一文件）：Claude 上用 Task/Workflow fan-out（各写 `review/<role>.md`）；
  探测无并行能力（如 Codex）→ **串行**逐角色跑，写同样的分文件。即 gsd-map 的 `Task-or-sequential` 降级范式。
- 任何需要选择 scope 的交互：用纯文本编号列表（gsd `text_mode`），不依赖 AskUserQuestion。

---

## 2. 路由规则表（v1：Python + TS + App）

> 从上到下匹配，**一个 diff 可命中多行，结果取并集**。glob 用 POSIX/gitignore 语义。
> `validate 模式` 列里的 `e2e:Web/OpenAPI/App` 指 `e2e` 模式的对应子模态。

| # | 改动路径 glob | 加载角色卡 | 跑 validate 模式 | 说明 |
|---|---|---|---|---|
| R1 | `**/*.tsx` · `**/*.jsx` · `**/*.vue` · `**/*.svelte` · `**/*.css` · `**/*.scss` · `**/components/**` · `**/pages/**` · `**/app/**`（web 前端） | client-dev + design | correctness + **e2e:Web** | 前端可见面，必走 Web 旅程 + 视觉评审 |
| R2 | `**/*.swift` · `**/*.kt` · `**/*.java`(android) · `**/mobile/**` · `**/ios/**` · `**/android/**` · `**/*.dart` | client-dev + design | correctness + **e2e:App** | 原生/跨端移动；App 模态 v1 排最后（工具选型未定，见 spec §13）。无工具时降级为人工旅程检查清单并记 PARTIAL |
| R3 | `**/api/**` · `**/handlers/**` · `**/routes/**` · `**/*.server.*` · `**/endpoints/**` · `**/controllers/**`（服务端接口） | server-dev | correctness + **e2e:OpenAPI** | API/handler；OpenAPI 端点用例（正向生成 + network_requests 抓真实端点） |
| R4 | `**/models/**` · `**/strategy/**` · `**/*.prompt*` · `**/prompts/**` · `**/ai/**` · `**/evals/**` · `**/llm/**` · `**/agents/**/*.py` · `**/agents/**/*.ts` | server-dev (+ qa) | correctness + **eval-bench** | **AI/模型/策略/prompt/评估的代码** → 触发 eval-bench（按 spec 阶段定的 rubric/数据集/阈值跑质量分）。注：声明式 agent/workflow/skill **定义**（JSON/YAML/SKILL.md）走 R7，不在此 |
| R5 | `**/*.sql` · `**/pipelines/**` · `**/etl/**` · `**/dbt/**` · `**/warehouse/**` · `**/*_spark*.py` · `**/*_pandas*.py` · `**/migrations/**` | big-data | correctness（+ **eval-bench** 当涉及数据质量/回填正确性） | 数据管道/数仓/迁移；big-data v1 为 stub 卡（种自 agency-agents data-engineer） |
| R6 | `**/*.test.*` · `**/*.spec.*` · `**/test/**` · `**/tests/**` · `**/e2e/**` · `**/__tests__/**` · `**/conftest.py` | qa | correctness + **e2e** | 测试/规格本身变更 → QA 视角，并跑相关 e2e |
| **R7** | `**/agents/**.json` · `**/workflows/**.json` · `**/processes/**.json` · `**/employees/**.{yaml,yml}` · `roles.json` · `people.json` · `app.json` · `installed.json` · `**/SKILL.md` · `**/*.skill.*` · `**/CLAUDE.md`（**配置/agent 定义型工程**：源即声明式配置） | server-dev（+ **security** 当含权限/授权矩阵，如 `roles.json`/`people.json`） | correctness | **配置定义型工程**（如 agentic-config-demo：agent/流程/组织/skill 的声明式定义 + 少量真实代码）。验证靠 **schema/契约一致性校验**，不跑 eval-bench（它不是 AI 模型代码）。内嵌真实代码（如 `*.py` CLI）仍按 R3/R4 各自路由 |
| **R8（跨链路）** | **元规则,非单一 glob**：本轮 diff 命中 **≥2 个不同 surface 类别**（前端 R1/R2 · 服务端 R3 · 数据 R5 · AI R4 · 配置 R7 中任意两类），**或** 跑 full-chain e2e | **+ architect** | （沿用各面已选模式） | 改动**跨越多个面 = 全链路/纵切** → 加载 architect 看接缝：全链路数据结构对齐、跨边界契约一致、单一事实源、blast-radius（与单面角色互补,不替代） |
| **R9** | `CLAUDE.md` · `AGENTS.md` · `.claude/**` · `justfile` · `Makefile` · `tsconfig.json` · `.github/**`（AI-上下文 / 构建工具配置） | **+ ai-readiness** | correctness | 动了"代码库对 agent 的友好度"相关文件 → 加载 ai-readiness 视角(别把级联 CLAUDE.md/scoped 命令改坏)。注:onboard 体检与"遗留改造 feature"也加载本卡(非 diff 驱动) |
| **R10（meta：改技能体系自身）** | `skills/**` · `**/SKILL.md` · `skills/sdlc/references/**` · `.claude-plugin/**`（改动落在 **sdlc-pilot 工具自身**，而非某目标项目的业务代码） | **+ skill-maintainer** | correctness（= `bash scripts/validate-skills`） | 在编辑这套技能族自己时加载维护者透镜:防臃肿(不新增顶层 skill)/ additive 合并 / 防孤儿 / 溯源 / 可移植 / semver / 自我修改安全。**小改走 `/sdlc evolve`(append-only),结构性大改走完整 `/sdlc`**(见 `evolve-loop.md` §1 的 guard)。本规则只在被改仓即 sdlc-pilot 时成立 |
| **兜底 B1** | 任意 diff（每次都加） | **qa（baseline）** | **correctness** | 永远至少跑正确性 + QA 基线视角 |
| **兜底 B2** | 触及敏感面：`**/auth/**` · `**/*login*` · `**/*payment*` · `**/*billing*` · `**/secrets/**` · `**/*credential*` · 含原始 SQL 拼接 · 文件系统/外部输入处理 | **+ security 视角**（由 server-dev/qa 卡的 security 子节承载，v1 不单列 security 角色卡） | correctness | 安全敏感面叠加 security 检查清单（见 sdlc-review 安全 10 域） |

---

## 3. 角色卡取值字典（v1 合法值）

路由结果里的角色名必须落在以下集合（对应 `references/roles/*.md`）：

| 角色 | 文件 | 关注切片 |
|---|---|---|
| `qa` | `roles/qa.md` | 测试覆盖追溯、回归、负路径、隔离、敌意测试 |
| `client-dev` | `roles/client-dev.md` | 前端 + 移动端实现（bundle/re-render/offline-first/语言 pitfall） |
| `server-dev` | `roles/server-dev.md` | 服务端 + API 契约 + 性能(N+1/index) + security 子节 |
| `design` | `roles/design.md` | 视觉/排版/交互态/a11y + UX-flow |
| `big-data` | `roles/big-data.md` | 管道/数仓/lineage/幂等/分区（v1 stub） |
| `architect` | `roles/architect.md` | **全链路**数据结构对齐 / 跨边界契约一致 / 单一事实源 / blast-radius（改动跨 ≥2 面时由 R8 加载） |
| `ai-readiness` | `roles/ai-readiness.md` | **面向 AI 的友好度/可维护性**:CLAUDE.md 级联 / scoped 命令 / 噪声 / 类型 / 测试 / LSP 就绪（onboard 只读体检 + 改造 feature + 改 AI-上下文/构建配置文件时加载，见 R9） |
| `skill-maintainer` | `roles/skill-maintainer.md` | **唯一作用于工具自身**:防臃肿 / additive 合并 / 防孤儿 / 溯源 / 可移植 / semver / 自我修改安全（改 sdlc-pilot 技能体系自身时由 R10 加载;`/sdlc evolve` 全程透镜） |

> `security` 在 v1 **不是独立角色卡**：敏感面命中时，由 `server-dev`/`qa` 卡内的 security 子节 + `sdlc-review` 的安全 10 域承载。后续蒸馏循环可升格为独立卡。

---

## 4. validate 模式取值字典（v1 合法值）

| 模式 | playbook | 何时进 |
|---|---|---|
| `correctness` | `validate-modes/correctness.md` | **总是**（兜底 B1） |
| `e2e` (Web / OpenAPI / App) | `validate-modes/e2e.md` | 用户可见面/接口/移动面变更（R1/R2/R3/R6） |
| `eval-bench` | `validate-modes/eval-bench.md` | **AI/模型/策略/prompt/评估变更**（R4），或数据质量(R5 条件) |

子模态选择：`e2e` 的 Web/OpenAPI/App 由命中行决定（R1→Web, R3→OpenAPI, R2→App, R6→沿用被测面对应子模态）。

> **规范 token 形式（单一事实源）**：子模态一律写**冒号形式** `e2e:Web` / `e2e:OpenAPI` / `e2e:App`，与本节字典、PROFILE 模板 surface-map 一致。**禁止**括号形式 `e2e(Web)`——字面匹配字典时 `e2e(Web)` 不等于 `e2e:Web`，严格执行器（如 Codex）会判为字典外野值。所有 STATE/spec/build/plan 快照都用冒号形式。

---

## 5. 已覆盖需求自检（对照任务清单）

- [x] 前端 tsx/vue/css/components → client-dev + design + e2e:Web — R1
- [x] 移动 swift/kt/mobile/ios/android → client-dev + design + e2e:App — R2
- [x] API/handlers → server-dev + e2e:OpenAPI — R3
- [x] AI/models/strategy/prompt/evals → server-dev + qa + eval-bench — R4
- [x] sql/pipelines → big-data — R5
- [x] test/spec → qa + e2e — R6
- [x] 配置/agent 定义型工程（agents/workflows/roles/skill 定义）→ server-dev(+security) + correctness — R7
- [x] **跨 ≥2 面 / 全链路 → + architect**（全链路数据结构对齐 / 跨边界契约 / blast-radius）— R8
- [x] **AI-上下文/构建配置(CLAUDE.md/.claude/justfile…) → + ai-readiness** — R9（onboard 体检/改造 feature 也加载）
- [x] **改技能体系自身(skills/** · *SKILL.md · references/** · .claude-plugin/**) → + skill-maintainer** — R10（`/sdlc evolve` 全程透镜）
  - 注:编辑 `skills/sdlc-backlog/**`(需求树 skill 自身)由 R10 的 `skills/**`·`**/SKILL.md` 覆盖,无需单列规则。需求树**数据**(`<target-repo>/.sdlc/requirements/`)是运行时产物,不是技能体系代码,不进路由。
- [x] 兜底 → qa + correctness（+ security 当敏感面）— B1/B2

---

## 6. 扩展点（蒸馏循环维护）

- 加语言/框架：写一份 `references/languages/<lang>.md` 语言包（见 §7），不再往角色卡塞大段 pitfall。
- 加角色/模式：先扩 §3 / §4 取值字典，再在 §2 引用，避免路由产出"野值"。
- 项目特化：优先写进该 repo 的 `PROFILE.md` surface-map（覆盖本表），不污染通用规则。
- App 模态工具定型后（Maestro/Appium，见 spec §13），更新 §2 R2 的降级说明与 `e2e.md` App 子模态。

---

## 7. 语言包（`references/languages/<lang>.md`）

语言相关知识(陷阱 / 测试·覆盖率命令 / lint / LSP / 框架)**不塞进角色卡**,各自一份语言包,**按改动文件扩展名加载**。角色卡(server-dev/client-dev)、validate/correctness、build TDD、ai-readiness(LSP 维度)都从这里取该语言的确切命令。

| 扩展名 | 语言包 | 默认 role |
|---|---|---|
| `**/*.py` | `languages/python.md`(+ Django) | server-dev |
| `**/*.ts` `**/*.tsx` `**/*.js` `**/*.jsx` | `languages/typescript.md` | server-dev(后端)/ client-dev(前端·E2E) |
| `**/*.go` | `languages/go.md` | server-dev |
| `**/*.rs` | `languages/rust.md` | server-dev(服务)/ client-dev(CLI/桌面/库) |
| `**/*.kt` `android/**` | `languages/kotlin.md` | client-dev(主)/ server-dev(Ktor/KMP) |
| `**/*.swift` `ios/**` | `languages/swift.md` | client-dev |
| `**/*.java` | `languages/java-spring.md`(+ Spring Boot) | server-dev |

> 加载逻辑:resolve 出 active roles 后,**按本轮改动文件的扩展名**加载对应语言包,叠加到角色视角 + validate 命令。一个特性多语言 → 加载多份。归属与 §2/§3 的 surface 路由正交(surface 决定"谁看",语言包决定"用哪套命令/陷阱")。
