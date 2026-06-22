---
name: sdlc-validate
description: >
  SDLC 主线的**验证中枢**(verification hub):build 之后、review 之前的独立验证阶段。
  根据本轮改动代码动态解析要跑哪些**验证模式**——correctness(总跑)/ e2e(改用户可见面)/
  eval-bench(改 AI/模型/策略)——依次执行各模式的厚 playbook,汇总写进 `.sdlc/validate/` 与 STATE。
  与 build 内的单元 TDD 不同:build 的 TDD 是"边写边红绿",validate 是"成体系地证明它真的能用"。
  触发于:用户说 "/sdlc validate"、"验证一下"、"跑 validate"、"测一遍"、"验收"、"e2e"、
  "跑端到端"、"评估这次模型/策略改动"、"eval"、"现状审计 / health check"、"baseline 健康检查";
  也在 STATE.stage=validate 时被 sdlc driver 路由进来,或某模式被单独点名
  (`/sdlc validate --mode=e2e --scope=full-chain`)。
  本 skill 是**调度层**:自己不实测——它解析改动→选模式→按序执行各模式 playbook→汇总门控→写交接。
  具体怎么测在 references/validate-modes/{correctness,e2e,eval-bench}.md。
---

# sdlc-validate — 验证中枢(调度层)

你是 SDLC 验证阶段的**调度员**。validate 是夹在 **build(实现)** 与 **review(评审)** 之间的
独立阶段,职责是:把"应该能用"变成"已验证能用"的硬证据。

> **定位铁律(与 build 区分)**
> - build 内的 TDD 是**边写边红绿**的单元循环(写一个测试→红→实现→绿)。
> - validate 是**成体系地证明它真的能用**:跑全量套件 + 覆盖率门控、走用户旅程、评 AI 质量。
> 两者不重复:build 关心"这个函数对不对",validate 关心"整个改动作为一个系统对用户/对质量站不站得住"。

> **调度层铁律**
> 你**不亲自实测**。你做四件事:① 解析改动→定模式;② 按序加载并执行每个模式的 playbook;
> ③ 汇总各模式门控成本阶段总门控;④ 写报告 + 回写 STATE 交接。
> 具体怎么跑测、怎么截图、怎么打分,全在 `references/validate-modes/<mode>.md`——你**读它、照它做**,
> 不把它的内容重抄进本文件。引擎 = Claude + Read/Edit/Bash/Grep(+ e2e 模式用 Playwright MCP)。

---

## 0. 可移植前置(每次入口先做)

> **共享 references 的位置(单一约定)**:本文引用的 `references/role-routing.md`、`references/validate-modes/<mode>.md` 等共享数据**物理上只在 sdlc 驱动器 skill 目录下**(`sdlc/references/`),不在本 skill 自己的目录里。解析时指向 `sdlc/references/...`(相对 skills 根)或经 dogfooding 软链接定位,**不要**当作相对本 skill 目录的路径去 Read。

本 skill 必须在 Claude 和 Codex 下都能跑。两条降级范式贯穿全程:

### 0.1 交互降级 — text_mode
凡需用户决策(选 scope、确认 eval 标准缺失时如何处理、确认 escalate),**优先用纯文本编号列表**,
不硬依赖 AskUserQuestion:

```
本次 validate 要验的范围,选一个:
  1) feature   — 只验本特性改动的旅程(默认)
  2) iteration — 验本迭代累积的几处改动
  3) full-chain — 全链路现状审计(也充当 onboard 的 baseline 健康检查)
回复编号即可。
```

有 AskUserQuestion 时可用,但回退路径必须是上面这种编号文本。默认按 text_mode 写提示。

### 0.2 并行降级 — Task-or-sequential
当本轮要跑**多个模式**(如 correctness + e2e + eval-bench)时,各模式产物互相独立、可并行:

- 有 Task/并行能力 → 可 fan-out,每个模式写**各自的报告文件**(`validate/<mode>-...-report.md`),最后汇总。
- 无并行能力(Codex / Gemini CLI 等)→ **串行**逐模式执行同一份 playbook,逐个写报告。

无论并行还是串行,**汇总写 STATE 由本调度层单点完成**(单写者原则,见 §6)。

---

## 1. 入口条件(什么时候进 validate)

满足任一即可进入本 skill:

| 入口 | 条件 | 来源 |
|---|---|---|
| **主线推进** | build 阶段门控通过(实现 green),STATE.stage 推进到 `validate` | sdlc driver 路由 |
| **续接** | STATE.stage 已是 `validate`(上次卡在某模式) | 跨会话 / sub-agent 接力 |
| **单模式点名** | 用户 `/sdlc validate --mode=<mode> [--scope=<scope>]` | 直接调用 |
| **现状审计** | `--mode=e2e --scope=full-chain`(无需经 build) | onboard 的 baseline 健康检查 |

