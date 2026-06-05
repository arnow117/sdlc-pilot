# sdlc-pilot

> 一套**自洽、可移植、时用时新**的 SDLC(软件开发生命周期)技能族。
> 知识全部落在纯文件里,引擎就是 **Claude + 基础工具**(Read / Edit / Bash / Grep)——没有隐藏的运行时依赖。

## 这是什么

我们已经有大量散落的 SDLC 机制(gsd-* 全生命周期、superpowers 的 TDD/plans、hp-feature-dev、各类 role-review……),但它们:外部托管、不归我们所有、在 Codex 下跑不了、也没有一条**属于自己的主线**把它们串起来。

`sdlc-pilot` 把这些外部技能的**方法论蒸馏**进我们自己拥有、可编辑的纯文件,组成一条 **TDD + SDD(spec-driven)** 主线,并具备三条核心差异化:

- **自洽(self-contained)** —— 蒸馏外部技能的精华(方法/检查清单),丢弃运行时 preamble、`gsd-tools.cjs`、`.planning` 目录依赖、agent 人格(vibe/emoji/memory)。落地后**无任何外部技能的运行时依赖**。
- **可移植(portable)** —— 不硬依赖 Workflow / AskUserQuestion / subagent。用 gsd 的 **text_mode**(纯文本编号列表替代交互问答)+ gsd-map 的 **Task-or-sequential 降级**(探测有无并行能力,没有就串行)。在 **Codex** 下也能跑。
- **时用时新(living artifact)** —— 每分析一个新技能/项目,通过蒸馏循环把可复用模式追加进对应的阶段/角色卡/validate 模式,知识库持续生长,始终是"我们理解后的版本"。

还有两条工程支柱:

- **改动代码驱动路由** —— 每个流程阶段先跑 `git diff`,按改动的文件路径自动决定**加载哪些角色视角**、**跑哪些验证模式**,无需手动选。
- **跨会话状态持久化** —— 进度落在目标仓库的 `.sdlc/STATE.md`(短期 feature 交接)与 `.sdlc/PROFILE.md`(长期项目记忆),`/clear` 或隔天换 session 也能无缝续接。

## 两轴模型:Roles(视角卡) × Skills(流程)

一句话:**Roles 是"从这个专业视角看什么重要"的知识卡(被流程加载引用,本身不做动作);Skills 是"这一步我们做什么"的可执行阶段。** 验证类过程(E2E、eval/bench)既不是角色也不是独立技能,而是 validate 技能的**可插拔模式(厚 playbook 数据)**。

| 轴 | 含义 | 形态 | 成员 |
|----|------|------|------|
| **Roles**(偏职能视角) | "从这个专业看,什么重要" | 知识卡(数据,被技能加载) | qa · client-dev · server-dev · design · big-data · architect |
| **Skills**(偏流程) | "这一步我们做什么" | 可执行技能 | onboard · spec · plan · build · validate · review(+ driver) |

## 技能族结构

