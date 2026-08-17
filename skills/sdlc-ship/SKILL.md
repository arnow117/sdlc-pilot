---
name: sdlc-ship
description: >
  发布阶段。读取已评审 Feature、项目部署配置和对应 commit，执行部署前检查、发布、smoke、
  观测与必要回滚；成功后记录 released 状态。
---

# sdlc-ship — 发布已验证 Feature

## 入口条件

- Feature 状态为 `reviewed`。
- validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外无差异。
- 当前业务代码工作树干净；仅 `.sdlc-v1/**` 可以有待提交的发布记录。
- `.sdlc-v1/project.md` 已记录部署目标或用户明确给出目标。
- 生产发布、外部消息、数据删除等不可逆动作仍需获得用户明确授权。

## 流程

1. 读取 [`deployment-patterns.md`](../sdlc/references/deployment-patterns.md)。
2. 根据目标选择 `deploy-targets/static-site.md`、`container.md` 或 `vps.md`。
3. 确认构建产物、配置、密钥来源、数据变更和可执行回滚方案；产物版本使用 validation commit，不使用后续只含 SDLC 文件的 HEAD。
4. 记录当前 last-good commit 或产物版本到研发上下文。
5. 按项目实际环境执行发布；每一步使用可复现命令。
6. 运行 health、smoke 和关键业务探测，观察约定指标。
7. 在研发上下文补齐发布后观察记录：方向来源、指标或不可观测原因、基线与目标、观察窗口、负责人、信号位置，以及新信息应更新当前 Requirement 还是创建新 Requirement。没有生产观测能力时也要记录原因、负责人和下次检查时间。
8. 失败时停止继续扩大范围，执行回滚并将结果写入研发上下文。
9. 成功后调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  record-release --feature-id <feature-id>
```

## 完成输出

返回实现版本（validation commit）、环境、产物版本、smoke 结果、观测结果、后续观察负责人/时间和回滚状态。`record-release` 记录 validation commit 作为发布实现版本，且只记录成功发布；失败或只完成发布准备时保持原状态。
