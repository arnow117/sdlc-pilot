---
name: sdlc-software-delivery
description: >
  软件交付生命周期。把 ready Requirement 转成研发上下文、Feature 和 Task，使用 SDD/TDD 完成实现，
  并把验证、评审和发布绑定到明确的 Git commit。
---

# sdlc-software-delivery

本技能回答“如何可靠地实现、验证和发布产品意图”。详细方法见
[`lifecycles/software-delivery.md`](../sdlc/references/lifecycles/software-delivery.md)。

## 输入

- ready Requirement 与 `product_context_ref`。
- `.sdlc-v1/project.md`。
- Feature 的 `engineering_context_ref`，若尚无则创建。
- 当前代码、测试和 Git 状态。

## 研发上下文结构

```text
关联 Requirement 与验收条件
长期方向来源与本 Feature 的预期结果
现状代码和约束
复用评估与决定（方法和触发条件由 `sdlc-plan` 定义）
设计与关键取舍
接口、数据和兼容性影响
Task 与依赖
测试和验证策略
风险、回滚与运维要求
实现过程中的工程决策
验证、评审和发布摘要
发布后观察：指标或不可观测原因、基线/目标、观察窗口、负责人、反馈回流 Requirement
```

## 默认序列

```text
start-feature → add-task → set-task-status
→ record-validation → record-review → record-release
```

1. 规划：先按 `sdlc-plan` 评估复用现有实现或成熟依赖，再把产品验收条件映射到设计和 Task，写入研发上下文。
2. 实现：依赖就绪的 Task 才开始；默认先写失败测试，再实现最小改动。
3. 调试：用假设和最小实验定位问题，避免无依据地连续改动。
4. 验证：运行与 diff 相符的检查，并把通过结果绑定到当前集成 commit。
5. 评审：根据 surface map 和 diff 加载相关角色；必须修复项清零后批准。
6. 发布：只发布评审对应的 commit；部署与回滚由 `sdlc-ship` 执行，并在工程上下文记录结果观察与反馈回流计划。

## 角色与方法

- 客户端、服务端、数据、设计、QA 与安全角色由 [`role-routing.md`](../sdlc/references/role-routing.md) 动态选择。
- 跨两个以上 surface、改变公共接口或数据归属时加载 `architect`。
- 只有高风险持久化格式、跨机器协议、不可逆外部行为或公共 API 兼容性决策，才使用对抗性架构复核。

## Commit 一致性

全部 Task 完成后才能记录通过验证。验证时 `.sdlc-v1/**` 之外的业务代码工作树必须干净；命令保存测试时的 HEAD 作为 validation commit。之后可以提交仅修改 `.sdlc-v1/**` 的状态、上下文和证据。评审与发布要求 validation commit 到当前 HEAD 在该目录之外无差异，且业务代码工作树干净。Task 重新打开或业务代码变化后，重新验证。

工程侧发现产品规则缺口时，停止相关 Task，将问题写回产品上下文，由产品侧决定补充规则、增加 Task 或建立新 Requirement。
