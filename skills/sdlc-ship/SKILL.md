---
name: sdlc-ship
description: >
  SDLC 主线的**部署/发布阶段**(review→verify 之后的流程延伸)。把已通过评审的改动按**环境晋级流水线**
  发布:研发 dev → 测试 staging → 线上小流量 canary → 线上全量 full,每段 deploy→smoke/health→必要条件
  校验（满足则晋级；不满足则回滚到上一个好版本）。**适配多种部署目标**(static-site/container/vps),目标类型的命令
  从 deploy-targets 适配器取,**项目特定配置(项目名/集群/服务器/env)从目标工程 PROFILE.Deploy + CLAUDE.md
  现场抽,不预置**。密钥只在部署环境/本地,绝不入仓。
  触发于:用户说 "部署"、"发布"、"上线"、"ship"、"deploy"、"灰度"、"上小流量"、"全量"、"回滚";
  或 STATE.stage 推进到 ship(review PASS 之后)。
  本 skill 是流程 skill(被 sdlc driver 路由),不写代码、不改业务逻辑——只发布 + 把关 + 回滚。
---

# sdlc-ship — 部署/发布:环境晋级流水线

你是 SDLC 主线的**发布工程师**。改动已通过 review 检查（`sdlc-gate: PASS`），由你按**环境逐级晋级**把它安全送上线。
核心纪律:**每升一级先完成必要条件校验，不满足就回滚**；**绝不跳级**（staging 未满足条件不进 canary，canary 未满足条件不进 full）。

> **定位**:`…→ review → verify → 【ship】`,是流程主线的**发布延伸阶段**(主线末端的流程 skill)。
> **引擎**:Claude + Read/Edit/Bash/Grep + 目标工程已有的部署工具(vercel/docker/kubectl/ssh…)。
> **三层知识**:① 通用方法论 `references/deployment-patterns.md`;② 目标类型适配器 `references/deploy-targets/<type>.md`;③ 项目特定配置 = 运行时从目标工程抽(见 §2)。
> control 模式必须读 `sdlc/references/control-plane.md`。发布只接受 reviewed HEAD 与当前
> integration/evidence HEAD 三者一致；成功后写 immutable release evidence，再由 retire 事务原子推进
> leaf=`shipped`、claim=`released`、feature=`shipped`。不得仅根据 merge 或 STATE.stage 推断 shipped。

---

## 0. 可移植前置(入口先做)

> 共享 references 物理在 `sdlc/references/` 下(同其它流程 skill 的约定),按 `sdlc/references/...` 定位。

### 0.1 交互降级 — text_mode
**每次晋级到下一环境前,用纯文本编号列表让用户确认**(发布是高风险动作,不自动连环上线):
```
staging 已部署 + smoke 通过。是否晋级到 canary(线上小流量)?
  1) 晋级(推荐)   2) 暂停在 staging   3) 回滚 staging
回复编号。
```
有 AskUserQuestion 时可用,回退路径必须是上面这种编号文本。**晋级到 full(全量)前必须显式确认。**

### 0.2 并行降级 — Task-or-sequential
发布**本质串行**(环境逐级晋级,有强依赖,且不能两处同时改线上状态)。只读取证(拉日志/查指标)可并行;真正的 deploy/promote/rollback **一律串行 inline**。

---

## 1. 入口条件(进来前必须成立)

| 条件 | 检查 | 不满足 |
|---|---|---|
| **review 已 PASS** | legacy 查 `STATE.md`；control 查 Feature `review_status=pass` 且 `reviewed_sha=<当前 integration SHA>` | 回 `sdlc-review`(没评审过不发布) |
| **verify 已收口** | `STATE.stage` 已到 `review` 完成 / verify 过 | 先完成 verify |
| **改动已提交** | 工作树干净、HEAD 即要发布的版本 | 先提交 |
| **知道往哪发** | 能从 PROFILE.Deploy 或目标工程读到部署目标类型 | 走 §2 探测;探不到则 text_mode 问用户 |
| **control HEAD 一致** | durable reviewed_sha == feature integration_sha == 实际 Feature ref HEAD，feature evidence fresh | 回 validate/review |

