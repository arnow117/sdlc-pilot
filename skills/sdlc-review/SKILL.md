---
name: sdlc-review
description: >
  SDLC 第⑦阶段 —— 多角色代码评审 + 验证收尾(Verify)。在改动落地前做四件硬事:
  (1) scope-drift / plan-completion 审计——只做了该做的吗?该做的都做了吗?
  (2) 按改动代码动态加载的多角色专家透镜并行(或串行降级)评审,统一 severity+confidence;
  (3) 安全 10 域门控(verify-mitigation-exists + disposition + open=0 硬门);
  (4) fix-first 处置 + 对抗 pass,把每条 finding 写进 review/<role>.md,把门控结果写回 STATE。
  触发于:用户说 "review 这次改动"、"评审一下代码"、"pre-landing review"、"check my diff"、
  "走 sdlc review"、"准备合并/落地前检查"、"sdlc-review"、"代码评审 + 收尾";
  也由 sdlc 驱动器在 STATE.stage=review 时路由进来,或在 validate 通过后主动建议。
  本 skill 是流程(可执行 playbook):它读改动→解析角色+模式→加载角色卡当透镜→产 findings→门控→写状态。
  它不写实现、不写测试、不跑端到端旅程(那是 sdlc-build / sdlc-validate 的事)。阶段末输出
  `## HANDOFF`;driver 是 canonical STATE writer。
---

# sdlc-review — 多角色评审 + Verify 收尾(流程 skill)

你正在执行 SDLC 主线的**第⑦阶段**。目标:在改动落地前,从**改动代码自动选出的多个专业角色视角**审一遍,
做完整性/范围审计与安全门控,把每条问题分类处置,产出可审计的 findings,并把门控结论写回 `STATE.md`。

> **引擎 = Claude + Read/Edit/Bash/Grep。** 所有知识在纯文件里(`references/roles/*.md`、本 skill)。
> 不依赖 gsd-tools / `.planning/` / subagent 人格 / AskUserQuestion / gstack 二进制。
> **可移植铁律**:交互用 text_mode(纯文本编号列表),并行用 Task-or-sequential 降级(见 §0)。

---

## 0. 可移植前置(每次入口先做)

> **共享 references 的位置(单一约定)**:本文引用的 `references/role-routing.md`、`references/roles/<role>.md` 等共享数据**物理上只在 sdlc 驱动器 skill 目录下**(`sdlc/references/`),不在本 skill 自己的目录里。解析时指向 `sdlc/references/...`(相对 skills 根)或经 dogfooding 软链接定位,**不要**当作相对本 skill 目录的路径去 Read。

### 0.1 交互降级 — text_mode
凡需向用户提问(确认 scope-drift 处置、批准 fix、确认接受风险),**优先用纯文本编号列表**:

```
我需要你选一个:
  1) 选项 A — 说明
  2) 选项 B — 说明
回复编号即可。
```
有 AskUserQuestion 时可用它,但**回退路径必须是上面这种编号文本**。默认按 text_mode 写。

### 0.2 并行降级 — Task-or-sequential
多角色评审天然可并行。**探测有无 Task/并行能力**:
- **有 Task** → fan-out:每个角色一个独立 agent,各自只写 `review/<role>.md`,最后由你合并。
- **无 Task**(Codex / Gemini CLI 等)→ **串行 inline**:你逐个角色加载该角色卡当透镜,顺序产 findings,逐个写 `review/<role>.md`。

**单写者原则(铁律 §10 rule 2)**:`STATE.md` 永远只由你(本 skill 主流程)写;并行角色只写各自的 `review/<role>.md`,绝不并发写 STATE。

### 0.3 非交互 / headless 变体
当本 skill 被 sub-agent、Workflow、CI 或 `--headless` / `--non-interactive` 调起(无人应答):
- **不发任何 AskUserQuestion / 编号提问**。所有需要用户裁决的点,改为:按"安全默认"处置 + 把待决项写进 finding 的 `disposition: needs-human`。
- 安全默认 = **不自动改高风险代码**(只 auto-fix 机械类),**不替用户接受安全风险**(open 安全项 → 阻断,不放行)。
- 全部 findings 落 `review/<role>.md`,门控结论落 STATE,正文最后输出一段机器可读的 `## REVIEW SUMMARY`(见 §7)。

