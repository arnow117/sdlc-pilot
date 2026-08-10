---
mode: e2e
triggers: ["*.tsx", "*.vue", "*.css", "components/**", "**/api/**", "**/handlers/**", "*.server.*", "**/*.swift", "*.kt", "mobile/**", "ios/**", "android/**", "e2e/**", "*.spec.*"]
distilled-from: [design-review, devex-review, web-api-reverse-engineering, browse, playwright-mcp]
---

# Validate mode: e2e

e2e 从真实用户视角验证受改动影响的旅程。Web、OpenAPI 和 App 可以组合运行；详细证据写入当前 Feature 的研发上下文，不生成独立 SDLC 报告。

## 输入与记录位置

- `.sdlc-v1/project.md` 的 surface map、启动命令和测试入口。
- 当前产品上下文的关键用户旅程与验收条件。
- 当前 `.sdlc-v1/context/<FEAT>.engineering.md` 的设计、测试策略和已知限制。
- 当前 Git diff。

结果追加到研发上下文的 `## Validation` / `### E2E`。测试框架产生的截图、trace、video 或 request/response 文件可以保留在项目原有测试产物目录，并在该小节引用；这些文件是证据附件，不保存进度。

## 选择范围与模态

范围：

| scope | 用途 |
|---|---|
| feature | 只验证本次改动直接影响的旅程，默认 |
| iteration | 验证本次迭代累积影响的旅程 |
| full-chain | 明确要求全链路检查时使用 |

模态：

| 改动 | 模态 |
|---|---|
| Web 页面、组件、样式、路由 | Web |
| API、handler、service | OpenAPI |
| iOS、Android、移动端 | App |

一次改动可触发多个模态。不要扫描与当前 Feature 无关的全站历史。

## 旅程推导

按以下优先级建立“名称 / 入口 / 步骤 / 期望终态”清单：

1. 产品上下文的验收条件和关键用户旅程。
2. 路由表或 OpenAPI paths。
3. Git diff 触达的页面、组件、端点或移动页面。
4. 项目文档中的产品入口。

每条核心旅程至少检查成功、错误和空态；不适用时在研发上下文说明原因。

## Web

使用项目已有 Playwright 套件或浏览器自动化能力：

1. 打开真实入口并记录初始状态。
2. 按用户步骤推进到终态。
3. 断言用户目标达成，不以“页面出现”代替业务结果。
4. 检查 console error 和关键 network request。
5. 使用确定性等待；不要用裸 sleep。
6. 对关键断点、键盘操作和错误反馈做适用检查。

每个结论标记：

- `TESTED`：在被测目标上实际运行并观察。
- `PARTIAL`：运行过，但受数据、凭证或环境限制。
- `INFERRED`：未运行，只能静态推断。

## OpenAPI

1. 优先从 OpenAPI/Swagger 生成请求与断言；没有规范时，从真实 Web 流量和路由实现推导。
2. 验证状态码、响应 schema、关键业务字段、认证和错误格式。
3. 生产或共享环境只执行只读或幂等请求。
4. 创建、更新、删除用例只在隔离测试环境运行；否则标记未运行并给出人工步骤。
5. 保留必要的 request/response 摘要，脱敏后写入研发上下文。

## App

1. 优先使用项目已有移动自动化；没有时探测 Maestro 或平台原生测试。
2. 有工具时运行真实 flow，断言最终用户目标并保存日志或截图。
3. 无工具时标 `INFERRED`，写明未在设备或模拟器验证，并列出人工步骤。
4. 缺少 App 工具不影响其他模态的真实结果，但不能把 App 标成通过。

## 失败处理

e2e 负责定位，不在验证阶段自动修实现：

1. 用 console、network、trace、snapshot 或设备日志定位责任文件。
2. 在研发上下文记录期望、实际、复现步骤和文件位置。
3. 返回 `sdlc-build` 做最小修复。
4. 修复提交后重新运行受影响旅程和必要回归旅程。

视觉问题可保留 before / target / after 证据；功能问题保留失败断言与修复后断言。不要强制“一条问题一次提交”，正常按当前 Feature 的 Git 工作流组织提交。

## 必要条件

e2e 通过需要：

- scope 内所有核心旅程都运行到终态。
- 成功路径断言通过。
- 适用的错误态和空态符合预期。
- 未运行部分明确标为 `PARTIAL` 或 `INFERRED`。
- 未解决的核心旅程失败为零。

环境或凭证不足时，结果是受限或失败，不伪造通过。

## 写入研发上下文

在 `.sdlc-v1/context/<FEAT>.engineering.md` 更新：

~~~markdown
## Validation

### E2E — <commit>

Scope: feature | iteration | full-chain
Modalities: Web, OpenAPI, App
Target: <URL / API base / device>

| journey | modality | result | method | evidence |
|---|---|---|---|---|
| <name> | Web/OpenAPI/App | PASS/FAIL/PARTIAL/SKIPPED | TESTED/PARTIAL/INFERRED | <observed result and artifact ref> |

Failures: <none or reproduction + source location>
Unverified: <none or limitation + manual steps>
~~~

同一 commit 重跑时更新对应小节。E2E 正文和进度只使用研发上下文与 lifecycle state；截图放项目原有测试产物目录。

## 状态更新

e2e 不直接编辑 `state.json`。所有选定验证方式结束后，`sdlc-validate` 根据合并结果调用一次 `record-validation`。后续评审与发布分别只由 `record-review` 和 `record-release` 更新机器状态。

## 常见错误

- 只走 happy path。
- 把 DOM 存在当作用户目标完成。
- 失败只写现象，没有复现步骤或源码定位。
- 在真实环境执行破坏性 API。
- 没有设备工具却把 App 结论标成 `TESTED`。
- 将截图或测试产物当作另一份进度来源。
