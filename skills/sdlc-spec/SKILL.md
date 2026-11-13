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
准备批次中，本阶段保留同样的产品确认和原型边界，并只返回自己的 canonical 候选块；未接受的 Plan 产物不得据此开始研发。

## 输入

- `product-projection --requirement-id <REQ-id>` 返回的 Requirement。
- Requirement 的 `product_context_ref`。
- 必要时读取 `.sdlc-v1/project.md` 了解产品与工程边界。
- `project.md` 列出的已验证长期目标/产品文档路径；若标为 `none` 或 `stale`，把方向缺口保留在产品上下文而不自行补全。

## 流程

1. 加载 `sdlc-product-design` 和 [`lifecycles/product-design.md`](../sdlc/references/lifecycles/product-design.md)。
2. 先核对产品上下文中的方向来源、预期结果和成功指标；长期文档只作为约束来源，不复制为当前需求正文。
3. 先复用已确认的来源和明确委托的选择，再按[尽早处理实质产品选择](../sdlc/references/lifecycles/product-design.md#尽早处理实质产品选择)
   提出会影响范围、行为或验收的少量问题；需要外部事实时按[调研上下文](../sdlc/references/research-context.md)
   记录问题、约束和证据范围，不把普通实现默认值或已经给出的答案重问一遍。
4. 用 Given/When/Then 或具体例子覆盖主路径、失败路径和边界。
5. 明确术语、业务规则、不变量、体验约束和非功能要求。
6. 将结论直接写回 `product_context_ref` 指向的 Markdown；按
   [`sdlc-product-design` 的产品决策来源规则](../sdlc-product-design/SKILL.md#产品上下文结构)
   保留当前决定的确认或委托来源、未决问题与结果指标。
   按 [sdlc-prototype 包内适配](../sdlc/references/integrations/product-prototype.md) 的唯一选择策略，使用它作为本阶段方法；适用时展示候选版本、
   定向反馈动作、实际检查范围和模拟边界，并把反馈造成的决定/版本变化写回当前产品上下文。
   小项目以语义完整且无重复为准：每项规则、数据 schema、接口和验收条件只保留一个权威定义，设计、计划和 Task 引用它，不复述它。
7. 仅对尚未有确认来源或明确委托、且会阻塞产品行为或验收的选择请求用户回答；未确认的建议、假设或开放替代项不能升格为 Requirement 或验收条件。
8. 条件满足后在 orchestrated mode 请求 `mark-requirement-ready`；只有独立、不在主 Agent 编排中的 standalone
   mode 才直接调用 CLI。

## 完成条件

- 需求描述的是产品行为，不是预先指定的实现方案。
- 每条关键规则至少有一个可验证例子。
- 范围内、范围外、异常行为和依赖均明确。
- 方向来源或其缺失已明确，预期结果包含可观察指标或明确的不可观测原因。
- 验收条件足以指导研发和测试。
- 每项规则、schema、接口和验收条件都有一个权威定义，后续内容只作必要引用；精简不删除失败边界或数据保护。
- 当前绑定要求有明确的用户确认、明确委托及实际采用项，或可追溯的已确认来源；推断、假设和开放替代项仍保持分离。
- 产品上下文路径仍与 `state.json` 中的 `product_context_ref` 一致。
- 产品/工程上下文中的持久规则段通过[持久规则写作清单](#持久规则写作清单人工检查)。

### 持久规则写作清单（人工检查）

在标记 ready 前，对产品/工程上下文中的长期行为、业务规则、契约与决定段执行本清单。它只适用于这些持久规则段；
确认来源、开放问题、当前计划及实现/验证/评审/发布记录段不适用，各自保留必要事实，不删生命周期证据。
这是人工检查：不新增脚本，不做全仓重写。编号沿用来源清单的实际定义（R1–R5、R7）；来源未定义 R6，不补造。

先做六个月测试：逐句问"当关联 PR 均已关闭且被遗忘后，这句话是否仍为真？"；不通过的句子按下表改写。

| 项 | 检查与处置 | 正反例 |
|---|---|---|
| R1 | 无历史叙事；写现在时系统行为 | "我们此前决定拒绝空值" → "空值被拒绝"。 |
| R2 | 持久规则段不塞调研、对比或 benchmark 过程；只留一两句结论并引用证据产物 | 十行候选比较移到既有调研产物；规则只留适用结论。 |
| R3 | 证据描述事实而非仅用 PR/issue 编号代替事实 | "由 PR #12 证明" → "非法输入时原文件字节保持一致"，必要时链接对应证据。 |
| R4 | 已拒方案在决定内一行说明 | 多段旧方案论证缩成一行 `Rejected: ...；原因 ...`。 |
| R5 | 无常驻 PR/issue 链接作为规则定义；使用当前记录或事实来源 | 链接本产品的兼容性规则，而不是让读者去关闭的 issue 找行为定义；确认日志中的真实来源可保留。 |
| R7 | 无"尚未构建/第一阶段"等项目状态充当持久规则 | 删除状态句，或写成准确的"某需求 gap：可观察偏差"；实际进度仍由 state/记录承载。 |

清单未通过时保持 `captured` 并改写对应段落；清单检查是文档语义证据，不冒充运行时行为测试。

未满足时保持 `captured` 并列出下一项澄清；不要为了推进状态而补猜答案。
