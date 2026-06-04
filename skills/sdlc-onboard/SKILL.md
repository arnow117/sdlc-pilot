---
name: sdlc-onboard
description: >
  SDLC 主线的 brownfield 入口流程 skill。把一个【已有项目】测绘成机器可路由的项目记忆——
  产出 <target-repo>/.sdlc/PROFILE.md(含技术栈/约定/入口/已知风险 + ★surface-map：模块→glob→
  默认角色→validate 模式)。surface-map 是改动代码路由(driver §3)的可追踪输入,sdlc-pilot 独有、需自建。
  四阶段管道:纯 bash 采证 → 类型与入口识别 → 自建 surface-map → 写聚合 PROFILE.md + 出口门控。
  触发于:用户说 "onboard 这个项目"、"给这个仓库建 PROFILE"、"扫一下这个 codebase"、"分析已有项目准备走 SDLC"、
  "map this repo"、"建立项目记忆"、"sdlc-onboard";driver 判定为 brownfield(无 PROFILE 且 repo 非空)时也路由到此。
  也可被独立调用,为现有项目首次建立 SDLC 记忆。
  本 skill 是流程 skill(被 sdlc driver 路由),不分叉、不写 spec、不拆任务——只测绘并写 PROFILE.md。
---

# sdlc-onboard — brownfield 入口：测绘已有项目 → PROFILE.md

你是 SDLC 主线的**测绘师**。当一个已有项目第一次走 SDLC 流程时,driver 会先把你叫进来。
你的唯一交付物是 `<target-repo>/.sdlc/PROFILE.md` —— 项目级、长寿、被之后**每个** feature 共享的记忆,
其中最关键的是 **surface-map**(模块→glob→默认角色→validate 模式),它是改动代码路由的可追踪输入。

> **定位**:PROFILE = 项目级、建一次、共享;STATE = feature 级、短寿、每任务交接。本 skill 只写 PROFILE,**不碰 STATE**。
> **引擎**:Claude + Read/Edit/Bash/Grep。纯文件 + 纯 bash 采证,无 node 工具、无 `.planning/`、无外部 agent 人格依赖。
> **只读纪律**(蒸馏自 agency codebase-onboarding-engineer):测绘阶段**只读源码、只陈述代码里能查证的事实**,不改代码、不提改进建议、不臆测意图。唯一写动作 = 在结尾写 `.sdlc/PROFILE.md`。

---

## 0. 可移植前置(入口先做)

> **共享 references 的位置(单一约定)**:本文出现的 `references/role-routing.md`、`references/roles/<role>.md`、`references/validate-modes/<mode>.md`、`references/templates/*.md` **物理上只存在于 sdlc 驱动器 skill 目录下**(`sdlc/references/`)。它们不在各流程 skill 自己的目录里。解析路径时一律指向 `sdlc/references/...`(相对 skills 根),或经 dogfooding 软链接定位——**不要**当作相对本 skill 目录的路径去 `cat`/Read,那样会找不到。

本 skill 在 Claude 和 Codex 下都要能跑。两条降级范式(来自 driver §0):

### 0.1 交互降级 — text_mode
凡需向用户提问(确认技术栈推断、确认 surface-map 草案、确认是刷新还是新建),**用纯文本编号列表**,不硬依赖 AskUserQuestion:

```
我推断出这些 surface,请确认或修正:
  1) 接受这份 surface-map(推荐)
  2) 我要改某几行(说明改哪行)
回复编号即可。
```

### 0.2 并行降级 — Task-or-sequential
采证(Phase A)可拆成 4 个正交 focus(stack / arch / conventions / concerns,蒸馏自 gsd-map-codebase 的 4-focus mapper)。
**探测有无 Task/并行能力**:

- 有 Task → 可 fan-out 4 个测绘子任务,各自把发现**写进各自的临时笔记**(如 `.sdlc/onboard-notes/<focus>.md`),最后由本 skill 聚合成单一 PROFILE.md。
- 无 Task(Codex 等)→ **串行**逐 focus 跑同一份采证清单,直接累积到内存/单笔记,再聚合。

> 关键差异(对齐 spec):产物**永远是单一聚合 `PROFILE.md`**,不是 gsd-map 那样 7 个散文件。并行只是加速采证,不改变交付形态。

