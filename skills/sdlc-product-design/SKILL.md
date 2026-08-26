---
name: sdlc-product-design
description: >
  产品设计生命周期。用 BDD、领域建模、体验设计和质量属性把原始请求收敛为可验证的产品上下文，
  并通过 lightweight state 管理 Requirement 进度。
---

# sdlc-product-design

本技能回答“为什么做、给谁做、系统对外表现什么行为”。详细方法见
[`lifecycles/product-design.md`](../sdlc/references/lifecycles/product-design.md)。

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。产品设计 Agent 只更新产品正文并请求
必要的 Requirement transition；主 Agent 验证后更新 state。缺少会改变范围的产品决定时返回问题，不猜测推进。

## 输入

- 原始用户请求或现有 Requirement。
- `.sdlc-v1/project.md` 中与产品边界有关的事实。
- `project.md` 列出的、当前 commit 已验证的长期目标/产品文档；缺失时记录 `none`，不臆造方向。
- `.sdlc-v1/context/<requirement-id>.product.md`。

若 Requirement 尚不存在，先创建产品上下文，再调用 `capture-requirement` 并保存 `product_context_ref`。

## 产品上下文结构

```text
问题与当前行为
方向来源（长期目标/产品文档路径、对应 commit，或 `none`）
目标用户与期望结果
预期结果、成功指标、基线/目标值与观测方式
发布后观察窗口、负责人和新反馈应回流到的 Requirement
范围内 / 范围外
用户场景与具体例子
术语、业务规则和不变量
体验约束
非功能要求
验收条件
依赖、未决问题和产品决策
```

稳定 ID 可以用于复杂需求：`SCN-*` 表示场景，`TERM-*` 表示术语，`RULE-*` 表示规则，`NFR-*` 表示质量要求。简单需求不必为了格式制造大量 ID。

## 工作顺序

1. 方向对齐：读取已验证的长期目标/产品来源，只引用与本 Requirement 有关的约束；没有来源时明确记录缺口。
2. 问题发现：确认用户痛点、现状、结果和不做什么。
3. 行为设计：用 Given/When/Then 和例子覆盖主路径、失败路径、权限与边界。
4. 领域澄清：建立统一语言，识别实体、值、规则、不变量和归属边界。
5. 体验设计：明确状态、反馈、空态、错误、无障碍和跨端差异。
6. 质量设计：明确性能、可靠性、安全、隐私、可观测和评估要求，以及可在发布后观察的结果信号。
7. 产品确认：检查方向来源、场景、规则、验收条件和结果指标无矛盾，处理未决问题。

## 角色

- 默认加载 `product-owner`。
- 术语、规则或业务边界复杂时加载 `domain-expert`。
- 交互或视觉行为显著时加载 `design`。
- 涉及敏感数据、认证、授权、支付或合规时加载 `security`。

## 状态

产品侧只执行 `capture-requirement` 和 `mark-requirement-ready`。它可以用 `product-projection` 查看研发进度，但不修改 Feature、Task、验证、评审或发布状态。

产品规则发生实质变化时，先更新产品上下文；已经发布的能力通常新建 Requirement，不改写已完成记录。
