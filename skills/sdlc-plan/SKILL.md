---
name: sdlc-plan
description: >
  兼容适配器：保留 /sdlc plan 的精确 0.19.2 legacy 计划流程。
  新 DeliveryPlan 只能由显式软件交付 lifecycle 生成；本 skill 不会从 legacy Markdown 推断或注册 v2 计划。
---

# sdlc-plan — legacy compatibility adapter

默认 /sdlc plan 保持 legacy spec.md → plan.md 流程。先读取固定历史 runbook：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage plan

历史 plan.md、Task 字段与 [control-plane.md](../sdlc/references/control-plane.md) 继续由 legacy runbook
解释。若 pinned Git blob 不可用，明确失败；不要把新编译器的输出写入 legacy plan.md。

显式 `/sdlc software-delivery --phase plan --authority dual-lifecycle-v1` 才进入 canonical delivery 规划；它必须
绑定已批准的 EngineeringSpec、当前 approval 与 Feature generation，并通过 ledger 原子创建完整 Task 集合。
`/sdlc preview delivery --phase phase.delivery.plan …` 仍只能创建 preview 诊断。DeliveryPlan@L 的 canonical JSON
manifest 与 Markdown projection 由 plan_compiler.py 的显式 API 处理；canonical projection 位于
`.sdlc/contracts/plans/<delivery-plan-id>/plan.projection.md`，preview projection 只能是
.sdlc/preview/<run-id>/plan.shadow.md，不能作为 legacy 计划或 control 输入。
