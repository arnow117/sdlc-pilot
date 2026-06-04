# SDLC-Pilot 吸收完整性审计

> 针对 sdlc-pilot v1 从三个上游系统(superpowers / gstack / GSD)蒸馏方法论的完整性评估。
> 范围限定为 SDLC 方法论核心:understand → spec → plan → build → validate → review。
> ship/release/部署/会话安全工具/纯环境 plumbing 均按 source-map 规则判为 out-of-scope。

产物 skill 路径:`/Users/arnow117/hansen_agent_team/workspace/20260603-sdlc-pilot/skills/`
(sdlc, sdlc-onboard, sdlc-spec, sdlc-plan, sdlc-build, sdlc-validate, sdlc-review +
`sdlc/references/validate-modes/{correctness,e2e,eval-bench}.md`、`role-routing.md`、`roles/*.md`)

---

## 1. 总览

| 系统 | SDLC 相关数 | absorbed | partial | missed | 覆盖率 |
|------|:----------:|:--------:|:-------:|:------:|:------:|
| superpowers | 11 | 6 | 3 | 2 | **82%** |
| gstack | 16 | 9 | 4 | 3 | **88%** |
| GSD (73 skills) | 20 | 14 | 4 | 2 | **85%** |
| **合计** | **47** | **29** | **11** | **7** | **~85%** |

整体判断:**方向成立、保真度高、未在重造上游**。四大方法论支柱(spec 讨论纪律、plan 任务模板、build TDD+调试状态机、validate/review 验证门)都被真实、可执行地落地,而非仅点名;运行时依赖(subagent / AskUserQuestion / .planning / gsd-tools / 遥测)被系统性剥离,替换为纯文件 playbook + `text_mode` + `Task-or-sequential` 两条可移植降级范式。

---

## 2. 分系统明细

### 2.1 superpowers(82%)

**Absorbed(6) — 四大支柱全部到位**

| skill | 吸收进 target |
|-------|--------------|
| brainstorming | sdlc-spec(HARD-GATE 先批后码 / 一次一问 / 2-3 方案带推荐 / 逐节批准 / 4 扫自检 / 隔离设计) |
| writing-plans | sdlc-plan(5 步 TDD 粒度 / No-Placeholder 红线 / 精确路径+完整代码 / 三扫自检) |
| test-driven-development | sdlc-build(Iron Law + RED→Verify→GREEN→Verify→REFACTOR 状态机 + 两道强制 Verify 门 + 反合理化表);build 还**新增**了统一 TDD-debug 状态机图 |
| systematic-debugging | sdlc-build §4(四阶段根因 + NO-FIX-WITHOUT-ROOT-CAUSE + 边界插桩 + 反向数据流 + 3-strike + DEBUG REPORT) |
| verification-before-completion | validate-modes/correctness.md(Iron Law + Gate Function + 反合理化);build exit gate 与 review G6 复用 |
| executing-plans | sdlc-build(load/critically-review/execute-exactly/stop-when-blocked,去 subagent 化为单 session 串行) |

**Partial(3) — 缺的都是运行时编排,价值低**

- **subagent-driven-development**:两阶段评审 + 4 状态协议已吸收;缺 *按任务复杂度选模型*(便宜 vs 强模型)——属编排运行时,对纯文件 pilot out-of-scope。
- **dispatching-parallel-agents**:可移植 fan-out 已用于 review/validate/onboard;缺 *调试场景*的并行变体(按 domain 分组独立失败→每域一个调查者→冲突检查+全量集成)。build 明令禁止并行实现,无并行调查 playbook。**中价值**,值得在 build §4 加一段。
- **using-git-worktrees**:worktree 机械 out-of-scope;但 *动手前验证 clean 测试基线*是真 SDLC 卫生,未在 build 入口捕获。**低-中价值**,可加一行入口检查。

**Missed(2)**

