---
name: sdlc-spec
description: >
  产品规格阶段。读取 Requirement 的 product_context_ref，调用产品设计方法收敛场景、业务规则、
  范围、质量属性与验收条件；完成后把 Requirement 标记为 ready。
distilled-from: [Zts0hg/codexspec]
---

# sdlc-spec — 收敛产品规格

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。spec Agent 写产品上下文并返回
`mark-requirement-ready` 请求；仅在 brief 明确允许时，可在项目约定目录创建或更新有界原型产物。由主 Agent 在验收条件
和用户决定已完整时执行。只有没有当前主 Agent 编排的独立调用才使用 standalone mode。

## 输入

- `product-projection --requirement-id <REQ-id>` 返回的 Requirement。
- Requirement 的 `product_context_ref`。
- 必要时读取 `.sdlc-v1/project.md` 了解产品与工程边界。
- `project.md` 列出的已验证长期目标/产品文档路径；若标为 `none` 或 `stale`，把方向缺口保留在产品上下文而不自行补全。

## 流程

1. 加载 `sdlc-product-design` 和 [`lifecycles/product-design.md`](../sdlc/references/lifecycles/product-design.md)。
2. 先核对产品上下文中的方向来源、预期结果和成功指标；长期文档只作为约束来源，不复制为当前需求正文。
3. 澄清问题、目标用户、期望结果和不做什么。
4. 用 Given/When/Then 或具体例子覆盖主路径、失败路径和边界。
5. 明确术语、业务规则、不变量、体验约束和非功能要求。
6. 将结论直接写回 `product_context_ref` 指向的 Markdown；按
   [`sdlc-product-design` 的产品决策来源规则](../sdlc-product-design/SKILL.md#产品上下文结构)
   保留当前决定的确认来源、未决问题与结果指标。
   按 [sdlc-prototype 包内适配](../sdlc/references/integrations/product-prototype.md) 的唯一选择策略，使用它作为本阶段方法。
7. 与用户确认范围和验收条件；未确认的建议、假设或开放替代项不能升格为 Requirement 或验收条件。
8. 条件满足后在 orchestrated mode 请求 `mark-requirement-ready`；只有独立、不在主 Agent 编排中的 standalone
   mode 才直接调用 CLI。

## 完成条件

- 需求描述的是产品行为，不是预先指定的实现方案。
- 每条关键规则至少有一个可验证例子。
- 范围内、范围外、异常行为和依赖均明确。
- 方向来源或其缺失已明确，预期结果包含可观察指标或明确的不可观测原因。
- 验收条件足以指导研发和测试。
- 当前绑定要求有明确的用户确认或可追溯的已确认来源；推断、假设和开放替代项仍保持分离。
- 产品上下文路径仍与 `state.json` 中的 `product_context_ref` 一致。

未满足时保持 `captured` 并列出下一项澄清；不要为了推进状态而补猜答案。
