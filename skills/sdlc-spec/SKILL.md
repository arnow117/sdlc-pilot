---
name: sdlc-spec
description: >
  SDLC 主线的 Explore + Spec 阶段（规格驱动 SDD）。把模糊点子收敛成获批的、可实现的规格，
  并在涉及 AI/模型/策略工作时【前置定义 eval 标准】（rubric / 数据集 / 阈值）供后续 sdlc-validate 执行。
  核心纪律：批准前不写任何代码（HARD-GATE）、一次只问一个问题、分节获批、给 2-3 个方案带取舍、
  spec 自检 + 双 gate（自检通过 + 用户复核）。产出落 <target-repo>/.sdlc/spec.md。
  触发于:用户说 "写 spec"、"做需求设计"、"这个功能怎么设计"、"开始 spec 阶段"、"sdlc spec"、
  "把这个点子定下来"、"我要做一个新功能（要走完整流程）"；也由 sdlc driver 在 stage=spec 时路由进来。
  本 skill 自己不写实现代码、不拆任务（那是 sdlc-plan）、不跑测试。它只产出获批的 spec.md（含 eval 契约）。
---

# sdlc-spec — Explore + Spec（规格驱动 / SDD）

把"想做点什么"变成一份**获批的、无歧义的、可被 sdlc-plan 直接消费**的规格。

> **铁律（HARD-GATE）**：在 spec 获得用户批准之前，**不写任何实现代码、不脚手架、不调用任何
> 实现类 skill**。无论需求看起来多简单——"简单"恰恰是未经检视的假设造成最多返工的地方。
> 规格可以很短（简单需求几句话即可），但**必须呈现并获批**。

> **本 skill 是导演交给的"收敛器"**：知识与状态全在纯文件里，引擎 = Claude + Read/Edit/Bash/Grep。
> 唯一的"下一步终态"是产出获批 `spec.md` 并把交接写回 STATE，由 driver 路由到 `sdlc-plan`。

---

## 0. 可移植前置（每次入口先做）

本 skill 必须在 Claude 和 Codex 下都能跑。两条降级范式贯穿全程：

### 0.1 交互降级 — text_mode（默认开）
凡向用户提问（澄清问题、方案选择、scope 确认、复核 gate），**默认用纯文本编号列表**，
不硬依赖 `AskUserQuestion`：

```
我需要你定一个点：
  1) 选项 A — 说明 / 取舍
  2) 选项 B — 说明 / 取舍
  3) 其它（你来描述）
回复编号即可（或直接打字补充）。
```

有 `AskUserQuestion` 时可以用它，但**回退路径必须是上面这种编号文本**。
若用户选"其它"且没填内容 → 输出一行 "你想补充什么？" 然后**停止生成、等待**，不要重问、不要自答。

### 0.2 并行降级 — Task-or-sequential
本阶段的"外部研究"（§3 可选）若需展开多源调研：探测有无 Task/并行能力——
有 → 可 fan-out 子调研，各写各的临时笔记；无（Codex/Gemini CLI 等）→ 串行 inline 跑同一 playbook。
**任何时候不得让两个写手同时写 `STATE.md` / `spec.md`**（单写者原则）。

---

## 1. 入口条件（entry）

进入本 skill 前应满足（由 driver 保证；独立调用时自检）：

| 条件 | 检查 |
|---|---|
| 有 `<target-repo>/.sdlc/PROFILE.md`，或确认是 greenfield | `ls .sdlc/PROFILE.md`；brownfield 缺 PROFILE 应先 `sdlc-onboard` |
| `STATE.stage` 为 `spec`，或这是一个全新特性的开始 | 读 `.sdlc/STATE.md`；无 STATE = 新特性，本 skill 会初始化一份 |
| 有一个待澄清的"点子 / 需求 / 变更意图" | 来自用户原话 |

入口动作：

```bash
ls -la <target-repo>/.sdlc/ 2>/dev/null      # 看有无 PROFILE / STATE / 既有 spec
```