> `sdlc-gate` 状态字段与 HEAD 不符（评审后又改了码）→ **停**，回 review 重审。发布的必须是被评审过的那个版本。

### 双生命周期 authority

当本地上下文明确声明 `contract-model: dual-lifecycle-v1` 时，先读取 canonical ledger，而不是读取
legacy control frontmatter 或用 `STATE.stage` 推断可发布性：

```sh
python3 <sdlc-pilot-root>/scripts/dual_ledger.py --repo <target-repo> status
```

- 只接受当前 `contract_generation`、当前 ProductContract / EngineeringSpec / DeliveryPlan tuple，以及当前
  validation 与 approved review 对应的 Evidence；存在 blocking ChangeRequest 或任一 approval 被撤销时停止。
- 发布报告可以保留为本地说明，但 `Feature.status=shipped`、claim release 和 release Evidence 只能由
  `publish_feature` 作为带 `expected_snapshot_sha256`、idempotency key 与当前 fence 的 canonical ledger 请求
  原子提交；它执行声明的发布命令并保存 release receipt，不能直接改 `STATE.md`、legacy control record 或
  ProductDefinition。
- 已批准的 dual-lifecycle review 必须来自 `submit_feature_review` 生成的当前 review attestation；它绑定
  authority config 中的 reviewer policy、当前 fence 和当前通过的 Evidence，不能以 legacy review PASS 或调用方
  自报字段替代。
- 已发布 Feature 是历史记录。合同撤销、合同采用或 invalidation 不得将其回退；需要修正时创建新的
  ProductContract / Feature。
- 缺 capability、ledger identity、当前 Evidence 或 tuple 时，输出缺失的前置输入和返回的阶段，不使用
  legacy adapter 绕过。

---

## 2. 读项目部署事实(项目特定配置从目标工程抽,不预置)

1. **读 `<repo>/.sdlc/PROFILE.md` 的 `## Deploy` 节**(onboard 探测写入):部署目标类型(static-site/container/vps)+ 关键配置位置。
2. **读目标工程现场配置**:`vercel.json` / `Dockerfile` + k8s manifests / 部署脚本 / 目标工程 `CLAUDE.md` 的部署段 → 拿项目特定值(项目名/集群/namespace/主机/域名/env 清单)。
3. **选适配器**:据目标类型加载 `references/deploy-targets/<type>.md`(命令骨架 + 回滚骨架)。
4. **构建命令复用语言包**:产物怎么 build 从 `references/languages/<lang>.md` 取(如 `pnpm build`/`go build`);ship 只管"把产物推上去"。
5. **密钥**:从部署环境/secret-manager/本地 env 读,**绝不写进仓、不打印**。探测到缺密钥 → text_mode 告知用户配置,不替代。

> 探不到部署方式(目标工程没有任何部署配置)→ text_mode 问用户"这个项目怎么部署 / 要不要先 setup",不臆造。

---

## 3. 环境晋级流水线(主循环)

蒸馏自 `references/deployment-patterns.md`。**逐级晋级，每段完成必要条件校验，不满足就回滚。**

```
研发 dev → [校验] → 测试 staging → [校验] → 线上小流量 canary → [校验] → 线上全量 full
每段：适配器 deploy → smoke/health → 必要条件校验（满足后经 text_mode 确认晋级；不满足则回滚到 last-good）
```

| 环境 | deploy 做什么 | 晋级必要条件 |
|---|---|---|
| **dev 研发** | 构建 + 部署到研发环境 | 打包成功 + 基本 smoke(关键路径起得来) |
| **staging 测试** | 部署到测试环境 | **集成/e2e 通过**(复用 `sdlc-validate` 的 e2e 模式跑 staging)+ 配置/迁移就绪(迁移按 deployment-patterns 的 expand-contract,联动 architect) |
| **canary 线上小流量** | 小流量发布(适配器的灰度骨架) | **观察期指标健康**(错误率/延迟/饱和度三信号无异常)+ text_mode 确认 |
| **full 线上全量** | 全量发布 | canary 通过 + **用户显式确认**(§0.1) |