---

## 1. 入口条件(进入本阶段的前提)

进入 sdlc-review 前应满足(由驱动器或上一阶段保证;若不满足,先回对应阶段):

1. **有改动可审**:`git diff` 相对 base 非空。若为空 → 输出 `Nothing to review — 工作区与 base 无差异` 并停。
2. **build 已 green**:`STATE.gates` 里 `tests written (red)` 与 `implement (green)` 已勾(或当前确实有实现 diff)。
3. **validate 已跑**(推荐但不强制):`STATE.validate-modes` 已解析,`.sdlc/validate/` 下有对应报告。
   - 若 validate 未跑且改动触及用户可见面/AI 策略 → 提示"建议先跑 sdlc-validate",但不阻断 review(review 可独立跑)。
4. **能定位状态**:`<target-repo>/.sdlc/STATE.md` 可读(没有则按 stage=review 新建一份骨架,见 §5)。

> 独立调用也允许:用户直接 `/sdlc-review` 审当前 diff。此时跳过驱动器,自己做 §2 的角色解析。

---

## 2. 步骤流程

### Step 0 — 定位 base 分支 + 取 diff(平台无关)

确定**审查范围 = 本次改动相对 base 的 diff**:
- **base 分支**:优先取 PR 的目标分支;无 PR 则退化到仓库默认分支(再退化 `main`/`master`)。
- **改动文件清单**:还没 commit 时用工作区相对 `HEAD` 的 diff;已 commit 到 feature 分支时用相对 base 的 diff(`<base>...HEAD`)。

> 用 `git`(配合 `gh` 取 PR 信息)即可,具体命令你定;关键是范围算准——审查只看本次改动,不要把历史也卷进来。

### Step 1 — 角色 + 模式解析(本流程 skill 的入口动作)

**这是流程 skill 入口的第一件实事**(spec §6:进 build/validate/review 都先动态重算路由)。
读驱动器的路由规则,把"改动代码 → 角色卡 + validate 模式"算出来:

1. 读 `references/role-routing.md`(规则表)与目标仓库 `.sdlc/PROFILE.md` 的 `## Surface map`(项目特化,优先级更高)。
2. 跑 `role-routing.md` §1 的决策算法:
   ```
   Decision = resolve( git-diff × PROFILE.surface-map × routing-rules )
   ```
   - 每个改动 path:先查 PROFILE.surface-map,命中则并入其 roles+modes;未命中则按 routing 表(R1–R6 + 兜底 B1/B2)匹配,可命中多行取并集。
   - **兜底 B1**:任意 diff → 必加 `qa`(baseline)。
   - **兜底 B2**:触及敏感面(auth / 支付 / 密钥 / 用户数据 / 外部输入 / 原始 SQL / 文件系统)→ 叠加 **security 视角**(v1 由 server-dev/qa 卡的 security 子节 + 本 skill §4 安全 10 域承载)。
3. 去重 → 得到 **active roles**(本次要加载哪些 `roles/*.md`)。
4. **漂移检测**:若有改动 path 既不命中 PROFILE 也不命中路由表,或命中路由但 PROFILE 查无此 surface →
   记一条 `architecture drifted — refresh PROFILE?`(交互态用 text_mode 提示,headless 写进 SUMMARY)。
5. 把解析结果(active roles + changed-files snapshot)准备好,稍后(Step 6 后)写回 STATE。

> 合法角色集合见 `role-routing.md` §3:`qa / client-dev / server-dev / design / big-data`。
> 路由产出不得出现字典外的"野值"。

### Step 2 — Scope-Drift + Plan-Completion 审计(蒸馏自 gstack `review`)

在审代码质量**之前**,先回答两个问题:**只做了该做的吗?该做的都做了吗?**

**2a. 确定 stated intent(意图)**,按优先级取来源:
1. `.sdlc/spec.md` 与 `.sdlc/plan.md`(SDLC 主线产物,**首选**)。
2. PR 描述:`gh pr view --json body -q .body 2>/dev/null`。
3. commit 信息:`git log <base>..HEAD --oneline`(过滤 WIP/tmp/merge/chore 噪声,抽真实意图)。

