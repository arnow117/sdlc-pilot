# sdlc-pilot — Design Spec

> Date: 2026-06-03
> Status: Design APPROVED → build (scope locked 2026-06-04, see §14). Source map: `docs/distillation-source-map.md`
> Location: `workspace/20260603-sdlc-pilot/` (future standalone GitHub repo)

## 1. Problem

We already own a lot of SDLC machinery (gsd-* full lifecycle, superpowers TDD/plans,
hp-feature-dev, the role-review series), but:

1. **Role perspectives are incomplete** — there is no dedicated lens for client-dev,
   server-dev, or big-data work. QA / design / security exist as separate skills. And E2E
   (a user-perspective test *process*) has no owned, report-producing home.
2. **There is no "my own main line"** — the pieces are scattered across external,
   tool-managed skills. Nothing ties them into one coherent, *owned*, editable flow.
3. **External skills are not portable** — they cannot be relied on under Codex, and
   they evolve outside our control.

We want **our own self-contained SDLC skill family** that:
- runs a TDD + SDD (spec-driven) main line,
- automatically pulls in **role lenses based on the code changed in each stage**,
- **distills** the essence of external skills into owned, editable data,
- stays a **living artifact** ("时用时新") — enriched whenever we analyze new skill projects,
- persists state **across sessions** for handoff,
- is compatible with **sub-agents, the Workflow tool, and Codex**.

## 2. Non-goals (YAGNI)

- NOT reimplementing gsd's 73-skill execution engine. The engine is **Claude + base tools**
  (Read / Edit / Bash / Grep) following a distilled playbook.
- NOT building one heavyweight sub-agent per role.
- NOT boiling the ocean in v1: we ship a skeleton + the 3 missing role cards, and let the
  distillation loop grow the rest over time.
- NOT making everything a skill: *viewpoints* stay role cards; *verification processes*
  (E2E, eval/bench) stay validate *modes* (data playbooks). Nothing graduates to an extra
  top-level skill beyond the driver + 6 process skills.
- NOT a CI/automation product in v1 (no GitHub Actions wiring yet).

## 3. Core decisions (resolved during brainstorming)

| Fork | Decision |
|------|----------|
|补 skill vs 搭主线 | **两者都要**: role lenses + an orchestrating main line |
| 角色形态 | **参数化主线 + 角色卡作数据**, reuse existing review skills where they already exist |
| 角色触发 | **Driven by changed code** (git diff → file globs → roles), not manual |
| 蒸馏深度 | **自洽 / fully self-contained** — internalize external skills, no runtime dependency |
| 单体 vs 拆分 | **拆分**: 1 driver + per-stage skills (context economy) + a STATE file for handoff |
| 测试验证 | **独立成一个 `sdlc-validate` 阶段**, 夹在 build 与 review 之间, 与 build 内的单元 TDD 区分 |
| Roles vs Skills 边界 | **Roles = 偏职能视角(知识卡, 被加载引用); Skills = 偏流程(可执行阶段)**. 见 §4.0 |
| 已有项目入口 | **新增 `sdlc-onboard` skill** + `PROFILE.md` 项目记忆(brownfield 先 onboard) |
| E2E 形态 | **E2E 是流程, 但收进 Validate 的一个模式**(不是顶层 skill, 不在 roles 里); 多模态 Web/OpenAPI/App + 截图报告 |
| 评估/bench | **Validate 的一个模式**; 评估标准在 spec 阶段定, validate 阶段执行; **改 AI/模型/策略时触发** |
| Validate = 验证中枢 | Validate 带可插拔模式 **correctness / e2e / eval-bench**, 每个是厚 playbook(数据文件), 非 skill |

## 4. Architecture

### 4.0 First principle — two orthogonal axes: Roles vs Skills

| Axis | Is | Form | Members |
|------|----|------|---------|
| **Roles** (偏职能视角) | "from this expertise, what matters" | **knowledge cards** (data, loaded/referenced by skills) | qa, client-dev, server-dev, design, big-data, architect (architect=全链路接缝视角, 跨 ≥2 面时由 routing R8 加载) |
| **Skills** (偏流程) | "what we DO at this step" | **executable skills** | onboard, spec, plan, build, validate, review (+ driver) |

