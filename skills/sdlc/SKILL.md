---
name: sdlc
description: >
  SDLC 总入口与兼容路由器。新项目的普通 /sdlc 默认进入产品设计/软件交付双生命周期；
  已有项目由 .sdlc/lifecycle.json 明确选择 legacy 或 dual，缺少选择时必须先迁移。
  preview/product-design/software-delivery 仍可显式调用。
  它不执行产品设计、工程实现、验证或发布。
---

# sdlc — façade / router

先解析用户命令。普通入口先读取目标仓库的 lifecycle profile；不要从文件、代码路径、旧 `STATE.md` 或 ledger
猜测应切换到新生命周期。profile 是唯一持久化选择来源。

| 调用 / profile | 路由 | 权威状态 |
| --- | --- | --- |
| 普通调用 + `new-project-default` | 先固定 dual profile，再进入 canonical 产品/交付路由 | `.sdlc/lifecycle.json` + dual ledger |
| 普通调用 + `dual-lifecycle-v1` | canonical `sdlc-product-design` / `sdlc-software-delivery` | `.sdlc/lifecycle.json` + dual ledger |
| 普通调用 + `legacy-0.19.2` | 精确加载 legacy 0.19.2 driver | legacy 的 control / STATE 语义 |
| 普通调用 + `migration-required` | 停止并报告需要选择；不得加载任一 lifecycle | 无写入 |
| /sdlc preview product … 或 /sdlc product-design … | sdlc-product-design | .sdlc/preview/<run-id>/ |
| /sdlc preview delivery … 或 /sdlc software-delivery … | sdlc-software-delivery | .sdlc/preview/<run-id>/ |
| /sdlc preview compatibility --operation legacy-composite-v1 … | legacy-composite-v1 renderer + sdlc-software-delivery compatibility protocol | .sdlc/preview/<run-id>/plan.shadow.md |
| /sdlc product-design --authority dual-lifecycle-v1 … | sdlc-product-design canonical contract flow | .sdlc-control/dual-lifecycle/ledger.json |
| /sdlc software-delivery --authority dual-lifecycle-v1 … | sdlc-software-delivery canonical delivery flow | .sdlc-control/dual-lifecycle/ledger.json |
| /sdlc onboard、/sdlc backlog、/sdlc ship | 对应正交 skill；dual profile 下 ship 读取 canonical ledger | 各自既有协议 |

## 普通入口与 profile

先读取 [`lifecycle-profile.md`](references/lifecycle-profile.md)，再以目标仓库为 `--repo` 调用
`lifecycle_profile.py status`。此读取不改任何文件。

- 返回 `new-project-default` 时，调用 `init` 固定 `.sdlc/lifecycle.json`，再按 dual 路由；在 profile 写入成功前不得创建 canonical intent。
- 返回 `configured / dual-lifecycle-v1` 时，普通 `/sdlc`、`/sdlc intake`、`/sdlc deliver`、`/sdlc next` 及旧 `spec → plan → build → validate → review` 入口改为对应 canonical 生命周期：产品问题先进入 product-design，已有获批 ProductContract 的工程动作进入 software-delivery。`next` 只读取 dual projection/ledger 后恢复，不读取 legacy STATE 推断。
- 返回 `configured / legacy-0.19.2` 时，普通调用严格执行本节 legacy runbook。
- 返回 `migration-required` 时，报告检测到的 artifact 类型并要求用户显式选择 `/sdlc migrate --mode legacy-0.19.2` 或 `/sdlc migrate --mode dual-lifecycle-v1`。后者在已有 artifact 时必须获得用户确认后带 `--allow-existing-artifacts` 执行；迁移仅写 profile，不转换任何状态或证据。

profile-derived dual 是 façade 的 canonical authority：它只能来自已固定的 profile，不能由存在 ledger、preview 或
legacy 文件替代。直接调用 product-design/software-delivery 仍须带 `--authority dual-lifecycle-v1`。

## 普通 legacy 调用

profile 已选择 `legacy-0.19.2` 的普通调用必须先读取精确、已校验的历史 runbook；它不能因为新模块存在而自动进入 preview：

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
- 产品侧与工程侧的 canonical artifact/reducer 代码只由显式 authority 或已固定的 dual profile 调用；普通
  `/sdlc` 不会因为 ledger 存在而切换语义。

## 显式 canonical 调用

`--authority dual-lifecycle-v1` 或 façade 已固定的 dual profile 表示本次请求使用已实现的 canonical ledger。先读取
[`dual-lifecycle-runtime.md`](references/dual-lifecycle-runtime.md)，确认 capability、当前 snapshot SHA、
Policy/Context/Obligation refs 与输入 artifact identity；再由对应 lifecycle 生成一个 structured intent。

façade 不拼装或解释 intent，也不直接写 STATE/control。它只把 intent 交给 `dual_ledger.py`；CAS 冲突、
缺 approval、旧 fence、blocking ChangeRequest 或不完整 Evidence 必须返回明确的缺失前置输入。产品与工程
路径可以直接调用各自 lifecycle，不必先经过 façade。

具体方法正文只在被路由到的 lifecycle skill 中加载；本 façade 不复制 BDD、DDD、SDD、TDD 或旧 stage 流程。