**2b. 抽取可执行项**:从 spec/plan 抽出每条"要做的事"(checkbox / 编号步骤 / 祈使句 / 文件级规格 / 测试要求 / 数据模型变更)。上限 50 条。
忽略:Context/Background、问题与开放项(TBD)、显式 Deferred("Out of scope"/"P2/P3")、决策记录段。

**2c. 验证模式分类**(diff 不能证明一切;先分类"这条怎么验"):

| 验证模式 | 含义 | 判定手段 |
|---|---|---|
| **DIFF-VERIFIABLE** | 本仓库的代码改动,会出现在 `git diff` | 对照 diff 找证据 |
| **CROSS-REPO** | 指向兄弟仓库的文件/改动 | 兄弟仓可达 → `[ -f <path> ]` 实测;不可达 → UNVERIFIABLE |
| **EXTERNAL-STATE** | 外部系统状态(DNS / 云配置 / OAuth 白名单 / 第三方 SaaS) | UNVERIFIABLE,注明用户须手验的具体检查 |
| **CONTENT-SHAPE** | 文件需符合某约定 | 本仓且有 validator → 跑它;否则 UNVERIFIABLE |

**路径具体性规则**:若 plan 项点名了**具体文件路径**(绝对 / `~/...` / `<sibling>/<file>`),**必须**靠 `[ -f <path> ]` 判 DONE/NOT-DONE。UNVERIFIABLE 只对真正抽象的外部态合法。"不想查"不算不可达。

**2d. 对照 diff 分类每条**:`DONE / PARTIAL / NOT-DONE / CHANGED / UNVERIFIABLE`。
- DONE 要**保守**:文件被碰过 ≠ 完成,描述的具体功能必须在场,引用 `file(+N lines)` 为证。
- CHANGED 要**宽容**:目标用别的手段达成也算解决,注明差异。
- UNVERIFIABLE 要**诚实**:宁可让用户手验 5 条,不要悄悄判 DONE。
- **诚实铁律**:处理某交付物的代码 ≠ 该交付物本身(发了 markdown 提取库 ≠ 发了那个 markdown 文件)。

**2e. SCOPE CREEP 检测**:diff 里有与 intent 无关的文件 / 计划外的新功能或重构 / "顺手改的"扩大了爆炸半径 → 列出每条越界改动。

**2f. 输出审计块**(信息性;HIGH-impact 缺口才升级为门控,见 Step 6):
```
SCOPE CHECK: [CLEAN / DRIFT DETECTED / REQUIREMENTS MISSING]
Intent:    <一句话:本次要做什么>
Delivered: <一句话:diff 实际做了什么>
Plan items: N DONE, M PARTIAL, K NOT-DONE, J UNVERIFIABLE
[若 NOT-DONE: 逐条列 + 调查 WHY(scope-cut / 上下文耗尽 / 误解需求 / 被依赖阻塞 / 遗忘)]
[若 creep: 逐条列越界改动]
```

### Step 3 — 选择评审深度(蒸馏自 gsd-code-review)

按 diff 规模与改动性质选 depth(也可由用户 `--depth=` 覆盖):

| depth | 做什么 | 何时 |
|---|---|---|
| **quick** | 仅模式扫描(grep 反模式:硬编码密钥 / 危险函数 / 空 catch / debug 残留) | diff < ~50 行,或快速过一遍 |
| **standard**(默认) | 逐改动文件读全文,带**语言相关**检查;跨引用 import/export | 一般改动 |
| **deep** | standard + 跨文件:追调用链、API 边界类型一致性、错误传播、状态一致性 | 安全敏感 / 大改 / 架构变更 |

文件数 > 50 时:提示收窄 scope;若同时是 deep,降到 standard 防浅评审。

### Step 4 — 多角色专家评审(Task-or-sequential)

对 Step 1 解析出的每个 active role,把对应 `references/roles/<role>.md` 当**透镜**加载,审 diff 产 findings。
**并行(有 Task)** 或 **串行(无 Task)** 见 §0.2。每个角色把自己的 findings 写进 `<repo>/.sdlc/review/<role>.md`。

