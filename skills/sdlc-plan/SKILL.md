---
name: sdlc-plan
description: >
  SDLC 主线的「规划」流程 skill:把【已批准的 spec.md】拆成可直接执行的 plan.md——两级贯通:
  spec → 阶段(phase,含 depends_on/wave 波次依赖) → 任务(task,含三必填字段 read_first/acceptance_criteria/action);
  按 L1-L4 复杂度自适应粒度。
  触发于:用户说 "/sdlc plan"、"拆任务"、"做计划"、"规划阶段"、"plan this"、"把 spec 拆成任务"、
  "spec 批了下一步怎么做",或 driver 在 STATE.stage=plan 处路由进来。
  入口前提:spec.md 已存在且已获批(讨论已在 sdlc-spec 完成,本 skill 不再做需求讨论)。
  本 skill 只产出 plan.md + 写回 STATE,不写代码/不跑测试/不评审。五准则、目标倒推、双向追溯门、蒸馏来源等见正文。
---

# sdlc-plan — 把已批准的 spec 拆成可执行的 plan.md

你的唯一职责：读 **已批准的 `spec.md`**，产出一份 **`<target-repo>/.sdlc/plan.md`**，
它把需求**两级贯通**：

```
spec(已批准)  →  阶段 phase(含 depends_on + wave 波次)  →  任务 task(含三必填字段)
```

产物必须满足两条铁律（贯穿全文）：

- **No-Placeholder（无占位红线）**：任何任务的 `action` 必须含真实可执行内容（具体文件路径、
  具体值、具体命令），不许出现 "TBD / 待定 / 实现细节后补 / 加适当的错误处理 / v1 先这样"。
- **100% Traceability（全覆盖追溯）**：spec 里每一条需求/决策都能指到至少一个任务；
  反向每个任务都能指回它实现的需求。靠 Source Audit + Coverage Gate 双向核验（§6）。

> **引擎 = Claude + Read/Edit/Bash/Grep。** 不依赖 gsd-tools.cjs / Task 子代理 / `.planning/`
> 目录 / AskUserQuestion。所有交互用 **text_mode**（纯文本编号列表），所有产物落纯文件。

---

## 0. 入口条件（先验，未满足就停）

进入本 skill 前确认：

1. `<target-repo>/.sdlc/spec.md` **存在**。
2. spec **已获批**（`sdlc-spec` 的出口门控已过；STATE 里 spec 状态为 approved）。

> 这是硬前置:没有获批的 spec 就拆 plan,等于在没对齐的设计上排兵布阵。两条都满足才往下走。

- **无 spec.md** → 停。text_mode 提示用户先走 `sdlc-spec`：

  ```
  没找到 .sdlc/spec.md。规划需要一份已批准的 spec 作输入。
    1) 现在去跑 sdlc-spec 产出并批准 spec（推荐）
    2) 我手动指给你一个已有的 spec 文件路径
  回复编号。
  ```

- **spec 存在但未确认获批** → 不静默继续。text_mode 让用户确认：

  ```
  找到 spec.md，但 STATE 里没看到"已获批"标记。规划会把 spec 当作锁定决策来拆。
    1) spec 已经批了，继续规划
    2) 还没批，我先回 sdlc-spec 走批准门控
  回复编号。
  ```

> **本 skill 不做需求讨论 / questioning。** 那是 `sdlc-spec` 的事。这里把 spec 当作**锁定的输入**。
> 若发现 spec 有歧义/缺口，**不是**自己拍板补——而是记进 STATE 的 Decisions log 并按 §6 的
> MISSING 流程上报，让用户决定（加任务 / 拆阶段 / 显式 defer）。

---

## 1. 可移植前置（每次入口一次性）

> **共享 references 的位置（单一约定）**：本文引用的 `references/role-routing.md` 等共享数据**物理上只在 sdlc 驱动器 skill 目录下**（`sdlc/references/`），不在本 skill 自己的目录里。解析时指向 `sdlc/references/...`（相对 skills 根）或经 dogfooding 软链接定位，**不要**当作相对本 skill 目录的路径。

与 driver 同源的两条降级范式（spec §10 兼容性铁律 rule 3）：

### 1.1 交互降级 — text_mode
凡需用户确认（复杂度分级、MISSING 项处置、最终 plan 确认），**优先纯文本编号列表**：

