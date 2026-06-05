---
name: sdlc
description: >
  SDLC 主线驱动器 / 路由器 / 跨会话交接中枢。读取 <target-repo>/.sdlc/ 的项目记忆(PROFILE.md)与
  特性状态(STATE.md),按是否 brownfield 分叉(无 PROFILE 且 repo 非空→onboard;repo 空→spec;
  有 PROFILE→在 STATE.stage 续接),用 resolve(diff × surface-map × routing) 动态决定加载哪些角色卡、
  跑哪些 validate 模式,路由到对应的 sdlc-* 流程 skill,并把进度写回 STATE 供下次会话或 sub-agent 接续。
  触发于:用户说 "/sdlc"、"开始一个特性"、"走 SDLC 流程"、"继续上次的开发"、"resume sdlc"、
  "我要做一个新功能/改一个 bug 想走完整流程"、"接着开发"、"上次做到哪了"、"on this repo run sdlc"。
  也在用户要对一个项目首次启动结构化研发流程时主动建议。
  本 skill 是编排层(导演):自己不写 spec、不拆任务、不写测试、不跑验证、不做 review——
  它只分叉、解析路由、装载上下文、交接。具体工作交给 sdlc-onboard/spec/plan/build/validate/review。
---

# sdlc — 主线驱动器(driver / router / handoff)

你是 SDLC 主线的**导演**。你的全部职责是四件事,按顺序:

1. **读状态**：从 `<target-repo>/.sdlc/` 读 `PROFILE.md`(项目记忆)+ `STATE.md`(特性交接)。
2. **分叉**：决定本次该进入哪个阶段(onboard / spec / 续接 STATE.stage)。
3. **解析路由(resolve)**：用 `resolve(diff × PROFILE.surface-map × routing-rules)` 动态算出本次要
   加载哪些**角色卡**、跑哪些 **validate 模式**;并做 **架构漂移检测**。
4. **路由 + 交接(handoff)**：装载选中的角色卡进入对应流程 skill,流程结束后把结果写回 `STATE.md`。

> **铁律**：你不执行任何阶段的实际工作。看到该 spec 就转 `sdlc-spec`,该 build 就转 `sdlc-build`。
> 你只负责"去哪、带什么、记到哪"。所有知识与状态都在纯文件里,引擎=Claude + Read/Edit/Bash/Grep。

---

## 0. 可移植前置(每次入口先做,一次性)

本 skill 必须在 Claude 和 Codex 下都能跑。两条降级范式贯穿全程:

### 0.1 交互降级 — text_mode
凡需要向用户提问(确认分叉、确认漂移、选 scope),**优先用纯文本编号列表**,不硬依赖 AskUserQuestion:

```
我需要你选一个:
  1) 选项 A — 说明
  2) 选项 B — 说明
回复编号即可。
```

有 AskUserQuestion 时可以用它,但**回退路径必须是上面这种编号文本**。默认按 text_mode 写提示。

### 0.2 并行降级 — Task-or-sequential
凡可并行的工作(典型:`sdlc-review` 的多角色并行评审、`sdlc-onboard` 的多 focus 测绘):
**探测有无 Task/并行能力**——

- 有 Task → 可 fan-out,每个 agent 写**各自独立文件**(如 `review/<role>.md`),最后合并。
- 无 Task(Codex / Gemini CLI / Copilot 等)→ **串行 inline 执行**同一份 playbook,逐个写文件。

任何时候**不得**让两个写手同时写 `STATE.md`(单写者原则,见 §5)。

---

## 1. 读状态：定位并解析 .sdlc/

目标仓库 = 当前工作目录(或用户指定的 `<target-repo>`)。状态全部落在 `<target-repo>/.sdlc/`:

| 文件 | 角色 | 谁产出 |
|---|---|---|
| `PROFILE.md` | **项目记忆**(长寿):技术栈 / 约定 / surface-map / 入口 / 测试命令 | `sdlc-onboard`,漂移时刷新 |
| `STATE.md` | **特性交接**(短寿):stage / status / gates / active roles / changed-files / decisions / next | 每个流程 skill 经由本 driver 写 |
| `spec.md` `plan.md` | 阶段产物 | sdlc-spec / sdlc-plan |
| `validate/*.md` `review/*.md` | 验证 / 评审报告 | sdlc-validate / sdlc-review |

入口动作:

```bash
ls -la <target-repo>/.sdlc/ 2>/dev/null
```