**4a. 每个角色透镜怎么审**:读该卡的「关注点 / 检查清单 / 常见翻车」,对照 diff 逐条核。强制语言相关检查(蒸馏自 gsd-code-reviewer,v1 = Python + TS):
- **Python**:裸 `except:` / 可变默认参数 / f-string 注入 / 动态执行内置函数(`eval` / `exec`)/ 文件操作缺 `with` / 缺类型。
- **JS/TS**:未判 `.length` / 漏 `await` / 未处理 promise 拒绝 / `as any` / `==` vs `===` / 空值合并漏判。
- 通用:函数 >50 行、嵌套 >4 层、async 缺错误处理、硬编码配置、魔法数。

**4b. Enum/值完整性(唯一需读 diff 之外代码的类)**:diff 新增 enum 值 / status / tier / 常量时,Grep 所有引用兄弟值的文件,Read 检查新值是否被处理。

**4c. 统一 finding 格式(severity + confidence,全 skill 一致)**:

```
[<SEVERITY>] (confidence: N/10) <file>:<line> — <一句话问题>
  role: <产出角色>   verify-mode: <DIFF-VERIFIABLE/...>
  fix: <具体修法,能给代码片段就给>
  disposition: <auto-fix / ask / needs-human / accept>   # 见 Step 6
```

**统一 severity 模型**(收编源里混用的 P0–P3 / Critical-Warning-Info / 1-10):

| severity | 含义 | 门控 |
|---|---|---|
| **CRITICAL** | 安全漏洞 / 数据丢失 / 崩溃 / authz 绕过 | **BLOCK** 落地 |
| **HIGH** | 真 bug 或重大质量问题 | 落地前**应**修 |
| **MEDIUM** | 可维护性问题 | 考虑修 |
| **LOW** | 风格 / 小建议 | 可选 |

**confidence 校准表(1–10)**:

| 分 | 含义 | 显示规则 |
|---|---|---|
| 9–10 | 读了具体代码已证实,可演示的 bug/exploit | 正常显示 |
| 7–8 | 高置信模式匹配,很可能对 | 正常显示 |
| 5–6 | 中等,可能误报 | 带提示"中置信,请核实" |
| 3–4 | 低,可疑但可能没事 | 移入附录,不进主报告 |
| 1–2 | 推测 | 仅当 severity=CRITICAL 才报 |

**4d. 多角色去重 + 互证**:多个角色在同一 `file:line:category` 命中同一问题 → 保留最高 confidence 一条,标 `MULTI-ROLE CONFIRMED (<role1>+<role2>)`,confidence +1(封顶 10)。

**4e. 验证声明(蒸馏自 devex-review,防幻觉)**:每条断言要么给证据要么标未验证。
- 说"这模式安全" → 引证明安全的那行;说"别处已处理" → 读并引那段;说"测试覆盖了" → 点名测试文件与用例。
- **禁止** "likely handled" / "probably tested"。"看起来没问题"不是 finding——要么引证据说它没问题,要么标 unverified。

**4f. 架构类 finding 的判断透镜(蒸馏自 plan-eng-review 15 认知模式)**:审架构/复杂度类改动时套这些资深直觉——
blast-radius(最坏情况波及多少系统/人)、boring-by-default(创新 token 只有三个,其余用成熟技术)、可逆性偏好(改动易回滚否)、
本质 vs 偶然复杂度(在解真问题还是自造的问题)、systems-over-heroes(为凌晨三点的疲惫工程师设计)。
**scope-challenge 阈值**:单次改动 >8 文件 或 引入 >2 新服务/类 → 视为 smell,在 finding 里挑战"能否更少动件达成同目标"。

### Step 5 — 安全 10 域门控(蒸馏自 security-review + gsd-secure-phase)

仅当 **B2 敏感面命中** 或 active roles 含 security 视角时跑(否则跳过,在 SUMMARY 注明 `security: not-applicable`)。

**5a. 安全 10 域**(逐域 PASS / FAIL,FAIL 须给 file:line + 修法):
1. **输入验证 / 注入**(SQL / 命令 / 路径遍历 / 不安全反序列化)
2. **认证**(身份校验 / 会话 / 凭据存储)
3. **授权**(IDOR / 越权 / 缺访问控制)
4. **密钥管理**(硬编码密钥 / 凭据 / token,绝不入源码)
5. **加密**(算法选型 / 随机性 / 明文敏感数据)
6. **数据暴露**(错误消息泄露 / 日志泄密 / 过度返回字段)
7. **信任边界**(LLM 输出 / 外部 API 响应 / 用户内容,落库/执行前校验)
8. **CSRF / 状态变更**(状态变更端点的防护)
9. **速率限制 / 滥用**(端点限流 / 防爆破)
10. **依赖 / 配置**(已知漏洞依赖 / 不安全默认配置 / 调试开关)