- 读 `PROFILE.md` → 拿到技术栈、约定、surface-map（哪些模块/glob/默认角色/模式），作为 Explore 的地图。
- 读 `STATE.md`（若有）→ 看 `Decisions log` 里是否已有相关决策，**不要重复问已决的事**。

### 1.0 入口先做：改动代码 → 角色 + 模式 解析（role-routing）
即便 spec 阶段还没真正改代码，也要**先确定本特性"打算动哪块 surface"**，因为这决定了：
- 要不要在 spec 里**前置 eval 标准**（动 AI/模型/策略 → 必须，见 §5）；
- 后续 build/validate/review 会加载哪些角色卡、跑哪些 validate 模式。

做法（读 driver 的路由规则，不内联整张表）：

1. 读 `references/role-routing.md`（路由规则）+ `PROFILE.md` 的 surface-map。
2. 若已有改动：`git -C <target-repo> diff --name-only HEAD` → 按 `resolve(diff × surface-map × routing)` 算出预期 active roles / validate-modes。
3. 若全新、尚无改动：让用户用 text_mode 声明**本特性要动哪个/哪些 surface**（前端 / 移动 / API / AI 策略 / 数据管道），据此预取默认角色 + 模式。
4. **关键派生**：若解析出的 validate-modes 含 `eval-bench`（即触及 `models/ strategy/ prompt/ ai/ evals/` 等 AI 面）→ **本次 spec 必须包含 §5 的 eval 契约**。

把这个预解析结果记进本阶段的 STATE 快照（`validate-modes:` / `Active roles`），仅作交接提示，**不作权威源**（build/validate 会重算）。

---

## 2. 步骤流程（procedure）

按顺序执行。每一步都建议建一个 todo 项跟踪。这是 brainstorming 骨架 + hp-feature-dev 文档矩阵 + gsd discuss/research 的蒸馏，**已剥离** gsd-tools/.planning/Task-reviewer/visual-companion 依赖。

```
1 Explore（摸现状·三现状）
2 Scope guard（拆超大需求 / 防 scope creep）
3 Clarify（一次一问，澄清意图）
4 Approaches（2-3 方案 + 推荐 + 取舍）
5 Design（分节呈现，逐节获批）
6 Eval 契约（仅 AI/模型/策略工作：定 rubric/数据集/阈值）★ 净新建
7 文档矩阵 → 写 spec.md（+ 必要时 ADR）
8 Spec 自检（占位/矛盾/scope/歧义 四扫，就地修）
9 用户复核 gate（用户看过写好的 spec）
10 交接 → 写回 STATE，路由 sdlc-plan
```

### 2.1 Explore — 摸清现状（三现状）
不要急于提方案。先理解三件事（hp-feature-dev 的"三现状" + gsd-discuss 的 codebase scout）：

- **代码现状**：涉及哪些模块？现有类型/接口/数据流？用 `grep` + `find` 快速定位；范围 > 3 模块时按 §0.2 并行/串行展开。
- **文档现状**：有无相关 spec/ADR？是否过期？（看 `docs/specs/`、`docs/adr/`、`.sdlc/spec.md`）
- **测试现状**：有无覆盖相关路径的测试？（这会影响 plan/build 的 TDD 起点）

把发现浓缩成几句"现状摘要"，作为提问与方案的依据。

### 2.2 Scope guard — 防爆量 / 防漂移
- **拆超大需求**：若需求描述了多个独立子系统（"建一个带聊天+存储+计费+分析的平台"），**先 flag 并分解**，不要在一个需注定要拆的项目上耗费澄清问题。每个子项目各走一遍 spec→plan→build。
- **防 scope creep**（gsd-discuss 的 scope_guardrail）：澄清阶段只澄清"**怎么实现已在范围内的东西**"，不引入新能力。用户提的新能力 → 记进 spec 的 **Deferred Ideas** 区，不丢失、不就地实现：

  ```
  「X」是一个新能力——它该是自己的一个特性/阶段。
  我先把它记进 Deferred，本次聚焦在【当前特性域】。
  ```

