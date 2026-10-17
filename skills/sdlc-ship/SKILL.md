---
name: sdlc-ship
description: >
  发布阶段。读取已评审 Feature、项目部署配置和对应 commit，执行部署前检查、发布、smoke、
  观测与必要回滚；成功后记录 released 状态。
---

# sdlc-ship — 发布已验证 Feature

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。ship Agent 准备发布和 smoke 证据，
但外部副作用及 `record-release`/`retract-release` 均由取得用户授权的主 Agent 执行；未授权时返回阻塞原因。

## 入口条件

- Feature 状态为 `reviewed`。
- validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外无差异。
- 当前业务代码工作树干净；仅 `.sdlc-v1/**` 可以有待提交的发布记录。
- `.sdlc-v1/project.md` 已记录发布目标或用户明确给出目标；目标可以是明确
  约定的源码分发，也可以是环境部署。
- 生产发布、外部消息、数据删除等不可逆动作仍需获得用户明确授权。
- 对用户可见改动，读取 [`Global usage-document, story, and parameter contract`](../sdlc/references/lifecycles/software-delivery.md#11-global-usage-document-story-and-parameter-contract)，以所选目标版本的真实可用条件为准；本地 synthetic 结果不能替代部署、live 或真人试用要求。

## 流程

1. 读取 [`deployment-patterns.md`](../sdlc/references/deployment-patterns.md)。
2. 根据目标选择 `deploy-targets/static-site.md`、`container.md` 或 `vps.md`。
3. 确认构建产物、配置、密钥来源、数据变更和可执行回滚方案；产物版本使用 validation commit，不使用后续只含 SDLC 文件的 HEAD。
4. 记录当前 last-good commit 或产物版本到研发上下文。
5. 完成声明的发布目标；环境部署按项目实际环境执行，源码分发则完成约定的
   仓库、版本或制品交接。每一步使用可复现命令。
6. 运行 health、smoke 和关键业务探测，观察约定指标。
7. 在研发上下文补齐技术发布后观察记录：引用产品上下文的结果观察计划，记录技术发布准备、信号位置、实际观测结果、反馈证据和缺口。
   没有生产观测能力时记录技术原因、下次技术检查时间和缺口；不要在工程上下文重复产品指标、基线、目标、观察窗口、负责人或
   Requirement 回流计划。
8. 失败时停止继续扩大范围，执行回滚并将结果写入研发上下文。
9. 成功后由主 Agent 调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  record-release --feature-id <feature-id>
```

如果历史记录把“合入主分支”或“发布准备完成”误写成 `released`，先在
Feature 工程上下文记录事实和原因，再由主 Agent 调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  retract-release --feature-id <feature-id> --reason <why-the-release-record-was-invalid>
```

该命令是纠错操作，不是失败发布的正常回滚路径；真实发布失败保持
`reviewed`，不调用 `record-release`。

## 完成输出

返回实现版本（validation commit）、环境、产物版本、smoke 结果、技术观测结果、产品观察计划引用、证据缺口和回滚状态。`record-release`
记录 validation commit 作为发布实现版本，且只记录成功发布；失败或只完成发布准备时保持原状态。