**5b. verify-mitigation-exists(非盲扫)**:若 `.sdlc/spec.md` 或 plan 里有威胁模型/缓解声明,**逐条验缓解是否真在代码里**(grep 缓解模式于其声明文件),而不是从头瞎扫新漏洞。

**5c. disposition(每条 open 安全项必须有处置)**:`mitigate`(修)/ `accept`(文档化接受风险)/ `transfer`(转移,如保险/供应商 SLA)。

**5d. open=0 硬门(BLOCK)**:统计 `threats_open`(= 未 mitigate 且未文档化 accept/transfer 的安全项数)。
- `threats_open > 0` → **门控 FAIL,阻断落地**。交互态:用 text_mode 让用户选「修 / 接受并记录 / 取消」;**headless 态:不替用户接受风险 → 保持阻断**,写进 SUMMARY。
- `threats_open == 0` → 安全门 PASS。

### Step 6 — Fix-First 处置(蒸馏自 gstack review)

**每条 finding 都给动作,不只是 CRITICAL。** 按 `disposition` 分流:

- **auto-fix**:机械、低风险、明确的修复(空 catch、漏 import、`==`→`===`、加 null 判等)→ 直接改,逐条输出 `[AUTO-FIXED] file:line 问题 → 改了什么`。
- **ask**:有判断成分 / 触及行为 / CRITICAL/HIGH → 交互态用一次 text_mode 批量征询(每条:A 按建议修 / B 跳过 / C 误报);**headless 态**:不自动改,标 `needs-human`,写进 SUMMARY。
- **needs-human**:无法自动验证或需要领域判断。
- **accept**:用户/规则明确接受(记入 finding)。

**处置铁律**:
- **修每条 finding 前守 `references/receiving-feedback.md` 纪律**:先核实该 finding **真成立、对本仓正确**(看着对≠真的对),再 auto-fix;**一次一项、各自验证、验无回归**;意见错了就技术反驳(标误报),别盲目照单全收;别顺手加没要求的(YAGNI grep)。治"被指出就乱改"。
- review 阶段**只改代码,不 commit / 不 push / 不建 PR**(那是 ship 的事)。
- **不改测试去迁就实现**;发现实现 bug → 标 finding 升级,不在 review 里默默改实现逻辑(除非是上面的机械 auto-fix)。
- 跨评审去重:本分支上一轮被用户 `skipped` 且相关文件未再变的 finding → 抑制(只抑制 skipped,绝不抑制 fixed)。

### Step 7 — 对抗 pass(always-on,蒸馏自 gstack review;**Codex 下跳过外脑**)

换一个"攻击者 + 混沌工程师"视角再扫一遍,找前面遗漏的:边界条件 / 竞态 / 资源泄漏 / 静默数据损坏 / 吞错 / 信任边界。
- **有 Task**:fan-out 一个 fresh-context agent 跑对抗扫(无前面 checklist 偏见),结果并入 findings。
- **无 Task**:你自己换视角再过一遍 diff。
- **可选外脑 codex**:仅当**本 skill 不是在 Codex 下运行**时,可调 `codex` 做跨模型对抗(`sdlc` 在 Codex 下跑时调 codex 是自指/冗余 → 跳过)。
对抗 pass 的 FIXABLE finding 走同一 Fix-First 流;INVESTIGATE 类作信息性列出。

---

## 3. 读写哪些 .sdlc/ 文件

