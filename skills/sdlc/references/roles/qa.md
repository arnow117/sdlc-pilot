---
role: qa
triggers: ["**/*.test.*", "**/*.spec.*", "e2e/**", "tests/**", "__tests__/**", "any-diff"]
distilled-from: [plan-eng-review, "gstack/review/specialists/testing.md", "gstack/review/specialists/red-team.md", qa, testing-reality-checker, testing-evidence-collector]
---

# QA 角色卡

QA 是每次代码变更都加载的质量视角。它提供检查方法，不维护独立流程或报告。

## 关注点

1. **覆盖 codepath，不只覆盖文件**：新增或改变的条件分支、错误处理和 early return 都要有对应证据。
2. **负路径优先**：拒绝、非法输入、权限不足、依赖失败和边界值通常比 happy path 更容易隐藏缺陷。
3. **用户旅程与代码覆盖分开检查**：单元测试不能替代跨页面、API、队列或设备的真实旅程。
4. **回归优先**：既有行为改变或历史缺陷复现时，增加针对原 codepath 的回归测试。
5. **测试装置可信**：测试应隔离、确定、无空断言；先确认 runner 和 coverage 真正统计目标代码。
6. **结论有本轮证据**：未实际运行的检查必须标明限制。

## 检查清单

### Codepath

- [ ] 每个改动入口的数据流已追踪到输出与失败位置。
- [ ] 每个条件分支的 true / false 两侧有覆盖。
- [ ] 每个错误处理器有能触发该条件的测试。
- [ ] helper 的关键分支没有被上层 smoke test 掩盖。
- [ ] 断言验证业务行为，不只是存在、渲染或“不抛异常”。

### 负路径与边界

- [ ] 0、负数、最大值、空字符串、空集合、单元素、null/nil/undefined。
- [ ] Unicode、特殊字符和最大长度输入。
- [ ] 未认证、无权限、对象归属错误和限流。
- [ ] 慢依赖、错误响应、部分完成和重试。
- [ ] 并发提交、重复请求、陈旧 session 和跨 tab 操作。

### 用户旅程

- [ ] 主要多步流程由 E2E 或集成测试走到终态。
- [ ] 成功、错误、空态有明确反馈且用户可以恢复。
- [ ] auth、支付、数据删除等关键集成点没有被过度 mock。
- [ ] 未运行的设备、浏览器或真实服务检查已明确标记。

### 隔离与稳定性

- [ ] 测试之间无共享可变状态或执行顺序依赖。
- [ ] 时间、时区、locale、随机数和网络依赖可控。
- [ ] 不使用裸 sleep 或紧 timeout 掩盖同步问题。
- [ ] flaky 测试修复根因，不以无限 retry 代替。

### 阈值

- [ ] 使用产品或研发上下文约定的覆盖率阈值。
- [ ] 未约定时，新增或改动代码参考行覆盖 80%、分支覆盖 70%。
- [ ] 低于阈值时工具返回非零 exit code，或在研发上下文明确写出缺口。

## 测试类型选择

| 类型 | 适用情况 |
|---|---|
| 单元测试 | 纯函数、状态机、校验、解析、数据变换和单函数边界 |
| 集成 / E2E | 跨多个组件或服务、真实认证、队列、数据库、浏览器或设备旅程 |
| Eval | 模型、prompt、system instruction、tool definition 或 agent 策略质量 |
| 不适用 | 纯样式或无逻辑配置；必须记录原因 |

## 覆盖质量

| 评级 | 含义 |
|---|---|
| ★★★ | 行为、边界和错误路径均覆盖 |
| ★★ | 正确行为已覆盖，但主要是 happy path |
| ★ | smoke、存在性检查或平凡断言，不能证明核心行为 |

## 阶段贡献

| 阶段 | QA 视角 |
|---|---|
| spec | 将“完成”改写为可运行、可观察的验收条件 |
| plan | 把测试、负路径和回归点纳入工程任务 |
| build | 检查 TDD 断言是否覆盖真实行为 |
| validate | correctness 默认运行；按改动补 e2e 或 eval-bench |
| review | 检查遗漏、flaky、隔离问题和证据可信度 |

## 记录方式

QA 的详细证据写入当前 `.sdlc-v1/context/<FEAT>.engineering.md`：

- 验证结果写 `## Validation` 下的 Correctness、E2E 或 Eval Bench 小节。
- 评审发现写 `## Review` / `### QA`。
- 每条发现包含严重级别、文件与行、问题、影响、证据和建议修复。
- 无发现时写明实际运行过哪些检查；不要只写 `NO FINDINGS`。

correctness、E2E 与 QA baseline 的正文只写研发上下文，不创建额外状态文件或进度字段。验证、评审和发布的机器状态分别只由 `record-validation`、`record-review`、`record-release` 更新，角色卡自身不调用这些命令。

## 常见错误

- 文件有测试就假定所有分支被覆盖。
- 只测 happy path。
- 用平凡断言堆覆盖率。
- 允许 flaky 测试靠重试通过。
- 在 validate 阶段改实现来配合测试。
- 把未运行的 E2E 或 Eval 写成通过。
- 另建 QA 报告并与 Feature 研发上下文重复。
