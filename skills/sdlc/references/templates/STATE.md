<!--
  STATE.md — feature 级 handoff 模板（sdlc-pilot）
  ─────────────────────────────────────────────────────────
  作用：跨 session 的"我们到哪了"单一事实源。落在【目标仓库】的
        `<target-repo>/.sdlc/STATE.md`，不在 skill 里。
  生命周期：短命。每个 feature/topic 一份；feature 完成（stage=done）后归档或清空。
  与 PROFILE.md 的区别：
    - PROFILE.md = 项目级、长命、所有 feature 共享（onboard 建一次）。
    - STATE.md   = feature 级、短命、本任务的 handoff 载体（本文件）。
  写入规则（来自 spec §10 兼容性铁律）：
    - 单写者（single-writer）：同一时刻只有主线在写 STATE.md。
    - 并行产物写各自的文件（如 .sdlc/review/<role>.md），不并发写本文件，避免竞态。
    - validate-modes 与 Active roles 是【每次运行从 git diff 动态重算】的快照，
      仅供 handoff/审计，不是持久化的事实源（diff 一变就过时）——见 spec §6.1。
  使用方式：
    1) 复制本模板到 <target-repo>/.sdlc/STATE.md
    2) 删除本注释块与所有 <填写...> 占位
    3) 每个阶段结束时由当前阶段 skill 更新对应字段
  ─────────────────────────────────────────────────────────
-->

# SDLC State: <feature/topic 一句话标题>

stage: onboard | spec | plan | build | validate | review | ship | done
status: in-progress | gated | blocked
work-type: feature | remediation | hotfix     # 流程画像(中央旋钮):各阶段读它自适应走多重。见下方说明
branch: <写 STATE 时记 `git rev-parse --abbrev-ref HEAD`>     # 并发边界戳:sdlc-guard 据此防串台
worktree: <写 STATE 时记 `git rev-parse --show-toplevel`>     # 同上(worktree 隔离)
updated: <时间戳，由调用方传入，例如 2026-06-04T15:30>
validate-modes: [correctness, e2e, eval-bench]   # 本次运行从 diff 动态解析（见 spec §6.1）；未进入 validate 前可留 []
sdlc-gate: <未设置>   # sdlc-review 全过(verdict=PASS)时写 `PASS reviewed-head=<HEAD的sha>`，否则写 `BLOCK`。本地 pre-push hook(若装)只认这一行来决定放不放行 push。

<!--
  字段取值说明：
  - stage：当前所处阶段，枚举见上。done = 全部 gate 通过且 verify 完成。
  - status：
      in-progress = 阶段进行中
      gated       = 卡在某个 exit gate（等待批准/等待修复后重测）
      blocked     = 被外部依赖/缺口阻塞，无法推进（在 Decisions log 记原因）
  - updated：调用方传入的时间戳，skill 不自造时间。
  - validate-modes：本轮 diff 解析出的验证模式子集。可能值见 validate-modes/ 目录：
      correctness（总是跑）/ e2e（用户可见面变更）/ eval-bench（AI/模型/策略变更）。
  - work-type（流程画像 / 中央旋钮）：由 spec/onboard 在流程开始时定；各阶段入口读它来自适应"走多重"。
      · feature（默认）：完整 spec→plan→build→validate→review，按 L1-L4 + 各门控正常自适应。
      · remediation（遗留改造 / AI-readiness 整改）：spec 一段话、eval/design 契约通常 N/A、plan 默认 L1、
        build 文档/配置改动走 Skip-TDD；**走轻,但 review/verify 门不短**(改的是全仓结构,更该审)。
      · hotfix（紧急修)：直奔 build 调试子循环 + 最小验证;**仍过 review 与 push 门**,事后补 spec/plan 记录。
    原则:work-type 只**偏置默认granularity**,不取消任何硬门(覆盖率/安全 open=0/review)。
-->


## Gates passed

<!--
  exit gate 清单。每个阶段 skill 完成自己的出口条件后勾选对应项。
  下面是覆盖完整主线的默认清单；按 feature 实际经过的阶段保留/删减。
  [x] = 已通过，[ ] = 未通过/未到。
-->

- [ ] onboard：PROFILE.md 已建立 / 已确认无漂移
- [ ] spec：spec.md 已获批（含 AI 工作的 eval 标准，若适用）
- [ ] plan：plan.md 已拆分（阶段含依赖、任务含三字段）
- [ ] build：tests written (red) — 测试先行且确认失败
- [ ] build：implementation (green) — 实现使测试通过
- [ ] validate：correctness 通过（套件 + 覆盖率门控）
- [ ] validate：e2e 通过（用户旅程，若有可见面变更）
- [ ] validate：eval-bench 通过（达 rubric/阈值，若有 AI 变更）
- [ ] review：多角色评审无 CRITICAL/未决项
- [ ] verify：完成前核验通过

## Active roles (from last diff scan)

<!--
  上一次 git diff 解析出的活跃角色卡（见 role-routing.md）。
  仅快照，不是事实源；下次进入 build/validate/review 时重算。
  取值字典：qa, client-dev, server-dev, design, big-data, architect（改动跨 ≥2 面/全链路时，
  看接缝:全链路数据结构对齐/跨边界契约/blast-radius）, ai-readiness（动 AI-上下文/构建配置，
  或 onboard 体检/遗留改造时:面向 AI 友好度/可维护性）, skill-maintainer（改技能体系自身时，
  R10:防臃肿/additive/防孤儿/溯源/可移植/semver/自我修改安全）；security（敏感面触及时，
  为视角叠加标签，无独立 roles/security.md，由 server-dev/qa 卡的 security 子节承载）。
-->

- <填写，例如：server-dev, qa>

## Changed-files snapshot

<!--
  上一次 git diff 的变更路径清单（解析角色/模式的依据）。一行一个路径。
-->

- <填写，例如：services/api/orders.py>
- <填写，例如：tests/test_orders.py>

## Decisions log

<!--
  关键决策与阻塞原因的追加式日志（append-only）。每条带日期 + 选了什么 + 为什么。
  blocked 状态的原因必须记在这里。
-->

- <date> 选 X 而非 Y，因为 ...

## Next action

<!--
  下一步动作。给"全新上下文的下一个 agent/session"看：不需要回放历史即可继续。
  写成可直接执行的指令，例如 "-> invoke sdlc-plan"。
-->

-> <填写，例如：invoke sdlc-plan>