---

## 1. 入口条件(Entry conditions)

进入本 skill 应满足(由 driver 判定,独立调用时自检):

| 条件 | 检查 |
|---|---|
| repo 非空(有真实代码) | `find <repo> -type f -not -path '*/.git/*' -not -path '*/.sdlc/*' \| head -1` 有输出。**不要只靠 `git ls-files`**——目标可能是未跟踪子目录(在父仓里显示为 `??`、无嵌套 `.git`)或刚克隆未 init 的目录,`git ls-files` 会返回空、把真实项目误判为空仓。可先 `git -C <repo> rev-parse --is-inside-work-tree` 探测,再 fallback 到 `find`。 |
| 尚无 PROFILE.md,**或**用户要求刷新 | `ls <repo>/.sdlc/PROFILE.md` 不存在;或漂移触发(见 §6) |

两种入口模式:
- **新建**(no PROFILE)→ 走完整 Phase A→D。
- **刷新**(PROFILE 已存在,driver 检测到架构漂移)→ 只重跑受影响 focus + 重算 surface-map 相关行,**保留** Conventions/Known-risks 里仍成立的条目(append/tighten,不盲删)。

入口先 text_mode 报告并确认:

```
.sdlc/PROFILE.md: <无 / 已存在>
repo: 非空(检测到 <N> 个被跟踪文件)
→ 模式判定:<新建 / 刷新(架构漂移:<触发面>)>

  1) 按上述模式开始 onboard(推荐)
  2) 改为只跑一次现状审计(交回 driver: sdlc-validate --mode=e2e --scope=full-chain)
回复编号。
```

---

## 2. 步骤流程(四阶段管道)

```
Phase A 采证(纯 bash) → Phase B 类型+入口识别 → Phase C 自建 surface-map → Phase D 聚合写 PROFILE.md
```

### Phase A — 纯 bash 采证(Codex 友好,移植性反超 node 工具)

蒸馏自 `arch-aifriendly-doctor` 的 Phase 0 一键采证脚本(取其 bash 形态,丢 10 维评分本身)。
目标:**先把证据收齐,再下判断**——不靠印象,靠 `grep/find/wc/git` 的输出。

按 4 个正交 focus 采证(gsd-map-codebase 的 4-focus 骨架):

**focus = stack(技术栈 + 集成)**
```bash
cd <repo>
# 语言/包管理器/依赖清单
ls package.json pnpm-workspace.yaml pyproject.toml requirements*.txt go.mod Cargo.toml composer.json 2>/dev/null
[ -f package.json ] && grep -E '"(dependencies|scripts)"' -A20 package.json
[ -f pyproject.toml ] && sed -n '1,60p' pyproject.toml
# 框架信号(v1 重点:Python + Web/TS)
# 注意:--include 的 glob 必须单引号,否则 zsh 会 nomatch 报 "no matches found" 在 grep 跑之前就中止。
grep -rIl -E 'fastapi|flask|django|next|react|vue|svelte|express' . --include='*.py' --include='*.ts' --include='*.tsx' --include='*.json' 2>/dev/null | head
# 外部集成(DB/队列/第三方)
grep -rIoE 'postgres|mysql|sqlite|redis|kafka|mongodb|s3|openai|anthropic' . 2>/dev/null | sort -u | head
```

**focus = arch(结构 + 入口)**
```bash
# 顶层结构(只看 code-bearing 目录,排除 noise)
# 未跟踪/未 init 的目标 git ls-files 会返回空 → fallback 到 find。
{ git ls-files 2>/dev/null | grep . || find . -type f -not -path '*/.git/*'; } \
  | grep -vE '/(node_modules|dist|build|\.next|__pycache__|vendor)/' | sed 's|^\./||' | awk -F/ '{print $1"/"$2}' | sort -u | head -40
# 入口候选:启动文件/路由/CLI/导出
grep -rIl -E 'if __name__|app = (FastAPI|Flask)|createServer|app\.listen|uvicorn|def main\(' . --include='*.py' --include='*.ts' --include='*.js' 2>/dev/null | head
ls Procfile docker-compose.yml Dockerfile Makefile justfile 2>/dev/null
```