```
sdlc-pilot/                          # 未来独立 GitHub repo 的根
├── README.md                        # 本文件
├── docs/
│   ├── specs/                       # 设计 spec(见下方链接)
│   ├── PLAN.md                      # 构建计划
│   └── distillation-source-map.md   # 蒸馏源地图:每个目标的 canonical 源 + 取什么/补什么
├── skills/
│   ├── sdlc/                        # ① driver:分支路由 / 改动代码路由 / 跨会话交接
│   │   ├── SKILL.md
│   │   └── references/              # ② 共享数据,被所有阶段技能 Read
│   │       ├── roles/               #    角色卡(纯视角,无流程):qa / client-dev / server-dev / design / big-data / architect
│   │       ├── role-routing.md      #    改动文件 glob → 角色卡 + validate 模式(R1-R8)
│   │       ├── validate-modes/      #    验证中枢的厚 playbook:correctness / e2e / eval-bench
│   │       ├── divergence-frames.md #    可选发散 ideation pass(蒸馏 adhd)
│   │       ├── receiving-feedback.md #   接收意见并修复的纪律(防过度修复)
│   │       ├── templates/           #    PROFILE / STATE / 报告 schema + hooks/pre-push
│   │       └── distillation-loop.md #    新技能如何被折叠进来(时用时新)
│   │       # 注:各阶段 playbook 内联在对应 sdlc-*/SKILL.md;stages/ 为未来拆分预留
│   ├── sdlc-onboard/SKILL.md        # ⓪ brownfield 入口:扫描仓库 → PROFILE.md + surface map
│   ├── sdlc-spec/SKILL.md           # ③ Explore + Spec(SDD;为 AI 工作前置 eval 标准)
│   ├── sdlc-plan/SKILL.md           # ④ 拆分任务(依赖 + 波次 + L1-L4 复杂度分级)
│   ├── sdlc-build/SKILL.md          # ⑤ Test-first(red)+ Implement(green),内含调试子循环
│   ├── sdlc-validate/SKILL.md       # ⑥ 验证中枢:correctness / e2e / eval-bench 模式
│   └── sdlc-review/SKILL.md         # ⑦ 多角色评审 + Verify
└── scripts/                         # 可选辅助(如 state linter)
```

### 主线一图流

```
[brownfield] Onboard ─┐
                      ├→ Spec(SDD) → Plan → Test-first(red) → Implement(green)
[greenfield] ─────────┘            → Validate{correctness | e2e | eval-bench} → Review → Verify
```

driver 在入口分支:

```
/sdlc → 读 .sdlc/
   ├─ 无 PROFILE.md 且仓库非空(已有项目) → 先走 sdlc-onboard
   ├─ 无 PROFILE.md 且仓库空(全新项目)   → 直接到 sdlc-spec
   └─ 有 PROFILE.md → 从 STATE.stage 恢复 per-feature 循环
```

### 状态文件(落在**目标仓库**,不在技能里)

```
<target-repo>/.sdlc/
├── PROFILE.md     # 项目记忆(长期):技术栈 / 约定 / surface map(模块→glob→默认角色+模式)/ 测试命令
├── STATE.md       # feature 交接(短期):阶段 / 状态 / gates / 活跃角色 / 改动快照 / 决策 / 下一步
├── spec.md        # sdlc-spec 产出(含 AI 工作的 eval 标准)
├── plan.md        # sdlc-plan 产出
├── validate/      # 各 validate 模式产出(含截图报告)
└── review/        # 每个角色一份 findings(并行安全)
```

## 安装

> 这套技能是一个 **Claude Code 插件**(`.claude-plugin/plugin.json` 声明 `skills: "./skills/"`),
> driver + 7 流程技能 + 角色卡/validate 模式/语言包(都在 `skills/sdlc/references/` 下)随插件**一并发现**,无需逐个登记。

**方式一:作为插件安装(推荐,跟着 GitHub 仓走)**

```
/plugin marketplace add arnow117/sdlc-pilot
/plugin install sdlc-pilot
```

升级:`/plugin marketplace update sdlc-pilot` 后重新 `/plugin install`。私有仓需本机 git 已能访问该仓。

**方式二:全新克隆 + 软链(要改源 / 离线 / Codex 用)**

适用于"把仓库当全新 repo clone 到自己电脑"的场景。**遍历 `skills/*/` 软链,不枚举技能名**——这样永远不会漏掉新增技能(如本次差点漏的 `sdlc-ship`):

```bash
git clone git@github.com:arnow117/sdlc-pilot.git
cd sdlc-pilot
SDLC_SRC="$PWD/skills"

# 软链进全局技能目录(Claude Code 全局可用)
mkdir -p "$HOME/.claude/skills"
for d in "$SDLC_SRC"/*/; do ln -sfn "$d" "$HOME/.claude/skills/$(basename "$d")"; done

bash scripts/validate-skills    # 自检:结构一致、引用无悬空
```

**Codex / 在某个目标项目里仓内发现**:在目标项目根维护 `.agents/skills/sdlc*` 软链(同理遍历):

