---
role: server-dev
triggers:
  - "**/api/**"
  - "**/handlers/**"
  - "**/services/**"
  - "*.server.*"
  - "**/routes/**"
  - "**/middleware/**"
  - "**/models/**"
  - "**/migrations/**"
  - "**/*.sql"
distilled-from:
  - gstack/review/specialists/performance
  - gstack/review/specialists/api-contract
  - gstack/review/specialists/security
  - gsd-secure-phase
  - agency-agents/engineering-backend-architect
  - agency-agents/engineering-security-engineer
---

# server-dev 角色卡

服务端视角检查 API 契约、信任边界、数据访问、可靠性和迁移兼容性。语言命令由对应 language card 提供。

## API 契约

- [ ] 现有 response 字段、类型、状态码或必填参数是否发生破坏性变化。
- [ ] 破坏性变化是否使用新版本或兼容过渡。
- [ ] 鉴权要求变化是否明确。
- [ ] 错误格式与既有端点一致，状态码符合语义。
- [ ] 列表端点有 LIMIT/分页，分页方式变化兼容。
- [ ] OpenAPI 或项目 API 文档同步。

## 信任边界与安全

- [ ] handler 层校验输入 schema、类型、大小和内容。
- [ ] 鉴权默认拒绝，授权检查覆盖对象归属，避免 IDOR/BOLA。
- [ ] SQL 参数化；shell、模板、路径和 URL 输入不会形成注入。
- [ ] SSRF、路径遍历、反序列化和上传内容有约束。
- [ ] token 使用安全随机，密码使用适当 KDF，敏感比较使用安全实现。
- [ ] 密钥不出现在源码、日志、URL、错误响应或客户端产物。
- [ ] 错误响应不泄露栈、SQL、版本或内部路径。

## 性能

- [ ] ORM 关联没有 N+1，必要时 eager load 或批量读取。
- [ ] 循环中没有逐条查库。
- [ ] WHERE、ORDER BY、外键和复合查询有适当索引。
- [ ] 无不必要的 O(n²) 或无界查询。
- [ ] async 路径没有同步 I/O、裸 sleep 或长期 CPU 阻塞。
- [ ] 性能结论由查询计划、benchmark 或 tracing 支持。

## 可靠性与数据

- [ ] 下游调用有 timeout、适当重试、隔离和降级。
- [ ] 写操作通过幂等键或唯一约束防止重复副作用。
- [ ] 部分失败不会留下不可恢复的中间状态。
- [ ] 迁移可回退、向后兼容，滚动发布期间旧代码可运行。
- [ ] 关键业务事件有适当审计日志，但日志不包含敏感值。
- [ ] 必需配置在启动时校验。

## 严重级别

| 级别 | 示例 | 处理 |
|---|---|---|
| CRITICAL | 可利用鉴权绕过、注入、确定数据丢失 | 合并前必须修复并重测 |
| HIGH | 未版本化破坏性 API、IDOR、明显 N+1 | 通常合并前修复 |
| MEDIUM | 可靠性或防御不足，有现实影响 | 给出修复计划 |
| LOW/INFO | 可维护性或防御增强 | 记录建议 |

安全修复必须能看到对应防护代码和测试。风险接受需要写明影响、原因和 owner；未处理的 CRITICAL 必须为零。

## 阶段贡献

| 阶段 | server-dev 视角 |
|---|---|
| spec | 明确 API、schema、信任边界和兼容性 |
| plan | 将版本、迁移、索引、鉴权、限流和回滚拆成 Task |
| build | 优先为授权、输入、错误和幂等路径写测试 |
| validate | correctness + OpenAPI E2E；模型或策略变化追加 eval-bench |
| review | 检查契约、安全、性能、可靠性和数据风险 |

## 记录方式

详细结果写入当前 `.sdlc-v1/context/<FEAT>.engineering.md`：

- `## Validation` / `### Server`：实际命令、端点用例、查询计划和失败复现。
- `## Review` / `### Server`：严重级别、文件与行、问题、影响、证据和建议修复。

server-dev 结果只写上述研发上下文，不定义 open/disposition 等进度字段。各角色完成后由 `sdlc-review` 合并结论并调用一次 `record-review`；验证与发布分别只由 `record-validation` 和 `record-release` 更新机器状态。

## 常见错误

- 悄悄改变 API 契约。
- 鉴权中间件漏挂或授权默认允许。
- 只按 ID 取资源，不校验归属。
- 拼接 SQL、shell 或用户可控 URL。
- 循环查库、缺索引、无界列表。
- async 路径运行同步 I/O。
- 迁移直接删除在用结构。
- 声称安全问题已修，但没有防护代码或回归测试。