- 读到 `PROFILE.md` → 解析 surface-map(模块→glob→默认角色→validate 模式)。
- 读到 `STATE.md` → 解析 `stage` / `status` / `Next action`。
- 都没有 → 进入分叉判断(§2)。

> 解析 PROFILE 的 surface-map 是后续 resolve() 的关键输入。schema 见设计 spec §4 / §6.1,
> 由 `sdlc-onboard` 写出。本 driver 只读、不写 PROFILE。

### 1.1 并发/边界自检(读完 STATE 立刻做)

读到 STATE 后,**先跑边界守卫再往下走**,防"串台 / 同分支并行第二个特性"把状态搞乱:

```bash
sh <sdlc 技能目录>/scripts/sdlc-guard    # 确定性检测:STATE.branch/worktree vs 当前
```

- **退出非 0(串台)** → 按它的提示停下:切回原分支续接,或为新工作**开 worktree / 新分支**(各自独立 `.sdlc`)。**不要**在串台状态下继续推进。
- **退出 0 但本次意图是"开新特性",而 STATE 仍有进行中特性** → text_mode 警告:
  ```
  ⚠ 当前分支已有进行中特性 '<F1>'(stage=<x>)。同分支并行第二个特性会文件冲突 + STATE 互覆盖。
    1) 为新特性开 worktree(推荐)  2) 切新分支  3) 先完成/暂存 F1
  ```

> **软硬两层**:本步是**软层**(driver 入口主动跑,Codex/无 hook 也有保护);**硬层** = `.git/hooks/pre-commit` 调同一个 `scripts/sdlc-guard`,**由 git 执行、模型绕不过**(onboard 脚手架自检会问装)。两层共用一份检测逻辑,单一事实源。
> 写 STATE 时记 `branch:` / `worktree:` 戳(STATE 模板已含),守卫据此比对。

---

### 1.2 work-type 流程画像 + `/sdlc next`

- **读 `STATE.work-type`**(feature / remediation / hotfix)并**透传给将进入的流程 skill**——它是"整条流走多重"的中央旋钮(定义见 STATE 模板)。各阶段读它自适应:remediation/hotfix 走轻(L1 / Skip-TDD / 跳无关契约),但**硬门(覆盖率 / 安全 open=0 / review / push gate)一律不短**。
- 新流程开始时若 STATE 无 work-type:默认 `feature`;若用户意图是"改造遗留/整 AI-readiness"→ 由 `sdlc-spec`/`sdlc-onboard` 定为 `remediation`;紧急修 → `hotfix`。
- **`/sdlc next`** = driver 的"直接推进"姿势:跑 §1.1 边界自检 → 读 `STATE.Next action` → 直接路由到下一步,不重复寒暄。(只是 driver 的一种调用,不是新 skill。)

---

## 2. 分叉：决定入口阶段

```
/sdlc → 读 .sdlc/
   ├─ 无 PROFILE.md  且  repo 非空(已有项目, brownfield)  → 先走 sdlc-onboard
   ├─ 无 PROFILE.md  且  repo 空(greenfield)              → 跳到 sdlc-spec
   └─ 有 PROFILE.md                                        → 在 STATE.stage 处续接特性循环
```

判定"repo 是否为空"(忽略 `.git`、`.sdlc`):

```bash
# 不要只靠 git ls-files——目标可能是未跟踪子目录(在父仓里显示为 ??、无嵌套 .git)
# 或刚克隆未 init,git ls-files 会返回空、把真实项目误判为空仓。
{ git -C <target-repo> ls-files 2>/dev/null | grep -vE '^\.(git|sdlc)/' \
  || find <target-repo> -type f -not -path '*/.git/*' -not -path '*/.sdlc/*'; } | head -1
```
有输出 = 非空。(与 sdlc-onboard 入口门同一套 find-fallback,保持一致。)

### 分叉决策(text_mode 确认)
读完状态后,**先说清你判定的入口,再让用户确认/改向**:

```
.sdlc/ 状态:
  - PROFILE.md: 无
  - repo: 非空(检测到已有代码)
→ 判定为 brownfield,建议先做 onboard 建立 PROFILE。

下一步:
  1) 走 sdlc-onboard(推荐)
  2) 跳过 onboard 直接 sdlc-spec(我已了解此项目)
  3) 只跑一次现状审计(sdlc-validate --mode=e2e --scope=full-chain)
回复编号。
```

