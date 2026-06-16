---
role: qa
reviewed: 2026-06-16
depth: standard
files_reviewed: 2 (scripts/backlog.py, scripts/test_backlog.py)
findings: { critical: 0, high: 1, medium: 1, low: 2, total: 4 }
status: issues_found (全部已处置)
---
# 角色评审: qa

## HIGH
### QA-01: `move --to` 路径遍历(信任边界) — ✅ FIXED
[HIGH] (confidence: 9/10) scripts/backlog.py cmd_move — `--to` 直接拼进文件路径,`../` 可逃出 root。
  role: qa  verify-mode: DIFF-VERIFIABLE
  evidence: `--to "../../../tmp/evil"` 实测原可写到 root 外。
  fix: 加守卫——`new_dp` 分段后禁含 `""/"."/".."`,非法即 return 2。
  disposition: auto-fix（已修 + 新增 `MoveTest.test_rejects_path_traversal_to` 4 例）

## MEDIUM
### QA-02: board HTML 转义无测试(信任边界) — ✅ FIXED
[MEDIUM] (confidence: 8/10) scripts/backlog.py render_board — 用了 `html.escape`,但无测试证明叶内容里的 HTML 被转义。
  evidence: 选叶详情/标题进 innerHTML 路径。
  fix: 加 `BoardTest.test_board_escapes_html_in_leaf_content`(title=`<script>` → 断言未原样出现 + `&lt;script&gt;` 在场)。已绿。
  disposition: auto-fix（补测;转义实现本就正确）

## LOW（accept — 防御性分支,低风险）
### QA-03: build_tree 的 domain_path 缺失回退分支未单测
[LOW] (confidence: 6/10) 当叶无 domain_path 时退回 `_path` 目录名——defensive,合法树不会触发。disposition: accept
### QA-04: _extract_body 无 frontmatter 分支未单测
[LOW] (confidence: 6/10) 返回全文兜底——defensive。disposition: accept

## 覆盖小结
- 新命令负路径覆盖良好:tree(空树)、move(源缺/目标占用/迁移+依赖改写/路径遍历)、board(空树/转义/详情嵌入)。
- 22 测试全绿(TreeTest2/MoveTest4/BoardTest4 + 既有12);validate-skills PASS;e2e:Web 已在 validate 实测。