```
需要你定一个：
  1) 选项 A — 说明
  2) 选项 B — 说明
回复编号即可。
```
有 AskUserQuestion 时可用，但回退路径必须是上面这种编号文本。默认按 text_mode 写。

### 1.2 并行降级 — Task-or-sequential
规划本身通常**单 session 串行**即可（拆任务是连贯推理，不强求并行）。
若 spec 覆盖**多个独立子系统**且环境有 Task/并行能力，可一子系统一 agent 并行起草分计划；
**无并行能力（Codex 等）→ 串行逐子系统拆**。不论哪种，最终合并成一份 `plan.md`，
且**单写者**写 plan.md / STATE.md（不并发写同一文件）。

---

## 2. 入口先做：改动代码 → 角色 + 模式 轻解析

> 规划不是 driver 列的三个"改动驱动阶段"(build/validate/review)之一，但**预解析**一次有用：
> 它让 plan 在拆任务时就**预告**哪些 surface 会被动、后续会装载哪些角色卡、跑哪些 validate 模式，
> 从而把"每个阶段的可观察成功标准"对齐到将来真正会跑的验证手段（避免拆出来的任务后面没法验）。

调用 driver 的路由规则 `references/role-routing.md`（**不内联整张表**），按其 §1 算法跑一次：

```bash
# 1) 取目标 surface：
#    - 若已有改动（如在分支上迭代）：
git -C <target-repo> diff --name-only HEAD
git -C <target-repo> status --porcelain
#    - 若是全新特性、尚无代码改动：从 spec 声明的"要动哪块"对照 PROFILE.surface-map 取默认 surface
```

解析（与 driver §3 同口径，结果只作**规划期参考 + 写进 STATE 快照**）：

1. 命中 `PROFILE.surface-map` 的 surface → 取其默认角色 + 默认 validate 模式。
2. 叠加 `role-routing.md` 通用 glob 规则。
3. 基线：任意改动 → `qa` + `correctness`；敏感面 → `security` 视角；
   AI/模型/策略/prompt/evals → `eval-bench`；用户可见面 → `e2e`(选 Web/App/OpenAPI 子模态)。

**用途（规划期，不是 review 期）**：
- 给每个阶段定"可观察成功标准"时，**优先用将来真会跑的验证手段表述**
  （前端面 → 用 e2e:Web 旅程能断言的行为；AI 面 → 用 eval-bench rubric 能打分的指标）。
- 把解析出的 `active roles` + `validate-modes` + `changed-files` **快照进 STATE**（§8），
  作交接/审计用，**不当权威源**（真正的 role review 在 sdlc-review 时按那一刻的 diff 重算）。

漂移检测：若目标 surface 落在 `PROFILE.surface-map` 之外（新建服务/首个移动目录），
text_mode 提示"架构漂移，建议先刷新 PROFILE（重跑 sdlc-onboard 相关部分）"——不阻断，记 STATE。

---

## 3. 复杂度分级 → 粒度自适应（L1–L4）

> 蒸馏自 `planner-breakdown-sdlc` 的 L1-L4 分级。**同样的流程不适用所有项目**：先定级，再定拆多细。
> 反过度规划：**只规划到能做出判断的程度**，不填充未来细节。

读 spec + PROFILE，按下表给本次特性定级（一句话写进 plan 头部 + STATE Decisions log）：

| 等级 | 特征 | 拆分粒度取向 | 阶段数典型 |
|---|---|---|---|
| **L1 原型/MVP** | 单人/验证概念/无严格质量要求（个人项目、内部工具、spike） | 合并设计与实现，压到最短；任务可粗 | 1–3 |
| **L2 产品级** | 小团队/有质量要求/需维护（SaaS MVP、小程序、简单业务系统） | 分离测试阶段；TDD 用于核心逻辑 | 3–5 |
| **L3 企业级** | 中大团队/多依赖/合规（管理系统、交易系统、有 SLA） | 独立设计评审 + 独立 UAT；阶段间硬依赖显式化 | 5–7 |
| **L4 平台/基础设施** | 大团队长期维护/横向扩展/高可用 | 架构优先 + 增量上线；波次依赖严格 | 多，分批 |

> v1 dogfood 目标 agentic-config-demo 多为 **L2**，少数核心模块 L3。定级影响：阶段数、每个阶段任务数、
> 是否需要独立"集成/UAT"阶段、TDD 覆盖范围。**每个拆分都要附"为什么这样拆"的理由**（写进 plan）。

---

## 4. 第一级：spec → 阶段（phase，含依赖与波次）