| 文件 | 读/写 | 用途 |
|---|---|---|
| `.sdlc/STATE.md` | 读 + **经 driver 写**(单写者) | 读 stage/gates/active-roles;本 skill 输出 `## HANDOFF`,由 driver 写回门控结果与 next(§5 schema) |
| `.sdlc/PROFILE.md` | 读 | `## Surface map` 参与角色解析(优先于通用路由表) |
| `.sdlc/spec.md` | 读 | Step 2 意图来源 + Step 5 威胁模型/缓解声明 |
| `.sdlc/plan.md` | 读 | Step 2 plan-completion 审计的可执行项 |
| `.sdlc/validate/*-report.md` | 读 | 引用 validate 证据(覆盖率/e2e/eval 结论)佐证 findings |
| `.sdlc/review/<role>.md` | **写**(每角色各一,parallel-safe) | 每个角色的 findings(并行不冲突) |
| `references/role-routing.md` | 读 | 路由规则表(skill 内置数据) |
| `references/roles/<role>.md` | 读 | 角色透镜:关注点 / 检查清单 / 常见翻车 |

**`review/<role>.md` 文件结构**(每个角色一份,内容自洽,可被 sub-agent/CI 独立消费):
```markdown
---
role: server-dev
reviewed: <stamp>
depth: standard
files_reviewed: N
findings: { critical: N, high: N, medium: N, low: N, total: N }
status: clean | issues_found
---
# 角色评审: server-dev

## CRITICAL
### CR-01: <标题>
[<CRITICAL>] (confidence: 9/10) path/to/file.py:42 — <问题>
  verify-mode: DIFF-VERIFIABLE
  fix: <具体修法/代码片段>
  disposition: ask

## HIGH / MEDIUM / LOW
...

## 附录(confidence 3–4,抑制项)
...
```

---

## 4. 出口门控(本阶段是否算通过)

**全部满足才算 review PASS**(任一 FAIL → 阶段未过,回对应处置):

- [ ] **G1 范围诚实**:scope-drift 审计已出;无 HIGH-impact 的 NOT-DONE 未处置(有则按 Step 5/§Step 6 升级:停下补做 / 落地+建 P1 待办 / 显式判为放弃)。
- [ ] **G2 多角色已审**:每个 active role 都产了 `review/<role>.md`(clean 或 issues_found),无角色被静默跳过。
- [ ] **G3 安全硬门**:若跑了安全门 → `threats_open == 0`(全部 mitigate 或文档化 accept/transfer);否则 **BLOCK**。
- [ ] **G4 CRITICAL 清零**:无未处置的 `CRITICAL` finding(已 fix / 已 accept-with-rationale 才算处置)。
- [ ] **G5 HIGH 已处置**:每条 `HIGH` 要么已修,要么用户/规则显式接受并记录(headless 态未获接受 → 标 needs-human,门控为 DONE_WITH_CONCERNS 而非 PASS)。
- [ ] **G6 验证声明完整**:findings 无"likely/probably"未验证断言;每条断言有证据或标 unverified。

**门控结论三态**(对齐 Completion Status Protocol):
- **PASS / DONE** — G1–G6 全过,有证据。
- **DONE_WITH_CONCERNS** — 主门过但有 MEDIUM/LOW 未修或 headless 待人决项,列清单。
- **BLOCKED** — G3(安全 open>0)或 G4(CRITICAL 未清)未过;写明 blocker + 已尝试 + 建议。

---

## 5. 写什么进 HANDOFF(交接契约,由 driver 写 STATE)

门控跑完,**由本 skill 主流程**输出 `## HANDOFF`;driver 作为 canonical writer 把结果写回
`<repo>/.sdlc/STATE.md`(单写者)。独立直调时先产同一 HANDOFF,再作为单写者应用。对齐驱动器 STATE schema(spec §8):

```markdown
## HANDOFF
# SDLC State: <feature/topic>
stage: review            # 通过则下一步 → done(Verify);未过则停在 review
status: in-progress | gated | blocked
updated: <stamp>
validate-modes: [...]    # 沿用本次解析
sdlc-gate: <见下>        # ★ G1–G6 全过(verdict=PASS)→ 写 `PASS reviewed-head=<git rev-parse HEAD 完整 sha>`;否则写 `BLOCK`。本地 pre-push hook 凭此行决定放不放行 push;改了代码必须重跑本 skill 刷新这行的 sha。

## Gates passed
- [x] spec approved
- [x] tests written (red)
- [x] implement (green)
- [x] validate: correctness   # 若跑了
- [<x/ >] review: scope-honest        (G1)
- [<x/ >] review: multi-role done     (G2)
- [<x/ >] review: security open=0     (G3,跑了才有)
- [<x/ >] review: critical=0          (G4)
- [<x/ >] review: high handled        (G5)

## Active roles (from last diff scan)
- <Step 1 解析出的 active roles>

## Changed-files snapshot
<Step 0 的 git diff 文件清单>

## Review findings rollup
- CRITICAL: <n> (<已处置 / 待决>)
- HIGH: <n>   MEDIUM: <n>   LOW: <n>
- security threats_open: <n>   verdict: <PASS/BLOCK/N-A>
- 角色文件: review/server-dev.md, review/qa.md, ...

## Decisions log
- <date> <接受了哪条风险/为何 / scope 缩减决定 / 误报判定>

## Next action
-> <PASS: 进 Verify 收尾(§6 引用 validate 证据做最终确认)→ stage=done>
-> <BLOCKED: 修 CRITICAL/安全 open 项后重跑 sdlc-review>
-> <DRIFT: 重跑 sdlc-onboard 相关部分刷新 PROFILE>
```

