---
role: design
triggers: ["web/**", "components/**", "**/*.tsx", "**/*.vue", "**/*.css", "**/*.scss", "**/*.swift", "**/*.kt", "**/*.dart", "mobile/**", "ios/**", "android/**", "**/*.html", "design-system.md", "DESIGN.md"]
distilled-from: [gstack/review/design-checklist, web/design-quality, design-ux-architect, design-ux-researcher, design-persona-walkthrough, google-labs/design.md]
updated: 2026-08-10
---

# design 角色卡

设计视角检查设计意图、体验、可用性、视觉品质和可访问性。组件性能与状态管理归 client-dev。

## 关注点

1. **明确设计方向**：页面体现项目自己的信息层级和视觉决策，不是默认组件模板的简单组合。
2. **层级与节奏**：尺度、间距和内容密度服务于阅读顺序。
3. **排版纪律**：正文可读，字体数量受控，标题层级连续，文本行长合理。
4. **完整交互状态**：hover、focus、active、loading、empty、error 均有反馈。
5. **可访问性**：语义 HTML、键盘可达、可见焦点、WCAG AA 对比、reduced motion。
6. **设计系统一致性**：颜色、字体、间距和动效使用 token；项目 `DESIGN.md` 优先于通用规则。
7. **信息架构**：首屏能回答“是什么、适合谁、下一步做什么”，关键动作位置明确。
8. **响应式**：移动、平板和桌面断点均可用，无横向溢出。

## 静态检查

对 diff 命中的 UI 文件读完整上下文：

- [ ] 正文通常不小于 16px；字体家族不无序增加。
- [ ] 标题层级不跳级。
- [ ] 文本容器有合理 max-width。
- [ ] 交互元素有可见 `:focus-visible`；没有无替代的 `outline: none`。
- [ ] 颜色、字体、间距和圆角优先使用项目 token。
- [ ] 没有新增无必要的 `!important`。
- [ ] 语义元素优先于纯 div 堆叠。
- [ ] 动画优先使用 transform/opacity，并支持 `prefers-reduced-motion`。
- [ ] 固定宽度有移动端处理。
- [ ] 项目已有 `DESIGN.md` 时，颜色、排版和组件选择与其一致。

模板化风险包括：无产品理由的紫靛渐变、等距图标卡、全居中、所有组件同一大圆角和通用营销套话。它们是需要视觉判断的提示，不是自动失败条件。

## 渲染检查

由 e2e 在真实页面执行：

1. 选择 1–3 条受影响用户旅程。
2. 在 320、375、768、1024、1440 等适用断点检查布局。
3. 用键盘走关键流程，检查焦点顺序与焦点可见性。
4. 检查颜色对比、触控目标和 reduced motion。
5. 双主题项目分别检查明暗主题。
6. 对视觉缺陷保存必要的 before / target / after 证据。

没有浏览器或设备能力时，只做静态检查，将渲染项标 `INFERRED` 并给出人工步骤。

## 必要条件

- 无无替代焦点样式、键盘不可达或已确认的 AA 对比回归。
- 关键旅程在适用断点可完成。
- 项目设计系统没有未解释的偏离。
- 定性走查明确标为假设，不当作统计证据。
- 无法运行的渲染检查没有被写成 `TESTED`。

## 阶段贡献

| 阶段 | design 视角 |
|---|---|
| spec | 明确风格参考、信息架构、关键旅程和可访问性要求 |
| build | 检查 token、语义结构、交互状态和响应式实现 |
| validate | 在 e2e 中运行真实页面和设备检查 |
| review | 对 UI diff 做静态设计与可访问性检查 |

## 记录方式

所有详细证据进入当前 `.sdlc-v1/context/<FEAT>.engineering.md`：

- `## Validation` / `### Design`：断点、旅程、键盘、对比度、截图引用和限制。
- `## Review` / `### Design`：文件与行、类别、严重级别、证据等级和建议修复。

测试 runner 的截图或 trace 可留在项目原有产物目录并由研发上下文引用。design 与 E2E 的正文只写研发上下文，角色不定义进度字段。外层 `sdlc-validate` 或 `sdlc-review` 汇总后分别调用 `record-validation` 或 `record-review`。

## 常见错误

- 只看 diff hunk，不读组件完整上下文。
- 只测桌面宽度。
- 删除 focus 样式却没有替代。
- 无视 `DESIGN.md`，把项目刻意选择误报为问题。
- 把组件性能问题当设计问题。
- 把 persona 或五秒走查当成统计验证。
- 另建设计报告，与 Feature 研发上下文重复。
