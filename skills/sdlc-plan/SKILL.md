---
name: sdlc-plan
description: >
  工程规划阶段。把 ready Requirement 转成一个 Feature、研发上下文和可执行 Task，
  明确设计、代码位置、依赖、测试策略与风险。
---

# sdlc-plan — Engineering plan

## 输入

- ready Requirement 及其 `product_context_ref`。
- `.sdlc-v1/project.md`。
- `product_context_ref` 中记录的方向来源、预期结果、成功指标和观察约束。
- 当前代码、测试和相关接口。

## 流程

1. 加载 `sdlc-software-delivery` 和 [`lifecycles/software-delivery.md`](../sdlc/references/lifecycles/software-delivery.md)。
2. 选择 Feature ID 与实际工作分支。
3. 创建 `.sdlc-v1/context/<feature-id>.engineering.md`，记录：
   - Requirement 与验收条件映射；
   - 长期方向来源与本 Feature 的预期结果；
   - 现状代码位置和约束；
   - 设计与关键取舍；
   - API、数据或兼容性变化；
   - Task、依赖和完成条件；
   - 测试策略、风险与回滚方式。
   - 发布后观察：指标/不可观测原因、基线和目标、观察窗口、负责人，以及反馈转为新 Requirement 的路径。
4. 调用 `start-feature --engineering-context-ref .sdlc-v1/context/<feature-id>.engineering.md`，写入 Requirement、Feature、分支和上下文引用。
5. 按可独立验证的增量调用 `add-task`；依赖使用 Task ID 明确表示。

## Task 质量

每个 Task 应有明确标题、代码范围、完成条件和验证方式。小改动可以只有一个 Task；不要为追求形式拆出无独立价值的步骤。

## 完成输出

返回 Feature ID、分支、研发上下文路径、Task 顺序、测试命令和第一个可开始的 Task。下一阶段是 `sdlc-build`。
