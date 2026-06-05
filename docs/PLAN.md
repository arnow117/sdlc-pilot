# sdlc-pilot — 建造蓝图（PLAN.md）

> Date: 2026-06-04 · 连接 spec → 蒸馏源地图 → 实际建造的工件
> 上游: `docs/specs/2026-06-03-sdlc-pilot-design.md`（设计 spec，scope locked §14）
> 上游: `docs/distillation-source-map.md`（每个目标的 canonical 源 + 取什么/补什么）
> 本文回答: **v1 要建哪些文件、各自蒸馏自哪、按什么依赖波次建、两个研究 spike 放在哪。**

---

## 0. 铁律回顾（每个文件都必须遵守）

1. **知识全落纯文件**；引擎 = Claude + 基础工具（Read / Edit / Bash / Grep）。每个文件都是可被任意 caller 直接读的 playbook，不依赖 Skill 调用机制。
2. **可移植（Codex 能跑）**：不硬依赖 Workflow / AskUserQuestion / subagent。
   - 交互 → gsd `text_mode`（AskUserQuestion 退化为**纯文本编号列表**）。
   - 并行 → gsd-map `Task-or-sequential` 降级（探测有无并行能力，没有就**串行**）。
3. **蒸馏方法论**：实读源地图点名的 canonical 源 skill，取方法/检查清单；**丢弃** runtime preamble、`gsd-tools.cjs`、`.planning/` 目录依赖、agent 人格（vibe/emoji/memory）。
4. **v1 语言范围 = Python + Web (TS)**；首个 dogfood = agentic-config-demo（`agentic-config-demo/`）。
5. 每个文件**中文为主、结构清晰、可直接执行**。
6. **反膨胀边界**：家族恒定为 **1 driver + 6 process skill**。验证流程（E2E / eval-bench）= validate 的**模式（数据 playbook）**，永不升级为顶层 skill。视角（role）= **知识卡（数据）**，不是 skill。

---

## 1. 文件清单总览（v1 全量）

> 仓库根 = `workspace/20260603-sdlc-pilot/skills/`（未来独立 GitHub repo）。
> 计数: **7 个 SKILL.md（driver+6）** + **5 角色卡** + **3 validate 模式** + **9 stage playbook** + **role-routing** + **distillation-loop** + **模板（PROFILE/STATE/spec/plan/报告）** + **README** + **2 研究 spike 占位**。

### 1A. Driver + 6 process skills（7 个 SKILL.md）

| # | 文件 | 角色 | 第一 canonical 源 | 移植要点 |
|---|------|------|------------------|---------|
| S1 | `skills/sdlc/SKILL.md` | driver / router / handoff | 自建（路由+分支逻辑）+ gsd-map `Task-or-sequential` | 读 `.sdlc/` → 分支 onboard/spec/resume；启动期 drift 检测 |
| S2 | `skills/sdlc-onboard/SKILL.md` | brownfield 入口 → PROFILE.md + surface map | `gsd-map-codebase`（+ `arch-aifriendly-doctor` bash 采证 / scoped 命令）+ `engineering-codebase-onboarding-engineer` | 4-focus → 纯文件角色卡；去 node/.planning |
| S3 | `skills/sdlc-spec/SKILL.md` | Explore + Spec（SDD；为 AI 工作定 eval rubric） | `superpowers:brainstorming`（+ `hp-feature-dev` 文档矩阵） | HARD-GATE；text_mode 替 AskUserQuestion；**eval 标准前置** |
| S4 | `skills/sdlc-plan/SKILL.md` | 拆 phase + task | `gsd-new-project` 五准则 + `gsd-plan-phase` 三字段/wave（+ `planner-breakdown-sdlc` L1-L4） | 去 gsd-tools；单技能内 spec→phase→task 两级贯通 |
| S5 | `skills/sdlc-build/SKILL.md` | Test-first(red) + Implement(green) | `superpowers:test-driven-development` + `systematic-debugging` | TDD↔调试统一状态机；去 subagent；语言无关 runner |
| S6 | `skills/sdlc-validate/SKILL.md` | 验证中枢（3 模式调度） | `verification-before-completion` + `verify` 阶梯 | 改动代码路由选模式；模式是 references 数据，不是子 skill |
| S7 | `skills/sdlc-review/SKILL.md` | 多角色 review + Verify | gstack `review` | 非交互/headless 变体；并行→串行降级；统一 severity+confidence |

### 1B. 5 角色卡（`skills/sdlc/references/roles/`）

