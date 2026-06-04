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
| **Roles**(偏职能视角) | "从这个专业看,什么重要" | 知识卡(数据,被技能加载) | qa · client-dev · server-dev · design · big-data |
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
│   │       ├── roles/               #    角色卡(纯视角,无流程):qa / client-dev / server-dev / design / big-data
│   │       ├── role-routing.md      #    改动文件 glob → 角色卡 + validate 模式
│   │       ├── stages/              #    各阶段蒸馏后的 playbook(0-onboard … 8-verify)
│   │       ├── validate-modes/      #    验证中枢的厚 playbook:correctness / e2e / eval-bench
│   │       ├── templates/           #    PROFILE / STATE / 报告等 schema 模板
│   │       └── distillation-loop.md #    新技能如何被折叠进来(时用时新)
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

## 安装与试用(开发期 dogfooding)

技能在本 workspace 的 `skills/` 下开发。要在当前项目里边开发边用,把每个技能**软链**进 `~/.claude/skills/`:

```bash
SDLC_SRC="/Users/arnow117/hansen_agent_team/workspace/20260603-sdlc-pilot/skills"
for s in sdlc sdlc-onboard sdlc-spec sdlc-plan sdlc-build sdlc-validate sdlc-review; do
  ln -sfn "$SDLC_SRC/$s" "$HOME/.claude/skills/$s"
done
```

为让 **Codex** 也能仓库内发现这些技能,维护 `.agents/skills/sdlc*` 软链(per soul.md 0.2.1):

```bash
mkdir -p .agents/skills
for s in sdlc sdlc-onboard sdlc-spec sdlc-plan sdlc-build sdlc-validate sdlc-review; do
  ln -sfn "$SDLC_SRC/$s" ".agents/skills/$s"
done
```

> 软链而非拷贝,保证"边开发边用"始终指向同一份源。成熟后,`sdlc-pilot/` 子树可 `git init` 推成独立 repo;届时安装方式改为 clone + 软链/拷进 `~/.claude/skills/`。

## Dogfooding

v1 语言范围 = **Python + Web(TS)**。首个 dogfood 目标 = **happycompany**(`corp/dingguo-happycompany/`):
对其先跑 `sdlc-onboard` 生成 `PROFILE.md` + surface map,再跑一条完整 feature 主线,用真实使用反过来打磨角色卡、路由规则与 validate 模式。

## 兼容性铁律(load-bearing)

1. 知识 + 状态都是纯文件(`references/`、`.sdlc/STATE.md`)—— 任何调用方不靠 Skill 机制也能用。
2. STATE 单写者;并行工作各写各的文件(`review/<role>.md`)—— 避免 subagent / workflow fan-out 竞态。
3. 流程平台无关;编排只是加速器,不是依赖。核心阶段只用 read/edit/shell;并行角色评审在 Claude 上用 Agent/Workflow,在 Codex 上**降级为串行**。不硬依赖 Workflow / AskUserQuestion。
4. 维护 `.agents/skills/sdlc*` 软链,供 Codex 仓库内发现。

## 延伸阅读

- 设计 spec:[`docs/specs/2026-06-03-sdlc-pilot-design.md`](docs/specs/2026-06-03-sdlc-pilot-design.md)
- 蒸馏源地图(每个目标的 canonical 源 + 取什么/补什么):[`docs/distillation-source-map.md`](docs/distillation-source-map.md)