- **receiving-code-review** — **最高价值缺口**。受评方接收纪律全缺:禁表演式同意("你说得对")、改前先核对代码库、先澄清全部不清项、带理由技术反驳、对"实现得更完整"做 YAGNI grep、一次一修各自验。SDLC 在 build 自检 / debug / review fix-first 反复回环过 fix cycle,这正是防止盲目/过度修复的纪律。**应补一节进 sdlc-build 或 sdlc-review。**
- **finishing-a-development-branch** — 集成/收尾(verify→4 选项 merge/PR/keep/discard→执行→清理)被 source-map 路由到 "ship",**out-of-scope,不值得补**;唯一重叠的"完成前测试须过"已被 validate/review 覆盖。

### 2.2 gstack(88%)

**Absorbed(9)** — review 引擎、qa/qa-only、browse、design-review、devex-review、investigate、verify、plan-eng-review、benchmark(-models)、codex 全部蒸馏为可执行 playbook,硬规则(scope-drift+plan-completion 分类、置信度 1-10、验证阶梯+Gate+反合理化、根因模式签名表、安全 10 域 open=0、baseline-diff 回归)保留完整。codex 正确地作为可选 + 自引用守卫吸收。

| 关键 target |
|------------|
| sdlc-review/SKILL.md(review + plan-eng-review + 安全门 + 对抗 pass) |
| validate-modes/correctness.md(qa + verify) |
| validate-modes/e2e.md(browse + design-review fix loop) |
| validate-modes/eval-bench.md(benchmark) |
| roles/{design,qa}.md(devex-review 证据纪律) |

**Partial(4)**

- **plan-design-review**:live 设计审计已吸收;缺 *plan 阶段*的 0-10 设计维度打分 + "怎样到 10"。
- **health**:基线 green/coverage 快照已吸收;缺加权综合 0-10 质量分 + 趋势。低价值(项目级仪表盘)。
- **cso**:diff 范围安全审查强;缺 infra 广度(history 密钥考古 / 依赖 CVE / CI-CD / skill 供应链)。多数 out-of-scope,*密钥考古 + 依赖 CVE* 是 SDLC 相邻的细条,可补进安全门。
- **office-hours(startup)**:builder/讨论已覆盖;缺六个 *需求现实*强制问题(demand reality / status-quo / 最窄楔子 / future-fit)——greenfield 需求验证透镜。

**Missed(3,均为 plan 阶段评审家族)**

- **plan-ceo-review** — **值得补**。产品/范围塑造透镜(10 星产品、挑战前提、4 模式 SCOPE EXPANSION/SELECTIVE/HOLD/REDUCTION)。sdlc-spec 只有 scope-GUARD(反蔓延,反方向),没有"把 plan 推向更好/更大或剥到本质"的动作。蒸馏 4 模式进 sdlc-spec/plan 作可选 ambition pass。
- **plan-devex-review** — 仅面向开发者产品时值得。DX *plan* 评审(persona / 魔法时刻 / 摩擦追踪 / 评分)无家,DX 当前只在 live 验证、从不在 plan 评审。优先级低于 plan-ceo-review。
- (retro/learn/plan-tune/ship/canary/careful/guard 及全部 tooling-doc-setup → **正确 out-of-scope**)

### 2.3 GSD(85%)

**Absorbed(14)** — discuss/research/plan/new-project/execute/code-review/secure/validate/add-tests/eval-review/map-codebase/debug/analyze-dependencies/discovery 全部落地。阶段五准则、任务三字段(read_first/acceptance_criteria/action)、depends_on/wave 波次、goal-backward must_haves、四阶段调试、安全 10 域、评审深度分层、eval 三态、4-focus 测绘——真实进入对应 sdlc-* skill;~50 个 plumbing(milestone/workspace/manager/stats/graphify/import 等)正确判 out-of-scope。

**Partial(4)**

- **gsd-ai-integration-phase**:AI-SPEC 四锁中只 *eval* 那件吸收;缺 *framework-selector + domain-researcher*(动 AI 前在 spec 定死框架/架构契约)——只被泛化 L3 研究覆盖。对 AI 重项目有价值,非阻断。
- **gsd-verify-work**:goal-backward 已吸收,STATE+escalate 部分等价;缺 *持久 UAT 循环*(对话式人工验收 + 状态 survives /clear + gaps 回喂 plan)。可在 validate 加轻量跨会话 UAT 清单产物。
- **gsd-list-phase-assumptions**:被 clarify 隐含;缺 *显式列假设供早期纠偏*的动作。轻量,可在 plan 定级时加一句。
- (health 见 gstack)