Rule: a thing is a **role** only if it is a *viewpoint* (no actions of its own). Anything
that *does* a multi-step activity (run a suite, map a codebase) is a **skill**. A process
that is a *kind of verification* (E2E, eval/bench) is a **mode of the validate skill**, not
its own top-level skill. → E2E and eval/bench are **validate modes** (thick playbooks),
neither roles nor separate skills. QA's *viewpoint* stays a role card; QA's *activity*
lives in validate.

Changed-code routing selects **which role cards to load** AND **which validate modes to
run** during a given process skill.

### Skill family (the future repo root)

```
sdlc-pilot/                          # future standalone GitHub repo
├── README.md
├── docs/specs/                      # design specs (this file lives here)
├── skills/
│   ├── sdlc/                        # ① driver / router / handoff (small)
│   │   ├── SKILL.md
│   │   └── references/              # ② SHARED data, read by all stage skills
│   │       ├── roles/               # 偏职能视角 (knowledge cards only — NO process)
│   │       │   ├── qa.md         client-dev.md  server-dev.md
│   │       │   ├── design.md     big-data.md
│   │       ├── role-routing.md      # changed-file globs → role cards + validate modes
│   │       ├── stages/              # distilled stage playbooks
│   │       │   ├── 0-onboard.md 1-explore.md 2-spec.md 3-plan.md
│   │       │   ├── 4-test-first.md 5-implement.md 6-validate.md
│   │       │   ├── 7-review.md 8-verify.md
│   │       ├── validate-modes/      # thick playbooks for the validate hub (data, not skills)
│   │       │   ├── correctness.md   #   suite + coverage gate
│   │       │   ├── e2e.md           #   user journeys: Web / OpenAPI / App + screenshot report
│   │       │   └── eval-bench.md    #   quality dims vs reference set / perf bench
│   │       └── distillation-loop.md # how new skills get folded in
│   ├── sdlc-onboard/SKILL.md        # ⓪ brownfield entry: map repo → PROFILE.md
│   ├── sdlc-spec/SKILL.md           # ③ Explore + Spec (SDD; sets eval criteria for AI work)
│   ├── sdlc-plan/SKILL.md           # ④ break into tasks
│   ├── sdlc-build/SKILL.md          # ⑤ Test-first (TDD red) + Implement (green)
│   ├── sdlc-validate/SKILL.md       # ⑥ verification hub: correctness / e2e / eval-bench modes
│   └── sdlc-review/SKILL.md         # ⑦ multi-role review + Verify
└── scripts/                         # optional helpers (e.g. state linter)
```

### State (lives in the *target* repo being worked on, not in the skill)

```
<target-repo>/.sdlc/
├── PROFILE.md               # ★ PROJECT memory (long-lived): tech stack / conventions /
│                            #    role surfaces / entry points / test commands. Built once
│                            #    by sdlc-onboard, read by every feature afterward.
├── STATE.md                 # ★ FEATURE handoff (short-lived): stage / status / gates /
│                            #    active roles / changed-files snapshot / decisions / next
├── spec.md                  # produced by sdlc-spec (incl. eval criteria for AI work)
├── plan.md                  # produced by sdlc-plan
├── validate/                # produced by sdlc-validate modes
│   ├── e2e-<scope>-report.md   #    screenshot-rich test-as-report (feature/iteration/full-chain)
│   └── eval-<scope>-report.md  #    quality/bench scores vs reference set
└── review/                  # one findings file per role (parallel-safe)
    ├── server-dev.md  client-dev.md  ...
```

**PROFILE.md vs STATE.md**: PROFILE = project-level, built once (or refreshed), shared by
all features. STATE = feature-level, short-lived, the per-task handoff carrier.

PROFILE carries the **architecture surface map** — the tracked input to the decision
function (§6.1):