**前置门(进 validate 前应已满足,否则先回退)**:
- build 的实现已 green(单元 TDD 通过)。若 build 未完成 → text_mode 提示先回 `sdlc-build`。
- 工作树状态可知(下面 §2 要读 git diff)。脏树不阻断,但 e2e 模式需要能原子提交修复,见其 playbook。

> 若 STATE.md / PROFILE.md 不存在(用户跳过了 driver 直接调本 skill):本 skill 仍可独立跑——
> 自己读 `git diff` 解析模式,产物落 `.sdlc/validate/`,但**不写 STATE**(无 driver 上下文时不假装交接),
> 在报告里注明"独立运行,未更新 STATE"。

---

## 2. 步骤流程(调度层主循环)

### Step 1 — 改动代码 → 角色 + 模式解析(先做)

validate 是**改动驱动**阶段。进来第一件事是解析"本轮该跑哪些模式",**复用 driver 的 role-routing**,
不自己另发明一套。

```bash
# 算改动集(合并去重)
git diff --name-only HEAD          # 已暂存 + 未暂存 vs HEAD
git diff --name-only --staged      # 仅暂存
git status --porcelain             # 含 untracked
```

拿到 changed-files 后,**读 `references/role-routing.md`**,按其 §1 决策算法解析:

```
modes := resolve( changed-files × PROFILE.surface-map × role-routing 规则 )
```

- 先查 `<repo>/.sdlc/PROFILE.md` 的 surface-map(项目特化,优先级高):命中 surface → 取其默认 validate 模式。
- 未被 PROFILE 覆盖的路径 → 套 `role-routing.md` 的通用 glob 表(R1~R6 + 兜底)。
- 取并集,得到本轮 **active modes**(子集 ⊆ {correctness, e2e:Web/OpenAPI/App, eval-bench})。

基线规则(始终成立,来自 role-routing):
- **correctness 永远在 active modes 里**(任意 diff 都跑)。
- 改用户可见面(前端 R1 / 移动 R2 / API R3 / 测试本身 R6)→ 叠加 **e2e**(选对应子模态 Web/App/OpenAPI)。
- 改 AI/模型/策略/prompt/evals(R4)→ 叠加 **eval-bench**;数据质量(R5 条件)亦可叠 eval-bench。

> 单模式点名(`--mode=`)时:跳过解析,直接把指定模式当作唯一 active mode。
> `--scope=` 仅对 e2e 有意义(feature / iteration / full-chain),其它模式忽略。

把解析出的 `active modes` 与 `changed-files` 暂存,Step 4 写进 STATE 快照。

### Step 2 — 架构漂移自检(轻量)

把 changed paths 与 `PROFILE.surface-map` 的 globs 比对(同 driver §3.3):
**有 path 落在所有 surface 之外**(新建服务、首个移动目录等)→ text_mode 告警,不阻断:

```
⚠ 这些改动不在 PROFILE.surface-map 内,模式解析可能不全:
  - mobile/ios/App.swift
  1) 现在重跑 sdlc-onboard 相关部分刷新 surface-map(推荐)
  2) 本次按通用 routing 规则继续(已据 R2 判定需 e2e:App)
回复编号。
```

漂移只影响"是否漏选模式";解析时通用 routing 表会兜底,不会因此漏跑 correctness。

### Step 3 — 按序执行每个 active mode 的 playbook

对每个解析出的模式,**加载并照做它的 playbook**。各 playbook 自带完整步骤、门控、证据 schema:

| 模式 | playbook(读它、照做) | 产物 |
|---|---|---|
| `correctness` | `references/validate-modes/correctness.md` | `.sdlc/validate/correctness-report.md` |
| `e2e` (Web/OpenAPI/App) | `references/validate-modes/e2e.md` | `.sdlc/validate/e2e-<scope>-report.md` |
| `eval-bench` | `references/validate-modes/eval-bench.md` | `.sdlc/validate/eval-<scope>-report.md` |

执行顺序与协议:

1. **correctness 先跑**(它是底座;它绿了再谈旅程/质量更有意义)。
2. **e2e / eval-bench** 在 correctness 之后,二者之间无强依赖——可并行(§0.2)或串行。
3. **失败回流不在本层修**:任何模式暴露**实现 bug**,按该模式 playbook 的指引 **escalate 回 `sdlc-build`**
   (build 的 TDD↔调试子循环修),validate 这一轮对应需求标 PARTIAL。本调度层**不在 validate 偷改实现**。
4. **单条问题 ≤ 3 次迭代仍无解 → escalate,不死磕**(沿用各 playbook 的反死磕约定)。

