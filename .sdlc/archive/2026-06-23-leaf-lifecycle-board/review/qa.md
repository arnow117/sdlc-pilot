---
role: qa
reviewed: 2026-06-23
depth: deep
files_reviewed: 3
findings: { critical: 0, high: 0, medium: 0, low: 2, total: 2 }
status: issues_found
---
# 角色评审: qa (负路径/边界)

## 负路径覆盖核对（都有测试或 dogfood 证）
- ✓ 非法 status：LintBadStatusTest（lint 拒 banana）+ SetStatusTest.test_bad_value（set-status exit1 不写）。
- ✓ 叶不存在：SetStatusTest.test_missing_leaf（exit2）。
- ✓ allow-any 回退：SetStatusTest.test_allow_any_backward（validated→spec'd exit0）+ dogfood 3。
- ✓ 无 STATE 向后兼容：BoardLiveBadgeTest.test_no_overlay_without_state + dogfood 5（无 live-badge）。
- ✓ 钩子 flag=0 不动作：dogfood 1（切文件不 flush）。
- ✓ 无树 no-op：钩子 `[ -d "$req" ]` 守住；dogfood 对 sdlc-pilot 自身验证（无树跳过）。
- ✓ reconcile 只前进不回退：dogfood 2（shipped 不被 build stage 降级）。
- ✓ localStorage 隐私模式降级：lsGet/lsSet try/catch 静默（代码核对，CHAT_JS）。

## Python 反模式扫
- ✓ 无裸 except（cmd_set_status 无 try；_read_state_overlay 用 `except OSError`，具体异常）。
- ✓ 文件操作：_set_frontmatter_status/_read_state_overlay 用 `open(...).read()`——_read_state_overlay 的 `open(state).read()` 未用 with（见 LOW-02）。

## LOW
### LOW-02: _read_state_overlay 的 open() 未用 with
[LOW] (confidence: 6/10) scripts/board.py:_read_state_overlay — `txt = open(state, encoding="utf-8").read()` 未用 `with`，依赖 GC 关 fd。功能无碍（CPython 引用计数即时回收），但项目 coding-style「文件操作缺 with」列为反模式。
  verify-mode: DIFF-VERIFIABLE
  fix: `with open(state, encoding="utf-8") as f: txt = f.read()`。
  disposition: auto-fix（机械、低风险）

### LOW-03: 搜索过滤不收起空父节点
[LOW] (confidence: 7/10) scripts/board.py CHAT_JS 搜索 — 搜索只对 `.leaf` 加 `.hide`，匹配为空的 subdomain/domain `<details>` 仍展开显示空壳。非 bug（叶确实隐藏了），但视觉上留空标题。
  verify-mode: DIFF-VERIFIABLE
  fix: 搜索时额外判断每个 details 下可见 .leaf 数为 0 则给 details 加 .hide。可本期补或 Deferred（看板高级交互）。
  disposition: needs-human（UX 增强，非阻断；建议落 Deferred）