---

## 6. Verify 收尾(本阶段尾部,蒸馏自 gsd-verify 思想)

review 门控 PASS 后做轻量 Verify 把整个特性收口(不重复 validate 的执行,只做最终确认):
1. **复核 validate 证据**:`.sdlc/validate/` 下报告存在且结论为通过(correctness 覆盖率达门、e2e 旅程 PASS、eval 分达阈)。缺失或不通过 → 回 sdlc-validate。
2. **plan-completion 收口**:Step 2 的 plan 项全部 DONE/CHANGED,或剩余 NOT-DONE 已显式落 P1 待办。
3. 满足 → `stage=done, status=in-progress→done`,**并向 STATE 写入 `sdlc-gate: PASS reviewed-head=$(git rev-parse HEAD)`**(给本地 pre-push hook 放行用),输出收尾摘要;不满足 → 停在 review、写 `sdlc-gate: BLOCK`、指出缺口。

---

## 7. 正文末尾输出(机器可读,headless 必出)

无论交互还是 headless,正文最后输出一段紧凑摘要,供驱动器/CI 解析:

```
## REVIEW SUMMARY
verdict: PASS | DONE_WITH_CONCERNS | BLOCKED
scope: CLEAN | DRIFT | REQUIREMENTS_MISSING
roles_reviewed: [server-dev, qa, ...]
findings: critical=<n> high=<n> medium=<n> low=<n>
security: threats_open=<n> verdict=PASS|BLOCK|N-A
plan_completion: DONE=<n> PARTIAL=<n> NOT-DONE=<n> UNVERIFIABLE=<n>
drift: none | "<描述>"
next: <一句话下一步>
```

---

## 8. 蒸馏来源(distilled-from)

- **gstack `review`** — scope-drift + plan-completion 审计(验证模式分类 DIFF-VERIFIABLE/CROSS-REPO/EXTERNAL-STATE/CONTENT-SHAPE × DONE/PARTIAL/NOT-DONE/UNVERIFIABLE + 诚实/路径具体性规则)、confidence 1–10 校准表、fix-first(auto-fix/ask)、多专家并行 + 互证去重、always-on 对抗 pass。
- **gsd-code-review / gsd-code-reviewer** — quick/standard/deep 深度分层、per-language pitfall 表、REVIEW.md(→ `review/<role>.md`)schema。
- **security-review(10 域)+ gsd-secure-phase / gsd-security-auditor** — 安全 10 域 PASS/FAIL、verify-mitigation-exists(非盲扫)、disposition(mitigate/accept/transfer)、`threats_open==0` 硬门。
- **plan-eng-review** — 15 资深工程认知模式(blast-radius / boring-by-default / 可逆性 / 本质 vs 偶然复杂度…作架构类 finding 的判断透镜)、test-coverage tracing(逐 codepath)、scope-challenge 阈值(8+ 文件 / 2+ 新服务即 smell)。
- **devex-review** — 验证声明(Evidence + Method:TESTED/PARTIAL/INFERRED + scope 自声明)。
- **codex** — 可选跨模型对抗外脑(**sdlc 在 Codex 下运行时不调**)。
- **丢弃**:运行时 preamble、telemetry/gbrain/artifacts-sync、gsd-tools.cjs、`.planning/` 目录、AskUserQuestion 硬依赖、subagent 人格(vibe/emoji/memory)。
