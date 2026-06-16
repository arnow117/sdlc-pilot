---
role: qa
reviewed: 2026-06-16
depth: standard
files_reviewed: 2 (backlog.py, test_backlog.py)
findings: { critical: 0, high: 0, medium: 0, low: 1, total: 1 }
status: issues_found (accept)
---
# 角色评审: qa

## 覆盖追踪（逐 codepath）
本特性新增分支真假两侧齐（见 validate/correctness-report.md）：
- `cmd_retire` 挂叶分支 真侧（test_marks_leaf_and_writes_sdlc_log）/ 假侧（test_leaf_no_entry / test_no_leaf_still_only_evolution）。
- `_append_leaf_sdlc_log` 段缺则建（正路径）/ 段已存在追加（test_sdlc_log_appends_to_existing_section，断言段头计数=1）。
- `_mark_leaf_shipped` 返回类型变更后既有 test_marks_leaf_shipped_and_unblocks 仍绿（leaf_shipped 语义不变）。
- 降级：无叶 → leaf_evolution=None（test_no_leaf_still_only_evolution 断言）。
26 测试全绿、validate-skills PASS。

## LOW（accept — 极低概率边界）
### QA-01: `_append_leaf_sdlc_log` 用子串检测段头
[LOW] (confidence: 5/10，中置信请核实) scripts/backlog.py `_append_leaf_sdlc_log` — `if LEAF_SDLC_LOG_HEADER not in text` 是子串匹配。若某叶**正文**恰含字面 "## sdlc 记录"（如需求本身在讲 sdlc 日志），会误判为段已存在、跳过建头，entry 仍追加到文件末尾（多数情况仍在该段下，行为可接受）。
  verify-mode: DIFF-VERIFIABLE
  evidence: 段头串 "## sdlc 记录" 足够独特，需求正文撞它的概率极低；即便撞上，entry 仍落文件尾，无数据损坏/崩溃。
  fix（若将来需要）: 改为行首锚定 `re.search(r"(?m)^## sdlc 记录\s*$", text)`。
  disposition: accept（极低概率 + 无害后果；记录待将来按需收紧）

## 负路径/边界小结
- rstrip("\n") 边界：空文件/无尾换行 → 仍正确建段+追加。
- 实现 bug：0（无 escalate 回 build）。