> 格式见 spec §7（关注点/检查清单/好的样子/常见翻车/介入哪些阶段 + frontmatter）。
> 高产源: `~/.claude/skills/gstack/review/specialists/*.md`；补缺口: agency-agents（取 mission/concerns，丢人格）。

| # | 文件 | 覆盖 | 主源 | 补什么 |
|---|------|------|------|--------|
| R1 | `roles/server-dev.md` | 强 | `gsd-code-reviewer` 语言表 + `review/specialists/{performance,api-contract,security}.md` + `security-review` 10 域 | 统一 severity；裁人格 |
| R2 | `roles/qa.md` | 强 | `plan-eng-review` §3 test-coverage tracing + `review/specialists/testing.md` + red-team 心态 | E2E/EVAL/unit 决策矩阵接 validate |
| R3 | `roles/client-dev.md` | 中-强 | `flutter-dart-code-review` 范式 + JS/TS 表 + perf-frontend + 项目 `web/` 规则 + agency `engineering-mobile-app-builder` | **原生移动切片补厚**（offline-first/RN/Compose/Swift） |
| R4 | `roles/design.md` | 中 | `design-checklist.md` + 项目 `web/design-quality.md` + agency `design-ux-architect/-ux-researcher/-ui-designer` | **UX-flow/交互/IA 深度自建** |
| R5 | `roles/big-data.md`（**stub**） | 弱（净新建） | agency `engineering-data-engineer`（Medallion/data contract/lineage/CDC/分区）+ `database-optimizer` + `review/specialists/data-migration.md` | pipelines/数据倾斜/列存/幂等/回填 —— stub 起步 |

### 1C. 3 validate 模式 playbook（`skills/sdlc/references/validate-modes/`）

| # | 文件 | 触发 | 第一 canonical 源 | 补什么 |
|---|------|------|------------------|--------|
| M1 | `validate-modes/correctness.md` | always | `verification-before-completion` + `verify` 阶梯 + `qa` framework bootstrap + `gsd-add-tests` 三分类 + `gsd-validate-phase` 三态 | **数字化覆盖率门控**（行/分支 ≥X% fail）；非浏览器"真跑应用" smoke；统一证据 schema |
| M2 | `validate-modes/e2e.md` | 用户面 surface 改动 | **Playwright MCP** + `design-review` fix loop + `devex-review` 证据规范 + `browse` 命令语义 + `web-api-reverse-engineering`（OpenAPI 模态） | **App 移动模态（最大缺口）**；用户旅程启发式推导；OpenAPI **正向**用例生成；多模态统一编排 |
| M3 | `validate-modes/eval-bench.md` | **AI/模型/策略改动** | `ai-evals.md` + `gsd-eval-review` + `benchmark`/`benchmark-models` 双阈值 + `tb-run-analyzer` 有效性甄别 + `tb-task-operator` oracle/nop 自检门 | 真正"对 dataset 按 rubric 跑出质量分"的执行层；**spec→validate 契约接口**；非网页性能采集 |

### 1D. 9 stage playbook（`skills/sdlc/references/stages/`）

> 阶段 playbook = 各 process skill 的"瘦身可读副本"，被对应 SKILL.md 引用、也可被任意 caller 直接读（铁律 1）。每个含: 进入条件 / 过程 / 退出 gate / 写什么进 STATE。

| # | 文件 | 对应 skill | 蒸馏自 |
|---|------|-----------|--------|
| T0 | `stages/0-onboard.md` | sdlc-onboard | gsd-map-codebase 4-focus + arch-doctor bash 采证 |
| T1 | `stages/1-explore.md` | sdlc-spec（前半） | hp 本地三现状 + discuss scout + research 有界外部研究（分级 Explore） |
| T2 | `stages/2-spec.md` | sdlc-spec（后半） | brainstorming 骨架 + hp 文档矩阵 + **eval 前置** |
| T3 | `stages/3-plan.md` | sdlc-plan | gsd-new-project 五准则 + gsd-plan-phase 三字段/wave + L1-L4 |
| T4 | `stages/4-test-first.md` | sdlc-build（red） | superpowers TDD RED→Verify-RED + No-skip 铁律 |
| T5 | `stages/5-implement.md` | sdlc-build（green） | superpowers TDD GREEN→Verify-GREEN→REFACTOR + 调试四阶段 + hp-bugfix 三分类 |
| T6 | `stages/6-validate.md` | sdlc-validate | verify 阶梯 + 模式调度（指向 M1/M2/M3） |
| T7 | `stages/7-review.md` | sdlc-review | gstack review + gsd-code-review 深度分层 + gsd-secure-phase |
| T8 | `stages/8-verify.md` | sdlc-review（收尾） | verification-before-completion gate + review plan-completion 审计 |