蒸馏自 `gsd-new-project` 五准则 + `gsd-plan-phase` 的 depends_on/wave + must_haves 目标倒推。

### 4.1 划分阶段：五准则（硬约束）

把 spec 拆成阶段时，**逐条满足**：

1. **派生阶段（derive，不照抄）**：阶段从 spec 的需求**结构**推导出来，而不是把 spec 章节标题
   直接当阶段名。问"要交付这个，必须先有什么、再有什么"。
2. **1 需求 ↔ 1 阶段（聚焦）**：尽量让一个阶段服务一组**内聚**的需求，避免一个阶段塞进互不相关的需求。
3. **可观察成功标准**：每个阶段必须有**从用户/外部视角可观察**的成功标准（不是"代码写完了"，
   而是"调用 X 返回 Y / 页面能完成 Z 流程 / 指标达 阈值"）。优先用 §2 预解析出的验证手段来表述。
4. **100% 覆盖**：所有阶段并起来，**覆盖 spec 的全部需求**——无遗漏、无凭空多出。
5. **Traceability（可追溯）**：每个阶段标注它覆盖 spec 的哪些需求 ID / 决策 ID；反向 spec 每条都能找到归属阶段。

### 4.2 目标倒推 must_haves（每个阶段）

对每个阶段，用**目标倒推**法（goal-backward）推出"必须成立的东西"，而不是"要做的活"：

1. 陈述**目标**（结果，不是任务）。
2. 倒推 **observable truths**（3–7 条，**用户视角**的可观察行为）。
3. 倒推 **required artifacts**（必须存在的具体文件）。
4. 倒推 **key_links**（关键连接/接线：UI→路由、workflow→触发它的 API/动作、config→默认值+消费者）。
5. **可达性自检**：每个 must-have 是否有**具体路径**能达成？无路径(UNREACHABLE) → 改阶段划分。

### 4.3 依赖 + 波次（depends_on / wave）

> 这是 `gsd-plan-phase` 的独有贡献：把阶段排成**可并行的波次**，而不是一根串行长链。

- `depends_on`：本阶段需要哪些前置阶段先完成（按产物/接口依赖，不是按"感觉先后"）。
- `wave` 计算规则：

  ```
  for 每个阶段:
    若 depends_on 为空        → wave = 1
    否则                      → wave = max(所有依赖的 wave) + 1
  ```

- **隐式依赖**：若两阶段改动**同一文件**，强制后者进更晚 wave（同 wave 内不得有文件冲突）。
- **优先纵切（vertical slice）**：一个用户特性的 model+API+UI 切成一个阶段（可并行）>
  按层横切（所有 model→所有 API→所有 UI，被迫串行）。仅当确需共享地基时才横切。

每个阶段在 plan 里带上 `depends_on` 与 `wave`，供 build 阶段按波次推进。

---

## 5. 第二级：阶段 → 任务（task，三必填字段 + TDD 五步粒度）

蒸馏自 `gsd-plan-phase` 的 **Anti-Shallow** 任务模板 + `writing-plans` 的 **TDD 五步粒度** +
`planner-antipatterns` 的具体化对照。

### 5.1 任务三必填字段（Anti-Shallow）

每个任务**必须**有这三个字段（缺一即不合格的"浅任务"）：

| 字段 | 含义 | 好 vs 坏 |
|---|---|---|
| **read_first** | 执行前必读的文件/上下文（精确路径，含行号区间更好） | 好：`src/auth/jwt.py:1-40, .sdlc/spec.md#auth`；坏：「相关文件」 |
| **acceptance_criteria** | **必可验证**的完成判据（命令 + 期望输出，或可观察状态） | 好：`pytest tests/test_login.py::test_401 -q` 期望 PASS；有效凭据返回 200+cookie，无效返回 401。坏：「能登录就行」 |
| **action** | 具体实现指令，**含具体值**（路径、库、参数、为什么避开某选择） | 好：「新建 `POST /api/login` 收 {email,password}，用 bcrypt 比对 User 表，返回 jose 签发的 JWT(15min) 进 httpOnly cookie。**不用 jsonwebtoken**——Edge runtime 的 CommonJS 问题」。坏：「加上认证」 |

> 另带：**files**（精确创建/修改路径）。三字段里的 action 即等价 gsd 的 `<action>`，
> acceptance_criteria 合并了 gsd 的 `<verify>`(自动化命令) + `<done>`(可测完成态)，read_first 合并 `<files>` 的读侧。