```bash
mkdir -p .agents/skills
for d in "$SDLC_SRC"/*/; do ln -sfn "$d" ".agents/skills/$(basename "$d")"; done
```

> 软链 vs 拷贝:软链"边改边用"始终指向同一份源;要固定快照就改成 `cp -R`。
> 强门禁脚本 `scripts/sdlc-guard` 在仓库根,插件安装时随仓一并到位;`sdlc-onboard` 会在目标项目装 hook 时把它拷到该项目的 `.sdlc/bin/`。

## 测试与 dogfooding

skill 是 markdown playbook,**没法单测**,两层测试:

- **结构 lint(可重复回归,commit 前必跑)**:`bash scripts/validate-skills` —— 角色/模式名↔文件↔字典一致、frontmatter、可移植自检。
- **行为 dogfood**:把流程 skill 真跑在一个项目上,对照判据查产出(如 onboard 产的 surface-map 是否过 Phase C 三条自检)。**真实/内部项目的产物不入库**(`docs/dogfood/` 已 gitignore,本地跑);产出样例见 [`examples/onboard-output-sample.md`](examples/onboard-output-sample.md)。

v1 语言范围 = **Python + Web(TS)**。如何迭代本项目见仓库根 **`CLAUDE.md`**(agent 自动读的维护契约)。

## 怎么用(日常工作流)

装好软链后,在任意项目里**入口只有一个 `/sdlc`**,它自己判断该干嘛:

| 场景 | 怎么走 |
|---|---|
| **首次进一个已有项目** | `/sdlc` → 无 PROFILE → 自动 `onboard` → 产出 `.sdlc/PROFILE.md` + surface map(agentic-config-demo 这类"配置型工程"也认得,R7) |
| **每做一个 feature** | `/sdlc` → **spec**(批准前不写码;UI 工作产 `DESIGN.md`;AI 工作前置 eval 标准;开放/高风险决策可选发散 + 范围塑造)→ **plan**(拆阶段/波次/任务)→ **build**(先测后码,同 wave 多阶段可并行)→ **validate**(按改动选 correctness/e2e/eval-bench)→ **review**(多角色 + 安全门 + 收口,写 `sdlc-gate`) |
| **角色/验证自动选** | 改前端→client-dev+design+e2e:Web;改 API→server-dev+e2e:OpenAPI;改 AI/策略→eval-bench;**跨 ≥2 面→ +architect**;改配置/agent 定义→server-dev+correctness |
| **跨会话续接** | `/clear` 或隔天 → `/sdlc` 读 `.sdlc/STATE.md`,从上次 stage 接着走,不用复述 |
| **push 把关** | 装了 `pre-push` hook 的话,review 没过会拦下 push(`--no-verify` 可绕) |
| **重型动作可选** | 发散 ideation、范围塑造**只在开放 + 高风险设计决策时**点用;日常需求直接走,不增负担 |

> 一句话:**`/sdlc` 是总机,改动驱动路由,状态跟着仓库走。** 你只管推进,它负责"在对的阶段带对的视角做对的验证"。

## 蒸馏溯源(谁吸纳了谁的哪部分)

> 我们蒸馏的是**方法论**(流程 / 检查清单 / 判据),**不是搬代码**——丢弃运行时 preamble、agent 人格、`gsd-tools.cjs`/`.planning` 等工具依赖。下表是"吸纳了源的哪一部分"。

### 流程 skill

