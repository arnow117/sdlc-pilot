---
name: sdlc-review
description: >
  评审阶段。根据已验证 commit 的 diff 动态加载产品、架构、客户端、服务端、数据、设计、
  质量与安全角色，合并发现并记录评审决定。
---

# sdlc-review — 多角色代码评审

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。运行时支持时，主 Agent 使用与实现者不同的
新 review Agent；否则按相同检查串行完成并披露 fallback。review Agent 不修改实现或 state，只返回发现、证据和
`record-review` 请求，由主 Agent 验证后执行。

## 入口

- Feature 必须已通过验证。
- validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外不能有差异。
- 当前业务代码工作树必须干净；仅 `.sdlc-v1/**` 可以有待提交的上下文或状态修改。
- 读取项目、产品和研发上下文，但只加载与本次 diff 有关的部分。

可用以下检查确认实现未变化：

```bash
git diff --quiet <validation-commit>..HEAD -- . ':(exclude).sdlc-v1/**'
test -z "$(git status --porcelain --untracked-files=all -- . ':(exclude).sdlc-v1/**')"
```

任一检查失败时回到 build/validate。角色选择和评审 diff 以 validation commit 的业务代码为准，不把后续 `.sdlc-v1/**` 提交当作实现改动。

## 角色选择

调用 [`role-routing.md`](../sdlc/references/role-routing.md) 的解析规则。通常至少加载 QA；跨模块或改变接口/数据边界时加载 architect；敏感数据、认证、授权、支付或供应链变化时加载 security。

可并行执行互相独立的角色评审，每个角色返回：严重级别、文件与行、问题、影响、建议修复和验证依据。没有多执行者能力时按相同角色顺序串行完成。

## 合并结论

1. 按稳定指纹去重同一问题。
2. 区分必须修复、建议改进和信息项；检查每项业务代码改动是否能映射到 Task 或验收条件，将无关的重构、格式化或清理作为 scope drift 报告。
3. 把结论与处理结果写入研发上下文。
4. 存在必须修复项时执行：

```bash
lifecycle_state.py --repo <repo> record-review \
  --feature-id <feature-id> --decision changes_requested --by <reviewer>
```

修复后重新验证，再重新评审。

5. 没有未处理的必须修复项时执行：

```bash
lifecycle_state.py --repo <repo> record-review \
  --feature-id <feature-id> --decision approved --by <reviewer>
```

评审决定只对应 validation commit。研发上下文和 state 的后续提交不改变该实现版本。通过后进入 `sdlc-ship`。
