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

## 流程

1. 确认所有非取消 Task 均为 `done`。
2. 根据 [`role-routing.md`](../sdlc/references/role-routing.md) 选择验证方式，并读取对应 `validate-modes/*.md`。
3. 逐条验证产品验收条件；同时运行相关单元测试、类型检查、构建和必要的端到端检查。
4. 记录实际命令、结果和失败原因到研发上下文。
5. 失败时调用 `record-validation --result fail --test-command <command>`，回到 build。
6. 全部必要检查通过，且 `.sdlc-v1/**` 之外的业务代码工作树干净时调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  record-validation --feature-id <feature-id> --result pass \
  --test-command <representative-command>
```

该命令记录测试时的当前 HEAD，作为 validation commit。若验证包含多条命令，完整列表留在研发上下文，状态中保留代表性入口。命令完成后可以继续修改并提交 `.sdlc-v1/**` 来同步状态、上下文和证据；这些提交不改变被验证的实现版本。

## 完成条件

- 产品验收条件有对应结果。
- 选择的验证方式覆盖实际变更区域。
- 没有把未运行的检查写成通过。
- 验证记录对应测试时的当前集成 commit。

通过后进入 `sdlc-review`。
