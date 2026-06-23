# SDLC State: 需求树生命周期状态同步 + 看板可视化重构

stage: done
status: in-progress
work-type: feature
branch: feat/leaf-lifecycle-board
worktree: /Users/mac/hansen_agent_team/workspace/sdlc-pilot
source-leaf: (none)
updated: 2026-06-23
validate-modes: [correctness]
sdlc-gate: PASS reviewed-head=9fbf434c7addfebcab31aaa4ae04b78b6a9096bc

## Gates passed

- [x] onboard：PROFILE.md 已建立（首次为 sdlc-pilot 自身测绘，6 个面 surface-map + 装 pre-commit/pre-push 硬门）
- [x] spec：spec.md 已获批（设计经多轮交互确认 + goal 指令"实现这个效果"；DESIGN.md §8 增补已 commit e6caa08）
- [x] plan：plan.md 已拆分（L3，6 阶段/12 任务，4 波次；Source Audit 全 COVERED）
- [x] build：tests written (red) — 每任务先红(StatusEnum/LintBadStatus/SetStatus/BoardLiveBadge/BoardReno)
- [x] build：implementation (green) — 48 测试绿 + validate-skills PASS；10 提交(含抽 board.py 重构守 800 行)
- [x] validate：correctness 通过（48 测试 + validate-skills + import 链）+ dogfood（写回三件套+看板+兼容全证，见 validate/summary.md）
- [x] review：多角色(skill-maintainer+qa+design)无 CRITICAL/HIGH；G1 scope-CLEAN / G2 多角色 / G3 安全 open=0 / G4 critical=0 / G5 high-handled
- [x] verify：validate 证据在(correctness+dogfood PASS) + plan P1-P6 全 DONE

## Review findings rollup

- CRITICAL: 0   HIGH: 0   MEDIUM: 0   LOW: 4（LOW-01/02 已 fix；LOW-03/04 UX 增强落 Deferred）
- security threats_open: 0   verdict: PASS（B2 文件写+HTML 注入：set-status 按构造无路径遍历[id 仅做相等匹配非拼路径]/post-checkout 引号 argv 无 shell 注入/看板 esc+白名单无 XSS）
- 角色文件: review/skill-maintainer.md, review/qa.md, review/design.md

## Active roles (from last diff scan)

- skill-maintainer (R10 改技能体系自身), qa, design (看板渲染重构)

## Changed-files snapshot

- (none yet — target surface: scripts-core + board-render + skill-prose)

## Decisions log

- 2026-06-22 #6 ship(0.14.0) 后接新特性「生命周期状态同步 + 看板重构」。选 onboard-first（补五个特性以来一直缺的 PROFILE.md）。
- 2026-06-22 work-type=feature。两个咬合部分：(数据层) status 权威枚举 + lint 校验 + 各 stage 中间态回写源叶；(展示层) 看板 4 痛点重构。
- 2026-06-22 并发串台已解：另一 codex 会话的 0.15.0(Codex runtime adapter, commit 9a34af1)已落 main + 本分支;本特性基线自动含 0.15.0(新 references/runtime-adapters/codex.md 已被 skill-prose 面覆盖,surface-map 无需改)。本特性将作为 0.16.0。注:main ahead 1 未推 origin(0.15.0 待 owner 决定何时推)。

## Decisions(spec)

- 写回机制 = **C 混合 + 边界 flush**：稳态(captured/shipped)落盘，过渡态(spec'd→validated)惰性派生(看板读 STATE 叠加 live badge)，离开特性时 flush 固化。blast ~L2(不碰 4 stage skill)。
- 强制保证 = **三件套**：post-checkout 钩子(git 硬保证切分支必 flush) + driver §1.1 reconcile(用 sdlc 必跑对账) + backlog.py set-status op(共享机械写原语)。worktree-cd 无即时钩子→靠隔离不丢+eventual reconcile(用户知情接受)。
- 状态机 = **allow-any-set**(set-status/lint 只校验值∈枚举,不挡跳/退)。
- scope = 一个 spec,plan 分波(wave1 数据层 / wave2 看板)。发布 0.16.0。

## Changed-files snapshot

- (目标 surface) scripts/backlog.py(枚举/lint/set-status/render_board) + scripts/test_backlog.py + skills/sdlc/references/templates/hooks/post-checkout(新) + skills/sdlc-onboard/SKILL.md + skills/sdlc/SKILL.md(§1.1 reconcile) + DESIGN.md + CHANGELOG/.claude-plugin

## Next action

-> 退场收口：sdlc-backlog Retire（归档 .sdlc 工件 + 回流 EVOLUTION + 清栈；无 source-leaf 跳标 shipped）；合并 feat/leaf-lifecycle-board 回 main + 推 + 删分支。注：基线含 0.15.0(9a34af1)+本特性 11 提交=0.16.0；main 仍 ahead 1 未推的 0.15.0 会随本次一起推。停看板演示服务(8799)。
