# 蒸馏回路（Distillation Loop）—— "时用时新"

> 蒸馏自 `sop-extractor`（逆向提炼方法）+ `kb-manage`（编译式知识维护：ingest / 交叉引用 / lint / 防孤儿）+ `explorer-repo-report`（分类驱动的深读策略）。
>
> 这份 playbook 是 **数据，不是 skill**。任何引擎（Claude + Read/Edit/Bash/Grep，或 Codex）都能照着执行，不依赖任何运行时工具。

---

## 0. 核心理念

sdlc-pilot 的知识（角色卡 / stage playbook / validate-mode playbook）不是一次写死的常量，而是 **被编译、可增长的资产**。每当我们用 Coding Agent 期间分析了一个新的 skill 或 repo，就把其中可复用的方法蒸馏出来，**追加进我们已有的卡片**，而不是新建散落的文件。

借用 `kb-manage` 的 LLM-Wiki 洞察：**知识应该被编译（compiled）一次、多次复用，而不是每次重新检索（retrieved）。** 我们的 `references/` 就是这个 wiki —— 交叉引用已经在那里，矛盾已经被标记，方法已经综合好。每吸收一个源，它就丰富一点。

借用 `sop-extractor` 的逆向洞察：**别人的 skill / agent 人格里隐含了一套工作决策逻辑**（什么阶段做什么、什么条件走什么分支）。蒸馏就是把这套隐含逻辑显式化、去人格化、落进我们的卡片。

一句话目标：**让 `references/` 永远是"我们理解过、能直接执行"的版本，且随使用越来越厚。**

---

## 1. 何时触发（Triggers）

蒸馏是**人引导、按需触发**的（对齐 `kb-manage` 的"不自动归档，让用户决定"原则）。下列场景应主动提示"要不要蒸馏进 sdlc-pilot？"：

| 触发场景 | 信号 | 典型来源 |
|---|---|---|
| 调研了一个新 skill / repo | 刚跑完 `explorer-repo-report`、读了别家 SKILL.md、clone 了一个 agent 框架 | GitHub repo、`~/.claude/skills/<name>/`、agency-agents |
| 实战中发现更好的做法 | 某次 build/validate/review 里临场想出的检查清单、修复套路、踩坑 | 当前 session 的洞察 |
| 现有卡片暴露缺口 | review/validate 时发现"这条我们的卡没覆盖"、漏判了某类问题 | 失败复盘 |
| 新增语言 / 框架 / 模态 | 第一次碰到 Go / Rust / 移动端 / 新 E2E 工具 | 新项目接入 |
| 用户明确要求 | "把这个 pattern 蒸馏进来"、"沉淀到 sdlc"、"distill 这个" | 显式指令 |

> 不触发的情况：纯一次性脚本、与 SDLC 流程无关的领域知识（那应去 `kb-manage` 的通用知识库）、未经验证就想记的"猜测"（对齐"先验证再记录"）。

### 1.1 来源②：从自己跑过的 loop 复盘提炼（retro,蒸馏自 `session-miner` + `retro` + `orchestrator-flow-reflect`）

除了"分析外部新 skill",还应**从本系统自己的运行中学习**:

- **触发**:`STATE.stage=done`(一个 feature 走完整 loop 收口)后,或 build 调试 3-strike 后 → 可选跑一段轻量 retro。
- **★硬门(必须)**:**只有这个 session 真正跑过 sdlc loop 才提炼** —— 即 `STATE` 存在且 `stage` 至少到过 build/validate/review(完成或接近完成一个 feature)。半截/中断/没走流程的 session **不提炼**(否则是噪声 learning,污染卡片)。这等于"带 sdlc 上下文的 session-miner",而非泛挖任意会话。
- **提炼什么**:这次哪个 pattern 反复出现 / 哪里绊住了 / 哪类问题我们的卡没覆盖 / 哪个修复套路值得固化。
- **去向**:追加进对应角色卡的"常见翻车"/检查清单、或 validate-mode、或路由规则,标 `distilled-from: session:<topic>-<date>`(见 §123 溯源)。仍走 §2 的两轴定位 + §4 防孤儿。

