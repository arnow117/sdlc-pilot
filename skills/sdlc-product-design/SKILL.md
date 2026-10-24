---
name: sdlc-product-design
description: >
  产品设计生命周期。用 BDD、领域建模、体验设计和质量属性把原始请求收敛为可验证的产品上下文，
  并通过 lightweight state 管理 Requirement 进度。
distilled-from: [Zts0hg/codexspec]
---

# sdlc-product-design

本技能回答“为什么做、给谁做、系统对外表现什么行为”。详细方法见
[`lifecycles/product-design.md`](../sdlc/references/lifecycles/product-design.md)。

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。产品设计 Agent 更新产品正文并请求
必要的 Requirement transition；仅在 brief 明确允许时，可在项目约定目录创建或更新有界原型产物。主 Agent 验证后更新
state。缺少会改变范围的产品决定时返回问题，不猜测推进。

## 输入

- 原始用户请求或现有 Requirement。
- `.sdlc-v1/project.md` 中与产品边界有关的事实。
- `project.md` 列出的、当前 commit 已验证的长期目标/产品文档；缺失时记录 `none`，不臆造方向。
- `.sdlc-v1/context/<requirement-id>.product.md`。

若 Requirement 尚不存在，先创建产品上下文，再调用 `capture-requirement` 并保存 `product_context_ref`。

## 产品上下文结构

产品上下文按 [PRODUCT.md](../sdlc/references/templates/PRODUCT.md) 保留 requirements 与详细 spec 的源章节顺序、必填标记和条件可选标记。
简单需求可以简写适用内容；条件可选部分仅在适用时出现，核心部分不改成另一种文档结构。产品结果观察计划应写明发布后观察窗口、负责人和反馈回流。

稳定 ID 可以用于复杂需求：`SCN-*` 表示场景，`TERM-*` 表示术语，`RULE-*` 表示规则，`NFR-*` 表示质量要求。简单需求不必为了格式制造大量 ID。
产品决策的来源、变更和未确认事项按[产品决策来源与变更](../sdlc/references/lifecycles/product-design.md#7-产品决策来源与变更)
记录。历史上下文不要求批量迁移，也不另建进度来源。

## 工作顺序

1. 方向对齐：读取已验证的长期目标/产品来源，只引用与本 Requirement 有关的约束；没有来源时明确记录缺口。
2. 问题发现：确认用户痛点、现状、结果和不做什么；按[尽早处理实质产品选择](../sdlc/references/lifecycles/product-design.md#尽早处理实质产品选择)
   只提出会影响当前产品行为或验收的针对性问题。已确认来源、明确委托的选择和普通低风险默认值不重复询问。
3. 行为设计：用 Given/When/Then 和例子覆盖主路径、失败路径、权限与边界。
4. 领域澄清：建立统一语言，识别实体、值、规则、不变量和归属边界。
5. 体验设计：明确状态、反馈、空态、错误、无障碍和跨端差异。涉及页面、组件、表单、导航、空态、loading/error
   反馈、响应式、无障碍或视觉方向时，即使没有代码 diff 也选择 `design`；按
   [`design` 角色卡](../sdlc/references/roles/design.md) 和其引用的可选适配复用既有事实，只补会改变体验或验收的缺口。
   按 [sdlc-prototype 包内适配](../sdlc/references/integrations/product-prototype.md) 的唯一选择策略制作有界 demo；
   展示可打开的候选版本与定向反馈动作，并把确认、委托或开放项和版本影响写回产品上下文。它不替代产品上下文、当前阶段或生产验证。
6. 质量设计：明确性能、可靠性、安全、隐私、可观测和评估要求，以及可在发布后观察的结果信号。
7. 产品确认：按[产品决策来源与变更](../sdlc/references/lifecycles/product-design.md#7-产品决策来源与变更)
   区分已确认的当前决定、假设和开放替代项；再检查方向来源、场景、规则、验收条件和结果指标无矛盾，处理未决问题。

## 角色

- 默认加载 `product-owner`。
- 术语、规则或业务边界复杂时加载 `domain-expert`。
- 交互或视觉行为显著时加载 `design`；没有代码 diff 不影响该选择。
- 涉及敏感数据、认证、授权、支付或合规时加载 `security`。

## 状态

产品侧只执行 `capture-requirement` 和 `mark-requirement-ready`。它可以用 `product-projection` 查看研发进度，但不修改 Feature、Task、验证、评审或发布状态。

产品规则发生实质变化时，先更新产品上下文；已经发布的能力通常新建 Requirement，不改写已完成记录。
