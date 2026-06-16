# SDLC State: archive 纳入 git + Evolution log 独立化（Deferred #2）

stage: done
status: done
sdlc-gate: PASS reviewed-head=75e3846
work-type: feature
branch: feat/archive-in-git
worktree: /Users/mac/hansen_agent_team/workspace/sdlc-pilot
source-leaf: (none — sdlc-pilot 自身无 requirements 树)
updated: 2026-06-16
validate-modes: [correctness]
plugin-version-base: 0.10.0   # 落地升 → 0.11.0(加 Evolution 独立化能力 = minor) 或 0.10.1(纯策略=patch)，build/ship 时定

## Gates passed
- [x] spec：spec.md 已获批（网页审 verdict=approve，0 批注；Eval/Design 契约 N/A）
- [x] plan：plan.md 已拆分（L2；3 phase / 2 wave；Source Audit 全 COVERED；Coverage Gate 全指回）
- [ ] build
- [x] build：P1-P3 全完成（3 commit 7a48317/f9abfb6/75e3846）；TDD red→green（test_retire_rejects_profile_flag 先红后绿）；12/12 测试；5 条 check-ignore 实测；隐私自查无敏感；首批 archive+EVOLUTION 入仓
- [x] validate：correctness PASS（12/12 + lint PASS + check-ignore 行为实测 + 无偷改）。报告 .sdlc/validate/correctness-report.md。
- [x] review：skill-maintainer 透镜 PASS（scope CLEAN / plan 全 DONE / additive 硬核实 / 对抗 pass / 0 CRITICAL/HIGH，1 LOW accepted）。报告 .sdlc/review/skill-maintainer.md。
- [x] verify：correctness 在场且 PASS + plan 全 DONE → 收口
- [x] ship：ff merge → main + push origin = 75e3846（远端无分叉，clean ff）；0.11.0 上线；首批 archive/EVOLUTION 进 git 远端。分支已删。

## Active roles (from last diff scan)
- skill-maintainer（改技能体系自身：gitignore 策略 + backlog.py 回流逻辑 + 模板/文档）

## Changed-files snapshot
- (none yet — target surface: skill-system-self；预期改 .gitignore + scripts/backlog.py(_append_evolution 简化 + 去 --profile) + scripts/test_backlog.py + templates/PROFILE.md(Evolution 节→指针) + skills/sdlc-backlog/SKILL.md §5 + CLAUDE.md + README.md + 元数据；并 git add 现有 archive/ + EVOLUTION.md)

## Decisions log
- 2026-06-16 起 Deferred #2；用户选 track 策略 = option B「蒸馏 + 历史归档」：archive/ + EVOLUTION.md + PROFILE.md 入 git，在飞工作态(顶层 spec/plan/STATE/validate/review)仍本地。
- 2026-06-16 gitignore 改法：`.sdlc/` → `.sdlc/*` + `!.sdlc/archive/` + `!.sdlc/EVOLUTION.md` + `!.sdlc/PROFILE.md`（保留 web-review json 忽略）。
- 2026-06-16 用户加 option 1：把 Evolution log 独立化折进本特性——EVOLUTION.md 为唯一正屋，PROFILE `## Evolution log` 节降为一行指针，`_append_evolution` 简化为单路径(去 --profile)。理由：PROFILE=有界快照、EVOLUTION=无界流水，本性不同该分文件；PROFILE 六节有界不拆。
- 2026-06-16 用户后续想法 → Deferred：做 backlog 相关特性时把 EVOLUTION.md 每条对应到需求树叶子节点内（Retire 标 shipped 时已知 source-leaf，可顺带挂叶）。

## Next action
-> ship（owner：merge feat/archive-in-git → main + push origin；0.11.0）。3 commit：7a48317/f9abfb6/75e3846。注意远端可能又有新 commit（如另一路 evolve），push 前 fetch + 必要时 rebase。