**Missed(2)**

- **gsd-ui-phase** — **GSD 侧最值得补**。在拆任务前锁定 *前端设计契约*(spacing/typography/color/copy/design-system),插在 discuss↔plan 之间,与已吸收的 *eval 契约前置完全同构*。当前 design 角色卡已引用 DESIGN.md 为权威却**无人产出它**。对前端重项目有真实价值。
- **gsd-extract_learnings** — 低-中价值。feature 完成后把 decisions/lessons/patterns 沉淀进长寿记忆(LEARNINGS)。sdlc 只有短寿 STATE.Decisions 与针对 skill 自身的 distillation-loop,缺"经验回写"。与本项目 kb-manage 理念契合,非闭环必需。

---

## 3. 优先补充清单(跨系统,按价值排序)

| # | 缺口 | 来源 | 补进 target | 价值 | 工作量 |
|---|------|------|------------|:----:|:-----:|
| 1 | **receiving-code-review** 受评接收纪律(禁表演式同意 / 改前核对 / 先澄清全部 / 技术反驳 / YAGNI grep / 一次一修) | superpowers | sdlc-build 或 sdlc-review 加一节 | **高** | 小(1 节,~半页) |
| 2 | **ui-phase 前端设计契约前置**(在拆任务前锁定 design-system,产出 DESIGN.md) | GSD | sdlc-spec 仿 §5 eval 契约加"design 契约(仅触前端可见面)"节 | **高** | 中(1 节 + 引用补 DESIGN.md 产出动作) |
| 3 | **plan-ceo-review 范围塑造**(10 星 / 挑战前提 / 4 模式 EXPANSION/SELECTIVE/HOLD/REDUCTION) | gstack | sdlc-spec 或 sdlc-plan 可选 ambition/scope-review pass | **中-高** | 中(1 节,与现有 scope-GUARD 配对成"双向范围") |
| 4 | **并行调查 playbook**(按 domain 分组独立失败→每域一调查者→冲突检查+全量集成) | superpowers | sdlc-build §4 短段 | **中** | 小 |
| 5 | **AI 框架/架构契约前置**(framework-selector + domain-researcher) | GSD | sdlc-spec(AI 重项目分支) | **中** | 中 |
| 6 | **office-hours 六需求现实强制问题** | gstack | sdlc-spec 新产品分支薄清单 | **中** | 小 |
| 7 | **持久 UAT 追踪**(跨会话人工验收清单产物) | GSD | sdlc-validate 加轻量 UAT.md 产物 | **中** | 中 |
| 8 | **plan-stage 设计 0-10 打分** | gstack | sdlc-plan(UI 在范围内时) | 低-中 | 小 |
| 9 | **clean 测试基线门** | superpowers | sdlc-build 入口条件加一行 | 低-中 | 极小 |
| 10 | **extract_learnings 经验回写** | GSD | sdlc-review Verify 收尾 append 进 PROFILE/LEARNINGS | 低-中 | 小 |
| 11 | **显式 assumptions 清单** / **密钥考古+依赖 CVE** / **plan-devex-review** / **composite health gate** | GSD/gstack | 各自 target | 低 | 小 |

**明确不补(out-of-scope,判定合理)**:finishing-a-development-branch、subagent 模型选择、retro/learn/plan-tune、ship/land-and-deploy/canary、careful/guard/freeze、全部 worktree 机械/browser plumbing/doc-slide 生成/环境 setup。

---

## 4. 总体结论

sdlc-pilot v1 已高保真吸收三系统 ~85% 的 SDLC 方法论核心(四大支柱全到位、硬规则保留、运行时正确剥离),不是在重造上游;最该补的三件是 **receiving-code-review 受评接收纪律(防盲目修复)**、**前端 design 契约前置(与 eval 前置同构、且 design 卡已引用却无人产出 DESIGN.md)** 和 **plan-ceo-review 范围塑造(补齐现有只反蔓延的单向 scope-GUARD)**。
