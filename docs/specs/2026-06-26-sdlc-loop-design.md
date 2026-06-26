# 设计:sdlc-loop —— 测试驱动的自治特性循环(子系统 B)

> Date: 2026-06-26
> Status: approved
> 形态结论:**不新增顶层 skill**。用「playbook(`references/build-loop.md`)+ driver 子命令(`/sdlc loop`)」表达,复用既有 8 阶段,不重写。
> 上游:`docs/specs/2026-06-03-sdlc-pilot-design.md`(主设计);`sdlc-backlog` 早已把 ready-queue 标注为"喂给未来的 sdlc-loop"——本 spec 即兑现那个"子系统 B"。

---

## 1. 问题 / 目标

现状是"**人推一步、它走一步**":每个特性要人工逐阶段催 spec→plan→build→validate→review→ship。
`sdlc-backlog` 产出的 **ready-queue**(解依赖的就绪叶 JSON)一直悬空——没有调度器消费它。

目标:补上 **loop 编排层**——一条轻量、可移植、文件式的**测试驱动自治循环**:
从 ready-queue 取就绪叶 → 自动跑完单特性主线 → 退场 → 取下一片,直到队列干。
**TDD 是循环的内核**(ground truth=测试执行,不是模型自我感觉)。

## 2. 非目标(YAGNI)