**具体化测试**：换一个全新上下文的 Claude/工程师，**能不能不问问题就执行这个任务？** 不能 → 加细节。

### 5.2 TDD 五步粒度（代码型任务）

> 蒸馏自 `writing-plans`。**每步是一个动作（2–5 分钟）**，代码步必须**贴真实代码**，不许"类似上面"。

对能写出 `expect(fn(input)).toBe(output)` 的任务（业务逻辑/接口契约/数据转换/校验/算法/状态机），
拆成五步：

```
- [ ] Step 1: 写失败的测试    （贴出真实测试代码）
- [ ] Step 2: 跑测试确认失败  （贴出命令 + 期望 FAIL 信息）
- [ ] Step 3: 写最小实现      （贴出真实实现代码）
- [ ] Step 4: 跑测试确认通过  （贴出命令 + 期望 PASS）
- [ ] Step 5: 提交            （贴出 git add/commit 命令）
```

非 TDD 任务（UI 布局/样式、纯配置、胶水代码、一次性脚本、无业务逻辑的简单 CRUD）：
不强求五步，但仍要满足三必填字段 + No-Placeholder。

### 5.3 任务定大小（context 预算，不用时间估）

| 信号 | 处置 |
|---|---|
| 触及 0–3 文件 / 纯配置接线 | 偏小——可与相邻任务合并 |
| 触及 4–6 文件 / 新子系统 | 正合适 |
| 触及 7+ 文件 / action 超过 1 段 / 多个互不相关 chunk | 太大——拆成两个任务 |

接口优先排序：一个阶段内若新建被后续任务消费的接口 →
**先定契约（类型/接口/导出）→ 中间实现 → 最后接线**，避免执行者满仓库找契约。

### 5.4 任务级红线（No-Placeholder + 反缩水）

`action` 里**禁止**出现：
- `TBD / TODO / 待定 / 实现细节后补 / fill in later`
- `加适当的错误处理 / 加校验 / 处理边界情况`（不写具体怎么处理）
- `给上面写测试`（不贴真实测试代码）
- `类似任务 N`（要重复贴代码——执行者可能乱序读任务）
- 引用任何**没在任一任务里定义过**的类型/函数/方法
- **缩水语言**：`v1 / 简化版 / 先静态写死 / 先 hardcode / 后续阶段再动态 / 占位 / 最小实现`

若某阶段确实太复杂塞不下 → **建议拆阶段**（回 §4），而不是悄悄把 action 缩水。

---

## 6. 出口门控：Source Audit + Coverage Gate（双向追溯）

> 蒸馏自 `planner-source-audit` + `writing-plans` 自查三扫。**plan 写完不等于完成**，必须过这道门。

### 6.1 Source Audit（正向：spec 每条 → 有任务覆盖）

逐条扫 spec 的每个来源，列一张审计表：

```
SOURCE     | ID     | 需求/决策                    | 覆盖任务 | 状态     | 备注
---------- | ------ | --------------------------- | -------- | -------- | ----
GOAL       | —      | <spec 的总目标>             | T1-T3    | COVERED  |
REQ        | R-01   | OAuth 登录(Google+GitHub)   | T2       | COVERED  |
REQ        | R-02   | 邮箱验证流                  | NONE     | ⚠MISSING | 无任务覆盖
DECISION   | D-01   | 用 jose 签 JWT              | T2       | COVERED  |
EVAL-CRIT  | E-01   | 答案准确率 ≥0.85(若有AI工作) | T5       | COVERED  |
```

四类来源都要扫：**GOAL**(spec 总目标) / **REQ**(每条需求) / **DECISION**(每个决策 D-xx) /
**EVAL-CRIT**(spec 阶段为 AI 工作定的 rubric/数据集/阈值——若适用，必须落进一个 validate(eval-bench) 相关任务)。

**不算 gap 的**（不要误报 MISSING）：spec 里明确标 Deferred/未来/超范围的项。

**任一行 ⚠MISSING → 不静默定稿**，回 text_mode 上报，让用户处置：

```
⚠ Source Audit：发现未被任何任务覆盖的需求：
  1. REQ R-02 邮箱验证流（来自 spec 的 "认证" 节）
     处置：
       A) 加一个任务覆盖它
       B) 拆阶段：移到子阶段
       C) 显式 defer：加入 backlog（需你确认）
回复 "条目-选项"（如 "1-A"）。
```