---

## 2. 蒸馏流程（5 步，借 sop-extractor 的管道形）

```
新 skill / repo / 实战洞察
    │
    ▼
① 深读源 ──── 用 explorer-repo-report 的分类深读思路，读完整 SKILL.md + references，不靠摘录
    │
    ▼
② 提炼 pattern ── 抽出"方法 / 检查清单 / 决策分支 / 状态机"，去掉运行时与人格 fluff
    │
    ▼
③ 定位归处 ──── 判断这条 pattern 属于哪个 stage / 角色卡 / validate-mode（一条可落多处）
    │
    ▼
④ 追加合并 ──── 借 kb-manage 的合并规则写进目标卡片：保留旧内容、标矛盾、不新建散文件
    │
    ▼
⑤ 标记溯源 ──── 在目标卡 frontmatter 的 distilled-from 追加 <源名>；防孤儿自检
```

### ① 深读源（用 explorer-repo-report 的思路）

- **读完整，不读摘录。** 至少读目标的整篇 SKILL.md + 它引用的 references。对照 `explorer-repo-report` 的 P0→P2 优先级：先 README/SKILL.md（定位），再目录结构（模块划分），再关键源码（实现细节）。
- **先分类，再定深读维度。** 沿用 explorer 的类型判断：是 *工程项目* / *agentic 项目* / *通用工具* —— 不同类型值得抽的东西不同。对 sdlc-pilot 我们额外问一句：**"这个源对应我们哪个 stage / 角色 / validate-mode？"**
- **识别并丢弃噪声**（源地图已点名的固定模式）：
  - gstack 源的 ~700 行 runtime preamble（telemetry / gbrain / artifacts-sync / gstack 二进制）→ 整段丢。
  - GSD 源对 `gsd-tools.cjs` / Task 子代理 / `.planning/` 目录 / AskUserQuestion 的依赖 → 蒸馏成纯文件 + git。
  - agency-agents 的 agent 人格（vibe / emoji / memory）→ 只取 mission / concerns，丢人格。

### ② 提炼 pattern（去运行时、去人格）

把源里**可复用的工作逻辑**显式化，目标产物是下面几类之一：

| pattern 类型 | 形态 | 落进哪种卡 |
|---|---|---|
| 方法 / 流程步骤 | 编号步骤、状态机、阶段闸 | stage playbook |
| 检查清单 | 关注点 / 检查项 / "好的样子" / "常见翻车" | 角色卡 |
| 决策分支 | "什么条件走什么分支"（sop-extractor 的条件树思路） | stage 或 validate-mode |
| 验证手法 | 具体的跑法、证据 schema、门控阈值 | validate-mode playbook |

**可移植铁律（必须执行）**：凡蒸馏出的 pattern，都要把运行时依赖降级为 **纯文件 + git + 基础工具**：
- AskUserQuestion → gsd 的 `text_mode`（纯文本编号列表让用户回数字）。
- Task 子代理并行 → gsd-map 的 `Task-or-sequential` 降级（探测有无并行能力，没有就串行 inline）。
- 任何二进制 / node 工具 → 等价的 `Read/Edit/Bash/Grep` 步骤。

> 若一条 pattern 离开它的运行时就不成立（例如纯粹是某二进制的调参），**不蒸馏**，记一句"该能力依赖 X，sdlc 暂不复刻"即可。

### ③ 定位归处（roles vs stages vs validate-modes）

按 §4.0 的两轴原则判断（spec 已定的边界）：

```
这条 pattern 是"视角/知识"还是"动作/流程"？
        │
   ┌────┴─────┐
   视角         动作
   │             │
   ▼             ▼
角色卡        是不是"一种验证"？
roles/<r>.md   ┌───┴───┐
              是       否
              │         │
              ▼         ▼
        validate-mode  stage 逻辑
        (correctness/  内联进 sdlc-<stage>/SKILL.md
         e2e/eval-bench)  (v1 无独立 stages/ 目录)
```