有 PROFILE 时,直接报告 `STATE.stage` 与 `Next action`,默认续接:

```
读到 STATE: stage=plan, status=in-progress, next=invoke sdlc-plan
→ 续接 sdlc-plan。回复 "1" 续接,或 "2" 跳到其它阶段。
```

**没有 STATE.md 但有 PROFILE** = 一个新特性的开始 → 路由到 `sdlc-spec`,并初始化一份新的 `STATE.md`(§5 schema)。

---

## 3. 解析路由：resolve(diff × surface-map × routing)

在进入 **sdlc-build / sdlc-validate / sdlc-review** 这三个改动驱动的阶段前,**动态重算**决策。
决策是一个**函数,不是存盘表**——三个输入按稳定度分离:

| 输入 | 稳定度 | 来源 |
|---|---|---|
| 架构模型(surface-map:模块/glob/默认角色/模式) | 慢变,**已跟踪** | `PROFILE.md` |
| 路由规则(glob → 角色 + 模式) | 极少变,**已跟踪** | `references/role-routing.md` |
| 改动文件(`git diff`) | 每次都变,**临时** | 实时计算 |

### 3.1 算改动集

```bash
git -C <target-repo> diff --name-only HEAD          # 已暂存+未暂存 vs HEAD
git -C <target-repo> diff --name-only --staged      # 仅暂存
git -C <target-repo> status --porcelain             # 含 untracked
```
合并去重得到 changed-files。若是全新特性尚无改动,退化为**按 PROFILE.surface-map 的目标 surface** 取默认角色/模式(由用户在 spec 阶段声明要动哪块)。

### 3.2 解析(resolve)
对每个 changed path:
1. 匹配 `PROFILE.surface-map` 的 globs → 命中的 surface 给出**默认角色 + 默认 validate 模式**。
2. 再叠加 `references/role-routing.md` 的通用 glob 规则(语言/层级级,不依赖具体仓库)。
3. 取并集 → 得到本次 **active roles** 与 **validate-modes**。

基线规则(始终叠加,来自 role-routing.md):
- 任何 diff → `qa`(baseline 角色) + `correctness`(baseline 模式)。
- 触及敏感面(auth / 支付 / 用户数据 / 密钥)→ 追加 `security` 视角。
- 触及 AI / 模型 / 策略 / prompt / evals → 追加 `eval-bench` 模式。
- 触及用户可见面(前端 / 移动 / API)→ 追加 `e2e` 模式(选对应模态 Web/App/OpenAPI)。

> 路由细节与 glob 表是 `references/role-routing.md` 的职责;本 driver 只**调用**它来解析,不内联整张表。

### 3.3 架构漂移检测(tracker)
把 changed paths 与 `PROFILE.surface-map` 的 globs 比对:
**有 path 落在任何 surface 之外**(如新建服务、首个移动目录)→ 标记漂移,text_mode 提示:

```
⚠ 架构漂移:这些改动不在 PROFILE.surface-map 内:
  - mobile/ios/App.swift
建议刷新 PROFILE。
  1) 现在重跑 sdlc-onboard 的相关部分刷新 surface-map(推荐)
  2) 本次先继续,稍后再刷新
回复编号。
```

漂移不阻断,但要让用户知情。这保证"已跟踪的架构"不悄悄过时。

### 3.4 快照进 STATE
resolve 的结果(active roles + validate-modes + changed-files)**写进 `STATE.md` 作交接/审计快照**,
但**永不当作权威源**——下次进改动阶段时**重新 resolve**(diff 每次都变,存盘会过时)。

---

## 4. 路由 + 装载：进入流程 skill

确定阶段与 resolve 结果后,路由到对应 skill,并把上下文**作为纯文件引用**带过去:

| stage | 路由到 | 进入前 driver 要做的装载 |
|---|---|---|
| onboard | `sdlc-onboard` | 传 repo 根;产出写 `PROFILE.md` |
| spec | `sdlc-spec` | 传需求 / 现状;AI 工作时提示在此定 eval rubric |
| plan | `sdlc-plan` | 传 `spec.md` |
| build | `sdlc-build` | **先 resolve(§3)**,装载 active 角色卡(`references/roles/<role>.md`),传 `plan.md` |
| validate | `sdlc-validate` | **先 resolve**,传 resolve 出的 `validate-modes`,各模式 playbook 在 `references/validate-modes/` |
| review | `sdlc-review` | **先 resolve**,装载 active 角色卡;并行能力按 §0.2 探测,每角色写 `review/<role>.md` |
| ship | `sdlc-ship` | review PASS(`sdlc-gate`)后;环境晋级发布(dev→staging→canary→full),读 `PROFILE.Deploy` + `deploy-targets/<type>` |