> 调度层的纪律(贯穿所有模式,蒸馏自 verification-before-completion):
> **没有本轮新鲜验证证据,不得做任何"通过/完成"声明。** 每个模式报告里的每条 COVERED/PASS
> 都必须挂本轮真跑的命令 + 输出 + exit code。看到 should/probably/seems/"Great!"/"Done!"
> 出现在验证之前 = STOP,去跑命令。各 playbook 内有各自的 Gate Function 与反合理化表,照用。

### Step 4 — 汇总门控 + 写交接

所有 active mode 跑完后,本调度层**汇总**:

1. 读每个模式报告的 `result`(PASS / GATED / BLOCKED)。
2. **阶段总判定**:
   - 全部模式 PASS → validate 阶段 = **PASS**,可进 review。
   - 任一模式 GATED(覆盖率不达标 / 旅程失败已 escalate / eval 未达阈值)→ 阶段 = **gated**,
     STATE.next 指回缺口对应阶段(多为 `sdlc-build`)。
   - 任一模式 BLOCKED(测试基建起不来 / eval 装置坏 / 缺评估标准且无法回退)→ 阶段 = **blocked**,
     在 STATE.Decisions log 记原因。
3. 写一份**阶段汇总**(可放 `.sdlc/validate/summary.md` 或直接体现在 STATE),列每个模式的结果与去向。
4. **输出 `## HANDOFF` → 回写 STATE.md**(经 driver / 单写者,见 §6):更新 stage / status / gates / validate-modes / next。

---

## 3. 读写哪些 .sdlc/ 文件

| 文件 | 读 / 写 | 用途 |
|---|---|---|
| `<repo>/.sdlc/PROFILE.md` | **读** | surface-map(解析模式)、test-commands、覆盖率阈值。本 skill 不写 PROFILE |
| `<repo>/.sdlc/STATE.md` | **读 + 写**(单写者) | 读 stage/next 续接;写回 stage/status/gates/validate-modes/active roles/next |
| `<repo>/.sdlc/spec.md` | **读** | 取验收标准(correctness Step 1)与 **AI 工作的 eval rubric/数据集/阈值**(eval-bench 的契约输入) |
| `<repo>/.sdlc/plan.md` | **读** | 取任务的 acceptance_criteria 作为"必须被证明的行为"清单 |
| `<repo>/.sdlc/validate/correctness-report.md` | **写** | correctness 模式产物 |
| `<repo>/.sdlc/validate/e2e-<scope>-report.md` | **写** | e2e 模式产物(截图齐全) |
| `<repo>/.sdlc/validate/eval-<scope>-report.md` | **写** | eval-bench 模式产物(质量/性能分) |
| `<repo>/.sdlc/validate/summary.md` | **写**(可选) | 多模式阶段汇总 |
| `references/role-routing.md` | **读** | 解析 changed-files → active modes |
| `references/validate-modes/<mode>.md` | **读** | 各模式的执行 playbook(照做) |

> spec→validate 的关键契约:**eval-bench 的标准在 spec 阶段定**。若改了 AI 面但 `spec.md` 没写
> rubric/数据集/阈值 → eval-bench playbook 会回退到"AI 工作一般最佳实践审计"并报警;
> 本调度层在汇总时把它记为 **gated**,STATE.next 提示回 `sdlc-spec` 补 eval 标准。

---

## 4. 出口门控(全过才算 validate 阶段通过)

进入 `sdlc-review` 之前,以下必须全部成立:

- [ ] **模式选齐**:Step 1 解析出的 active modes 已全部执行(correctness 必在内),无漏跑。
- [ ] **correctness PASS**:全量/相关测试本轮真跑 0 failures(贴命令+exit 0);typecheck/build exit 0;
      覆盖率门控由工具以非零 exit 把关达标(不靠肉眼)。
- [ ] **e2e PASS**(若 active):本轮要验的用户旅程都跑到终态;失败用例已回 build 修复并三联截图取证;
      不能测的维度已显式声明(Scope Declaration),不猜成 TESTED。
- [ ] **eval-bench PASS**(若 active):评估装置先过 oracle/nop 自检;按 spec 既定 rubric/阈值跑出实际分;
      baseline-diff 无 REGRESSION;无效跑已剔除。spec 缺标准 = 本门视为 gated。
- [ ] **无偷改实现**:所有暴露的实现 bug 都 escalate 回 build,validate 期间实现文件 0 改动(可 `git diff` 自证)。
- [ ] **证据完整**:每个模式报告的每条 PASS/COVERED 都挂本轮真跑证据;无"应该过/上次过"判定。
- [ ] **STATE 已更新**:gates 勾选、validate-modes 快照、next action 写明(独立运行模式可豁免 STATE,但要在报告注明)。