- **角色卡**（`roles/`）：某职能视角"在意什么"。无动作 → 检查清单 / 关注点。
- **stage 逻辑**（v1 **内联**在对应 `skills/sdlc-<stage>/SKILL.md`，无独立 `stages/` 目录）：某一步"我们怎么做"。有多步动作 → 进度、闸门、状态机。`stages/` 为未来拆分预留点。
- **validate-mode playbook**（`validate-modes/`）：某种验证手法。属于 correctness / e2e / eval-bench 三者之一 → 跑法 + 证据 + 阈值。
- **role-routing.md**：如果蒸出的是"什么改动该上什么角色/模式"的映射（新语言 glob、新模态），追加进路由表。

> 一条 pattern 可能落多处（如一个"安全审查"源 → server-dev 角色卡的检查清单 + review stage 的安全闸）。允许，但每处都要独立写清、独立标溯源。**禁止**为一条 pattern 新建一个游离文件 —— 必须挂进既有卡片体系。

### ④ 追加合并（借 kb-manage 的合并规则）

写进目标卡片时，照搬 `kb-manage` Step 4 的合并纪律：

1. **合并、不覆盖**：把新方法融进目标卡对应的 section（如角色卡的"检查清单"），保留有价值的旧内容。
2. **标矛盾、不裁决**：若新源与卡里已有说法冲突，在冲突处加 `<!-- CONFLICT: 旧:… / 新:…（源:<name>） -->`，不删旧内容，留给人决策。
3. **更新时间戳**：目标卡 frontmatter 的 `updated` 字段刷新为当天（stamp 由调用方传入，不要硬编造）。
4. **保持精炼**：卡片是门面不是仓库。一条 pattern 抽其精华（方法 / 判据），别把源全文糊进来。若确需保留长底稿，照 kb-manage 双层模型存到知识库的 `sources/`，卡里只留链接 —— **不要把长文塞进 references/**。
5. **交叉维护**：若这条 pattern 影响别的卡（如改了一个角色，路由表也得加 glob），顺手更新关联卡（kb-manage Step 5 的全局交叉思想）。

### ⑤ 标记溯源（distilled-from）

每张被改动的卡片，frontmatter 里维护一个 `distilled-from` 列表，**追加**本次源名（去重）：

```markdown
---
role: server-dev
triggers: [api/**, handlers/**, *.server.*]
distilled-from: [gsd-secure-phase, code-review, <new-source-name>]
updated: <stamp>
---
```

- 源名用稳定标识：内部 skill 用其 name（`gsd-secure-phase`）；外部 repo 用 `owner/repo`；实战洞察用 `session:<topic>-<date>`。
- stage / validate-mode playbook 没有 frontmatter 时，在文件顶部维护一行：
  `> distilled-from: gsd-plan-phase, writing-plans, <new-source>`
- 这行溯源是**审计与防孤儿的锚点** —— lint 靠它反查。

---

## 3. 产物去向（Where output lands）

| 蒸馏出的东西 | 落点 | 不该去哪 |
|---|---|---|
| 职能视角 / 检查清单 | `references/roles/<role>.md` | ❌ 新建顶层 skill |
| 流程步骤 / 阶段闸 | v1 内联进 `skills/sdlc-<stage>/SKILL.md`（`stages/` 为未来拆分预留，v1 暂空） | ❌ 散落 md |
| 验证手法 / 阈值 / 证据 schema | `references/validate-modes/{correctness,e2e,eval-bench}.md` | ❌ 新建 validate skill（验证永远是 mode，不是 skill） |
| 改动代码 → 角色/模式 的映射 | `references/role-routing.md` | — |
| 项目级架构事实（surface map） | 目标 repo 的 `.sdlc/PROFILE.md`（由 onboard 维护，不进 references） | ❌ references/ |
| 与 SDLC 无关的通用领域知识 | `kb-manage` 的 `~/Documents/nsync/ai_knowledge/` | ❌ sdlc references/ |

**反膨胀红线（对齐 spec §5.1）**：蒸馏**永远不新增顶层 skill**。家族边界恒为 **1 driver + 6 process skills**。所有增长都发生在 `references/` 的既有卡片里。验证类 pattern 一律进 validate-mode（数据），不graduate成 skill。

---

## 4. 防孤儿（Anti-orphan）—— 借 kb-manage 的 Lint

蒸馏最大的风险是**写了游离文件 / 断链 / 没人引用**。每次蒸馏完，跑一遍轻量自检（这是 `kb-manage` Lint 的 sdlc 化裁剪）：

| 检查 | 怎么查（Grep/Read） | 不通过的修法 |
|---|---|---|
| **无游离文件** | 新写的每个 `.md` 都必须被某处引用：被 `sdlc/SKILL.md` 或某 stage playbook 读到、或被 `role-routing.md` 指向 | 没人引用 → 要么挂进既有卡，要么删 |
| **溯源完整** | 被改动的卡都有 `distilled-from`（含本次源）；`grep -L "distilled-from"` 找漏标 | 补 `distilled-from` 行 |
| **路由闭环** | 新增/改名的角色卡、validate-mode 都在 `role-routing.md` 里有对应 glob 入口 | 角色存在但无 glob 触发 → 该卡是孤儿，补路由或说明"仅手动调用" |
| **反向引用** | `role-routing.md` 引用的每个角色/模式文件都真实存在 | 路由指向不存在的文件 → 断链，补文件或改路由 |
| **矛盾标记** | `grep -r "CONFLICT" references/` 列出待人决策的冲突，不自动裁决 | 汇总给用户 |
| **不空洞** | 新卡 / 新 section 不少于实质 5 行，不是占位符 | 补实质内容或不要写 |

> 自检遵循 kb-manage 的"LLM 不自动裁决矛盾"原则：发现冲突只标记 + 上报，由人定夺。

---

## 5. 端到端示例

> 场景：调研了 agency-agents 的 `engineering-data-engineer`，想充实 big-data 角色卡（v1 是 stub）。

1. **① 深读**：读完整 agent 文件，识别它是 agentic 人格 → 丢 emoji / memory / vibe，留 Medallion 分层 / data contract / lineage / CDC / 分区 这些 *concerns*。
2. **② 提炼**：抽成检查清单 pattern（"数据契约是否显式""分区键是否合理""有无 lineage 追踪""幂等回填"）—— 纯知识，无运行时。
3. **③ 定位**：是职能视角 → 落 `roles/big-data.md` 的"检查清单"与"常见翻车"两节；其中"data pipeline 改动该上 big-data + 可能 eval-bench"这条映射 → 落 `role-routing.md`。
4. **④ 合并**：把检查项融进 big-data 卡现有 section（stub 也保留），刷新 `updated`，无冲突则不加 CONFLICT。
5. **⑤ 溯源**：`distilled-from: [data-migration, msitarzewski/agency-agents:engineering-data-engineer]`。
6. **防孤儿自检**：big-data 卡被 `role-routing.md` 的 `*.sql / **/pipelines/**` glob 触发 ✅；溯源已标 ✅；无游离文件 ✅。

---

## 6. 与其他源的配合关系（一句话）

- `explorer-repo-report` 提供 **①深读** 的分类与优先级策略（read-as-report 的探索骨架）。
- `sop-extractor` 提供 **②提炼** 的逆向思路（把隐含决策逻辑显式化成条件分支 / 模板）。
- `kb-manage` 提供 **④合并 + ⑤溯源 + §4防孤儿** 的编译式维护纪律（ingest 合并规则、交叉引用、CONFLICT 标记、Lint 体检）。
- 三者合起来，让 `references/` 成为一个**永远在用、永远更新**的自有 SDLC 知识 wiki。
