---
name: sdlc-build
description: >
  SDLC 主线的"先测后码"实现阶段(red→green)。按已批准的 plan.md 逐任务做 TDD:写失败测试→看它失败→
  最小实现→看它通过→重构;遇到 bug 切入系统化调试子循环(根因优先,bug 三分类),再回到 TDD。
  入口先做改动代码→角色+模式解析(读 driver 的 role-routing),把命中的角色卡作为实现视角。
  触发于:用户说 "开始实现"、"进入 build"、"按 plan 写代码"、"red green"、"做这个任务"、"实现这个特性"、
  "tdd 一下"、"边写边测"、"继续实现下一个任务"、"resume build";也在 STATE.stage=build 时由 sdlc driver 路由进入。
  本 skill 只负责把 plan 的任务以 TDD 方式落成代码 + 调试。它不写 spec(sdlc-spec)、不拆任务(sdlc-plan)、
  不跑验收级验证(sdlc-validate)、不做多角色评审(sdlc-review)。
---

# sdlc-build — 先测后码(Test-first red → Implement green)

你是 SDLC 主线的**实现工**。职责:把 `plan.md` 里已批准的任务,**一个一个**用 TDD 落成可工作、被测试覆盖的代码;
其间任何 bug 都走系统化调试子循环。核心心法两条铁律:

```
铁律 1(TDD):   没有先失败的测试,就不写生产代码。
铁律 2(调试): 没有根因,就不写修复。
```

> 知识与状态全在纯文件,引擎 = Claude + Read/Edit/Bash/Grep。可移植:Claude / Codex 都能跑(§0)。
> **单写者原则**:本 skill 不直接写 `STATE.md`;进度由 `sdlc` driver 在阶段结束时写回(见 §7 交接)。

---

## 0. 可移植前置(每次入口先做)

> **共享 references 的位置(单一约定)**:本文引用的 `references/role-routing.md`、`references/roles/<role>.md` 等共享数据**物理上只在 sdlc 驱动器 skill 目录下**(`sdlc/references/`),不在本 skill 自己的目录里。解析时指向 `sdlc/references/...`(相对 skills 根)或经 dogfooding 软链接定位,**不要**当作相对本 skill 目录的路径去 Read。

继承 driver 的两条降级范式,本阶段照用:

### 0.1 交互降级 — text_mode
凡需向用户提问(确认分叉、确认 blast-radius、3-strike 升级),**优先用纯文本编号列表**,不硬依赖 AskUserQuestion:

```
我需要你选一个:
  1) 选项 A — 说明
  2) 选项 B — 说明
回复编号即可。
```

有 AskUserQuestion 时可用,但**回退路径必须是上面这种编号文本**。STOP 点就是 STOP:停下等用户,不要自作主张续跑。

### 0.2 执行模型 — wave 并行 / 串行 inline(Task-or-sequential)

> **源码协作纪律(本阶段部分)**:提交守 Conventional Commits;波内并行执行守 plan 的「同 wave 不碰同一文件」。分支模型 / worktree 决策 / 并行**前置合约** / 收敛安全网由 **driver §1.1 跨阶段加载**,见 `references/collaboration-discipline.md`。

**先分清两个层次**:
- **任务内**(一个任务的 TDD):**永远串行**,一个写手——red→green 是连贯推理,且不得两个写手同改一处。
- **任务间**:**可并行**,且"哪些能并行"已由 `plan.md` 的 **wave/depends_on** 算好。关键保证:plan 的硬规则「**同 wave 不碰同一文件**」(§plan 4.3)使得**同一 wave 内并行写代码是构造上安全的**。

**逐 wave 执行,每个 wave 二选一(探测决定)**:

```
进入 wave N(plan 已保证 wave 内无文件冲突):
  ├─ 有 Task/并行能力 且 本 wave ≥2 个独立**阶段(phase)**
  │     → fan-out:**一阶段一 agent**,各自跑完该阶段的所有任务(每任务完整 TDD)、各写各自文件、各写各自笔记
  │        orchestrator(build 主流程)收集结果 → 合并 → **单写 STATE**
  └─ 无并行能力(Codex/Gemini 等) 或 本 wave 仅 1 个阶段
        → 串行 inline 逐阶段→逐任务(= gsd-execute-phase --interactive 形态:无 subagent、单 session)

> 粒度:**并行单元 = 阶段(phase)**(plan 在 phase 上标 wave/depends_on)。一个阶段内的多个任务通常有 TDD 依赖(测试→实现),**阶段内仍串行**;并行发生在**同 wave 的不同阶段之间**。
  ↓
  wave 屏障:本 wave 全部 green + 出口门过,才进 wave N+1(后波依赖前波产物)
```