- **不新增顶层 skill**(铁律 #1)。loop = playbook + driver 入口,复用 8 阶段。
- **不做声明式 YAML 引擎 / 不依赖 Workflow**(那是 spec-kit 的重量级路线,违背可移植铁律)。loop 是"模型读薄 playbook + STATE 续接",Codex 也能跑。
- **不重写 build/validate/review 的内部纪律**——loop 只编排它们,各阶段 playbook 不动。
- **不绕过硬门**:review / 安全 open=0 / 覆盖率门一律照旧;loop 只自动化"推进",不削弱"把关"。
- **不做并发跑多特性**:同分支并行第二特性会 STATE 互覆盖(driver §1.1 已禁);loop 串行取叶,真要并行靠 worktree(collaboration-discipline)。

## 3. 关键认知(决定设计形态)

### 3.1 零件已造好,只差一根轴 + 一盏灯
loop 需要 5 样:①工作源 ②取就绪单元 ③RGR 内核 ④可恢复完成账本 ⑤"该不该再转一圈"判定器。
sdlc-pilot 已有前四样:**ready-queue(油)= backlog.py · RGR(发动机)= sdlc-build · STATE+叶 status(里程表)**。
唯一真缺 = ⑤**收敛判定器(converge oracle)**。本 spec 补:一根薄轴(`/sdlc loop` + build-loop.md)+ 一盏完工检查灯(converge)。

### 3.2 loop 是 meta 子命令,不是新 stage
与 `/sdlc evolve`、`/sdlc next` 同范式:**不进 STATE 的 stage 枚举**,不动契约。
它在既有 stage 之上做编排;每片叶仍走标准 stage 并写标准 STATE。
→ 因此本特性按 evolve 设计 §4 guard **判为结构性改动**(新建 playbook + 动 driver),
**实现走完整 `/sdlc`**(本 spec 即其产物),**不走 evolve**。

### 3.3 v1 留白给 evolve(时用时新)
v1 只落**最小骨架**;5 个权威 loop 先进思路(见 §7)**留待 evolve 逐条 append 进 build-loop.md**——
这正是 distillation-loop + evolve 的本意:把外部方法论一条条蒸馏进已存在卡,标 `distilled-from`。

---

## 4. 边界:小改 vs 大改(沿用 evolve guard)

| 维度 | 本特性(造 loop) |
|---|---|
| 判据 | 新建 `references/build-loop.md` + 改 driver `SKILL.md` → **结构性大改** |
| 路径 | **完整 `/sdlc`**(onboard 已有 PROFILE → spec→plan→build→validate→review→ship) |
| 不碰 | role-routing 字典 / STATE stage 枚举 / validate-modes / languages —— **零契约改动**(loop 是 meta) |

> v1 之后,往 build-loop.md append 一条原则 = **小改 → 走 `/sdlc evolve`**。两者边界与 evolve 自身完全一致。

## 5. loop 主循环(v1 最小骨架)

```
/sdlc loop:
  前置: driver §1.1 边界自检(防串台) + 确认 .sdlc/requirements/ 存在
  while ready-queue 非空 且 未达 max-iterations:
     leaf = readyqueue[0]                          # ① 工作源: python3 scripts/backlog.py readyqueue
     起 feature 分支/worktree → 写 STATE(source-leaf=leaf)
     spec(若该叶无 spec) → plan(拆成扁平可勾任务)    # 复用 sdlc-spec/sdlc-plan
     build: 逐任务 RED→GREEN→verify(测试=ground truth) # 复用 sdlc-build RGR
     validate(按改动 resolve 模式) → review(多角色+安全门)# 复用,硬门不短
     ── converge oracle(⑤,本特性新增最小版):
        通过 = 测试全绿 + 满足 spec done-criteria
        不通过 → 把缺口 append 成新任务,回 build,不退出该叶
     通过 → ship → backlog Retire(标叶 shipped, 解锁下游) # checkpoint=每叶独立可交付
  done(队列干 = 全局收敛) 或 gated(达 max-iter/遇 blocker → 停, 回报)
```

**单写者**:仍只有 driver 写 STATE;loop 串行取叶,无 fan-out 竞态。
**可恢复**:崩了重进 → 读 STATE + 叶 status + 任务 `[X]` 续接(状态全在文件,上下文可丢弃)。

## 6. converge oracle(v1 最小定义)

> 它是循环的**不动点检测器**,回答"这片叶真做完没"(而非"任务划完没")。

- **输入**:本叶 spec 的 `## Done Criteria` + 测试执行结果 + `backlog.py readyqueue`。
- **通过判据**(全满足):① correctness 全绿(命令+exit 0) ② 每条 done-criteria 有证据 ③ review gate PASS。
- **不通过**:列出未满足的 done-criteria → append 成 build 任务 → 回 build(不退出该叶,不误判完成)。
- **轻**:复用既有测试执行 + done-criteria,不新建脚本、不做跨工件大报告。
- **全局停止**:`readyqueue` 空 = 所有叶 shipped = loop done。

## 7. 留给 evolve 的 5 条先进思路(v1 后逐条 append)

> 蒸馏自权威 agent loop 研究;每条 = build-loop.md 的一节 + `distilled-from` 溯源。

| # | 思路 | 源 | append 进 build-loop.md 的内容 |
|---|---|---|---|
| E1 | **复述(recitation)** | Manus context-engineering | 每圈开头重读 spec done-criteria + 未勾任务,把目标顶回注意力,抗长循环跑偏 |
| E2 | **失败写教训** | Reflexion | 红/失败先落一行根因教训进 STATE.Decisions,下一轮迭代先读本叶教训栈 |
| E3 | **自生成测试强化 oracle** | AlphaCodium | converge 不止跑计划测试,额外生成边界/反例测试 + 测试锚点防改 A 坏 B |
| E4 | **独立外脑交叉验证** | Anthropic evaluator-optimizer | review/converge 处可选调 Codex 只读复核(探测→调用→优雅跳过;**永不卡 loop**) |
| E5 | **停止条件 + ground-truth** | Anthropic building-effective-agents | 收紧停止:测试=每步 ground truth;max-iter + 三振升级 + 人工 checkpoint;无新鲜证据不声称 done |

## 8. 要改/新增的文件(实现清单)

| 文件 | 动作 | 说明 |
|---|---|---|
| `skills/sdlc/references/build-loop.md` | **新增** | loop playbook(数据非 skill,任何引擎可执行):§1 边界 §2 工作源 §3 单叶内循环 §4 converge §5 checkpoint §6 文件态/可恢复 §7 停止 §8 可移植。留 §E 占位给 evolve |
| `skills/sdlc/SKILL.md` | 改 | §1.2 加 `/sdlc loop` 子命令入口 + 触发语;§4 路由表加一行 loop 引用 build-loop.md;description 补 loop 触发 |
| `CLAUDE.md` | 改 | "怎么迭代"表加一行"加/改 loop 编排"(走 evolve append) |
| `README.md` | 改 | "怎么用"表加一行 loop 场景 |
| `CHANGELOG.md` + 版本 | 改 | minor(新增能力)0.16.2→0.17.0;plugin.json + marketplace.json 同步 |

> 不新增:顶层 skill、role-routing/STATE/枚举改动、运行时依赖、backlog.py 改动。全长在 references + driver 入口,符合反膨胀红线。

## 9. 可移植性

- 交互:所有提问 text_mode;不硬依赖 AskUserQuestion。
- 并行:loop 本质串行取叶(单写 STATE);worktree 并行靠 collaboration-discipline,非 loop 内置。
- 工具:核心只需 Read/Edit/Bash/Grep + git + `backlog.py`;Codex 交叉验证(E4)是机会型增强,缺失即跳。
- Codex:build-loop.md 是纯数据,`.agents/skills/` 软链可发现,任何引擎照跑。

## 10. 怎么算 done(验收)

- `build-loop.md` 落地,被 driver §1.2/§4 + CLAUDE.md + README 引用(无孤儿)。
- `/sdlc loop` 入口在 driver 可触发,描述清"工作源/单叶内循环/converge/停止"。
- converge oracle 定义明确:通过=测试绿+done-criteria+review;不通过=append 回 build;空队列=全局 done。
- `bash scripts/validate-skills` PASS(结构 lint 不破)。
- 版本/CHANGELOG 同步;Codex 复核无 CRITICAL。
- 5 条先进思路在 §7 列明,留 build-loop.md §E 占位,可由后续 evolve 逐条 append。

## 11. 实现路径(dogfood)

本能力按 §4 判为大改 → 走完整 `/sdlc`:
spec(本文件)→ plan(§8 多文件同步)→ build(写 build-loop.md + driver)→ validate(`validate-skills` lint)→ review(skill-maintainer 透镜 + Codex 外脑)→ ship(升 0.17.0 + CHANGELOG)。
v1 落地后,E1–E5 各走一次 `/sdlc evolve`(本次以同分支 append 提交模拟,owner 不直推 main、改为推特性分支不合并)。

## 12. Deferred Ideas

- **loop 内 worktree 并行多叶**(无依赖叶同时跑)—— Why:吞吐;Trigger:串行成瓶颈时;Breadcrumbs:collaboration-discipline §5.4 监督式多-agent loop 已有原型。
- **backlog.py 加 `converge` 子命令**(把 done-criteria 核对脚本化)—— Why:确定性;Trigger:模型判定不稳时;Breadcrumbs:§6。
- **loop 进度看板**(board.py 叠加 loop 实时态)—— Why:可观测;Trigger:长跑需盯进度时;Breadcrumbs:0.16.0 live badge。