### 1E. 路由 + 蒸馏循环（2 个）

| # | 文件 | 蒸馏自 |
|---|------|--------|
| X1 | `skills/sdlc/references/role-routing.md` | **净新建**（surface-map 路由是核心差异化，无源）；glob 字典参考 spec §6 表 + §4 surface map。v1 = Python + TS globs |
| X2 | `skills/sdlc/references/distillation-loop.md` | `explorer-repo-report` + `sop-extractor`；产出"分析新 skill → 提取模式 → append 到 stage/role/mode + 标 `distilled-from`" |

### 1F. 模板（`skills/sdlc/references/templates/`）

> 统一 schema（源地图缺口 #8）。每个是可复制骨架，含 frontmatter / 字段注释。

| # | 文件 | 契约出处 | 备注 |
|---|------|---------|------|
| P1 | `templates/PROFILE.md` | spec §4 surface map + §6.1 | 项目级长寿记忆；技术栈表带"原因"列 + 禁止事项（startup-claude-md-init schema） |
| P2 | `templates/STATE.md` | spec §8 | feature 级短寿 handoff；single-writer（铁律 2） |
| P3 | `templates/spec.md` | spec §5 + hp 文档矩阵 | 收编五套异构产物为统一格式；**含 eval criteria 段**（AI 工作） |
| P4 | `templates/plan.md` | gsd-plan-phase 三字段 + Plan Header | phase（depends_on/wave）+ task（read_first/acceptance_criteria/action） |
| P5 | `templates/e2e-report.md` | design-review 三联截图 + devex-review 证据规范 | `.sdlc/validate/e2e-<scope>-report.md` 骨架 |
| P6 | `templates/eval-report.md` | gsd-eval-review EVAL-REVIEW 模板 + 加权阈值 verdict | `.sdlc/validate/eval-<scope>-report.md` 骨架 |
| P7 | `templates/review-finding.md` | gstack review + 统一 severity+confidence | `.sdlc/review/<role>.md` 骨架（parallel-safe，per-role 一文件） |

### 1G. README（1 个）

| # | 文件 | 内容 |
|---|------|------|
| D1 | `skills/README.md`（或 repo 根 `README.md`） | 家族总览（1 driver+6 skill）、主线图、dogfooding symlink 步骤（`~/.claude/skills/sdlc*` + `.agents/skills/sdlc*` Codex 发现）、可移植规则、v1 scope vs grow-over-time |

---

## 2. 依赖波次（建造顺序）

> 原则: 先打地基（契约 + 共享数据），再建被多个 skill 共享的 references，最后建消费它们的 SKILL.md，末尾做集成与自吃狗粮验证。波内文件**互不依赖、可并行 fan-out**（Claude 端用 Task；Codex 端串行降级）。

### Wave 0 — 地基：契约 + 路由骨架（无前置依赖）
- P1 `templates/PROFILE.md`
- P2 `templates/STATE.md`
- X1 `role-routing.md`（surface-map → glob → roles + modes 字典；后续所有路由消费它）
- X2 `distillation-loop.md`

> 理由: STATE/PROFILE 契约与 role-routing 是后面所有 skill 的共享语言；必须先冻结。

### Wave 1 — 知识数据：角色卡 + validate 模式 + 余下模板（依赖 Wave 0 的 routing/契约词汇）
- R1 server-dev / R2 qa / R3 client-dev / R4 design / R5 big-data（5 角色卡，互不依赖，可并行）
- M1 correctness / M2 e2e / M3 eval-bench（3 模式，互不依赖，可并行）
- P3 spec / P4 plan / P5 e2e-report / P6 eval-report / P7 review-finding（5 模板）

> 理由: 这些是纯数据 playbook，被 process skill 引用但不引用 skill；先于 skill 完成，让 skill 只做编排。

### Wave 2 — stage playbook（依赖 Wave 1 的角色卡/模式，引用它们）
- T0 onboard / T1 explore / T2 spec / T3 plan / T4 test-first / T5 implement / T6 validate（指向 M1/M2/M3）/ T7 review / T8 verify
- 9 个互不依赖，可并行。

### Wave 3 — process SKILL.md（依赖 Wave 2 stage + Wave 1 数据；引用它们做编排）
- S2 onboard / S3 spec / S4 plan / S5 build / S6 validate / S7 review（6 个，可并行）