### 2.3 Clarify — 一次一问（核心纪律）
- **一条消息只问一个问题**。一个话题需要多问就拆成多条。不要一次轰炸多问。
- **优先多选**（text_mode 编号列表），开放式也可。
- 聚焦：**目的 / 约束 / 成功标准**。
- **你是 builder，用户是 visionary**（gsd-discuss 哲学）：问"愿景与实现选择"，**不要问**用户：代码库模式（你自己读代码）、技术风险（你识别）、实现路径（plan 决定）、成功度量（从工作推断）。
- **gray-area 要具体化**（gsd-discuss）：**禁用泛标签**（"UI/UX/行为"）。生成针对本特性的具体灰区：
  - "用户认证" → 会话处理 / 错误响应 / 多设备策略 / 找回流程
  - "整理图库" → 分组依据 / 重复处理 / 命名约定 / 文件夹结构
- **空答处理**（gsd-discuss）：回答为空 → 重问一次；仍空 → 用纯文本编号列表请用户输入编号。绝不带着空答继续。

### 2.4 Approaches — 2-3 方案
- 永远先提 **2-3 个不同方案**，带取舍，**领头给你的推荐 + 理由**。
- 对话式呈现，让用户做决策（不是你替他定）。

### 2.5 Design — 分节呈现，逐节获批
- 自认为理解了再呈现设计。**每节按其复杂度伸缩**：直白的几句话，微妙的可到 200-300 字。
- 覆盖：架构 / 组件 / 数据流 / 错误处理 / 测试策略。
- **每节问一句"到这里对不对？"**，获批再继续（incremental validation）。某节不对就回头澄清。
- **为隔离与清晰而设计**（brainstorming）：拆成单一职责、接口清晰、可独立理解与测试的小单元；每个单元能答"它做什么 / 怎么用 / 依赖什么"。
- **在既有代码库里工作**：先探索现有结构、沿用既有模式；只对"影响本次工作的既有问题"做定向改进，**不提无关重构**。

### 2.6 Eval 契约（★ 仅当本特性触及 AI/模型/策略）
见 §5。这是所有蒸馏源都缺的**净新建**：AI 工作的质量标准**必须在 spec 阶段定死**，由后续 `sdlc-validate` 的 `eval-bench` 模式执行。非 AI 特性跳过本步。

### 2.7 文档矩阵 → 写 spec.md
用 hp-feature-dev 的**文档选择矩阵**决定写什么、写哪：

| 变更类型 | 写什么 | 放哪里 |
|---|---|---|
| 核心数据结构变更、模块拆分合并、API 契约变更 | **ADR** | `docs/adr/`（同时在 spec 里引用） |
| 用户可感知的功能变更（页面 / 流程 / 交互） | **Spec** | `.sdlc/spec.md`（主产物） |
| 局部实现细节、UI 微调 | 更新已有文档 | 找到对应 spec 追加/修订 |
| 纯 bug fix（行为不变） | 不改文档 | —（且更可能该走 hp-bugfix / sdlc-build 调试子循环） |

主产物始终是 `<target-repo>/.sdlc/spec.md`（统一格式，见 §4）。涉及架构变更时**额外**写一份 ADR 并在 spec 里链接。

### 2.8 Spec 自检（写完后用新视角扫一遍，就地修）
1. **占位扫描**：有 "TBD/TODO"、空节、模糊需求？→ 补全。
2. **内部一致**：各节是否互相矛盾？架构是否与功能描述对得上？
3. **scope 检查**：是否聚焦到一个实现计划可承载？还是需要分解？
4. **歧义检查**：任何需求能被两种解读？→ 挑一种、写明确。

就地修完即可，不必再 review 一轮。

### 2.9 用户复核 gate
自检通过后，请用户复核**写好的 spec 文件**：