```markdown
# Project Profile: <name>
tech-stack: [next.js, fastapi, postgres, swift/ios]
test-commands: { unit: "pytest", e2e: "playwright test", build: "pnpm build" }

## Surface map        # modules/surfaces → globs → default roles + validate modes
- web-frontend:  globs[ web/**, components/** ]  roles[client-dev, design]  modes[e2e:Web]
- mobile-app:    globs[ ios/**, android/** ]     roles[client-dev, design]  modes[e2e:App]
- api:           globs[ services/api/** ]         roles[server-dev]          modes[e2e:OpenAPI]
- ai-strategy:   globs[ models/**, strategy/** ]  roles[server-dev, qa]      modes[eval-bench]
- data:          globs[ pipelines/** ]            roles[big-data]            modes[correctness]

## Conventions / entry points / known-risks
- ...
```

### Dev / dogfooding setup

- Develop the skills inside `workspace/20260603-sdlc-pilot/skills/`.
- To use them in the current project while developing, symlink each into the active
  skills dir: `~/.claude/skills/sdlc -> .../skills/sdlc`, etc.
- Maintain Codex discovery symlinks: `.agents/skills/sdlc*` → the skill dirs
  (per soul.md 0.2.1).
- When mature, the `sdlc-pilot/` subtree can be `git init`'d and pushed as its own repo.

## 5. The distilled main line (mapped into the driver + 6 process skills)

```
[brownfield] Onboard ─┐
                      ├→ Spec(SDD) → Plan → Test-first(red) → Implement(green)
[greenfield] ─────────┘            → Validate{correctness | e2e | eval-bench} → Review → Verify
```

The **driver** branches at the start:

```
/sdlc → read .sdlc/
   ├─ no PROFILE.md & repo non-empty (existing project) → sdlc-onboard first
   ├─ no PROFILE.md & repo empty   (greenfield)         → skip to sdlc-spec
   └─ PROFILE.md present → resume the per-feature loop at STATE.stage
```

| Stage | Skill | Distilled from |
|-------|-------|----------------|
| Onboard (brownfield entry) | `sdlc-onboard` | gsd-map-codebase, explorer-repo-report, arch-aifriendly-doctor, code-explorer, startup-claude-md-init |
| Explore + Spec | `sdlc-spec` | brainstorming, gsd-discuss-phase, hp-feature-dev |
| Plan | `sdlc-plan` | writing-plans, gsd-plan-phase, planner-breakdown-sdlc |
| Test-first + Implement | `sdlc-build` | superpowers TDD, executing-plans, subagent-driven-dev |
| Validate (验证中枢) | `sdlc-validate` | qa, verify, gsd-add-tests/validate-phase, gsd-eval-planner/review, browse, e2e-runner, Playwright MCP, web-api-reverse-engineering, tb-run-analyzer |
| Review + Verify | `sdlc-review` | code-review, security-review, gsd-verify, role-review series |

Each stage skill defines **entry conditions, the procedure, exit gates, and what it
writes to STATE**. red/green are grouped into `sdlc-build` because they iterate within
one session. **`sdlc-validate` ≠ build's unit TDD**: it is the verification hub — see §5.1.

### 5.1 `sdlc-validate` — verification hub with pluggable modes

Validate is one skill that runs one or more **modes** (thick playbooks in
`references/validate-modes/`, selected by changed-code routing — see §6):

| Mode | What it does | Triggered when |
|------|-------------|----------------|
| **correctness** | full unit/integration suite + coverage gate; run the app | always |
| **e2e** | scope (feature/iteration/full-chain) → heuristic user journeys → per-modality cases (**Web** Playwright MCP / **OpenAPI** endpoint cases / **App** mobile automation) → execute → on fail loop back to build → **screenshot test-as-report** | user-facing surfaces changed |
| **eval-bench** | measure quality dims vs a reference set by rubric, or perf bench; criteria are set back in `sdlc-spec` and executed here | **AI / model / strategy changed** |