> 理由: 每个 SKILL.md = 薄编排层，进入条件→调对应 stage playbook→跑路由→写 STATE。

### Wave 4 — driver + 集成 + README（依赖全部）
- S1 `sdlc/SKILL.md`（driver：分支 onboard/spec/resume + drift 检测 + Task-or-sequential 探测）
- D1 README + dogfooding symlink 步骤 + `.agents/skills/sdlc*` Codex 发现 sync

### Wave 5 — dogfood 验证（依赖全部建成）
- 在 agentic-config-demo（`agentic-config-demo/`）跑一遍主线：`/sdlc` → onboard 产出 PROFILE.md → 一个小 feature 走 spec→plan→build→validate→review→verify。
- 校验: 跨 session handoff（STATE.md resume）、改动代码路由（前端改动加载 client+design + 排 Web E2E）、Codex 串行降级。
- 把 dogfood 中发现的缺漏经 X2 distillation-loop 回填到对应 stage/role/mode。

---

## 3. 两个研究 spike（占位 — 不阻塞主波次）

> 二者均为 spec §13 open question；遵循"先验证再记录"。占位在此登记，建造时按 Wave 排入但**不阻塞** Wave 0–3。

### SPIKE-A — App 移动 E2E 工具选型（源地图 #4：零素材零工具，最大净新建缺口）
- **问题**: Web（Playwright MCP）与 OpenAPI（network_requests 抓端点）已确认；移动自动化工具未定。
- **候选**: Maestro（默认倾向，简单）/ Appium / device-farm。
- **产物**: 验证后写入 M2 `e2e.md` 的 **App 模态**小节（命令语义 + 截图报告闭环 + 已验证工具调用）。
- **排期**: App 模态在 spec §11 中"sequenced last"。Spike 可与 Wave 1–3 并行调研，**结论在 Wave 5 dogfood 前落地**；未验证前 M2 的 App 段标 `[SPIKE-A pending]`，Web/OpenAPI 段先完整可用。
- **占位文件**: `docs/spikes/SPIKE-A-app-e2e-tooling.md`（验证记录；结论 merge 回 M2 后保留为决策档案）。

### SPIKE-B — eval-bench 执行层落地（源地图 #2/#3：eval 前置 + 数字化门控，多源全无）
- **问题**: "对 dataset 按 rubric 跑出实际质量分"的执行层需缝合 `ai-evals` rubric × LLM judge × verdict，并打通 spec→validate 契约接口（validate 读 rubric/数据集/阈值的位置约定）。
- **产物**: 验证后写入 M3 `eval-bench.md` 执行层 + P3 `spec.md` 的 eval criteria 段 + P6 `eval-report.md`，三者契约对齐。
- **排期**: 与 Wave 1（M3 起草）耦合；先用 agentic-config-demo 一个最小 AI 工作样例（10-20 样本起，ai-evals 准则）跑通端到端，再固化契约。
- **占位文件**: `docs/spikes/SPIKE-B-eval-bench-execution.md`（最小样例 + 契约定稿）。

---

## 4. 验收门（PLAN 完成判据）

- [ ] 7 个 SKILL.md 全部为薄编排层，无 runtime preamble / gsd-tools / .planning 依赖。
- [ ] 5 角色卡符合 §7 格式，big-data 为 stub 但已 seed agency `data-engineer`。
- [ ] 3 validate 模式为 references 数据，非顶层 skill；correctness 含数字化覆盖率门控。
- [ ] role-routing.md 覆盖 Python + TS globs，可解析 agentic-config-demo 的 surface。
- [ ] 所有交互点用 text_mode；所有并行点有 Task-or-sequential 降级。
- [ ] STATE/PROFILE/spec/plan/报告均有统一 schema 模板。
- [ ] README 含 dogfooding symlink + Codex `.agents/skills` 发现步骤。
- [ ] agentic-config-demo dogfood 跑通一条主线（Wave 5）。
- [ ] SPIKE-A / SPIKE-B 结论落地或明确标 pending。

---

## 5. 文件计数（v1）

| 类别 | 数量 | 文件 |
|------|------|------|
| Driver + process SKILL.md | 7 | S1–S7 |
| 角色卡 | 5 | R1–R5 |
| validate 模式 | 3 | M1–M3 |
| stage playbook | 9 | T0–T8 |
| 路由 + 蒸馏循环 | 2 | X1–X2 |
| 模板 | 7 | P1–P7 |
| README | 1 | D1 |
| 研究 spike 占位 | 2 | SPIKE-A, SPIKE-B |
| **合计** | **36** | |