```
Spec 已写入并（如适用）提交到 `<path>`。请你过一眼，
有要改的告诉我；没问题我就进入 sdlc-plan 出实现计划。
```

等待用户响应。要改 → 改完**重跑 §2.8 自检**。**只有用户批准后才前进**。

### 2.10 交接
见 §6（写回 STATE，路由 sdlc-plan）。

---

## 3. 分级 Explore（合并三处"探索"，外部研究可选）

源地图指出三处"探索"职责重叠，本 skill 合成一条**分级 Explore**（轻→重，按需升级）：

| 级别 | 做什么 | 何时用 | 蒸馏自 |
|---|---|---|---|
| L1 本地三现状 | grep/find 摸代码/文档/测试现状（§2.1） | **总是** | hp-feature-dev Explore |
| L2 轻量 scout | 在现状基础上识别 gray areas、可复用资产、决策点 | 需求有多种实现走向时 | gsd-discuss scout |
| L3 有界外部研究（可选） | 调 unknown-unknowns：标准架构模式 / 标准技术栈 / 常见坑 / **Don't-Hand-Roll**（哪些不该手搓）/ SOTA vs 训练直觉 | 引入不熟的技术 / 第三方依赖 / 新框架时 | gsd-research-phase |

**L3 关键提问**（gsd-research）：核心问题不是"该用哪个库"，而是"**我不知道自己不知道什么**"。
研究产出要**规定性**（"用 X"），不是探索性（"可考虑 X 或 Y"），并附 **confidence 分级**（高/中/低，关键论断多源核实）。

**L3 可移植化**：剥掉 gsd 的 Task 子代理 / `.planning/RESEARCH.md` / context7 硬依赖——
有并行能力就 fan-out 子调研，没有就串行；研究结论**直接并入 spec 的"技术约束 / Don't-Hand-Roll"节**，不另起运行时产物。

---

## 4. 读写哪些 .sdlc/ 文件

| 文件 | 读 / 写 | 内容 |
|---|---|---|
| `.sdlc/PROFILE.md` | **读** | 技术栈 / 约定 / surface-map（Explore 地图、路由输入）。本 skill 不写 PROFILE。 |
| `.sdlc/STATE.md` | **读 + 写**（经 driver，单写者） | 读 Decisions log 防重问；写回 stage/gates/decisions/next（§6） |
| `.sdlc/spec.md` | **写（主产物）** | 统一格式见下 |
| `docs/adr/*.md` | **写（条件）** | 仅架构变更时；spec 内链接 |

### 4.1 统一 spec.md 格式（收编五套异构产物）
源里有 brainstorming design-doc / hp spec+ADR / gsd CONTEXT.md 五套异构格式，本 skill 统一成一份：

```markdown
# Spec: <feature/topic>

> Date: <由 caller 传入的日期>
> Status: draft | approved
> Target surface(s): <web-frontend / api / ai-strategy / ...>  # 来自 §1.0 路由解析
> Active roles (anticipated): <server-dev, qa, ...>
> Validate modes (anticipated): <correctness, e2e(Web), eval-bench, ...>

## 1. 问题 / 目标
为什么做？要达成什么用户/业务结果？

## 2. 非目标（YAGNI）
明确不做什么，防 scope creep。

## 3. 现状摘要（Explore 产出）
代码 / 文档 / 测试三现状的浓缩。

## 4. 方案与决策
选了哪个方案、为什么（含被否方案的取舍）。架构变更链接到 ADR。

## 5. 设计
架构 / 组件 / 数据流 / 错误处理 / 测试策略（逐节获批后的最终版）。

## 6. 怎么算 done（前置验收）
在改任何代码前就对齐的验收标准 + 验证命令（喂给 sdlc-plan / sdlc-validate）。

## 7. Eval 契约（仅 AI/模型/策略工作；否则写"N/A"）
见 §5 —— rubric / 数据集 / 阈值 / 测量法 / guardrail-vs-flywheel。

## 8. Deferred Ideas（结构化延后）
被挡下的 scope creep / 大点子。每条带 Why + Trigger（何时再捡起）+ Breadcrumbs（相关文件/决策）。

## 9. Canonical refs（强制累积）
本特性依赖/参考的源文件、文档、外部资料路径（gsd-discuss 的 canonical_refs：每轮讨论持续累积，不丢线索）。
```

