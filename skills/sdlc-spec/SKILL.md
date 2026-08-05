---
name: sdlc-spec
description: >
  兼容适配器：保留 /sdlc spec 的精确 0.19.2 legacy 规格流程。
  产品设计 preview 必须由用户显式调用 sdlc-product-design；本 skill 不会自动迁移或写双生命周期状态。
---

# sdlc-spec — legacy compatibility adapter

默认 /sdlc spec 是 legacy 行为，不是 ProductContract、EngineeringSpec 或审批操作。先加载经 SHA-256
校验的 0.19.2 runbook，再完全按其原有流程执行：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage spec

历史 runbook 的 [control-plane.md](../sdlc/references/control-plane.md) 约束仍然有效。无法读取固定 Git
对象时停止并报告 legacy-runbook-error；不得用新的 product-design 流程静默替代。

仅当调用者明确请求 `/sdlc product-design --authority dual-lifecycle-v1` 时，转到
sdlc-product-design 的 canonical 产品侧流程；它必须通过 dual ledger 写入 ProductDefinition、ProductContract
及由 authority config 派生的 Approval，不能反向写 legacy spec.md。`/sdlc preview product` 仍只用于预览：
它必须固定 run-id、PolicyManifest、PhaseContract 和输入 identity，只能写
.sdlc/preview/<run-id>/，不能修改 legacy spec.md、STATE.md 或 control。普通 legacy spec.md
可作为 preview 的观察输入，但不能自动转换为 ProductContract 或 EngineeringSpec。