**focus = conventions(约定 + 风格)**
```bash
# 现有 AI 上下文 / 文档(P0,优先读)
ls CLAUDE.md AGENTS.md README.md 2>/dev/null
find . -name CLAUDE.md -not -path '*/node_modules/*' 2>/dev/null
# 测试约定 + 测试命令线索
find . \( -name '*.test.*' -o -name '*_test.*' -o -name 'test_*.py' -o -name 'conftest.py' \) -not -path '*/node_modules/*' 2>/dev/null | head
grep -rE '"test"|"build"|"lint"|"typecheck"' package.json 2>/dev/null
grep -rE '\[tool\.(pytest|coverage)\]' pyproject.toml setup.cfg 2>/dev/null
# 覆盖率门控线索(correctness 模式要用)
grep -rIoE 'cov-fail-under|coverageThreshold|--cov-fail-under=[0-9]+' . 2>/dev/null | head
```

**focus = concerns(已知风险 + 坑)**
```bash
# 大文件(>800 行)= 改动热点风险(未跟踪目标 fallback 到 find)
{ git ls-files 2>/dev/null | grep . || find . -type f -not -path '*/.git/*' | sed 's|^\./||'; } \
  | grep -E '\.(py|ts|tsx|js|go|rs)$' | xargs wc -l 2>/dev/null | sort -rn | awk '$1>800{print "  - "$2" ("$1")"}' | head
# 调试残留 / TODO / FIXME 密度
grep -rIcE 'TODO|FIXME|HACK|XXX' . --include='*.py' --include='*.ts' 2>/dev/null | awk -F: '$2>0' | head
# 敏感面(路由表 B2 要用):auth/支付/密钥/原始 SQL
grep -rIl -E 'auth|login|payment|billing|secret|credential' . --include='*.py' --include='*.ts' 2>/dev/null | head
```

> 采证只读不写;输出落进临时笔记(并行)或内存(串行)。**不在此阶段下评分/做改造**(那是 arch-doctor 的事,我们只借它的 bash 采证)。

### Phase B — 类型识别 + 入口定位

蒸馏自 `explorer-repo-report` 的 type-detection(P0/P1/P2 优先级)+ agency onboarding-engineer 的入口发现纪律。

1. **读 P0**:README + CLAUDE.md/AGENTS.md → 项目一句话定位(只取代码/文档里能查证的事实)。
2. **定类型**(按最显著信号归类,混合则取权重最高):
   - 工程/基础设施(database/engine/framework/library/SDK/server)
   - Agentic/AI(agent/LLM/prompt/RAG/eval)→ 提示:这类项目 surface-map 大概率含 `ai-strategy` 面 + eval-bench 模式。
   - 通用/其他(CLI/工具/脚手架)
3. **定入口**(agency onboarding-engineer Step 2):找出"系统怎么启动"的最小文件集——启动文件、路由表、CLI 命令、配置入口、迁移命令。
4. **提测试命令抽象**:从 Phase A 的 scripts/pyproject 线索归纳出 `{ unit, coverage, e2e, typecheck, build }`(语言无关命令,validate/correctness 据此发现并运行套件)。v1 对照 pytest/coverage + vitest/playwright/tsc。

> 三级输出纪律(agency onboarding-engineer):先一句话定位 → 五分钟高层(任务/输入/输出/关键文件) → 深入(代码流/边界)。本 skill 把这三级**沉淀进 PROFILE 的对应小节**,不另出报告。

### Phase C — 自建 surface-map(★核心差异化,无外部源)

这是 sdlc-pilot 独有、必须自建的那张表:**模块/面 → globs → 默认角色 → 默认 validate 模式**。
机制原型借自 `arch-aifriendly-doctor` 的 P13(git diff → 只跑该域)+ P23(模块 scoped 命令);表本身净新建。

构建步骤:
1. 从 Phase A 的顶层结构 + Phase B 的入口,切出**有意义的模块/面**(一个面 = 一类会一起改、共享角色/验证策略的代码区)。
2. 给每个面写 **globs**(用 POSIX/gitignore 语义,匹配该面的文件路径)。
3. 用 `references/role-routing.md` 的 §2 规则 + §3/§4 取值字典,给每个面**推荐默认角色 + 默认 validate 模式**:
   - 角色取值字典:`client-dev | server-dev | design | qa | big-data`(security 在 v1 不单列,敏感面由 server-dev/qa 卡的 security 子节承载)。
   - 模式取值字典:`correctness | e2e:Web | e2e:OpenAPI | e2e:App | eval-bench`。
