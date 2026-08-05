---
name: sdlc-validate
description: >
  兼容适配器：保留 /sdlc validate 的精确 0.19.2 验证流程和 validate modes。
  新验证 preview 必须显式进入 sdlc-software-delivery，且不会影响 legacy control 或发布状态。
---

# sdlc-validate — legacy compatibility adapter

默认 /sdlc validate 先加载精确历史 runbook：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage validate

它保留所有 legacy validate modes、tested_sha Evidence 和
[control-plane.md](../sdlc/references/control-plane.md) 约束。固定对象缺失时停止并明确报告错误；不回退到
新 lifecycle。

显式 `/sdlc software-delivery --phase validate --authority dual-lifecycle-v1` 才进入 canonical 验证：当前
DeliveryPlan 的每个 Task 都需要与当前 tuple 匹配的通过 receipt，随后由 trace lint 写入 Feature 验证状态。
`/sdlc preview delivery --phase phase.delivery.validate …` 仍只进入 preview；其 Evidence 只能是 scoped 诊断，
不能更新 legacy Evidence、Feature 状态、review 或 ship 输入。