**三条安全铁律(并行也守住)**:
1. **同 wave 不碰同一文件** —— plan 的 wave 规则保证(并行的前提);若发现冲突 = plan 有 bug,回 plan 修波次。
2. **任务内严格串行单写手** —— 每个 agent 内部 TDD 照旧,绝不在一片代码上并发两个写手。
3. **STATE 单写者** —— 只有 orchestrator 写 STATE;并行任务只写各自产物/笔记(`review/<role>.md`、任务笔记)。

> 这是把 `gsd-execute-phase` 的**完整 wave 模型**吸收进来(上档 fan-out + 下档 --interactive 串行),不再只取串行那一半。只读工作(多文件取证)任何时候都可并行。

---

## 1. 入口条件(进来前必须成立)

| 条件 | 要确认的事 | 不满足时 |
|---|---|---|
| 有已批准的 `plan.md` | `<repo>/.sdlc/plan.md` 存在 | 回 `sdlc-plan`(无计划不实现) |
| 在 git 仓库且非 main/master 直写 | 当前在特性分支,不是直写主干 | 提示先切特性分支(text_mode 确认) |
| 已 resolve 出 active 角色 + validate 模式 | 读 `STATE.md` 的 `## Active roles`;若空则现做(§2) | 现场 resolve |
| spec 已批准(SDD 前置) | `STATE.md` 中 spec 状态为 approved | 回 `sdlc-spec` |

> 入口铁律:**改动代码→角色+模式解析先做**(§2),再开始第一个任务。这样实现时就带着对的视角(client-dev/server-dev/...)
> 和对的"完成后要跑什么验证"的预期。

---

## 2. 改动代码 → 角色 + 模式解析(入口必做)

进入 build 前,**动态重算**决策(决策是函数,不是存盘表)。完整算法见 driver 的
`references/role-routing.md` §1;这里只调用、不内联整表。

### 2.1 算改动集

```bash
git -C <repo> diff --name-only HEAD        # 工作区+暂存 vs HEAD
git -C <repo> diff --name-only --staged    # 仅暂存
git -C <repo> status --porcelain           # 含 untracked
```

合并去重 = changed-files。**全新特性尚无改动**时:退化为按 `PROFILE.surface-map` 中本特性要动的 surface
取默认角色/模式(用户在 spec 阶段已声明动哪块);随着第一个任务落地,后续任务重算时会有真实 diff。

### 2.2 解析(resolve)

对每个 changed path:① 先查 `PROFILE.surface-map` 的 glob(项目特化,优先);② 再叠加
`references/role-routing.md` §2 的通用规则;③ 取并集。基线始终叠加:

- 任意 diff → `qa`(baseline 角色) + `correctness`(baseline 模式)。
- 触及敏感面(auth / 支付 / 密钥 / 用户数据 / 原始 SQL / 文件系统 / 外部输入)→ 追加 `security` 视角。
- 触及 AI/模型/策略/prompt/evals → 标记 `eval-bench` 模式(本阶段不跑,留给 validate;但实现时按 eval 视角写)。

### 2.3 装载角色卡为"实现视角"

把命中的 `references/roles/<role>.md` 内容作为本阶段的**视角输入**(纯文件,不是起 sub-agent 人格)。
实现与调试时**对照角色卡的"关注点 / 好的样子 / 常见翻车"**:

- `server-dev` → API 契约、N+1/索引、错误处理、security 子节。
- `client-dev` → 语言 pitfall、re-render/bundle、offline-first。
- `qa`(baseline)→ 负路径、隔离、敌意输入,确保测试不只覆盖 happy path。
- `design` → (前端可见面)交互态、a11y——主要在 review/validate 兑现,build 时留意。

### 2.4 架构漂移检测
若某 changed path 落在 `PROFILE.surface-map` 任何 surface 之外(新建服务/首个移动目录)→ text_mode 告警
"架构漂移,建议刷新 PROFILE",**不阻断**,记入 STATE 的 decisions。

