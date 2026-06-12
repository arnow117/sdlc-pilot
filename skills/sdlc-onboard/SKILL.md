---
name: sdlc-onboard
description: >
  SDLC 主线的 brownfield 入口流程 skill。把一个【已有项目】测绘成机器可路由的项目记忆——产出
  <target-repo>/.sdlc/PROFILE.md(技术栈/约定/入口/已知风险 + ★surface-map:模块→glob→默认角色→validate 模式;
  + AI-readiness 体检 + Deploy 探测)。surface-map 是改动代码路由的可追踪输入。
  触发于:用户说 "onboard 这个项目"、"给这个仓库建 PROFILE"、"扫一下这个 codebase"、"分析已有项目准备走 SDLC"、
  "map this repo"、"建立项目记忆"、"sdlc-onboard";driver 判定为 brownfield(无 PROFILE 且 repo 非空)时也路由到此。
  也可独立调用为现有项目首次建立 SDLC 记忆。
  本 skill 只测绘并写 PROFILE.md(只读源码),不分叉/不写 spec/不拆任务。四阶段管道(采证→类型→surface-map→聚合)见正文。
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

| 条件 | 要确认的事 |
|---|---|
| repo 非空(有真实代码) | 目录里有源码文件。**别只靠 `git ls-files` 判空**——目标可能是未跟踪子目录(父仓里显示 `??`、无嵌套 `.git`)或刚克隆未 init 的目录,只看跟踪文件会把真实项目误判为空仓;空时 fallback 到直接列文件。 |
| 尚无 PROFILE.md,**或**用户要求刷新 | `<repo>/.sdlc/PROFILE.md` 不存在;或架构漂移触发(见 §6) |

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

### Phase A — 采证(先把证据收齐,再下判断)

蒸馏自 `arch-aifriendly-doctor` 的 Phase 0(借"先采证后判断"的纪律,丢 10 维评分)。
**目标**:在归类型、建 surface-map 之前,先收齐客观证据——靠仓库里查得到的事实,不靠印象。
**怎么采你定**(grep/find/wc/git 这类只读工具,Claude/Codex 都有);本 skill 只约束**采什么**和**避哪些坑**。

按 4 个正交视角采证(gsd-map-codebase 的 4-focus 骨架),每个视角要回答的问题:

| 视角 | 要查证的问题 |
|---|---|
| **stack** | 有哪些语言/包管理器/依赖清单?用了什么框架?接了哪些外部系统(DB/队列/AI API)? |
| **arch** | 顶层结构长什么样?系统从哪启动(入口/路由/CLI/容器编排)? |
| **conventions** | 有无 CLAUDE.md/AGENTS.md/README?测试怎么组织、用什么命令跑?有无覆盖率门控? |
| **concerns** | 改动热点在哪(超大文件)?敏感面(auth/支付/密钥/原始 SQL)在哪?调试残留/TODO 多不多? |

**采证原则(避坑,作为原则而非某条命令的写法)**:
- **排噪声再统计**:`node_modules` / 构建产物(`dist` `build` `out` `.next`)/ agent 运行时产物(`.session*` `memory/` `archive/` `.backups/`)不是源码;统计"大文件""顶层结构"时先把它们剔掉,否则会把产物当源码、把汇总行当文件。
- **别只扫根目录**:monorepo / 子目录前端(如 `web/package.json`)只看仓库根会误判"无栈";依赖清单要连嵌套一起找。
- **只读不写**:采证阶段不碰源码、不下评分、不提改进(评分是 Phase D 的 AI-readiness 体检,改造是后续 feature)。输出落临时笔记(并行)或内存(串行)。

### Phase B — 类型识别 + 入口定位

蒸馏自 `explorer-repo-report` 的 type-detection(P0/P1/P2 优先级)+ agency onboarding-engineer 的入口发现纪律。

