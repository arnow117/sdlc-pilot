---
role: qa
reviewed: 2026-06-16
depth: standard
files_reviewed: 2 (backlog.py, test_backlog.py)
findings: { critical: 0, high: 1, medium: 0, low: 0, total: 1 }
status: issues_found (已处置)
---
# 角色评审: qa
## HIGH
### WT-01: write-tree 无防路径遍历 — ✅ FIXED（兼 security 信任边界）
[HIGH] (confidence: 9/10) scripts/backlog.py cmd_write_tree — 叶 domain_path/id 直接拼文件路径，`domain_path:"../../etc"` 或 `id:"../../evil"` 可逃出 root（同 move QA-01 类，move 有守卫 write-tree 漏了）。tree JSON 来自 agent fan-out，受控但仍属外部输入。
  verify-mode: DIFF-VERIFIABLE  evidence: 加 test_rejects_path_traversal 两例（恶意 dp/id）→ 修前可写出 root 外。
  fix: dp 分段禁空/./.. + id 禁含 // 或 ..；非法即 skip。已修 + 测试绿。
  disposition: auto-fix
## 覆盖小结
新分支真假两侧齐：lint 4 字段(valid clean/无字段 clean/bad enum)、write-tree(正路径+可选字段/跳过已存在/防遍历)、board 交叉字段。33 测试绿 + validate-skills PASS。