解析结果(active roles + validate-modes + changed-files)产出给 driver,在阶段末快照进 `STATE.md`(§7)。

---

## 3. 主循环:逐任务 TDD(red → green → refactor)

按 `plan.md` 的 **wave 顺序**推进(执行模型见 §0.2:同 wave 多**阶段**有并行能力则一阶段一 agent fan-out,否则串行 inline;后波依赖前波)。**无论并行还是串行,每个任务都跑完整 TDD 五拍状态机,任务内永远单写手串行。**

### 3.0 统一状态机(TDD ⊕ 调试子循环)

正常路径是 TDD;一旦 Verify 出现**非预期失败 / 已有测试挂 / 行为诡异**,切入调试子循环(§4),
根因修复后**回到当前拍重跑**。这张统一图是本 skill 的核心(无外部源画过):

```
            ┌──────────────────────────────────────────────────┐
            │                  TDD 主循环(每任务)               │
            │                                                  │
  ┌────────▶ RED ──▶ Verify-RED ──(失败正确)──▶ GREEN ──▶ Verify-GREEN ──(全绿)──▶ REFACTOR ──┐
  │          写失败测试   看它失败          写最小实现    看它通过                清理(保持绿)  │
  │                       │                              │                                    │
  │                  (失败不对/                      (该过没过 /                              │
  │                   测试一上来就过)                  别的测试挂了 /                          │
  │                       │                            行为诡异)                              │
  │                       ▼                              ▼                                    │
  │                 修测试本身                    ┌─────────────────────┐                     │
  │                 (在测错东西)                  │  调试子循环(§4)      │                     │
  │                                              │  根因优先 + bug 三分类 │                     │
  │                                              └──────────┬──────────┘                     │
  │                                                         │ 根因已修(代码 bug)              │
  └─────────────────────────────────────────────◀─────────┘ → 回到出问题的那一拍重跑          │
                                                            │ spec 缺失 / 设计缺陷             │
            下一个失败测试 ◀──────────────────────────────── REFACTOR ──▶ 升级 → STOP(§4.3)──┘
```

### 3.1 RED — 写一个失败测试

写**一个最小**测试,描述"应该发生什么"。要求:一次一个行为、名字说清行为、用真实代码(非必要不 mock)。

- 好:`test('retries failed operations 3 times', ...)` — 清晰、测真实行为、单一关注。
- 坏:`test('retry works', ...)` 用 mock 链测 mock 本身——在测 mock,不是测代码。

测试落在被测面对应的测试目录(由 §2 角色 / PROFILE 的测试约定决定)。

### 3.2 Verify-RED — 看它失败(强制,绝不跳过)

```
跑这一条测试(语言无关 runner,见 §5)
```

确认三点:① 是 **fail** 不是 **error**(语法错/导入错先修到能正常 fail);② 失败信息是预期的;
③ 失败是因为**功能没实现**,不是 typo。

- 测试**一上来就过** → 你在测已存在的行为,测试写错了 → 改测试。
- 测试**报错(error)** → 修到它能正常失败,再继续。

> 这一拍是 TDD 的灵魂:没看过它失败,你不知道它在测对的东西。

### 3.3 GREEN — 写最小实现

写**刚好让这条测试通过**的最简代码。不加测试没要求的特性、不顺手重构别处、不"提前优化"(YAGNI)。

- 好:循环重试三次就够。
- 坏:加 `maxRetries` / `backoff` / `onRetry` 一堆没人要的选项。

### 3.4 Verify-GREEN — 看它通过(强制)

```
跑这一条 + 跑相关已有测试
```

确认:① 本测试 **pass**;② **其它测试没被改坏**;③ 输出干净(无 error / warning)。

- 本测试没过 → 改**代码**,不是改测试。
- 别的测试挂了 → **现在就修**;若一时不解,切调试子循环(§4)。
- 行为诡异 / 间歇 → 切调试子循环(§4)。

### 3.5 REFACTOR — 清理(仅在全绿之后)

去重、改名、抽 helper。**保持绿**,不加新行为。改完重跑 Verify-GREEN 确认仍全绿。

### 3.6 任务收尾(去 subagent 化的两阶段自检)

