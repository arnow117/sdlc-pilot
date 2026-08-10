---
title: 部署方法论
scope: methodology
applies-to: sdlc-ship
distilled-from: [deployment-patterns, land-and-deploy, gsd-ship, "session:secret-no-transmit-ingest-2026-06-15"]
updated: 2026-08-10
---

# 部署方法论

本文提供跨平台的环境推进、发布策略、迁移、回滚、smoke、观测和密钥方法。目标平台命令由 `deploy-targets/` 适配器提供，项目值从 `.sdlc-v1/project.md`、部署配置和代码读取。

部署细节、实际命令和结果写入当前 Feature 的研发上下文。机器状态只在成功发布后由 `record-release` 更新；失败或只完成准备时保持原状态。

## 1. 环境推进

默认顺序为 dev → staging → canary → full。每段都执行：

~~~text
deploy → smoke/health → 检查必要条件 → 继续或回滚
~~~

| 环境 | 目的 | 继续所需条件 |
|---|---|---|
| dev | 证明产物可构建、可启动 | 构建可复现；关键 smoke 通过；health 正常 |
| staging | 检查类生产配置、集成和迁移 | 集成/E2E 通过；配置正确；迁移与回滚已演练 |
| canary | 用少量真实流量观察新版本 | smoke/health 正常；错误率、延迟、饱和度不劣于基线；无新告警 |
| full | 全量发布 | canary 条件满足；用户或发布策略批准；全量后 smoke 与观察通过 |

任一必要条件不满足，停止扩大范围并回滚到该环境的 last-good。不要在线上边调试边继续发布。

每段在研发上下文记录：

- 环境、commit、产物版本和访问地址。
- last-good commit 或产物版本。
- 实际部署与检查命令。
- smoke/health 和观测结果。
- 回滚是否执行及结果。

## 2. 发布策略

| 策略 | 适用情况 | 回滚 |
|---|---|---|
| rolling | 标准、向后兼容改动 | 反向滚动到 last-good |
| blue-green | 关键服务，需要原子切流 | 流量切回旧环境 |
| canary | 高流量或高风险改动 | 撤掉 canary 流量 |
| feature flag | 希望部署与用户可见性解耦 | 关闭开关 |

- rolling 要求新旧版本短暂共存时仍兼容。
- blue-green 需要额外资源，但切换与回退更快。
- canary 需要流量切分、稳定观测窗口和基线。
- feature flag 必须有 owner、默认值、清理日期和故障时关闭方式。

## 3. 数据库迁移

使用 expand-contract：

1. **Expand**：新增列、表或兼容结构，不删除旧结构。
2. 部署能同时处理新旧结构的应用，可使用双写或读回退。
3. 分批回填历史数据并对账。
4. 观察新旧一致性和应用稳定性。
5. **Contract**：确认无代码依赖旧结构后，在后续独立发布中删除。

迁移检查：

- [ ] 本次迁移向后兼容，滚动或 canary 期间旧版本仍可运行。
- [ ] 有可执行 rollback/down，或明确证明纯加法可回退。
- [ ] forward 与 rollback 已在接近生产规模的数据上演练。
- [ ] 回填分批、可暂停、可恢复，并有对账。
- [ ] 删除、重命名、类型收窄和 NOT NULL 收紧不与 expand 同批。

## 4. 回滚

每个环境保留一个可用的 last-good：

- 镜像使用不可变 tag；静态部署保留可寻址 deployment；VPS 保留前一 release。
- 发布前先记录 last-good。
- smoke、health 或观测失败后使用平台原生回滚操作。
- staging 中提前演练回滚。
- 回滚应用前确认 schema 仍兼容旧版本。

常见原语：

~~~bash
kubectl rollout undo deployment/<deployment-name> -n <namespace>
kubectl rollout status deployment/<deployment-name> -n <namespace>
~~~

平台专属命令由对应适配器提供。回滚结果写入 Feature 研发上下文，不新增失败状态文件。

## 5. Smoke 与 health

| 检查 | 说明 |
|---|---|
| health | 进程、依赖和就绪状态 |
| smoke | 用户最关键的只读或幂等路径 |

建议应用提供：

- 浅层 `/health`：进程存活返回 200。
- 深层 `/health/detailed`：返回关键依赖、版本和 uptime；关键依赖异常时返回 503。

探测示例：

~~~bash
curl -fsS "https://<host>/<health-path>"
~~~

`curl -f` 在非 2xx 时返回非零 exit code。线上 smoke 优先只读或幂等操作；写入或删除用例仅在隔离环境运行。

## 6. Canary 观测

至少对比 canary 与同期 last-good 的：

| 信号 | 检查 |
|---|---|
| errors | 5xx、异常和失败请求率 |
| latency | p50、p95、p99 |
| saturation | CPU、内存、队列和连接池 |

放量后保留足够观察时间，再决定是否扩大范围。瞬时无错误不能证明稳定。超过项目阈值时停止并回滚；阈值、时间窗口和实际指标写入研发上下文。

## 7. 配置与密钥

- 每个环境有独立配置和密钥。
- 非敏感配置通过环境变量或平台配置注入。
- 密钥只存在于 secret manager、部署环境或本机获授权凭据存储。
- 不把密钥写入源码、Markdown、命令行明文、日志、URL、截图或对话。
- 启动时校验必需配置，缺失或非法立即失败。
- 从台账或控制台读取时，只取 host、port、namespace、registry 等坐标，不复制密钥块。
- 密钥进入仓库、日志、对话或截图即视为泄露，应立即轮换。

环境坐标可记录在 `.sdlc-v1/project.md`：

~~~text
env → cluster context / namespace / host / registry / domain / secret name
~~~

只记录 Secret 名，不记录 Secret 值。

## 8. 发布前检查

- [ ] 目标环境、provider、账号和部署坐标已解析。
- [ ] 构建、部署和回滚命令来自项目或适配器，没有臆造参数。
- [ ] 产物版本不可变且使用 validation commit；后续只含 `.sdlc-v1/**` 的 HEAD 不作为实现版本。
- [ ] registry 与运行集群的地域、网络和认证可用。
- [ ] 数据迁移满足兼容与回滚要求。
- [ ] last-good 已记录。
- [ ] smoke、health、观测阈值和观察窗口已确定。
- [ ] full 发布和其他不可逆外部行为已获得用户明确授权。

## 9. 状态与证据

- 每段结果追加到 `.sdlc-v1/context/<FEAT>.engineering.md` 的 `## Release`。
- 平台 CLI 产生的日志或链接可以作为证据附件，由研发上下文引用。
- 发布证据只写当前 Feature 研发上下文；失败不生成状态或环境进度文件。
- 所有阶段成功后，`sdlc-ship` 调用一次 `record-release --feature-id <FEAT>`。
- 失败时保持 Feature 机器状态不变，在研发上下文记录失败、回滚和下一动作。
