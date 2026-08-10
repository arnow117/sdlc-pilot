---
mode: correctness
triggers: [always]
distilled-from:
  - verification-before-completion
  - verify
  - gsd-add-tests
  - qa
  - gsd-validate-phase
---

# Validate mode: correctness

任何代码改动都运行 correctness。它证明当前 Feature 的实现符合产品验收条件和研发测试策略；详细正文只写研发上下文，机器进度只写 lifecycle state。

## 输入与记录位置

只读取：

- `.sdlc-v1/project.md` 中已经验证过的测试、类型检查和构建命令。
- 当前 Requirement 的产品上下文及验收条件。
- 当前 Feature 的 `.sdlc-v1/context/<FEAT>.engineering.md`。
- 当前 Git diff，以及本轮测试将绑定的实现 commit。

详细结果追加到当前研发上下文的 `## Validation` / `### Correctness`。不要创建 correctness report、baseline 状态文件或其他进度文件。所有验证方式完成后，由 `sdlc-validate` 统一调用一次 `lifecycle_state.py record-validation`。

## 核心原则

1. 完成声明必须由本轮实际运行的命令支持。
2. 测试覆盖行为和分支，不以“存在测试文件”代替覆盖。
3. 每条验收条件只标 `COVERED`、`PARTIAL` 或 `MISSING`。
4. correctness 可以补测试；发现实现缺陷时返回 build，不在验证阶段顺手改实现。
5. 覆盖率使用项目约定阈值；项目未约定时，新增或改动代码默认行覆盖 80%、分支覆盖 70%。

## 执行方法

### 1. 发现现有命令

优先使用 `project.md` 已记录命令，再根据语言卡和仓库配置核对。若发现项目实际命令与 `project.md` 不一致，先实际运行确认，再更新 `project.md`。

常见顺序：

1. 相关测试或全量测试。
2. 类型检查。
3. 构建。
4. 覆盖率。
5. 无自动化覆盖时的最小手工检查。

不要把 linter 当作编译或测试的替代。

### 2. 列出必须证明的行为

按以下优先级建立清单：

1. 产品上下文中的验收条件。
2. 研发上下文中的测试策略和 Task 验收说明。
3. Git diff 新增或改变的分支、错误路径和公共行为。

每项写成“触发条件 / 动作 / 期望结果”，并分类：

| 类型 | 处理 |
|---|---|
| 可直接断言的函数、状态机、校验、解析、数据变换 | 单元或集成测试 |
| 需要浏览器、真实端点或设备的用户旅程 | 交给 e2e mode |
| 模型、提示、策略或评估数据质量 | 交给 eval-bench mode |
| 纯样式、无逻辑配置等不适用项 | 记录原因，不伪造测试 |

### 3. 补齐测试

- 使用 Arrange / Act / Assert。
- 同时覆盖成功、拒绝、错误和边界路径。
- 禁止用 `toBeDefined()`、只验证“不抛异常”等平凡断言代替行为验证。
- 修过的缺陷增加能复现原问题的回归测试。
- 若测试暴露实现缺陷，记录期望、实际、文件位置和最小复现，返回 `sdlc-build`。

### 4. 本轮实际运行

每条命令都记录：

- 完整命令。
- exit code。
- 通过、失败和跳过数量。
- 覆盖率或构建摘要。
- 未运行的原因。

在写“通过”前执行：

1. 识别能证明结论的命令。
2. 完整运行。
3. 阅读全部输出和 exit code。
4. 确认输出确实支持结论。

上次运行结果或主观信心不能替代本轮结果。

### 5. 覆盖率阈值

优先使用项目原生配置让工具在低于阈值时返回非零 exit code，例如 pytest-cov、Vitest/Jest coverage 或 JaCoCo verification。

| 情况 | 结论 |
|---|---|
| 达到项目约定阈值 | 通过覆盖率检查 |
| 项目无阈值且新增/改动代码达到 80% 行、70% 分支 | 通过默认检查 |
| 低于阈值 | 补测试后重跑 |
| 工具无法统计 | 标记未验证并说明原因，不把它写成通过 |

### 6. 验收条件映射

| 状态 | 判定 |
|---|---|
| `COVERED` | 测试打中目标行为，且本轮运行通过 |
| `PARTIAL` | 只覆盖部分路径、测试失败或环境受限 |
| `MISSING` | 没有可验证证据 |

只有所有必要验收条件为 `COVERED`，测试、类型检查、构建和适用覆盖率检查均通过，correctness 才通过。

## 写入研发上下文

在 `.sdlc-v1/context/<FEAT>.engineering.md` 更新：

~~~markdown
## Validation

### Correctness — <commit>

| command | result | summary |
|---|---|---|
| <command> | PASS/FAIL/NOT_RUN | <exit code and counts> |

| acceptance / behavior | status | evidence |
|---|---|---|
| <behavior> | COVERED/PARTIAL/MISSING | <command and observed result> |

Coverage: <lines/branches or not available>
Implementation defects: <none or reproduction + file>
Unverified: <none or limitation>
~~~

同一 commit 重跑时更新对应小节，不另建报告。

## 状态更新

- 任一必要检查失败：`sdlc-validate` 调用 `record-validation --result fail`，Feature 返回 build。
- 所有选定验证方式通过：`sdlc-validate` 统一调用 `record-validation --result pass`。
- correctness 自身不直接编辑 `state.json`，也不记录 review 或 release。

## 常见错误

- 只跑一个测试文件就宣布全量通过。
- linter 通过后跳过类型检查或构建。
- 覆盖率靠肉眼判断，没有使用阈值或明确缺口。
- 在 validate 中修改实现，使失败证据消失。
- 把 E2E 或模型质量问题硬塞进单元测试。
- 把未运行、受限或推断结果标成已验证。