Each mode writes its own report under `.sdlc/validate/`. Any mode is also runnable
**standalone** (e.g. `/sdlc validate --mode=e2e --scope=full-chain` for a current-state
audit, which doubles as `sdlc-onboard`'s baseline health check).

**Anti-bloat principle**: verification processes are *modes/playbooks (data)*, never new
top-level skills. This bounds the family at 1 driver + 6 process skills.

## 6. Changed-code-driven routing (roles + validate modes)

On entering `sdlc-build`, `sdlc-validate`, and `sdlc-review`, the skill runs `git diff` and
matches changed paths against `role-routing.md`. Routing resolves **which role cards to
load** AND **which validate modes to run**:

| Changed-file pattern | Role cards loaded | Validate mode(s) |
|----------------------|-------------------|------------------|
| `*.tsx *.vue *.css components/**` | client-dev + design | correctness + e2e (Web) |
| `**/*.swift *.kt mobile/** ios/** android/**` | client-dev + design | correctness + e2e (App) |
| `**/api/** **/handlers/** *.server.*` | server-dev | correctness + e2e (OpenAPI) |
| `**/models/** **/strategy/** *.prompt* ai/** evals/**` | server-dev (+ qa) | correctness + **eval-bench** |
| `*.sql **/pipelines/** (spark/pandas)` | big-data | correctness (+ eval-bench if data-quality) |
| `**/*.test.* e2e/** *.spec.*` | qa | correctness + e2e |
| any diff | qa (baseline) + security (when sensitive surface touched) | correctness |

→ frontend change loads client+design cards and queues Web/App E2E; **AI/strategy change
triggers the eval-bench mode**; a data pipeline loads the big-data card. No manual selection.
(E2E and eval are validate *modes*, not skills or role cards.)

### 6.1 The decision map — tracked architecture, dynamic decision

The "given this change, run what with which lens" decision is a **function**, not a stored
table. Separate its three inputs by how stable they are:

| Input | Stability | Where it lives | Who maintains |
|-------|-----------|----------------|---------------|
| **Architecture model** (surface map: which modules/surfaces exist, their globs, tech, default roles/modes) | slow-changing → **tracked** | `PROFILE.md` (§4 surface map) | `sdlc-onboard`, refreshed on drift |
| **Routing rules** (glob → roles + modes) | rarely changes → **tracked** | `references/role-routing.md` | distillation loop |
| **Changed files** (`git diff`) | different every run → **ephemeral** | computed live | — |

**Decision = resolve(diff × PROFILE.surface-map × routing-rules).** It is recomputed
**dynamically at the start of each process skill** (build/validate/review), and the resolved
result (active roles + validate modes) is snapshotted into `STATE.md` for handoff/audit —
but never treated as a persisted source of truth (that would go stale).

**Why dynamic, not a stored decision map:** the diff changes every run, so a persisted
decision map would be wrong by the next change. We persist the *inputs* (architecture +
rules), recompute the *decision* each time. Best of both: stable knowledge is tracked,
the per-change call is always fresh.

**Architecture drift detection (the "tracker" part):** at session start the driver compares
the diff's paths against `PROFILE.surface-map`. If a change touches a module/surface not in
the map (e.g. a brand-new service or a first mobile dir), it flags
*"architecture drifted — refresh PROFILE?"* and offers to re-run the relevant part of
`sdlc-onboard`. This keeps the tracked architecture honest without a heavyweight watcher.

## 7. Role card format

Each card is an owned, editable unit of professional knowledge:

```markdown
---
role: server-dev
triggers: [api/**, handlers/**, *.server.*]
distilled-from: [gsd-secure-phase, code-review, <new-project-name>]
---
## 关注点      # what this role cares about
## 检查清单    # concrete checklist
## 好的样子    # what "good" looks like
## 常见翻车    # common failure modes
## 介入哪些阶段 # which stages this role participates in
```

## 8. STATE.md contract (cross-session handoff)

`STATE.md` is the single source of truth for "where are we". Schema:

```markdown
# SDLC State: <feature/topic>
stage: onboard | spec | plan | build | validate | review | done
status: in-progress | gated | blocked
updated: <stamp passed in by caller>
validate-modes: [correctness, e2e, eval-bench]   # resolved this run from the diff (see §6.1)

## Gates passed
- [x] spec approved
- [ ] tests written (red)
- [ ] ...

## Active roles (from last diff scan)
- server-dev, client-dev

## Changed-files snapshot
<paths from last git diff>

## Decisions log
- <date> chose X over Y because ...

## Next action
-> invoke sdlc-plan
```

Cross-session flow:

```
Session A: /sdlc → reads empty STATE → routes to sdlc-spec → writes spec.md,
           STATE: stage=spec done, next=plan
   ↓ /clear or next day
Session B: /sdlc → reads STATE(stage=plan) → resumes sdlc-plan, no context replay needed
```

## 9. Distillation loop ("时用时新")

Reuses existing `explorer-repo-report` + `sop-extractor`:

```
analyze a new skill/repo  →  extract reusable patterns  →
append to the matching stage / role card / validate-mode playbook  →  tag `distilled-from: [<project>]`
```

The owned knowledge base grows and always stays "our understood version".
`distillation-loop.md` documents this procedure.

## 10. Compatibility rules (load-bearing)

Compatibility comes from one decision: **knowledge + state live in plain files**, never
only in the skill-invocation context. Four rules enforce it:

| # | Rule | Solves |
|---|------|--------|
| 1 | Knowledge + state are plain files (`references/`, `.sdlc/STATE.md`) | any caller can use it without the Skill mechanism |
| 2 | STATE is single-writer; parallel work writes separate files (`review/<role>.md`) | sub-agent / workflow fan-out concurrency races |
| 3 | Procedure is platform-agnostic; orchestration is an accelerator, not a dependency. Core stages run with read/edit/shell only; parallel role review uses Agent/Workflow on Claude and **degrades to sequential on Codex**. No hard dependency on Workflow / AskUserQuestion. | Codex + portability |
| 4 | Maintain `.agents/skills/sdlc*` symlinks | Codex repo-local discovery |

| Scenario | Compatible? | Notes |
|----------|-------------|-------|
| Sub-agent | ✅ | fresh-context agent reads STATE + role cards; rule 2 prevents races |
| Workflow tool | ✅ native fit | stage=phase, role lens=parallel fan-out (each writes own findings, then merge), STATE=resumable journal; workflow agent prompt points at reference files |
| Codex | ✅ with rules 3+4 | base read/write/shell maps to Codex tools; graceful degradation of fan-out |

## 11. v1 scope vs grow-over-time

| v1 (build now) | Later (via distillation loop) |
|----------------|-------------------------------|
| `sdlc` driver + STATE/PROFILE contracts | full榨干 of gsd's 73 skills |
| `sdlc-onboard` (brownfield entry → PROFILE.md + surface map) | deep big-data eval mode |
| 6 process skills: onboard/spec/plan/build/validate/review skeleton | complex gates / CI wiring |
| 3 validate-mode playbooks: correctness / e2e (Web+OpenAPI; **App** sequenced last) / eval-bench | App-tooling deep integration once chosen |
| 6 role cards: qa, design, client-dev, server-dev, big-data (**stub**), architect (全链路接缝, post-build add) | big-data full lens |
| `role-routing.md` v1 (Python + TS globs) + `distillation-loop.md` | more language globs |
| README + dogfooding symlinks + `.agents/skills` sync | |

**v1 language scope: Python + Web (TS).** Test exec abstraction targets pytest/coverage +
vitest/playwright/tsc first. **First dogfood target: agentic-config-demo** (`agentic-config-demo/`).

## 12. Housekeeping

- `planner-breakdown-sdlc` is **NOT empty** (correction: 6.4KB, has L1-L4 complexity tiering).
  It is **absorbed** by `sdlc-plan`, contributing its L1-L4 tiering — not deleted as a stub.
- This whole family is a cohesive `sdlc-*` namespace sharing one `references/` and one
  STATE/PROFILE contract — it counts as *one* thing (1 driver + 6 process skills), not a
  pile of scattered skills.

## 13. Open questions / future

- **App E2E tooling** — Web (Playwright MCP) and OpenAPI confirmed; mobile-automation tool
  (Appium / Maestro / device-farm) is a **build-time research spike** (App modality sequenced
  last). Default lean: Maestro for simplicity, verify before committing (per "先验证再记录").
- `role-routing.md` globs tuned to agentic-config-demo + Python/TS first; more repos later.
- Whether to add a `scripts/validate-state.mjs` linter (like workflow-creator's validator).
- Eventual GitHub publish: license, README polish, install instructions.

## 14. Resolutions (2026-06-04)

| Item | Resolution |
|------|-----------|
| **Reinventing gsd?** | **No** — confirmed by the source map: every target's "build-what" is dominated by (a) stripping runtime deps and (b) our 3 differentiators (routing/surface-map, portability, ownership). We distill gsd's methodology, not its runtime. |
| **First dogfood target** | **agentic-config-demo** (`agentic-config-demo/`) |
| **v1 language scope** | **Python + Web (TS)** |
| **big-data role** | **stub card** in v1 (now seeded from agency-agents `data-engineer`, so a rich stub at low cost) |
| **Supplementary role source** | **agency-agents** (`workspace/agency-agents/`) — fills big-data / design-UX / client-mobile gaps. See source map §6. |
| **Portability patterns to reuse everywhere** | gsd `text_mode` (AskUserQuestion → numbered text) + gsd-map `Task-or-sequential` degradation. |
| **Build orchestration** | Fan-out authoring grounded in the source map, in dependency waves (foundation → role cards + validate modes → process skills → integration/verify). |

### 14.1 Post-build evolution (2026-06-04, after v1 authored + 2-round review)

| 演进 | 内容 |
|------|------|
| **push 前 SDLC 检查** | 本地 `pre-push` hook(纯 shell, 无 secret), 读 STATE 的 `sdlc-gate: PASS reviewed-head=<sha>`; onboard 脚手架自检主动询问安装。CI 路线降级为团队场景可选(secret 不进容器) |
| **R7 配置/agent 定义型工程** | onboard + routing 识别 agentic-config-demo 这类"源即声明式配置"项目(agents/workflows/roles JSON)→ server-dev+correctness, 非 eval |
| **发散 ideation pass** | 蒸馏 adhd → `references/divergence-frames.md`; spec §2.4 选方案前的可选门控发散(开放+高风险+开放措辞); 补审计缺口 #3 的"做大"方向 |
| **build wave 并行执行** | 吸收 gsd-execute-phase 完整 wave 模型: 同 wave 多阶段 Task-or-sequential fan-out(一阶段一 agent), 安全靠 plan §4.3 同 wave 无文件冲突 |
| **设计契约前置** | spec §2.6b(对称 eval §5): UI 工作产出 `DESIGN.md`; 闭合 design 卡引用却无人产出的洞(审计缺口 #2) |
| **architect 角色** | `roles/architect.md` + routing R8(跨 ≥2 面/全链路触发): 全链路数据结构对齐/跨边界契约/单一事实源/blast-radius。角色 5→6 |
| **ai-readiness 角色 + arch-doctor 吸纳决定** | 两轴拆解 arch-aifriendly-doctor:**知识**(10 维 + 23 模式)→ `roles/ai-readiness.md`(角色卡);**扫描**→ onboard Phase A(已);**评估**→ onboard Phase D 只读体检写 PROFILE;**整改**→ remediation feature(work-type)走标准 loop。**不另起 `sdlc-remediate` skill**(整改是 feature,不是技能;接手层=onboard 读 + 改造走流程)。角色 6→7 |
| **并发边界硬门** | `skills/sdlc/scripts/sdlc-guard`(随技能自包含) + `pre-commit` hook(git 执行、模型绕不过)+ STATE branch/worktree 戳 + driver §1.1。多特性并行引导用 worktree;重型 per-feature 引擎故意缓做 |
| **work-type 流程画像** | STATE `work-type`(feature/remediation/hotfix)中央旋钮:偏置 granularity、不取消硬门。driver §1.2 + `/sdlc next` |

> 审计缺口收口(全清): #1(受评接收纪律)**已补**(`references/receiving-feedback.md` + build/review fix 点引用); #2(设计契约)**已补**(spec §2.6b); #3(范围塑造)**已补**(divergence §2.4 做大 + scope-shaping §2.4b 显式 10星/挑战前提/EXPAND-HOLD-REDUCE-SELECTIVE + scope-guard 防蔓延, 三者凑齐)。