4. **项目特化优先于通用规则**:这张表写进 PROFILE 后,路由时**覆盖** role-routing 通用兜底(spec §6.1)。所以这里要尽量贴合本仓真实结构,而不是照抄模板示例。

把 Phase A/B 命中的信号映射成面(典型示例,按实际增删):

| 信号(Phase A 发现) | surface 名 | globs(按实际) | 默认角色 | 默认 modes |
|---|---|---|---|---|
| 前端目录(tsx/vue/components/pages/app) | web-frontend | `web/**`, `components/**`, `app/**` | client-dev, design | correctness, e2e:Web |
| 原生/跨端移动(swift/kt/dart/ios/android) | mobile-app | `ios/**`, `android/**`, `mobile/**` | client-dev, design | correctness, e2e:App |
| 服务端接口(api/handlers/routes/controllers) | api | `services/api/**`, `**/handlers/**` | server-dev | correctness, e2e:OpenAPI |
| AI/模型/策略/prompt/evals | ai-strategy | `models/**`, `strategy/**`, `prompts/**`, `evals/**` | server-dev, qa | correctness, eval-bench |
| 数据管道/数仓/迁移(sql/pipelines/etl) | data | `pipelines/**`, `**/*.sql`, `migrations/**` | big-data | correctness |

5. **surface-map 自检**(三条硬约束,违反则回 Phase A 补采证):
   - [ ] 每个被跟踪的 code-bearing 顶层目录,要么落进某个面,要么明确归为"未归类"(不能静默丢)。
   - [ ] 每个面的角色/模式取值都在字典内(无野值)。
   - [ ] globs 之间尽量不互相吞并到歧义(一个 path 可命中多面是允许的,取并集)。

### Phase D — 聚合写 PROFILE.md + 自检

1. 把模板 `references/templates/PROFILE.md` 复制到 `<target-repo>/.sdlc/PROFILE.md`(目录不存在先建)。
2. 删掉模板的注释块与所有 `<填写...>` 占位,按 Phase A-C 的实测结果填:
   - 顶部 `tech-stack` + `test-commands`(Phase B 的命令抽象)。
   - `## Tech stack`(带"原因"列,蒸馏自 startup-claude-md-init 的 schema:每个技术为何选它)。
   - `## Surface map`(Phase C 产物,用模板里的 `面: globs[...] roles[...] modes[...]` 行格式)。
   - `## Conventions`(Phase A conventions focus,蒸馏自 startup-claude-md-init 的"禁止事项" + gsd-map conventions)。
   - `## Entry points`(Phase B 入口集,让全新上下文 agent 知道"从哪开始读/跑")。
   - `## Known risks`(Phase A concerns focus:大文件热点、无测试覆盖的危险面、N+1 等)。
3. 清理临时笔记(`.sdlc/onboard-notes/` 若用过)。
4. text_mode 把 surface-map 草案给用户确认(§0.1),用户改完再定稿。

---

## 3. 读写哪些 .sdlc/ 文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `<repo>/.sdlc/PROFILE.md` | **写(唯一交付物)** | 据 `references/templates/PROFILE.md` 模板填实测结果 |
| `references/templates/PROFILE.md` | 读(skill 内) | PROFILE 模板,复制后填写 |
| `references/role-routing.md` | 读(skill 内) | §2 规则表 + §3/§4 取值字典,给 surface 推荐默认角色/模式 |
| `<repo>/.sdlc/onboard-notes/<focus>.md` | 临时写/读(可选) | 仅并行采证用的中转笔记,Phase D 聚合后删除 |
| `<repo>/.sdlc/STATE.md` | **不碰** | STATE 是 feature 级,由 driver 单写;onboard 只管项目级 PROFILE |

> 兼容铁律:知识与状态都是纯文件;onboard 不并发写同一文件(单写者);并行采证写各自 focus 笔记,聚合时才合一。

---

## 4. 出口门控(Exit gates)

PROFILE.md 视为合格、可交回 driver,需**全部**通过:

