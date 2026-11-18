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

任何代码改动都运行 correctness。先从实际入口核对主流程的预期结果，再用必要边界和适用回归证明当前 Feature 符合产品验收和研发测试策略；详细正文只写研发上下文，机器进度只写 lifecycle state。

## 输入与记录位置

只读取：

- `.sdlc-v1/project.md` 中已经验证过的测试、类型检查和构建命令。
- 当前 Requirement 的产品上下文及验收条件。
- 当前 Feature 的 `.sdlc-v1/context/<FEAT>.engineering.md`。
- 当前 Git diff，以及本轮测试将绑定的实现 commit。

详细结果追加到当前研发上下文的 `## Validation` / `### Correctness`。不要创建 correctness report、baseline 状态文件或其他进度文件。所有验证方式完成后，由 `sdlc-validate` 统一调用一次 `lifecycle_state.py record-validation`。

## 核心原则

1. 完成声明须由当前候选的实际验证，或按阶段协议确认仍适用的独立实测证据支持。
2. 测试以实际行为断言为依据。边界用例按失败后果选择，覆盖已确认的拒绝、恢复、兼容性和数据保护。涉及已支持的变体时，选代表用例验证接口契约与既有行为。
3. 每条验收条件只标 `COVERED`、`PARTIAL` 或 `MISSING`。
4. 验证使用同一候选。验证者可在约定范围内调整临时环境和测试数据。必要的实现、仓库内测试或被测配置修改由原实现任务完成，之后绑定新候选重验。
5. 数值覆盖率默认用于发现漏测。何时作为通过条件见[覆盖率阈值](#5-覆盖率阈值)。

## 执行方法

### 1. 发现现有命令

优先使用 `project.md` 已记录命令，再根据语言卡和仓库配置核对。若发现项目实际命令与 `project.md` 不一致，先实际运行确认，再更新 `project.md`。

优先取得主流程的实际运行证据，按依赖安排构建和前置检查，再在同版候选上完成必要边界与项目要求的完整回归。典型检查包括：

1. 相关测试或全量测试。
2. 类型检查。
3. 构建。
4. 已约定为必要检查的覆盖率。现成报告也可作为补测参考。
5. 无自动化覆盖时的最小手工检查。

不要把 linter 当作编译或测试的替代。

### 2. 列出必须证明的行为

按以下优先级建立清单：

1. 产品上下文中的验收条件。
2. 研发上下文中的测试策略和 Task 验收说明。
3. Git diff 影响的公共行为、重要不变量和实际错误后果。

每项写成“触发条件 / 动作 / 期望结果”，并分类：

| 类型 | 处理 |
|---|---|
| 可直接断言的函数、状态机、校验、解析、数据变换 | 单元或集成测试 |
| 需要浏览器、真实端点或设备的用户旅程 | 交给 e2e mode |
| 模型、提示、策略或评估数据质量 | 交给 eval-bench mode |
| 纯样式、无逻辑配置等不适用项 | 记录原因，不伪造测试 |

### 3. 补齐测试

- 使用 Arrange / Act / Assert。
- 主流程断言最终业务结果。按照本次验收和风险选择必要的拒绝、恢复和边界用例。
- 禁止用 `toBeDefined()`、只验证“不抛异常”等平凡断言代替行为验证。
- 修过的缺陷增加能复现原问题的回归测试。
- 若发现实现缺陷或缺少必要的行为断言，记录期望、实际、文件位置和最小复现，交原实现任务在 `sdlc-build` 修正。验证者重验新版受影响的检查和项目要求的回归，按阶段协议复用仍适用的独立证据。

### 4. 本轮实际运行

每条命令都记录：

- 完整命令。
- exit code。
- 通过、失败和跳过数量。
- 覆盖率或构建摘要。
- 未运行的原因。

在写“通过”前执行：

1. 对每项确认可用的验证命令。已有独立证据按[阶段协议](../stage-agent-protocol.md#5-evidence-git-and-mandatory-stop)核对适用性。
2. 完整运行仍需重验的检查。
3. 阅读全部输出和 exit code。
4. 确认输出确实支持结论。

### 5. 覆盖率阈值

仅当项目既定校验或已确认的 Feature、发布要求明确约定时，数值覆盖率才是对应验收的通过条件。
覆盖率命令索引与语言示例用于找到工具。必检时确认适用环节、目标代码、比较基线（适用时）和阈值，优先使用项目原生校验。

| 约定范围 | 执行与判定 |
|---|---|
| 当次无必检约定 | 使用现成报告定位漏测即可。数值或报告缺失不影响本次验证或发布结论，也无需为此另建采集装置。 |
| 项目或 Feature 明确列为必要验证 | 在 Validate 对当前候选执行。低于阈值或缺可信证据时，保持对应检查未通过，按原因补行为测试或修测量。 |
| 指定发布明确列为必要检查，例如已约定的大版本 | 在发布前核对同版候选。复用仍适用的验证证据，缺少时补验。阈值或证据不满足时暂停该发布。 |

已发现的实际行为缺口仍按当前验收条件处理。任何覆盖率结果都只支持对应的代码执行范围。受阻时只暂停依赖该结论的操作，继续其他已授权且可独立完成的工作。

### 6. 验收条件映射

| 状态 | 判定 |
|---|---|
| `COVERED` | 本轮实测通过，或仍适用的独立实测证据证明目标行为通过 |
| `PARTIAL` | 只覆盖部分路径、测试失败或环境受限 |
| `MISSING` | 没有可验证证据 |

只有主流程、必要边界与其他必要验收条件均为 `COVERED`，并且适用的测试、类型检查、构建、项目约定回归及本阶段必检项均通过，correctness 才通过。

## 写入研发上下文

统一遵循 [sdlc-validate 的验证归因](../../../sdlc-validate/SKILL.md#验证归因)，在下列小节记录每项检查的
outcome、分类依据、执行时间和脱敏环境信息；混合问题分开记录。这里的覆盖/质量指标不替代验证归因。


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

Coverage: <applicability and measured lines/branches when available>
Implementation defects: <none or reproduction + file>
Unverified: <none or limitation>
~~~

同一 commit 重跑时更新对应小节，不另建报告。

## 状态更新

- 必要检查未通过时，由 `sdlc-validate` 按统一归因规则记录未通过并决定下一动作；环境阻塞或证据不足不自动触发实现修复。
- 所有选定验证方式通过：`sdlc-validate` 统一调用 `record-validation --result pass`。
- correctness 自身不直接编辑 `state.json`，也不记录 review 或 release。

## 常见错误

- 只跑一个测试文件就宣布全量通过。
- linter 通过后跳过类型检查或构建。
- 把未约定的数值当作通过条件，或把必检项的未测量写成通过。
- 在 validate 中修改实现，使失败证据消失。
- 把 E2E 或模型质量问题硬塞进单元测试。
- 把未运行、受限或推断结果标成已验证。
