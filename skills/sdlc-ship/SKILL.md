---
name: sdlc-ship
description: >
  SDLC 主线的**部署/发布阶段**(review→verify 之后的流程延伸)。把已通过评审的改动按**环境晋级流水线**
  发布:研发 dev → 测试 staging → 线上小流量 canary → 线上全量 full,每段 deploy→smoke/health→门
  (过=晋级 / 不过=回滚到上一个好版本)。**适配多种部署目标**(static-site/container/vps),目标类型的命令
  从 deploy-targets 适配器取,**项目特定配置(项目名/集群/服务器/env)从目标工程 PROFILE.Deploy + CLAUDE.md
  现场抽,不预置**。密钥只在部署环境/本地,绝不入仓。
  触发于:用户说 "部署"、"发布"、"上线"、"ship"、"deploy"、"灰度"、"上小流量"、"全量"、"回滚";
  或 STATE.stage 推进到 ship(review PASS 之后)。
  本 skill 是流程 skill(被 sdlc driver 路由),不写代码、不改业务逻辑——只发布 + 把关 + 回滚。
---

# sdlc-ship — 部署/发布:环境晋级流水线

你是 SDLC 主线的**发布工程师**。改动已过 review(`sdlc-gate: PASS`),由你按**环境逐级晋级**把它安全送上线。
核心纪律:**每升一级先过门,过不了就回滚**;**绝不跳级**(没过 staging 不上 canary,没过 canary 不上 full)。

> **定位**:`…→ review → verify → 【ship】`,是流程主线的**发布延伸阶段**(主线末端的流程 skill)。
> **引擎**:Claude + Read/Edit/Bash/Grep + 目标工程已有的部署工具(vercel/docker/kubectl/ssh…)。
> **三层知识**:① 通用方法论 `references/deployment-patterns.md`;② 目标类型适配器 `references/deploy-targets/<type>.md`;③ 项目特定配置 = 运行时从目标工程抽(见 §2)。

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
| **review 已 PASS** | `STATE.md` 有 `sdlc-gate: PASS reviewed-head=<当前 HEAD>` | 回 `sdlc-review`(没评审过不发布) |
| **verify 已收口** | `STATE.stage` 已到 `review` 完成 / verify 过 | 先完成 verify |
| **改动已提交** | 工作树干净、HEAD 即要发布的版本 | 先提交 |
| **知道往哪发** | 能从 PROFILE.Deploy 或目标工程读到部署目标类型 | 走 §2 探测;探不到则 text_mode 问用户 |

> `sdlc-gate` 与 HEAD 不符(评审后又改了码)→ **停**,回 review 重审。发布的必须是被评审过的那个版本。

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

蒸馏自 `references/deployment-patterns.md`。**逐级晋级,每段一个门,过不了就回滚。**

```
研发 dev → [门] → 测试 staging → [门] → 线上小流量 canary → [门] → 线上全量 full
每段:  适配器 deploy → smoke/health → 门(过=text_mode 确认后晋级 / 不过=回滚到 last-good)
```

| 环境 | deploy 做什么 | 门(过了才晋级) |
|---|---|---|
| **dev 研发** | 构建 + 部署到研发环境 | 打包成功 + 基本 smoke(关键路径起得来) |
| **staging 测试** | 部署到测试环境 | **集成/e2e 通过**(复用 `sdlc-validate` 的 e2e 模式跑 staging)+ 配置/迁移就绪(迁移按 deployment-patterns 的 expand-contract,联动 architect) |
| **canary 线上小流量** | 小流量发布(适配器的灰度骨架) | **观察期指标健康**(错误率/延迟/饱和度三信号无异常)+ text_mode 确认 |
| **full 线上全量** | 全量发布 | canary 通过 + **用户显式确认**(§0.1) |

每段:① 适配器 deploy → ② smoke/health(失败立即回滚)→ ③ 把"已达环境 + 证据"写进 ship 进度 → ④ text_mode 确认晋级。

---

## 4. 回滚(任何环境门失败即触发)

- **回滚到 last-good**:适配器各有回滚骨架(vercel 重 alias 上一个 deployment / kubectl rollout undo / current 软链切回上一个 release)。
- 回滚后 **smoke 复验**确认线上恢复。
- 记录:回滚原因 + 哪一级失败 → 写进 ship 报告 + STATE.Decisions log;严重的回 build/sdlc-review。
- **回滚要快、可演练**:把回滚命令当一等公民,别等出事才现想。

---

## 5. 读写哪些 .sdlc/

| 文件 | 动作 | 说明 |
|---|---|---|
| `<repo>/.sdlc/PROFILE.md` | **读** | `## Deploy` 节(目标类型 + 配置位置);不写 PROFILE |
| `<repo>/.sdlc/STATE.md` | **读 + 写**(经 driver,单写者) | 读 `sdlc-gate` 入口门;写 stage=ship/done、ship 进度、Decisions |
| `<repo>/.sdlc/ship/<release>-report.md` | **写** | 本次发布报告:各环境晋级时间/证据/指标/回滚(若有) |
| `references/deployment-patterns.md` · `deploy-targets/*` · `languages/*` | 读(skill 内) | 方法论 / 目标适配器 / build 命令 |

---

## 6. 出口门(本阶段算完成)

- [ ] **逐级晋级无跳级**:dev→staging→canary→full,每段门都过(或显式停在某级并记录)。
- [ ] **每级有 smoke/health 证据**(真跑的命令输出 / health 探活结果),无"应该好了"。
- [ ] **迁移安全**(若有):向后兼容、可回滚已确认。
- [ ] **晋级到 full 经用户显式确认**。
- [ ] **ship 报告已写** `.sdlc/ship/<release>-report.md`;STATE 更新(stage=done)。
- [ ] **密钥未入仓**(全程从环境读)。

任一未过 / 中途回滚 → status=`gated`/`blocked`,STATE.next 指明(回滚后多回 build/review)。

---

## 7. 写什么进 STATE(经 driver,单写者)

```markdown
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
