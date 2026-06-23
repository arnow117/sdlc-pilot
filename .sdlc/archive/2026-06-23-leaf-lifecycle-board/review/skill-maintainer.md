---
role: skill-maintainer
reviewed: 2026-06-23
depth: deep
files_reviewed: 11
findings: { critical: 0, high: 0, medium: 0, low: 1, total: 1 }
status: issues_found
---
# 角色评审: skill-maintainer (R10 改技能体系自身)

## 三铁律核对
- **不加顶层 skill** ✓：写回三件套挂在 backlog op（set-status）+ driver 规程（§1.1b）+ 钩子模板，无新 stage/skill。看板抽 `board.py` 是脚本拆分，非新 skill。
- **可移植纯标准库** ✓：backlog.py/board.py 纯 stdlib；board.py `from backlog import` + backlog 惰性 `import board`（仅 board 子命令触发），dogfood 验 import 链 OK，无运行期循环。post-checkout 纯 sh，无外部依赖。
- **纯文件 + 单写者** ✓：STATE 仍只 driver 写；叶 status 由 set-status 机械写 `.sdlc/requirements/`（另一文件域），与 STATE 无写竞争。

## 单一事实源
- ✓ STATUS_ORDER/STAGE_TO_STATUS 在 backlog.py 顶部唯一定义；legend/dist 迭代 STATUS_ORDER，_read_state_overlay 用 STAGE_TO_STATUS；driver §1.1b 明确"见 backlog.py，不重抄顺序"；钩子 case 映射与 STAGE_TO_STATUS 一致（sh 无法 import，是必要的镜像，已注释标注"与 backlog.STAGE_TO_STATUS 一致"）。
- ✓ BOARD_CSS 的 `.status-X` 是颜色（渲染必需），非顺序，不算重复事实源。

## semver + 溯源
- ✓ plugin/marketplace 0.15.0→0.16.0（MINOR，纯增能力，向后兼容）。
- ✓ CHANGELOG distilled-from: `session:sdlc-leaf-lifecycle-board-2026-06-23`。

## CLAUDE.md 迭代清单符合
- ✓「加/改 backlog 派生操作」：set-status 加子命令 + test + SKILL（注：backlog SKILL op 枚举本期未列 set-status——见 LOW-01）。
- ✓「改 spec/plan/build 流程」：driver §1.1b、onboard Phase D 改的是 SKILL.md，§0 可移植前置未动。

## LOW
### LOW-01: set-status 未登记进 sdlc-backlog SKILL 的 op 枚举
[LOW] (confidence: 7/10) skills/sdlc-backlog/SKILL.md — set-status 是新 backlog op，但本期未在 sdlc-backlog SKILL 顶部 op 枚举 + 操作章节登记（CLAUDE.md「加/改 backlog 派生操作」步骤②要求）。
  verify-mode: DIFF-VERIFIABLE（diff 未含 sdlc-backlog/SKILL.md）
  fix: 在 sdlc-backlog SKILL.md op 列表加 `set-status`（一行说明：机械改叶 status，allow-any，供钩子/reconcile/人手）。set-status 主要是内部原语（钩子/reconcile 调），但人手也可用，登记利于发现。
  disposition: needs-human（是否登记 = 维护者判断；可本期补或落 P1 待办）