- [ ] `<repo>/.sdlc/PROFILE.md` 存在,无残留 `<填写...>` 占位 / 注释块。
- [ ] `tech-stack` + `test-commands` 已据实填写。规则:**有套件就必须抓到对应命令**;**没有套件不是阻断,但必须显式标 `none`**(如 `unit: "none — 项目无测试套件"`),并在 `## Known risks` 记一条覆盖率缺口。绝不留空白。brownfield 真实项目常零测试,这恰恰是最需要建 baseline 的,不能卡在门口。(有可见面且存在 e2e 工具则填 `e2e`,有 TS 则填 `typecheck`。)
- [ ] `## Surface map` 通过 Phase C §5 三条自检(覆盖全、取值合法、无歧义)。
- [ ] 每个 surface 的角色/模式落在 role-routing 字典内。
- [ ] `## Entry points` 至少给出一个可执行的启动/入口线索。
- [ ] surface-map 草案已经 text_mode 给用户确认。
- [ ] **只读纪律守住**:onboard 期间未修改任何源码,唯一写动作是 PROFILE(+临时笔记)。

任一未过 → 停在门口(不前进),text_mode 列出缺项让用户补全或确认。

---

## 5. 写什么进 STATE(经由 driver,不自己写)

onboard **不直接写 STATE.md**(STATE 由 driver 单写,见兼容铁律 rule 2)。onboard 完成后,**向 driver 返回**以下结果,由 driver 落进 STATE:

- `stage: onboard` → 完成后建议 driver 将下一步设为 `spec`(brownfield 主线:Onboard → Spec)。
- Gates passed:勾选 `onboard：PROFILE.md 已建立 / 已确认无漂移`。
- Next action:`-> invoke sdlc-spec`(开始第一个 feature),或若用户只想审计现状 → `-> invoke sdlc-validate --mode=e2e --scope=full-chain`。
- 告知 driver:PROFILE.surface-map 已就绪,后续进 build/validate/review 时可被 `resolve(diff × surface-map × routing)` 消费。

返回话术(text_mode):

```
✅ onboard 完成。
  - 写出:<repo>/.sdlc/PROFILE.md
  - surface-map:<N> 个面(<列出面名>)
  - 下一步建议:开始第一个 feature → sdlc-spec
交回 driver:stage=onboard 完成,next=invoke sdlc-spec。
```

---

## 6. 架构漂移刷新(refresh 模式)

driver 在 session 开始会拿 `git diff` 路径对照 PROFILE.surface-map;若改动触及 map 里没有的面(新建服务、首个移动目录),会**重新路由到本 skill 做局部刷新**。刷新时:

1. 只对**漂移触及的面**重跑 Phase A 相关 focus + Phase B 入口识别。
2. 在 surface-map **新增/收紧**对应行(append/tighten,不推翻整张表)。
3. Conventions / Known-risks 里仍成立的旧条目**保留**;只追加新发现。
4. 同样过 §4 出口门控 + text_mode 确认后交回 driver。

> 这让"已跟踪的架构"保持诚实,而不需要重头 onboard 整个项目。

---

## 7. 蒸馏来源(distilled-from,供时用时新追溯)

- `gsd-map-codebase` — 4 正交 focus(stack/arch/conventions/concerns)+ Task-or-sequential 降级范式(取范式,丢 Task 子代理 / 7 散文件 / `.planning/`)。
- `arch-aifriendly-doctor` — Phase 0 纯 bash 采证清单(Codex 友好);P13 domain-aware check + P23 模块 scoped 命令(作 surface-map 机制原型)。取采证 + 机制,丢 10 维评分与改造管道。
- `explorer-repo-report` — type-detection(工程/agentic/通用)+ P0/P1/P2 探索优先级。取分类与优先级,丢 clone-to-workspace / 5W1H 报告外壳。
- `startup-claude-md-init` — PROFILE schema:技术栈表带"原因"列 + "禁止事项"。取 schema,丢"写 CLAUDE.md/对话问卷"形态。
- `agency: codebase-onboarding-engineer` — 只读纪律 + 入口发现 + 三级解释结构(1 行/5 分钟/深入)。取 mission/concerns,丢 agent 人格(emoji/vibe/memory)。

> 新蒸馏一个 onboard 相关源时,把可复用方法**追加进本 skill 的对应 Phase**,并在此登记 `distilled-from`(见 `references/distillation-loop.md`)。
