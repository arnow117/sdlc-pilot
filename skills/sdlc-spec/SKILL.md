---
name: sdlc-spec
description: >
  兼容适配器：在 legacy profile 下保留 /sdlc spec 的精确 0.19.2 规格流程；
  façade 已固定 dual profile 时转交产品设计 canonical 生命周期，不迁移 legacy artifact。
---

# sdlc-spec — legacy compatibility adapter

先读取 `sdlc/references/lifecycle-profile.md`；`migration-required` 时停止且不写 legacy spec。

façade 已固定 `.sdlc/lifecycle.json=dual-lifecycle-v1` 时，`/sdlc spec` 进入 product-design 的下一产品阶段；
它只从 profile 和 dual ledger/projection 判断继续哪一阶段，不读取 legacy Markdown 推断。直接调用本 skill 或
legacy profile 下的 `/sdlc spec` 是 legacy 行为，不是 ProductContract、EngineeringSpec 或审批操作。先加载经
SHA-256 校验的 0.19.2 runbook，再完全按其原有流程执行：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage spec

历史 runbook 的 [control-plane.md](../sdlc/references/control-plane.md) 约束仍然有效。无法读取固定 Git
对象时停止并报告 legacy-runbook-error；不得用新的 product-design 流程静默替代。

直接调用者明确请求 `/sdlc product-design --authority dual-lifecycle-v1`，或 façade 已固定 dual profile 时，转到
sdlc-product-design 的 canonical 产品侧流程；它必须通过 dual ledger 写入 ProductDefinition、ProductContract
及由 authority config 派生的 Approval，不能反向写 legacy spec.md。`/sdlc preview product` 仍只用于预览：
它必须固定 run-id、PolicyManifest、PhaseContract 和输入 identity，只能写
.sdlc/preview/<run-id>/，不能修改 legacy spec.md、STATE.md 或 control。普通 legacy spec.md
可作为 preview 的观察输入，但不能自动转换为 ProductContract 或 EngineeringSpec。
