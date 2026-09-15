---
name: sdlc-validate
description: >
  验证阶段。根据项目 surface、产品验收条件和研发测试策略运行必要检查，
  并将结果绑定到当前 Git commit。
---

# sdlc-validate — 验证实现

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。validate Agent 不修改实现或 state，只记录
验证证据和请求 `record-validation`；主 Agent 核对运行输出、当前 commit 与工作树后执行。产品 `eval-bench` 仍按实际
改动面选择，不增加新的行为评估流程。

## 输入

- Feature projection 及其两个上下文。
- 当前 Git diff 和 `.sdlc-v1/project.md` 的测试命令、surface map。
- `correctness | e2e:Web | e2e:OpenAPI | e2e:App | eval-bench` 中与改动相关的方式。

## 询问前的定向查找

索取测试账号、参数或环境信息前，先查看当前项目相关文档、配置示例、fixture 和已有验证记录。
只查与当前缺口有关的来源，不默认扫描整个知识库；不输出凭据。仍缺信息或证据冲突时，集中说明
已查来源、确切缺口及其影响，再提出最小问题。既有授权仅在原范围内有效，查到凭据不等于获得外部操作授权。

## 验证归因

以下分类只写入现有研发上下文，不增加 lifecycle 字段，也不替代各验证方式的覆盖率或质量指标。

| outcome | 必要证据 | 下一动作 |
|---|---|---|
| `PASS` | 所有必要检查实际执行并满足验收要求 | 可请求通过验证 |
| `IMPLEMENTATION_FAILED` | 可定位的实现异常、断言失败或验收/质量阈值未满足 | 修复对应实现、测试或设计，再验证 |
| `ENV_BLOCKED` | 已确认的凭据、运行时、依赖或外部服务缺口 | 解决环境后重验，不因此盲目修改实现 |
| `INCONCLUSIVE` | 执行不完整、证据冲突或原因未确认 | 补证据，保持未通过 |

逐项记录命令（未执行写 `NOT_RUN`）、exit code/观察结果、分类依据、实际执行时间、被测 commit、
相关配置与脱敏环境信息，以及下一动作。超时、非零退出码或连接错误本身不足以断言是环境问题。
混合问题分别记录；已确认的实现缺陷不能被环境阻塞覆盖。所有必要检查通过才可汇总为 `PASS`。

## 流程

1. 确认所有非取消 Task 均为 `done`。
2. 根据 [`role-routing.md`](../sdlc/references/role-routing.md) 选择验证方式，并读取对应 `validate-modes/*.md`。
3. 逐条验证产品验收条件；同时运行相关单元测试、类型检查、构建和必要的端到端检查。
4. 按上面的归因规则记录本轮证据到研发上下文。
5. 任一必要检查失败、受阻或证据不足，都请求 `record-validation --result fail`；实际执行过时附 `--test-command <command>`，全部未运行时省略该参数并在上下文写明原因。这里的 `fail` 只表示未通过必要验证，不代表已证明代码有错。主 Agent 按允许的 lifecycle 命令记录后，按归因决定修复实现、解决环境或补证据；不要仅凭 `fail` 自动重做实现。Task 均为 done 时，当前 `next` 仍选择 validate。需要实现修复时由主 Agent 将相关 Task 恢复为 in_progress，再进入 build。
6. 全部必要检查通过，且 `.sdlc-v1/**` 之外的业务代码工作树干净时，在 orchestrated mode 请求；只有独立、
   不在主 Agent 编排中的 standalone mode 才直接调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  record-validation --feature-id <feature-id> --result pass \
  --test-command <representative-command>
```

该命令记录测试时的当前 HEAD，作为 validation commit。若验证包含多条命令，完整列表留在研发上下文，状态中保留代表性入口。命令完成后可以继续修改并提交 `.sdlc-v1/**` 来同步状态、上下文和证据；这些提交不改变被验证的实现版本。

## 旧验证记录与受阻重验

本轮必要重验不是 `PASS` 时，即使同一 commit 曾通过，也必须先记录本轮 `fail`，使旧 validation、review
与 release 待推进记录失效；不能只写一段受阻说明而继续使用旧通过记录。由主 Agent 核对这一状态变化后才恢复调度。
若工作树等前置条件使 `record-validation` 被拒绝，记录阻塞并停止该 Feature 的调度，不运行 review/ship、
不直接改 state；满足前置条件后先记录本轮结果。已 released 的 Feature 不自动撤回发布，转入维护工作并报告
已知验证风险；只有符合 `retract-release` 的误记录纠正条件时才使用该命令。

## 完成条件

- 产品验收条件有对应结果。
- 选择的验证方式覆盖实际变更区域。
- 没有把未运行的检查写成通过。
- 验证记录对应测试时的当前集成 commit。

通过后进入 `sdlc-review`。