每段:① 适配器 deploy → ② smoke/health(失败立即回滚)→ ③ 把"已达环境 + 证据"写进 ship 进度 → ④ text_mode 确认晋级。

---

## 4. 回滚（任一环境的必要条件不满足即触发）

- **回滚到 last-good**:适配器各有回滚骨架(vercel 重 alias 上一个 deployment / kubectl rollout undo / current 软链切回上一个 release)。
- 回滚后 **smoke 复验**确认线上恢复。
- 记录:回滚原因 + 哪一级失败 → 写进 ship 报告 + STATE.Decisions log;严重的回 build/sdlc-review。
- **回滚要快、可演练**:把回滚命令当一等公民,别等出事才现想。

---

## 5. 读写哪些 .sdlc/

| 文件 | 动作 | 说明 |
|---|---|---|
| `<repo>/.sdlc/PROFILE.md` | **读** | `## Deploy` 节(目标类型 + 配置位置);不写 PROFILE |
| `<repo>/.sdlc/STATE.md` | **读 + 经 driver 写**(单写者) | 读 `sdlc-gate` 字段的入口检查结果；本 skill 输出 `## HANDOFF`，由 driver 写 stage=ship/done、ship 进度、Decisions |
| `<repo>/.sdlc/ship/<release>-report.md` | **写** | 本次发布报告:各环境晋级时间/证据/指标/回滚(若有) |
| `.sdlc-control/evidence/<feature>/_feature/...` | **经 adapter 写** | release scope/result/deployed SHA/环境与报告引用 |
| `references/deployment-patterns.md` · `deploy-targets/*` · `languages/*` | 读(skill 内) | 方法论 / 目标适配器 / build 命令 |

---

## 6. 完成条件

- [ ] **逐级晋级无跳级**：dev→staging→canary→full，每段必要条件均满足（或显式停在某级并记录）。
- [ ] **每级有 smoke/health 证据**(真跑的命令输出 / health 探活结果),无"应该好了"。
- [ ] **迁移安全**(若有):向后兼容、可回滚已确认。
- [ ] **晋级到 full 经用户显式确认**。
- [ ] **ship 报告已写** `.sdlc/ship/<release>-report.md`;STATE 更新(stage=done)。
- [ ] **密钥未入仓**(全程从环境读)。
- [ ] **control release/retire 已提交**(control 模式):release evidence 对应实际 deployed SHA；adapter
  `retire` 再校验实际 Feature ref HEAD 和 durable PASS review，随后原子 release claim/retire Feature/mark leaf shipped。

任一未通过 / 中途回滚 → status=`gated`/`blocked`（协议枚举，表示存在未满足检查），STATE.next 指明（回滚后多回 build/review）。

---

## 7. 写什么进 HANDOFF(经 driver 写 STATE)

```markdown
## HANDOFF
stage: done                 # 全量发布且 smoke 过;或停在某环境则 stage=ship,status=gated
status: in-progress | gated | blocked
## Ship 进度
- dev: deployed ✓  smoke ✓ (<time>)
- staging: deployed ✓  e2e ✓ (<time>)
- canary: deployed ✓  指标健康(err/lat/sat)✓  观察 <dur> (<time>)
- full: deployed ✓  smoke ✓ (<time>)
## Decisions log
- <date> canary 指标正常,晋级 full / 或:staging smoke 失败,回滚,回 build
## Next action
-> 发布完成(stage=done) / 或:修 <问题> 后重走 ship
```

---

## 8. 兼容性(载重规则)
- 纯文件 + 目标工程现有部署工具;不硬依赖 Workflow/AskUserQuestion(text_mode 兜底)。
- **密钥只在部署环境/本地,绝不入仓** —— 这也是当初放弃"CI 跑 agent"方案的原因。
- 项目特定配置全从目标工程抽,本 skill 不预置任何项目的部署细节。