### 6.2 Coverage Gate（反向：每个任务 → 指回某需求）

反向扫每个任务：它的 `requirements` 字段必须**非空**，指回 spec 的某需求/决策 ID。
有任务指不回任何需求 → 要么它是多余的（删），要么 spec 漏了该需求（回 sdlc-spec 补）。

### 6.3 自查三扫（writing-plans，定稿前自己跑）

1. **Spec 覆盖扫**：spec 每节能指到一个任务吗？列出 gap → 补任务。
2. **占位符扫**：搜 plan 里的 §5.4 红线词 → 全部修掉。
3. **类型一致扫**：后面任务用到的类型/方法签名/属性名，与前面任务里定义的一致吗？
   （Task 3 叫 `clearLayers()`、Task 7 写成 `clearFullLayers()` 就是 bug）→ 修。

发现问题就地修，无需重审。spec 有需求无任务 → 加任务。

**三扫 + Source Audit 全 COVERED + Coverage Gate 全指回 → 才算 plan 完成，可写出 plan.md。**

### 6.4 用户确认 gate（呈现定稿 plan）

三扫全过、`plan.md` 写出后，向用户呈现定稿请其确认——提示里**必须含「网页审」那一行**（一次性告知义务，别让用户自己去发现有这条路）：

```
实现计划已写入 `<path>`（N 个阶段 / M 个任务）。请你过一眼，
有要改的告诉我；没问题我就进入 sdlc-build 开始 TDD 实现。
（plan 阶段多/任务多，逐条聊批太累？说「网页审」，我渲染成可划词批注的本地网页让你标。）
```

> **不得**以"默认聊天确认更快 / plan 简单"为由省略括号那行——选不选归用户，不点即默认 text_mode 聊天确认。要改 → 改完**重跑 §6.3 三扫**，再回本 gate。**只有用户确认后才前进。**

**可选 · 网页划词批注复核（机制说明）**：plan 阶段多、任务多、聊天逐条对太累时，可把 plan.md 渲染成「划词加批注」的本地网页让用户标注，再统一改回——见 `references/web-review/playbook.md`。（呈现定稿 plan 时硬性带出「网页审」选项的纪律见 §6.4；本段只补它的机制与适用面。）它只升级"意见怎么喂回来"的机制，不改"最终 plan 确认"的纪律。默认走 text_mode 聊天确认；用户说"网页审/划词批注"才用。需要**实时双向**（提交即自动回流、改完页面自刷新、跨引擎）→ 同 playbook §6 Live mode。

---

## 7. 读写哪些 .sdlc/ 文件

| 文件 | 读/写 | 说明 |
|---|---|---|
| `.sdlc/spec.md` | **读** | 唯一输入：已批准的 spec（需求/决策/eval 标准） |
| `.sdlc/PROFILE.md` | **读** | 取 surface-map（§2 预解析）、技术栈、测试命令（写进任务 acceptance_criteria 的命令要用 PROFILE 里登记的 runner） |
| `references/role-routing.md` | **读** | §2 路由解析规则（不内联，调用其 §1 算法） |
| `.sdlc/plan.md` | **写** | 本 skill 的主产物（§5 schema），单写者 |
| `.sdlc/STATE.md` | **写** | 经 driver 回写：stage/gates/active roles/modes/changed-files/decisions/next（§8），单写者 |

> 注：本设计用**单一 `.sdlc/plan.md`** 承载"阶段(含依赖)→任务(含三字段)"两级，
> **不**生成 gsd 的 `.planning/phases/*/NN-PLAN.md` 多文件结构（已剥离运行时目录依赖）。

### plan.md schema（产物格式）