蒸馏自 `subagent-driven-development` 的两阶段评审,但**去掉 subagent**,改为单 session 自检
(完整多角色评审在 `sdlc-review`,不在这):

1. **spec 符合自检**:本任务实现是否**恰好**满足 plan/spec 的验收标准?——没有缺漏(missing),也**没有多做**(extra,如塞了没要求的 flag)。多做 = 也要删。
2. **质量自检**:对照 §2 装载的角色卡"常见翻车"——魔法数抽常量、错误处理齐全、命名清楚、无调试残留(console.log/print)。

两项都过 → 该任务在 `plan.md` 标记完成,**进入下一个任务**(回 3.1)。任一项不过 → 当作"行为 bug"在本任务内修掉再过。

> **修复时守 `references/receiving-feedback.md` 纪律**:自检/调试发现问题 → **先核实该问题真成立、对本仓正确,再改;一次一项、各自验证**;别一被指出就乱改、别顺手加没要求的东西(YAGNI)。治"疯狂过度修复"。

### 3.7 连续执行(不要中途请示)
任务间**不要**停下问"要继续吗"。用户让你执行 plan,就一路执行。**唯一**的停下理由:
BLOCKED 无法自解、根因 3-strike 触顶(§4.3)、blast-radius 闸触发(§4.4)、或全部任务完成。

---

## 4. 调试子循环(遇 bug 切入;根因优先 + bug 三分类)

任何"非预期失败 / 已有测试挂 / 行为诡异 / 报错栈"都进这里。**铁律 2:没有根因,不写修复。**
四阶段(蒸馏自 systematic-debugging + investigate),完成一阶段才进下一阶段。

### 4.1 Phase 1 — 根因调查(动手修之前)

1. **认真读错误**:读完整栈、行号、文件、错误码——常含答案。
2. **稳定复现**:能确定性触发吗?不能 → 多试几次找触发条件(竞态/缓存/时序),先取证再说,别猜。
   - 前端崩溃类优先用 dev server(可读栈)而非 build 版(minified 栈)。
3. **查近期改动**:`git -C <repo> log --oneline -20 -- <受影响文件>`——回归说明根因在 diff 里。
4. **多组件系统先插桩取证**:CI→build→签名 / API→service→DB 这类,在**每个组件边界**打点(进什么、出什么、
   环境/配置是否透传),**先跑一次拿证据定位哪层断**,再深挖那一层。
5. **回溯数据流**:坏值从哪来?谁用坏值调它?一路往上追到**源头**,在源头修,不在症状处补。

### 4.2 Phase 2 — 模式签名比对(先认模式再修)

对照模式签名表(蒸馏自 investigate)。命中即知去哪找:

| 模式 | 签名 | 去哪看 |
|---|---|---|
| Race condition(竞态) | 间歇、与时序相关 | 共享状态的并发访问 |
| Null/nil 传播 | NoMethodError / TypeError / `Cannot read properties of undefined` | 可选值缺兜底(数据源 state/API 返回 undefined) |
| State corruption(状态损坏) | 数据不一致、部分更新 | 事务、回调、hook |
| Integration failure(集成失败) | 超时、响应异常 | 外部 API、服务边界;mock 格式 vs 真实返回不一致 |
| Configuration drift(配置漂移) | 本地通过、staging/prod 挂;配置反复被重置 | env var、feature flag、集成测试直写真实配置文件 |
| Stale cache(陈旧缓存) | 显旧数据、清缓存即好 | Redis / CDN / 浏览器缓存 |

同时:看 `git log` 同区域的历史修复——**同一文件反复出 bug 是架构异味**,不是巧合。

> **签名表没命中 + 模糊 bug(无已知根因)** → 可选跑 `references/divergence-frames.md` 出**假设类**(多框架发散,如 inversion / 移除承重假设 / 竞争者),再带回 Phase 3 逐一最小验证。门控同 divergence §0(开放+高风险才值得),无并行则串行跑几个框架。

### 4.3 Phase 3 — 假设与最小验证

