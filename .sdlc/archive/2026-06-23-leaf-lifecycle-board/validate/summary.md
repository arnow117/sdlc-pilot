# Validate 汇总 — 需求树生命周期状态同步 + 看板重构（0.16.0）

> 日期 2026-06-23 ｜ 分支 feat/leaf-lifecycle-board ｜ modes: correctness + dogfood
> 阶段总判定: **PASS**

## correctness — PASS
- `python3 scripts/test_backlog.py` → **48 测试 OK exit 0**（含新增 StatusEnumTest/LintBadStatusTest/SetStatusTest/BoardLiveBadgeTest/BoardRenoTest）。
- `bash scripts/validate-skills` → **PASS ✅**。
- `import board`（抽模块后 import 链）→ OK（render_board / _read_state_overlay 可达）。

## dogfood — PASS（带树 git fixture 真跑）

| # | 验什么 | 结果 |
|---|--------|------|
| 1 | post-checkout 钩子真 flush | ✓ 临时 git repo 真 `git checkout` 切分支 → 源叶 status `captured→built` 落盘；切文件(flag=0)不动作 |
| 2 | driver reconcile 只前进不回退 | ✓ `captured` vs validate stage = 落后(补)；`shipped` vs build stage = 不落后(不降级) |
| 3 | set-status allow-any 迁移 | ✓ `validated→spec'd` 回退 exit 0 成功（不挡迁移） |
| 4 | 看板 4 痛点 + live badge | ✓ HTML 含 legend/dist/tree-search/crumb/字段分组(身份·交叉)/dep-link/live-status；带 STATE 时在飞叶有 `live-badge` + "validate中"文案 |
| 5 | 无 STATE 向后兼容 | ✓ 无 STATE 渲染不含 `class="live-badge`，行为同旧版 |
| — | lint 拒非法 status | ✓ `status: banana` → bad-status exit 1（correctness SetStatus/LintBadStatus 覆盖） |
| — | set-status 四路径 | ✓ 成功/allow-any 回退/非法值 exit1/叶不存在 exit2（SetStatusTest） |

## 无偷改实现
- validate 期间 `git status --porcelain scripts/` 干净——所有实现都在 build 阶段 10 提交内，validate 未改实现文件。

## 看板效果（人工可看）
- 已起本地服务：**http://127.0.0.1:8799/**（examples/requirements-fixture + 演示 STATE，源叶 order.checkout.place-order 标 build 在飞）。
- 可看：状态图例（点击过滤）/ 每域+全树进度分布条 / 搜索框 / 折叠记忆 / 选叶面包屑 / 叶详情 4 组分组 + depends_on 可点跳转 + 字段 tooltip / 聊天面板 live 监听状态（纯 http 无 /rev → ⚪未监听，符合预期）/ 在飞叶 live badge。

## 门控
- [x] correctness PASS
- [x] dogfood PASS（写回三件套 + 看板 + 兼容全证）
- 阶段 = **PASS**，next → sdlc-review。
