---
name: sdlc-build
description: >
  兼容适配器：保留 /sdlc build 的精确 0.19.2 legacy TDD/调试流程。
  新软件交付 preview 必须显式调用 sdlc-software-delivery；本 skill 不把 legacy Evidence 或 Task 迁成双生命周期记录。
---

# sdlc-build — legacy compatibility adapter

默认 /sdlc build 必须读取并执行历史 runbook：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage build

这保留 legacy 的 TDD、调试、TASK.md、integration_sha 和
[control-plane.md](../sdlc/references/control-plane.md) 语义。加载失败时报告
legacy-runbook-error；不要改用新 lifecycle 补偿执行。

显式 `/sdlc software-delivery --phase implement --authority dual-lifecycle-v1` 才能在当前 Feature fence 下执行
canonical Task；测试结果必须由 ledger 发起的 argv-only runner receipt 派生，不能由调用方填写 pass/fail。
`/sdlc preview delivery --phase phase.delivery.implement …` 仍只产生 .sdlc/preview/<run-id>/ 内容。preview runner 的
结果不是 legacy Evidence，也不能建立 Task 完成、验证、评审或发布事实。
