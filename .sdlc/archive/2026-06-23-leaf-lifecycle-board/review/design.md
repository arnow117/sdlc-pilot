---
role: design
reviewed: 2026-06-23
depth: standard
files_reviewed: 2
findings: { critical: 0, high: 0, medium: 0, low: 1, total: 1 }
status: issues_found
---
# 角色评审: design (看板,DESIGN.md §8 为判定基准)

## 对照 DESIGN.md §8 契约核对
- ✓ §8.1 进度分布条：按 STATUS_ORDER 分段，段用 §2.1 status 色，段 title="status·N"，8px 高 4px 圆角描边；保留 shipped/total 旁注。
- ✓ §8.2 live badge：status 映射色底 + 1px green 描边 + opacity 脉冲动画；`prefers-reduced-motion` 关动画（CSS `@media ... .live-badge{animation:none}`）；无 STATE 不渲染。
- ✓ §8.3 叶详情 4 组：身份/定位/关系/交叉 小标题；depends_on 渲染 `.dep-link`（仅已知叶 id，getElementById 跳转）；字段 tooltip（FIELDTIP）。
- ✓ §8.4 树导航：搜索框 + localStorage 折叠记忆 + 面包屑（domain › subdomain › leaf）+ 图例点击状态过滤。
- ✓ §8.5 聊天监听状态：🟢/⚪ live-status + 空态引导文案。

## 交互态 / a11y
- ✓ 图例 `.lg` hover/aria-pressed；搜索框 :focus 边框；状态过滤用 opacity 不动 layout。
- ✓ 动效仅 opacity（live badge 脉冲）+ reduced-motion 全关。
- ✓ 状态色板沿用既有 §2.1（已声明对比达 AA）。
- ✓ 6 状态语义色为强调底，深墨文字 on 浅底（captured/specd/planned/validated）、shipped 绿底白字——对比 AA（沿用既有）。

## LOW
### LOW-04: 面包屑 crumb 各级未做成可点回跳
[LOW] (confidence: 8/10) scripts/board.py CHAT_JS setCrumb — DESIGN §8.4 写"各级可点回跳"，实现 setCrumb 只渲染纯文本 `domain › subdomain › leaf`（.crumb a 的 CSS 已备但未生成 <a>）。功能性面包屑（显示定位）达成，可点回跳未做。
  verify-mode: DIFF-VERIFIABLE
  fix: setCrumb 把 domain/subdomain 段渲染成 <a> 点击展开对应 details 并 scrollIntoView。属增强，非阻断。
  disposition: needs-human（建议落 Deferred「看板高级交互」或本期补；面包屑核心价值=显示定位已达成）