1. **读 P0**:README + CLAUDE.md/AGENTS.md → 项目一句话定位(只取代码/文档里能查证的事实)。
2. **定类型**(按最显著信号归类,混合则取权重最高):
   - 工程/基础设施(database/engine/framework/library/SDK/server)
   - Agentic/AI **代码**(agent/LLM/prompt/RAG/eval 的可执行实现)→ 提示:大概率含 `ai-strategy` 面 + eval-bench 模式。
   - **配置/agent 定义型**(源主要是 agents/workflows/processes/roles/employees/skill 的**声明式** JSON/YAML/SKILL.md,真实代码很少;如 agentic-config-demo——一家 AI agent 运营的公司,42 个 JSON 定义 + 3 个 Python 文件)→ 提示:走 R7,默认 `server-dev` + `correctness`,验证靠 **schema/契约一致性校验**,**不跑 eval-bench**(它不是 AI 模型代码);内嵌真实代码(*.py/*.ts)按其类型**单独归面**(如 med_crm CLI → server-dev)。
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
   - 角色取值字典:`client-dev | server-dev | design | qa | big-data | architect | ai-readiness | skill-maintainer`(architect 跨 ≥2 面由 R8 加载;ai-readiness 由 R9/体检加载;skill-maintainer 仅当被 onboard 的仓是 sdlc-pilot 技能体系自身时由 R10 加载,普通目标项目用不到;security 在 v1 不单列,敏感面由 server-dev/qa 卡的 security 子节承载)。
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
| 配置/agent 定义(agents/workflows/roles/employees/skill 声明式定义) | agent-config | `agents/**.json`, `workflows/**.json`, `processes/**.json`, `roles.json`, `people.json`, `employees/**.yaml`, `**/SKILL.md` | server-dev(+security 当含权限/授权矩阵如 roles.json) | correctness |
| 内嵌真实代码(配置型工程里少量 .py/.ts) | (按其类型归面,如) embedded-cli | `**/med_crm/**.py` 等 | server-dev | correctness |

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
   - `## AI-readiness 体检`(★只读评分,加载 `references/roles/ai-readiness.md` 的 10 维):对照 CLAUDE.md 级联 / scoped 命令 / 噪声 / 类型 / 测试 / LSP 就绪等,给一个**健康分 + 缺口清单**。**只评估、不整改**(守只读纪律);整改是后续 feature 的事。接手陈旧项目时,这是"它对 AI 友不友好、值不值得先改造"的判断依据。
     - **低分软推荐(保证 AI 友好的入口,不阻断 onboard)**:健康分 **< 阈值(默认 7/10)** → 写完 PROFILE 后用 text_mode **软推荐**起一个 remediation feature 补缺口(典型:CLAUDE.md 级联 / scoped 命令 / 类型 baseline / 测试 baseline / AGENTS.md 软链)。整改走标准 `spec→…→review`(L1 + 文档/配置改动走 Skip-TDD,review/verify 门不短)。**只推荐、不强制**——是否整改由用户决定;onboard 本身不因低分阻断。
   - `## Deploy`(只读探测,供 `sdlc-ship` 用):扫 `vercel.json` / `netlify.toml` / `Dockerfile` + k8s manifests / `.github/workflows/*deploy*` / 部署脚本(`deploy.sh` 等)/ 目标工程 `CLAUDE.md` 的部署段 → 判**部署目标类型**(static-site / container / vps / 未知)+ 记关键**配置位置**(项目名/集群/主机在哪个文件)。**只记位置与类型,不抄密钥、不臆造**;探不到就写"未检测到部署配置"。
3. 清理临时笔记(`.sdlc/onboard-notes/` 若用过)。
4. text_mode 把 surface-map 草案给用户确认(§0.1),用户改完再定稿。
5. **脚手架自检 — 询问装两个硬门 hook**(纯 shell,不跑 AI、无密钥;由 **git 执行,模型绕不过**,唯一逃逸 = 人 `--no-verify`)。检测 `<repo>/.git/hooks/{pre-commit,pre-push}` 是否已是 sdlc 的。缺则 text_mode 问:
   ```
   要装这两个硬门吗?(git 自动跑,模型绕不过)
     · pre-commit:并发/边界守卫 —— commit 前查 STATE 与当前 branch/worktree 是否串台(防同分支并行/串台)
     · pre-push:SDLC 检查 —— push 前核对 validate+review 已过(读 sdlc-gate 行)
     1) 都装(推荐)  2) 只装 pre-commit  3) 只装 pre-push  4) 跳过
   ```
   选装 → 把 `references/templates/hooks/pre-commit` / `pre-push` 拷到 `<repo>/.git/hooks/` 并 `chmod +x`;**仅 git 仓装**(非 git 仓跳过)。pre-commit 调 `sdlc-guard`(确定性边界检测,脚本在 `skills/sdlc/scripts/sdlc-guard`,随技能自包含),为让 hook 在任何安装方式下都能找到,把它拷/软链到 `<repo>/.sdlc/bin/sdlc-guard`(hook 优先找这里)。装完一句话说明各自管什么。

---

## 3. 读写哪些 .sdlc/ 文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `<repo>/.sdlc/PROFILE.md` | **写(主交付物)** | 据 `references/templates/PROFILE.md` 模板填实测结果 |
| `references/templates/PROFILE.md` | 读(skill 内) | PROFILE 模板,复制后填写 |
| `references/templates/hooks/pre-push` | 读(skill 内) | push 前 SDLC 检查模板,Phase D 用户同意后拷贝 |
| `references/role-routing.md` | 读(skill 内) | §2 规则表 + §3/§4 取值字典,给 surface 推荐默认角色/模式 |
| `<repo>/.git/hooks/pre-push` | **写(仅用户同意 + git 仓)** | Phase D 脚手架自检装的纯 shell 检查;装完即与 skill 解耦 |
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
- [ ] **只读纪律守住**:onboard 期间**未修改任何源码**;写动作仅限 PROFILE(+临时笔记)+ 用户明确同意后装的 `pre-push` hook(在 `.git/hooks/`,非源码)。
- [ ] (若为 git 仓)已询问是否装 push 前 SDLC 检查(Phase D 步 5);用户选了才装。

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
