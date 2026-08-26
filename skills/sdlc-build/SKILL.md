---
name: sdlc-build
description: >
  实现阶段。按 Feature 的研发上下文和 Task 依赖推进代码，默认使用 TDD，
  记录必要的工程决策并通过 lifecycle_state 更新 Task 状态。
---

# sdlc-build — 实现 Feature

## 入口

1. 读取 `feature-projection --feature-id <feature-id>`。
2. 读取 `engineering_context_ref` 与 `product_context_ref`。
3. 对当前流程中新规划的非简单 Feature，确认研发上下文已经记录复用评估及决定；若缺失，或实现前发现候选框架、依赖能力与原评估明显不符，返回 `sdlc-plan` 更新设计，不在 build 阶段临时拍板引入框架。
4. 选择一个依赖已完成的 Task；不要同时修改多个相互覆盖的 Task。
5. 根据 `.sdlc-v1/project.md` 和 Git diff 加载相关角色卡与语言参考。

## 实现循环

1. 调用 `set-task-status ... --status in_progress`。
2. 复述本 Task 的完成条件和对应产品验收条件。
3. 写明会影响实现或验收的假设；高风险歧义先确认，低风险默认值说明后继续。
4. 优先写失败测试；确认失败原因与目标行为一致。
5. 实现满足当前完成条件的最小改动，不为推测的未来需求新增抽象或扩展点。
6. 运行受影响区域的静态检查和测试。
7. 必要时重构，再运行相同检查；只修改本 Task 范围内的代码，不顺带格式化、重构或清理无关区域，只删除本次改动产生的无用代码。
8. 把有长期价值的设计决定、代码位置变化和风险更新到研发上下文。
9. 逐条核对完成条件与验收条件，记录实际检查命令和结果；满足后调用 `set-task-status ... --status done`。

## 调试

遇到意外失败时，先形成可证伪假设，再做最小实验。不要连续堆叠无依据的修补。若发现产品规则缺口，停止当前 Task，将问题写回产品上下文并交给产品侧确认。

## 并行

只有写集基本不重叠、接口已明确、可以独立验证的 Task 才并行。每个执行者使用独立分支或 worktree；合并后由 Feature 负责人在集成 commit 上重新运行验证。

## 完成输出

返回已完成 Task、变更摘要、测试结果、尚未完成或被阻塞的 Task。全部 Task 为 `done` 后进入 `sdlc-validate`。