1. **一次一个假设**,写下来:"我认为是 X,因为 Y"。具体,别含糊。
2. **最小验证**:插临时 log / 断言到疑似根因处,跑复现,看证据是否吻合。一次只动一个变量。
3. **假设错 → 回 Phase 1** 取更多证据,再立新假设。**不要**在旧修复上叠加新修复。
4. **3-strike 升级**:连续 3 个假设都不中 → **STOP**,这多半是**架构问题**不是简单 bug。text_mode:

   ```
   已测 3 个假设都不中,可能是架构问题而非简单 bug。
     1) 继续:我有新假设 — <描述>
     2) 升级人工评审:需要懂这套系统的人
     3) 加日志后观察:埋点等下次复现
   回复编号。
   ```

   **红旗**(出现就慢下来):"先快速修一下"(没有"先"——要么修对要么升级)、没追数据流就提修复(在猜)、
   每修一个又冒一个新问题(改错层了,不是改错代码)。

### 4.4 Phase 4 — bug 三分类 → 分类修复(关键决策点)

根因找到后,**先看 spec,再分类**(蒸馏自 hp-bugfix)。搜 `docs/specs/` `docs/adr/` 与 `.sdlc/spec.md`:

```
根因找到了
  ├─ spec 里有这个行为定义,代码实现与之不一致
  │     → 【代码 bug】从根因处修(不是补丁式 ?. 掉所有 .map);修完 grep 全仓查同类问题
  │
  ├─ spec 里没定义,但当前行为是 feature 的自然延伸
  │     → 【spec 缺失】先补 spec(回 sdlc-spec / 写 mini-ADR),再回来按 TDD 实现;不要硬修代码
  │
  └─ spec 里没定义,当前行为不符合设计意图
        → 【设计缺陷】不写代码,说清问题与连锁风险,引导回 sdlc-spec 想清楚该行为
```

**代码 bug 的修复规程(回到 TDD)**:
1. 先写一个**复现该 bug 的失败测试**(回归测试):没修时**失败**、修后**通过**——这就是 TDD 的 RED。
2. 从**根因**最小化修复:动的文件最少、行数最少,**别顺手重构邻近代码**。
3. **blast-radius 闸**:若修复触及 **>5 个文件**,STOP,text_mode 报告爆炸半径:

   ```
   这个修复触及 N 个文件,对 bug 修复来说爆炸半径偏大。
     1) 继续:根因确实横跨这些文件
     2) 拆分:先修关键路径,其余延后
     3) 重想:也许有更聚焦的做法
   回复编号。
   ```
4. 修完**回到出问题那一拍重跑**(Verify-GREEN / 全量),确认 bug 消失且**无回归**。

### 4.5 DEBUG REPORT(每次调试子循环收尾输出)

```
DEBUG REPORT
════════════════════════════════════════
Symptom:         <用户/测试观察到什么>
Root cause:      <真正错在哪>
Classification:  代码 bug | spec 缺失 | 设计缺陷
Fix:             <改了什么,带 file:line>
Evidence:        <测试输出 / 复现验证证明已修>
Regression test: <新增回归测试的 file:line>
Related:         <同区域历史 bug / 架构注记 / 受影响的 spec 是否需同步更新>
Status:          DONE | DONE_WITH_CONCERNS | BLOCKED
════════════════════════════════════════
```

修复改了行为(哪怕很微小)→ 同步更新相关 spec。修 bug 时若改了测试,确认是**因为行为变了**才改,不是测试错了。

---

## 5. 语言无关测试执行抽象(Python + TS,v1)

源里测试命令全是 npm/vitest。本阶段需**先发现 runner,再运行**;命令优先取 `PROFILE.test-commands`,
缺失则按下表探测。**永不跳过**"看它失败 / 看它通过"两拍——只是底层命令换。

| 语言/栈 | 单条/定向测试 | 全量 | 类型检查 | 覆盖率(留给 validate/correctness) |
|---|---|---|---|---|
| Python | `pytest <path>::<test>` 或 `pytest -k <name>` | `pytest` | `mypy <pkg>` / `pyright`(若配置) | `pytest --cov=<pkg> --cov-report=term-missing` |
| Web/TS | `npx vitest run <file>` / `npx jest <file>` | `npx vitest run` / `npx jest` | `npx tsc --noEmit` | `npx vitest run --coverage` |
| Web E2E | `npx playwright test <spec>`(归 validate/e2e 模式) | — | — | — |

发现顺序:① 读 `PROFILE.md` 的 `test-commands`;② 否则看 `package.json` scripts / `pyproject.toml` / `pytest.ini`;
③ 仍无则 text_mode 问用户该用什么命令,并建议把它写进 PROFILE 供下次复用。