```markdown
# Plan: <feature/topic>

> 来源 spec: .sdlc/spec.md（已批准）
> 复杂度等级: L2 —— 理由: <一句话>
> 生成: <由 caller 传入的时间戳，本 skill 不自造时钟>

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | <名> | R-01,R-03 | — | 1 |
| P2 | <名> | R-02 | P1 | 2 |

---

## Phase P1: <名称>

**目标**: <结果，不是任务>
**覆盖需求(traceability)**: R-01, R-03, D-01
**depends_on**: []   **wave**: 1
**为什么这样拆**: <理由（planner-breakdown 要求每个拆分附理由）>

**must_haves（目标倒推）**:
- truths(可观察行为): <3–7 条用户视角>
- artifacts(必存文件): <具体路径>
- key_links(关键接线): <UI→路由 / workflow→触发 / config→默认值+消费者>

**可观察成功标准**: <用将来会跑的验证手段表述：e2e:Web 旅程 / OpenAPI 端点断言 / eval-bench 指标≥阈值 / 覆盖率≥X%>

### Task P1-T1: <动作名>
- **requirements**: R-01            # 反向追溯，必填非空
- **files**: <精确创建/修改路径>
- **read_first**: <执行前必读：路径#锚点 或 路径:行号区间>
- **action**: <含具体值的实现指令；含要避开什么 + 为什么>
- **acceptance_criteria**: <命令 + 期望输出 / 可观察完成态>

<!-- 代码型任务用 TDD 五步展开（§5.2），每步贴真实代码/命令 -->
- [ ] Step 1: 写失败测试 …（真实测试代码）
- [ ] Step 2: 跑测试确认 FAIL …（命令 + 期望）
- [ ] Step 3: 写最小实现 …（真实实现代码）
- [ ] Step 4: 跑测试确认 PASS …（命令 + 期望）
- [ ] Step 5: 提交 …（git 命令）

### Task P1-T2: …

---

## Phase P2: …（depends_on: P1, wave: 2）

---

## Source Audit（出口门控，§6.1）
<四类来源审计表，全部 COVERED>

## 风险 / 关键决策点
<L3+ 时列；进入下一阶段前需确认的决策>
```

---

## 8. 写什么进 HANDOFF（由 driver 写 STATE）

plan 定稿、双向追溯全过后，输出 `## HANDOFF` block，**经由 driver** 写回 `.sdlc/STATE.md`
（driver 单写者；并行产物各写各文件）。独立直调时先产同一 HANDOFF，再作为单写者应用到 STATE：

- `stage: plan`，`status: in-progress`（若有 MISSING 未决 → `gated`；被外部缺口阻塞 → `blocked`）。
- `validate-modes: [...]`：§2 预解析出的模式快照（仅交接/审计，不当权威源）。
- **Gates passed**：勾选 `- [x] plan：plan.md 已拆分（阶段含依赖、任务含三字段）`。
- **Active roles (from last diff scan)**：§2 预解析出的角色快照。
- **Changed-files snapshot**：§2 取到的改动/目标 surface 路径。
- **Decisions log**：追加本次复杂度定级理由 + 任何 spec 歧义/MISSING 的处置结论。
- **Next action**：`-> invoke sdlc-build`（按 wave=1 的阶段开干）。

> 时间戳由 caller 传入，本 skill **不自造时钟**。

---

## 9. 一次完整规划的动作清单（checklist）

1. [ ] 验入口条件：spec.md 存在且已获批（§0），否则停并 text_mode 引导
2. [ ] 可移植前置：text_mode + Task-or-sequential 探测（§1）
3. [ ] 入口预解析：`git diff`/目标 surface → 调 role-routing 算 active roles + modes + 漂移检测（§2）
4. [ ] 复杂度定级 L1–L4 + 写理由（§3）
5. [ ] 第一级拆阶段：五准则 + must_haves 目标倒推 + depends_on/wave 波次（§4）
6. [ ] 第二级拆任务：三必填字段 + TDD 五步粒度 + 任务大小 + No-Placeholder（§5）
7. [ ] 出口门控：Source Audit（正向全 COVERED）+ Coverage Gate（反向全指回）+ 自查三扫（§6）
8. [ ] 写 `.sdlc/plan.md`（§7 schema，单写者）
9. [ ] 输出 `## HANDOFF` 并经 driver 写回 `STATE.md`：gates / roles / modes / changed-files / decisions / next（§8）
10. [ ] 向用户报告：复杂度等级 / 阶段数与波次 / 下一步（-> sdlc-build）

---

## 10. 边界与不做什么

- **不做需求讨论 / questioning** —— 那是 sdlc-spec。spec 当锁定输入；有歧义按 §6 MISSING 上报。
- **不写代码、不跑测试、不做 review** —— 那是 sdlc-build / sdlc-validate / sdlc-review。
- **不缩水 scope** —— 太复杂就建议拆阶段，绝不把 action 写成 "v1/先静态"。
- **不内联 role-routing 整张表** —— 调用 `references/role-routing.md` 解析，保持单一事实源。
- **不依赖运行时** —— 无 gsd-tools.cjs / Task 必需 / `.planning/` 目录 / AskUserQuestion；纯文件 + git + text_mode。