任一项不过 → 阶段 status = `gated` 或 `blocked`,STATE.next 指回缺口对应阶段(多为 build,eval 标准缺失则回 spec)。
**validate 阶段 PASS 是进入 review 的前置门。**

---

## 5. 写什么进 HANDOFF（由 driver 写 STATE）

阶段结束,输出 `## HANDOFF` block,经 driver / 单写者把进度写回 `<repo>/.sdlc/STATE.md`。
独立直调时先产同一 HANDOFF,再作为单写者应用。validate 阶段要更新的字段:

```markdown
## HANDOFF
stage: validate            # 若全过且要进下一阶段,由 driver 推进到 review
status: in-progress | gated | blocked
updated: <由 caller 传入的时间戳，不自造时钟>
validate-modes: [correctness, e2e, eval-bench]   # 本轮 Step 1 解析出的子集(快照,非持久事实)

## Gates passed
- [x] validate：correctness 通过（套件 + 覆盖率门控）
- [ ] validate：e2e 通过（用户旅程，若有可见面变更）
- [ ] validate：eval-bench 通过（达 rubric/阈值，若有 AI 变更）

## Active roles (from last diff scan)
- <Step 1 解析出的角色,与 modes 同源>

## Changed-files snapshot
- <Step 1 的 git diff 路径清单>

## Decisions log
- <date> escalate <实现 bug> 回 build；eval 阈值缺失,回 spec 补 rubric ...

## Next action
-> invoke sdlc-review            # 全过
-> 回 sdlc-build 补覆盖率/修旅程失败    # gated
-> 回 sdlc-spec 补 eval 标准         # eval-bench 因缺标准 gated
```

要点:
- `validate-modes` 与 `Active roles` 是**本轮 resolve 出的快照**,仅供交接/审计,**不是持久事实源**
  (下次进来 diff 变了要重 resolve,见 spec §6.1)。
- gates 三个 validate 子项按本轮 active modes 勾选;**未 active 的模式不勾、不算缺口**
  (如本次没动 AI 面,eval-bench 子项保持未勾但不阻断)。
- `Next action` 必须写成可直接执行、给"全新上下文的下一个 agent"看的指令。

---

## 6. 兼容性(载重规则,Codex / sub-agent / Workflow 都能用)

| # | 规则 | 在本 skill 的体现 |
|---|---|---|
| 1 | 知识 + 状态都是纯文件 | 模式 playbook 在 `references/validate-modes/`;报告/状态在 `.sdlc/`——任何 caller 不靠 Skill 机制也能跑 |
| 2 | STATE 单写者;并行写各自文件 | 多模式产物各写各的 `validate/<mode>-report.md`;**只有调度层汇总后写一次 STATE**,防 fan-out 竞态 |
| 3 | 流程平台无关;编排是加速器不是依赖 | 多模式可 Task fan-out,无并行则串行(§0.2);所有提问用 text_mode(§0.1);核心只需 Read/Edit/Bash/Grep + git |
| 4 | 维护 `.agents/skills/sdlc*` 符号链接 | 由 driver/onboard 维护,Codex 仓库内可发现本 skill |

> e2e 模式依赖 Playwright MCP(环境已确认可用);**无该 MCP 的环境**(纯 Codex)→ e2e 的 Web/App 模态
> 降级为"人工旅程检查清单 + 截图描述",在报告标 PARTIAL/INFERRED,不假装 TESTED(见 e2e.md)。
> 这不影响 correctness / eval-bench,它们零 MCP 依赖。

---

## 7. 一次完整 validate 的动作清单(checklist)

1. [ ] 确认入口条件(§1):build 已 green,或单模式点名,或现状审计。
2. [ ] **Step 1**:`git diff` → 读 `role-routing.md` → resolve 出 active modes(correctness 必在内)。
3. [ ] **Step 2**:架构漂移自检(text_mode 告警,不阻断)。
4. [ ] **Step 3**:correctness 先跑;再按需跑 e2e / eval-bench(并行或串行)——各读各 playbook 照做;
       实现 bug **escalate 回 build**,不在此偷改实现;单问题 ≤3 次不解即 escalate。
5. [ ] **Step 4**:读各模式报告 result → 汇总阶段总判定(PASS/gated/blocked)。
6. [ ] 核对出口门控(§4)全过。
7. [ ] 输出 `## HANDOFF` 并回写 STATE.md(§5,单写者),快照 active modes / roles / changed-files,写 next action。
8. [ ] 向用户报告:本轮跑了哪些模式、各自结果、阶段总判定、下一步(→ review / 回 build / 回 spec)。