> 数字化**覆盖率门控**(行/分支 ≥X% 否则 fail)不在 build——它是 `sdlc-validate` 的 correctness 模式职责。
> build 只保证"每个新函数有测试、都先红后绿"。

---

## 6. 出口门控(满足才算 build 完成,可进 validate)

逐项核对(对照 TDD 检查清单 + 本阶段铁律):

- [ ] `plan.md` 的本批任务全部完成并标记。
- [ ] 每个新函数/方法都有测试。
- [ ] **每条测试都先看它失败过**,且失败原因正确(功能缺失,非 typo)。
- [ ] 每条测试用最小实现转绿;现全部测试通过,输出干净(无 error/warning)。
- [ ] 测试用真实代码(mock 仅在不可避免时),覆盖边界与错误路径(qa 视角)。
- [ ] 期间所有 bug 都经调试子循环根因修复,各有回归测试,有 DEBUG REPORT。
- [ ] 行为变更已同步相关 spec;无调试残留(console.log/print/临时断言)。
- [ ] 类型检查通过(`tsc --noEmit` / `mypy`,若适用)。

**勾不全 = 跳过了 TDD,回去补**。全勾 → 报 `DONE`,交给 driver 路由到 `sdlc-validate`(跑 §2 解析出的 modes)。

完成状态协议:`DONE`(有证据)/ `DONE_WITH_CONCERNS`(完成但列出顾虑)/ `BLOCKED`(说明阻塞 + 已尝试)/
`NEEDS_CONTEXT`(说明缺什么)。3 次失败、不可验证的安全敏感改动、或无法验证的范围 → 升级。

---

## 7. 写什么进 STATE(经 driver 交接)

本 skill **不直接写 `STATE.md`**(单写者 = driver)。阶段结束把以下结果产出给 driver,由它写回:

```markdown
stage: build
status: in-progress | gated | blocked
validate-modes: [correctness, e2e:Web, ...]      # §2 本次 resolve 出的,留给 validate

## Gates passed
- [x] spec approved
- [x] tests written (red)            # 每任务都先红
- [x] implementation green           # 全绿
- [x] refactor done

## Active roles (from last diff scan)
- server-dev, client-dev, qa

## Changed-files snapshot
<本次 git diff 的路径>

## Decisions log
- <date> 修了 <bug> 根因=<...> 分类=代码bug;若架构漂移亦记于此

## Next action
-> invoke sdlc-validate (modes: correctness + e2e:Web)
```

并行产物(若有,如调试取证笔记)写各自文件,**不与 STATE 同写**(防竞态)。driver 据 `status` 决定:
`in-progress` 续到 validate;`gated` 停闸口列待批项;`blocked` 报阻塞不前进。

跨会话:新会话 `/sdlc` 读 `STATE(stage=build)` + 角色卡 + `plan.md` 即可接力,无需重放上下文。

---

## 8. 反 rationalization(看到这些念头 = STOP,回到铁律)

| 借口 | 现实 |
|---|---|
| "太简单不用测" | 简单代码也会坏,写测试 30 秒。 |
| "先写完再补测试" | 事后测试一上来就过,证明不了任何东西。 |
| "我手动测过了" | 手动是 ad-hoc,无记录、不能重跑。 |
| "都写了 X 小时,删了可惜" | 沉没成本。留着不可信的代码才是债。先写的代码请**删掉重来**。 |
| "留作参考,再补测试" | 你会去抄它 = 事后测试。删就是删。 |
| "先快速修一下,稍后查根因" | 没有"先"。第一刀定调,一开始就做对。 |
| "我看到问题了,直接修" | 看到症状 ≠ 懂根因。 |
| "多个修复一起上省时间" | 没法隔离哪个起效,还会引新 bug。 |
| "再试最后一个修复"(已失败 2+ 次) | 3+ 次失败 = 架构问题,质疑模式,别再修。 |
| "TDD 太教条,我很务实" | TDD 才务实:先抓 bug 比上线后 debug 快。 |

红旗(任一出现,删码 / 停手,回到 §3 或 §4 起点):代码先于测试、测试一上来就过、说不清测试为何失败、
"测试稍后加"、"它应该能修好"(没验证)、每修一个又冒一个新问题。