> **结构化 deferral**（gsd-plant-seed 蒸馏）：Deferred 不是一句话扔进角落没人看，而是带
> **Why（为什么重要）+ Trigger（什么条件下再做）+ Breadcrumbs（去哪找细节）**，避免 context rot。

---

## 5. ★ Eval 标准前置（净新建：AI 工作在 spec 阶段定质量门）

**所有蒸馏源都没有这一节**——这是 sdlc-pilot 的真活。当 §1.0 路由解析出 `eval-bench` 模式
（即本特性触及 `models/ strategy/ prompt/ ai/ evals/ agents/` 等 AI 面），**spec 必须把 AI 的质量标准
在动代码前定死**，后续 `sdlc-validate` 的 `eval-bench` 模式据此执行。蒸馏自 `ai-evals.md` + `gsd-eval-review`。

### 5.1 为什么必须前置
AI 系统**非确定性**：同样输入不保证同样输出。单测/集成测不足以判 AI 工作"够不够好"。
质量标准若不在 spec 阶段定，到 validate 阶段就会临时拍脑袋——这正是源地图点名的最大缺口之一。

### 5.2 spec 里要写清的 5 件事（→ §4.1 的"Eval 契约"节）

1. **系统类型 + 关键失败模式**：这是什么 AI 系统（RAG / 对话 / 结构化抽取 / 多步 agent / 分类）？
   列 **3-5 个绝不能出错的行为**（决定主导 eval 维度）。
2. **测量法**（三选优先级，可组合）：
   - **代码指标优先**（确定性：JSON 合法、必带免责声明、性能阈值、分类 flag）——快/便宜/可靠，先用这个。
   - **LLM judge**（主观质量：语气/推理/升级判断）——**必须先用人工校准过**才可信。
   - **人工评估**（金标准，不可规模化）——用于校准、边缘、抽样、高风险。
3. **rubric**（每个被测维度必须有）：
   - 测的维度名；
   - 1 / 3 / 5 分（或 pass/fail）各代表什么——**领域特化，不要泛指标**（"helpfulness"在房产=清晰总结房源，在医疗=知道何时**不**回答）；
   - 可接受 vs 不可接受 的领域示例。
   没有 rubric，LLM judge 只产噪声不产信号。
4. **reference dataset**：起步 **10-20 个高质量样本**（不是 200 个平庸的）；覆盖关键成功场景 / 常见工作流 / 已知边缘 / 历史失败模式；最好由领域专家标注。写明数据集**存放位置**（供 validate 读取）。
5. **阈值 + verdict 规则**（gsd-eval-review）：各维度加权 + 通过阈值（如"加权分 ≥ 4.0/5 且无任一维度 < 3 才算过"）；并区分 **guardrail（出错即灾难→在线实时拦截）vs flywheel（不灾难→离线批量驱动迭代）**。

### 5.3 spec→validate 契约接口
在 spec 的 Eval 契约节里**显式写明三个位置**，让 `sdlc-validate/eval-bench` 无歧义读取：
- rubric 定义在哪（spec 本节 / 独立文件路径）；
- reference dataset 在哪（路径）；
- 阈值/verdict 规则是什么。

> 这就是"标准在 spec 定、执行在 validate 做"的契约——validate 不需要回放讨论历史即可执行评估。

---

## 6. 出口门控（exit gates）+ 写回 STATE

