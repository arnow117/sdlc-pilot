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

4. 应用兜底（§2 最后两行）：
     - 任意 diff → 并入 qa（baseline）+ correctness。
     - 触及敏感面（auth/支付/密钥/用户数据/外部输入/SQL/文件系统）→ 并入 security 视角。

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
> `validate 模式` 列里的 `e2e(Web/OpenAPI/App)` 指 `e2e` 模式的对应子模态。

| # | 改动路径 glob | 加载角色卡 | 跑 validate 模式 | 说明 |
|---|---|---|---|---|
| R1 | `**/*.tsx` · `**/*.jsx` · `**/*.vue` · `**/*.svelte` · `**/*.css` · `**/*.scss` · `**/components/**` · `**/pages/**` · `**/app/**`（web 前端） | client-dev + design | correctness + **e2e(Web)** | 前端可见面，必走 Web 旅程 + 视觉评审 |
| R2 | `**/*.swift` · `**/*.kt` · `**/*.java`(android) · `**/mobile/**` · `**/ios/**` · `**/android/**` · `**/*.dart` | client-dev + design | correctness + **e2e(App)** | 原生/跨端移动；App 模态 v1 排最后（工具选型未定，见 spec §13）。无工具时降级为人工旅程检查清单并记 PARTIAL |
| R3 | `**/api/**` · `**/handlers/**` · `**/routes/**` · `**/*.server.*` · `**/endpoints/**` · `**/controllers/**`（服务端接口） | server-dev | correctness + **e2e(OpenAPI)** | API/handler；OpenAPI 端点用例（正向生成 + network_requests 抓真实端点） |
| R4 | `**/models/**` · `**/strategy/**` · `**/*.prompt*` · `**/prompts/**` · `**/ai/**` · `**/evals/**` · `**/llm/**` · `**/agents/**` | server-dev (+ qa) | correctness + **eval-bench** | **AI/模型/策略/prompt/评估** → 触发 eval-bench（按 spec 阶段定的 rubric/数据集/阈值跑质量分） |
| R5 | `**/*.sql` · `**/pipelines/**` · `**/etl/**` · `**/dbt/**` · `**/warehouse/**` · `**/*_spark*.py` · `**/*_pandas*.py` · `**/migrations/**` | big-data | correctness（+ **eval-bench** 当涉及数据质量/回填正确性） | 数据管道/数仓/迁移；big-data v1 为 stub 卡（种自 agency-agents data-engineer） |
| R6 | `**/*.test.*` · `**/*.spec.*` · `**/test/**` · `**/tests/**` · `**/e2e/**` · `**/__tests__/**` · `**/conftest.py` | qa | correctness + **e2e** | 测试/规格本身变更 → QA 视角，并跑相关 e2e |
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

> `security` 在 v1 **不是独立角色卡**：敏感面命中时，由 `server-dev`/`qa` 卡内的 security 子节 + `sdlc-review` 的安全 10 域承载。后续蒸馏循环可升格为独立卡。

---

## 4. validate 模式取值字典（v1 合法值）

| 模式 | playbook | 何时进 |
|---|---|---|
| `correctness` | `validate-modes/correctness.md` | **总是**（兜底 B1） |
| `e2e` (Web / OpenAPI / App) | `validate-modes/e2e.md` | 用户可见面/接口/移动面变更（R1/R2/R3/R6） |
| `eval-bench` | `validate-modes/eval-bench.md` | **AI/模型/策略/prompt/评估变更**（R4），或数据质量(R5 条件) |

子模态选择：`e2e` 的 Web/OpenAPI/App 由命中行决定（R1→Web, R3→OpenAPI, R2→App, R6→沿用被测面对应子模态）。

---

## 5. 已覆盖需求自检（对照任务清单）

- [x] 前端 tsx/vue/css/components → client-dev + design + e2e(Web) — R1
- [x] 移动 swift/kt/mobile/ios/android → client-dev + design + e2e(App) — R2
- [x] API/handlers → server-dev + e2e(OpenAPI) — R3
- [x] AI/models/strategy/prompt/evals → server-dev + qa + eval-bench — R4
- [x] sql/pipelines → big-data — R5
- [x] test/spec → qa + e2e — R6
- [x] 兜底 → qa + correctness（+ security 当敏感面）— B1/B2

---

## 6. 扩展点（蒸馏循环维护）

- 加语言/框架：在 §2 增行或扩 glob（如 Go `**/*.go`、Rust `**/*.rs`），并在角色卡补对应 pitfall 表。
- 加角色/模式：先扩 §3 / §4 取值字典，再在 §2 引用，避免路由产出"野值"。
- 项目特化：优先写进该 repo 的 `PROFILE.md` surface-map（覆盖本表），不污染通用规则。
- App 模态工具定型后（Maestro/Appium，见 spec §13），更新 §2 R2 的降级说明与 `e2e.md` App 子模态。