主线形状(供参考,具体由各 skill 执行):

```
[brownfield] Onboard ─┐
                      ├→ Spec(SDD) → Plan → Build{red→green} →
[greenfield] ─────────┘   Validate{correctness | e2e | eval-bench} → Review → Verify → Ship{dev→staging→canary→full}
```

**装载角色卡 = 把 `references/roles/<role>.md` 的内容作为该流程 skill 的视角输入**(纯文件,任何 caller
都能读),不是起一个独立 sub-agent 人格。validate 模式同理:`references/validate-modes/<mode>.md` 是厚 playbook,
不是 skill。

任一 validate 模式也可**独立调用**:`/sdlc validate --mode=e2e --scope=full-chain` 做现状审计
(也充当 onboard 的 baseline 健康检查)。

---

## 5. 交接(handoff)：写回 STATE.md

每个流程 skill 跑完,**经由本 driver** 把进度写回 `STATE.md`。**单写者原则**:只有 driver 写 STATE;
并行产物各写各的文件(`review/<role>.md`、`validate/<mode>-report.md`),最后由 driver 汇总入 STATE。

`STATE.md` schema(由 caller 传入时间戳,不要自造时钟假设):

```markdown
# SDLC State: <feature/topic>
stage: onboard | spec | plan | build | validate | review | ship | done
status: in-progress | gated | blocked
updated: <由 caller 传入的时间戳>
validate-modes: [correctness, e2e, eval-bench]   # 本次 resolve 出的(§3.4)

## Gates passed
- [x] spec approved
- [ ] tests written (red)
- [ ] ...

## Active roles (from last diff scan)
- server-dev, client-dev

## Changed-files snapshot
<上次 git diff 的路径>

## Decisions log
- <date> 选 X 而非 Y,因为 ...

## Next action
-> invoke sdlc-plan
```

写 STATE 后,向用户报告"现在在哪 / 下一步是什么",并据 `status`:
- `in-progress` → 提示可继续下一阶段(或本会话直接续)。
- `gated` → 停在闸口,等用户确认(text_mode 列出待批项)。
- `blocked` → 报告阻塞原因,不前进。

### 跨会话流
```
会话 A: /sdlc → 读到空 STATE → 路由 sdlc-spec → 写 spec.md,
        STATE: stage=spec/done, next=plan
   ↓ /clear 或隔天
会话 B: /sdlc → 读 STATE(stage=plan) → 直接续 sdlc-plan,无需重放上下文
```
这就是"持久状态 + 无上下文重放"的交接:新会话 / sub-agent 只读 `STATE.md` + 角色卡即可接力。

---

## 6. 兼容性自检(载重规则)

进入任何路由前,确认这四条成立(它们让 sub-agent / Workflow / Codex 都能用):

| # | 规则 |
|---|---|
| 1 | 知识 + 状态都是纯文件(`references/`、`.sdlc/STATE.md`)——任何 caller 不靠 Skill 机制也能用 |
| 2 | STATE 单写者;并行工作写各自文件(`review/<role>.md`)——防 fan-out 竞态 |
| 3 | 流程平台无关;编排(Task/Workflow)是加速器不是依赖;无并行时降级串行(§0.2);交互用 text_mode(§0.1) |
| 4 | 维护 `.agents/skills/sdlc*` 符号链接 —— Codex 仓库内发现 |

---

## 7. 一次完整入口的动作清单(checklist)

1. [ ] `ls .sdlc/` 读 PROFILE.md + STATE.md
2. [ ] 判定分叉(§2),text_mode 报告并让用户确认/改向
3. [ ] 若进改动阶段(build/validate/review):`git diff` → resolve(§3) → 漂移检测
4. [ ] 装载 active 角色卡 + 选定 validate 模式(§4)
5. [ ] 路由到对应 `sdlc-*` 流程 skill(自己不执行其内容)
6. [ ] 流程返回后:写回 `STATE.md`(§5,单写者),快照 active roles / modes / changed-files
7. [ ] 向用户报告当前 stage / status / next action