### 6.1 出口门控（双 gate，全过才离开本阶段）
- [ ] **HARD-GATE 守住**：批准前未写任何实现代码。
- [ ] **设计逐节获批**：每节都拿到用户确认。
- [ ] **spec.md 已写**，格式符合 §4.1，无占位（§2.8 自检通过）。
- [ ] **若 AI 工作**：§5 Eval 契约已填（rubric/数据集/阈值/契约位置齐全），否则该节写明 "N/A"。
- [ ] **用户复核 gate 通过**：用户看过写好的 spec 并批准（§2.9）。

任一未过 → `status: gated`，停在闸口，用 text_mode 列出待办项，**不前进**。

### 6.2 写回 STATE（经 driver，单写者）
spec 获批后，把交接写回 `<target-repo>/.sdlc/STATE.md`（schema 见 driver / STATE 模板；时间戳由 caller 传入）：

```markdown
# SDLC State: <feature/topic>
stage: spec
status: in-progress            # 或 gated（未过复核时）
updated: <caller 传入时间戳>
validate-modes: [correctness, e2e(Web), eval-bench]   # §1.0 预解析的快照（非权威，build 会重算）

## Gates passed
- [x] spec：spec.md 已获批（含 AI 工作的 eval 标准，若适用）
- [ ] plan：...

## Active roles (from last diff scan)
- <§1.0 预解析的 anticipated roles，例如 server-dev, qa>

## Changed-files snapshot
- <若已有 diff 则记；全新特性记 "(none yet — target surface: <surface>)">

## Decisions log
- <date> 选 <方案> 而非 <备选>，因为 <理由>
- <date>（若 AI 工作）eval rubric/数据集/阈值已在 spec §7 定义

## Next action
-> invoke sdlc-plan
```

写完向用户报告 stage / status / next，并据 status：
- `in-progress` → 提示可进入 `sdlc-plan`（或本会话直接续）。
- `gated` → 停在复核闸口，列出待批项。

---

## 7. 一次完整 spec 阶段的动作清单（checklist）

1. [ ] `ls .sdlc/` 读 PROFILE + STATE；读 Decisions log 防重问
2. [ ] §1.0 路由预解析：确定 target surface → 预取 roles/modes → 判定是否需要 Eval 契约
3. [ ] Explore 三现状（必要时升 L2/L3，§3）
4. [ ] Scope guard：拆超大需求 / 防 creep（creep 记 Deferred）
5. [ ] Clarify：一次一问，gray-area 具体化，空答重问
6. [ ] 提 2-3 方案 + 推荐 + 取舍
7. [ ] 分节呈现设计，逐节获批
8. [ ] 若 AI 工作：填 §5 Eval 契约（rubric/数据集/阈值/契约位置）
9. [ ] 按文档矩阵写 `.sdlc/spec.md`（+ 必要 ADR），统一格式（§4.1）
10. [ ] Spec 自检四扫，就地修
11. [ ] 用户复核 gate（看写好的 spec）→ 批准
12. [ ] 出口双 gate 全过（§6.1）
13. [ ] 写回 STATE（单写者，§6.2），报告 stage/status/next → 交给 driver 路由 sdlc-plan

---

## 8. 不要做的事（反模式）

- ❌ 批准前写实现代码 / 脚手架 / 调实现类 skill（违反 HARD-GATE）。
- ❌ 一条消息塞多个问题（违反一次一问）。
- ❌ 用泛标签（UI/UX/行为）当 gray area，不具体化。
- ❌ 替用户做愿景决策；或问用户技术风险/实现路径/成功度量（那些你自己定/识别）。
- ❌ 引入范围外的新能力（应记 Deferred，结构化延后）。
- ❌ AI 工作不定 eval 标准就放行到 plan（违反 §5 前置）。
- ❌ 把 Deferred 写成无人看的一句话（必须带 Why+Trigger+Breadcrumbs）。
- ❌ 并发写 STATE.md / spec.md（违反单写者）。
- ❌ 在本 skill 里拆任务 / 写测试 / 跑验证（那是 plan / build / validate 的活）。
