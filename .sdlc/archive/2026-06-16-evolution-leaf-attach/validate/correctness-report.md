# Validate · correctness — EVOLUTION 挂源叶（## sdlc 记录）

> 日期: 2026-06-16 ｜ 分支: feat/evolution-leaf-attach ｜ modes: correctness（only）
> 结果: **PASS**

## 模式解析
改动 = scripts/backlog.py + test_backlog.py + SKILL.md + CHANGELOG + 版本 json。纯后端逻辑，无用户可见面（无 e2e）、无 AI（无 eval-bench）→ active modes = **correctness only**。

## 证据（本轮真跑）
| 检查 | 命令 | 结果 |
|------|------|------|
| 全量套件 | `python3 scripts/test_backlog.py` | Ran 26 tests, OK, exit 0 |
| 结构 lint | `bash scripts/validate-skills` | PASS, exit 0 |

## 覆盖追踪（qa 视角，逐 codepath）
本特性新增分支真假两侧齐：
- `cmd_retire` 的 `if leaf_path`（挂叶）真侧 → `test_marks_leaf_and_writes_sdlc_log`（叶含 `## sdlc 记录`+entry+status:shipped，EVOLUTION 同写，JSON leaf_evolution 非空）。
- 假侧（不挂）→ `test_leaf_no_entry_no_sdlc_log`（有叶无 entry）+ `test_no_leaf_still_only_evolution`（无叶，leaf_evolution=None）。
- `_append_leaf_sdlc_log` 的"段缺则建"路 → 正路径用例覆盖；"段已存在追加"路 → `test_sdlc_log_appends_to_existing_section`（段头不重复、新旧条目都在）。
- `_mark_leaf_shipped` 返回类型 bool→path 变更后，既有 `test_marks_leaf_shipped_and_unblocks` 仍绿（`leaf_shipped` 语义不变）。

## 门控
- [x] 模式选齐（correctness 必跑，已跑）
- [x] correctness PASS（26 测试 0 fail exit 0 + validate-skills PASS）
- [x] e2e / eval-bench — N/A（无可见面 / 无 AI）
- [x] 无偷改实现（validate 期间工作树干净，0 改动）
- [x] 证据完整（命令 + exit code 在场）

→ validate 阶段 **PASS**，可进 sdlc-review。
