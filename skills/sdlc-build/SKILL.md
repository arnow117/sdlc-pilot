---
name: sdlc-build
description: >
  兼容适配器：在 legacy profile 下保留 /sdlc build 的精确 0.19.2 TDD/调试流程；
  façade 已固定 dual profile 时转交软件交付 canonical 生命周期，不迁移 legacy Evidence 或 Task。
---

# sdlc-build — legacy compatibility adapter

先读取 `sdlc/references/lifecycle-profile.md`；`migration-required` 时停止且不写 legacy Task 或 Evidence。

façade 已固定 `.sdlc/lifecycle.json=dual-lifecycle-v1` 时，`/sdlc build` 进入 software-delivery 的
canonical Task 实现/证据阶段。直接调用本 skill 或 legacy profile 下的 `/sdlc build` 必须读取并执行历史 runbook：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage build

这保留 legacy 的 TDD、调试、TASK.md、integration_sha 和
[control-plane.md](../sdlc/references/control-plane.md) 语义。加载失败时报告
legacy-runbook-error；不要改用新 lifecycle 补偿执行。

显式 `/sdlc software-delivery --phase implement --authority dual-lifecycle-v1` 或 façade 已固定 dual profile 才能在
当前 Feature fence 下执行
canonical Task；测试结果必须由 ledger 发起的 argv-only runner receipt 派生，不能由调用方填写 pass/fail。
`/sdlc preview delivery --phase phase.delivery.implement …` 仍只产生 .sdlc/preview/<run-id>/ 内容。preview runner 的
结果不是 legacy Evidence，也不能建立 Task 完成、验证、评审或发布事实。
