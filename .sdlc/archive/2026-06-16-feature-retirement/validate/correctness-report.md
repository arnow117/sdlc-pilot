# Validate · correctness 报告 — feature 退场 / backlog Retire op

> Date: 2026-06-16
> 特性: backlog Retire op（feature 退场 / 工件生命周期）
> active modes: [correctness]（仅此——target surface = skill-system-self，无用户可见面 → 无 e2e；无 AI/模型/策略 → 无 eval-bench）
> result: **PASS**

## 改动集（vs main）
11 文件，全 additive：
- 代码：`scripts/backlog.py`、`scripts/test_backlog.py`
- 文档/契约：`skills/sdlc-backlog/SKILL.md`、`skills/sdlc/SKILL.md`、`templates/STATE.md`、`templates/PROFILE.md`
- 元数据：`.claude-plugin/{plugin,marketplace}.json`、`CHANGELOG.md`、`README.md`、`CLAUDE.md`

## 证据（本轮新鲜跑）

| 检查 | 命令 | 结果 |
|---|---|---|
| 全量单测 | `python3 scripts/test_backlog.py` | **exit 0**；`Ran 11 tests … OK`（既有 5 + RetireTest 6） |
| 结构 lint | `bash scripts/validate-skills` | **exit 0**；`RESULT: PASS ✅`（角色/模式/frontmatter/引用一致、无悬空、可移植自检、sdlc-guard 自包含） |
| 无偷改实现 | `git status --porcelain` | **空**（工作树干净，3 commit 全提交；validate 期间 0 改动源码） |
| 新函数有测试 | — | `cmd_retire` + `_set_frontmatter_status`/`_mark_leaf_shipped`/`_append_evolution` 均被 RetireTest 6 用例覆盖 |

## RetireTest 覆盖的行为（qa 视角：含边界/降级/错误路径）
1. `test_archives_and_clears` — 归档落位 + 顶层清空
2. `test_marks_leaf_shipped_and_unblocks` — 标源叶 shipped → ready-queue 解锁下游
3. `test_backflow_to_profile_section` — 回流 PROFILE `## Evolution log`（建段）
4. `test_backflow_fallback_evolution_md` — 无 PROFILE 兜底 `.sdlc/EVOLUTION.md`
5. `test_archive_exists_refuses` — 幂等：archive 已存在拒绝覆盖、不动文件（错误路径）
6. `test_no_leaf_graceful` — 无 leaf/无树优雅降级（边界）

## dogfood（端到端，临时目录，不污染本仓）
`backlog.py retire --sdlc <tmp> --slug demo --leaf <id> --req-root <r> --profile <p> --evolution-entry "..."`
六行为人工核对全过：归档落位 / 顶层清空 / 叶 status=shipped / PROFILE 建 Evolution log 段并追加 / 重跑幂等拒绝（exit 1）。

## 门控判定
- correctness：**PASS**（测试全绿 exit 0 + lint PASS exit 0 + 新函数有测试 + 无偷改实现）。
- 无数字覆盖率门（markdown skill 族；correctness 定义 = 套件全绿 + 结构 lint clean + 新函数有测试）。
- 阶段总判定：**PASS** → 可进 sdlc-review。