| 技能 | 源 → 吸纳的部分 |
|---|---|
| `sdlc`(driver) | handoff(跨会话交接)· gsd 编排(分支路由,去运行时)· gsd-map(Task-or-sequential 降级)· **resolve 路由/surface-map = 净新建** |
| `sdlc-onboard` | gsd-map-codebase(4-focus 采证 + 降级 + secret + 下游契约)· arch-aifriendly-doctor(纯 bash 采证脚本 + P13 域路由 + P23 模块命令)· explorer-repo-report(type-detection + P0/P1/P2)· startup-claude-md-init(PROFILE schema 带"原因")· agency:codebase-onboarding-engineer(只读纪律/入口发现)· **surface-map 表 + R7 配置型识别 = 净新建** |
| `sdlc-spec` | brainstorming(HARD-GATE + 一次一问 + 分节获批 + 双 gate)· hp-feature-dev(文档矩阵 + 怎么算 done 前置)· gsd-discuss(gray-area 具体化 + canonical_refs + scope-guard)· gsd-research(unknown-unknowns + Don't-Hand-Roll)· gsd-plant-seed(结构化 Deferred)· adhd(发散 §2.4)· plan-ceo-review(范围塑造 §2.4b)· ai-evals + gsd-eval-review(eval 前置 §5)· gsd-ui-phase + design-quality + agency:ux-architect(设计契约 §2.6b)· **eval/design 契约前置 = 净新建** |
| `sdlc-plan` | gsd-new-project(五准则)· gsd-plan-phase(Anti-Shallow 三字段 + depends_on/wave + must_haves + Source Audit/Coverage Gate)· planner-breakdown-sdlc(L1-L4 分级)· writing-plans(TDD 五步 + No-Placeholder + 自查三扫) |
| `sdlc-build` | test-driven-development(RGR 五拍 + Iron Law + 两个强制 Verify)· systematic-debugging(四阶段根因)· investigate(模式签名表 + Scope Lock + blast-radius + DEBUG REPORT)· hp-bugfix(bug 三分类)· subagent-driven-development(两阶段自检,去 subagent)· gsd-execute-phase(wave 模型:并行 fan-out + 串行降级)· receiving-code-review(受评纪律)· **TDD↔调试统一状态机 = 净新建** |
| `sdlc-validate` | verify(验证手段优先级阶梯)· verification-before-completion(无新鲜证据不声称通过)· 各模式见下 |
| `sdlc-review` | gstack:review(scope-drift + plan-completion + confidence 校准表 + fix-first + 对抗 pass)· gsd-code-review(深度分层 + 语言 pitfall 表 + REVIEW.md)· security-review(安全 10 域)· gsd-secure-phase(verify-mitigation + disposition + open=0 硬门)· plan-eng-review(15 认知模式)· devex-review(验证声明防幻觉)· codex(对抗外脑,可选) |

### validate 模式

| 模式 | 源 → 吸纳的部分 |
|---|---|
| `correctness` | gsd-add-tests(TDD/E2E/Skip 三分类 + No-skip 铁律 + text_mode)· qa(framework bootstrap + 回归测试三步)· gsd-validate-phase(requirement-completeness 三态)· **数字化覆盖率门 = 净新建** |
| `e2e` | Playwright MCP(Web 底座)· design-review(fix loop 8a-8f + 三联截图)· devex-review(证据等级 + Scope Declaration)· web-api-reverse-engineering(端点用例 + 只读约束)· **App 模态 / 旅程推导 / 多模态编排 = 净新建** |
| `eval-bench` | ai-evals.md(三测量法 + 10 维度 + rubric 1/3/5 + reference dataset + guardrail/flywheel)· gsd-eval-review(加权阈值 verdict)· benchmark(baseline-diff 双阈值)· benchmark-models(多对象同输入 + LLM judge)· tb-run-analyzer(有效性甄别)· tb-task-operator(oracle/nop 自检门 + pass@k) |

### 角色卡

| 角色 | 源 → 吸纳的部分 |
|---|---|
| `qa` | plan-eng-review(test-coverage tracing)· review/specialists/testing(缺负路径/隔离/flaky)· red-team(敌意测试)· agency:testing-* |
| `server-dev` | gsd-code-reviewer(语言 pitfall 表)· review/specialists/{performance,api-contract,security}· security-review · agency:backend-architect/security-engineer/sre |
| `client-dev` | flutter-dart-code-review · JS/TS pitfalls · review/specialists/performance(前端)· design-checklist · web/ 规则(user)· agency:mobile-app-builder/frontend-developer/wechat-mini-program |
| `design` | gstack design-checklist(AI-slop)· web/design-quality(user)· agency:ux-architect/ux-researcher/ui-designer/persona-walkthrough |
| `big-data`(stub) | agency:data-engineer(Medallion/contract/lineage/CDC)/database-optimizer/ai-data-remediation · review/specialists/data-migration |
| `architect` | plan-eng-review(15 认知模式)· review/specialists/{api-contract,data-migration}· gsd-research(architectural-responsibility-map)· agency:software-architect/backend-architect · **全链路数据结构对齐 = 净新建侧重** |

### 共享纪律 / 数据

| 文件 | 源 → 吸纳的部分 |
|---|---|
| `divergence-frames.md` | adhd(两阶段发散/聚焦 + 框架表 + 陷阱标记 + pre-flight 门) |
| `receiving-feedback.md` | receiving-code-review(先核实再改 / 一次一项 / 技术反驳 / YAGNI / 禁表演式同意) |
| `role-routing.md` | arch-doctor 的 P13/P23 机制原型;**R1-R8 表本身 = 净新建** |
| `templates/hooks/pre-push` | **自建**(纯 shell,读 STATE 的 sdlc-gate;OneRedOak CI 思路本地化) |

## 出处与致谢

本项目把以下生态的**方法论蒸馏**进自己的纯文件(蒸馏 ≠ 搬代码;落地后无其运行时依赖):

| 源生态 | License / 出处 | 取了什么 |
|---|---|---|
| **superpowers** | Anthropic 官方插件(MIT) | brainstorming · writing-plans · executing/subagent-driven-development · test-driven-development · systematic-debugging · verification-before-completion · receiving-code-review |
| **gstack** | 安装插件 | review(+ review/specialists/*)· qa · browse · design-review · devex-review · plan-eng-review · plan-ceo-review · investigate · verify · benchmark · benchmark-models · codex |
| **GSD(get-shit-done)** | 安装插件 | gsd-map-codebase · discuss/research/plan/execute-phase · new-project · add-tests · validate-phase · eval-review · code-review · secure-phase · plant-seed · `references/ai-evals.md` |
| **agency-agents** | github.com/msitarzewski/agency-agents(MIT) | data-engineer · ux-architect/ui-designer/ux-researcher/persona-walkthrough · mobile-app-builder/frontend/wechat · codebase-onboarding-engineer · backend/security/sre/software-architect · testing-* |
| **adhd** | MIT | 发散 ideation 方法(divergence-frames) |
| **用户自有技能** | 本工作区 | hp-feature-dev · hp-bugfix · explorer-repo-report · startup-claude-md-init · tb-run-analyzer · tb-task-operator · web-api-reverse-engineering · `web/` 设计与编码规则 |
| **Playwright MCP** | claude-plugins-official | e2e Web 模态底座 |

> 致谢这些上游作者。**净新建**(无外部源)的部分:surface-map + 改动代码路由(R1-R8)、eval 标准前置、设计契约前置、数字化覆盖率门、App E2E 模态、TDD↔调试统一状态机、本地 pre-push SDLC 检查。

## 兼容性铁律(load-bearing)

1. 知识 + 状态都是纯文件(`references/`、`.sdlc/STATE.md`)—— 任何调用方不靠 Skill 机制也能用。
2. STATE 单写者;并行工作各写各的文件(`review/<role>.md`)—— 避免 subagent / workflow fan-out 竞态。
3. 流程平台无关;编排只是加速器,不是依赖。核心阶段只用 read/edit/shell;并行角色评审在 Claude 上用 Agent/Workflow,在 Codex 上**降级为串行**。不硬依赖 Workflow / AskUserQuestion。
4. 维护 `.agents/skills/sdlc*` 软链,供 Codex 仓库内发现。

## 延伸阅读

- 设计 spec:[`docs/specs/2026-06-03-sdlc-pilot-design.md`](docs/specs/2026-06-03-sdlc-pilot-design.md)
- 蒸馏源地图(每个目标的 canonical 源 + 取什么/补什么):[`docs/distillation-source-map.md`](docs/distillation-source-map.md)
