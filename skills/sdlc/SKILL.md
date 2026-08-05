---
name: sdlc
description: >
  SDLC 总入口与兼容路由器。普通 /sdlc、intake、deliver、next 和旧 stage 命令保持 0.19.2 legacy 行为；
  只有显式 preview/product-design/software-delivery/compatibility 命令才进入双生命周期的 preview 路径。
  它不执行产品设计、工程实现、验证或发布。
---

# sdlc — façade / router

这个 skill 只有两条互斥路由。先解析用户命令；不要从文件、代码路径或旧 STATE.md 猜测应切换到新生命周期。

| 调用 | 路由 | 权威状态 |
| --- | --- | --- |
| /sdlc、/sdlc intake、/sdlc deliver、/sdlc next，以及没有 preview 的旧命令 | 精确加载 legacy 0.19.2 driver | legacy 的 control / STATE 语义 |
| /sdlc preview product … 或 /sdlc product-design … | sdlc-product-design | .sdlc/preview/<run-id>/ |
| /sdlc preview delivery … 或 /sdlc software-delivery … | sdlc-software-delivery | .sdlc/preview/<run-id>/ |
| /sdlc preview compatibility --operation legacy-composite-v1 … | legacy-composite-v1 renderer + sdlc-software-delivery compatibility protocol | .sdlc/preview/<run-id>/plan.shadow.md |
| /sdlc product-design --authority dual-lifecycle-v1 … | sdlc-product-design canonical contract flow | .sdlc-control/dual-lifecycle/ledger.json |
| /sdlc software-delivery --authority dual-lifecycle-v1 … | sdlc-software-delivery canonical delivery flow | .sdlc-control/dual-lifecycle/ledger.json |
| /sdlc onboard、/sdlc backlog、/sdlc ship | 对应正交 skill | 各自既有协议 |

## 普通 legacy 调用

普通调用必须先读取精确、已校验的历史 runbook；它不能因为新模块存在而自动进入 preview：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage driver

legacy_runbook.py 固定到 0.19.2 Git blob，并验证 SHA-256。历史对象缺失时明确报告
legacy-runbook-error 并停止；不要以新生命周期代替旧行为。该历史 driver 仍以
[control-plane.md](references/control-plane.md) 为普通 control 调用的权威协议。

## 显式 preview 调用

preview 必须带 lifecycle_run_id、固定 policy_manifest_ref、phase_contract_ref、operation 和
输入 artifact identity。调用前用 policy_compiler.py 生成并固定 PolicyManifest；用
context_resolver.py 得到 Context Manifest；用 obligation_engine.py 记录 selected/completed/
explicitly-skipped obligation。缺字段或 selector 未知时返回 needs_classification。

- preview 只写 .sdlc/preview/<run-id>/，禁止改 .sdlc-control/、STATE.md、legacy spec.md 或 plan.md。
- preview Context、Evidence、attestation、shadow plan 都不能作为 control、validate、review 或 ship 的输入。
- legacy-composite-v1 只消费 approved legacy spec bytes 与 legacy_approval_observation，只生成
  LegacyPlan shadow；它不产生 ProductContract、EngineeringSpec、Approval、Task 或 DeliveryPlan。
- 产品侧与工程侧的 canonical artifact/reducer 代码只由显式 authority 调用；普通 `/sdlc` 不会因为
  ledger 存在而切换语义。

## 显式 canonical 调用

`--authority dual-lifecycle-v1` 表示本次请求使用已实现的 canonical ledger。先读取
[`dual-lifecycle-runtime.md`](references/dual-lifecycle-runtime.md)，确认 capability、当前 snapshot SHA、
Policy/Context/Obligation refs 与输入 artifact identity；再由对应 lifecycle 生成一个 structured intent。

façade 不拼装或解释 intent，也不直接写 STATE/control。它只把 intent 交给 `dual_ledger.py`；CAS 冲突、
缺 approval、旧 fence、blocking ChangeRequest 或不完整 Evidence 必须返回明确的缺失前置输入。产品与工程
路径可以直接调用各自 lifecycle，不必先经过 façade。

具体方法正文只在被路由到的 lifecycle skill 中加载；本 façade 不复制 BDD、DDD、SDD、TDD 或旧 stage 流程。
