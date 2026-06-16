# Validate · correctness — archive 纳入 git + Evolution log 独立化

> Date: 2026-06-16 · 特性: Deferred #2 · active modes: [correctness]（skill-system-self，无 e2e/eval-bench）· result: **PASS**

## 证据（本轮新鲜跑）
| 检查 | 命令 | 结果 |
|---|---|---|
| 单测 | `python3 scripts/test_backlog.py` | exit 0；`Ran 12 tests … OK`（含改后 test_backflow_always_evolution_md + 新增 test_retire_rejects_profile_flag） |
| 结构 lint | `bash scripts/validate-skills` | exit 0；PASS |
| gitignore 行为 | `git check-ignore` ×3 | `.sdlc/spec.md` IGNORED；`archive/.../spec.md`、`EVOLUTION.md` TRACKED ✓ |
| 无偷改实现 | `git status --porcelain`（去未跟踪） | 空（无已跟踪未提交改动） |

## 改动集（vs main，21 文件）
代码：backlog.py（_append_evolution 单路径、去 --profile）、test_backlog.py。
契约/文档：.gitignore、templates/PROFILE.md（节→指针）、skills/sdlc-backlog/SKILL.md §5、CLAUDE.md、README.md。
元数据：plugin/marketplace（0.11.0）、CHANGELOG.md。
**dogfood 入仓**：.sdlc/archive/{sdlc-backlog,feature-retirement}/** + .sdlc/EVOLUTION.md（首批历史归档进 git）。

## 门控
correctness PASS（测试全绿 + lint clean + 新/改函数有测试 + gitignore 行为实测 + 无偷改）→ 可进 review。
