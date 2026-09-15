---
name: sdlc-review
description: >
  评审阶段。根据已验证 commit 的 diff 动态加载产品、架构、客户端、服务端、数据、设计、
  质量与安全角色，检查重复实现与可避免工程债，合并发现并记录评审决定。
distilled-from: [DietrichGebert/ponytail]
updated: 2026-09-05
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

当前 review Agent 串行汇总所选角色视角，每个发现包含严重级别、文件与行、问题、影响、建议修复和验证依据。
主 Agent 决定是否在实现之后另派一个实际独立的只读 review Agent；不能派发时只能披露串行 fallback，不称独立评审。

## 重复实现与可避免工程债

每次 review 都检查本次 diff 中新增或修改的实现。由当前 review Agent（串行 fallback 时为主 Agent）执行，
与角色发现一起汇总，不新增角色或子流程。可以只读检索相关调用链和候选实现以采集证据；不扩大为全仓清理，
不直接修改实现，不设置删行指标。

| 检查项 | 需要确认的事实 |
|---|---|
| 重复实现 | 仓库已有实现、标准库、平台原生能力或已安装依赖是否已满足当前需求；确认实际版本、调用方式和语义差异后再建议复用。 |
| 不必要的抽象 | 新接口、包装层、工厂或扩展机制是否承担当前需求或明确工程约束中的职责，还是仅服务尚不存在的需求。 |
| 冗余配置与依赖 | 新配置项或依赖是否有当前使用场景，其能力是否可由现有实现或能力满足；删除时是否影响部署或使用方。 |

单实现接口、调用者少、代码行数多，本身都不构成问题。保留有据的职责边界与依赖隔离，以及必要校验、错误处理、
安全与可访问性、版本兼容、幂等与并发控制和必要测试；不能用减少代码量替代需求与工程约束判断。

每项发现沿用现有评审格式，并明确写出：

- **严重级别与位置**：文件与行、问题及实际影响。
- **可删或替换项与证据**：明确具体项；纯删除写“无需替代”，给出相关调用或配置使用情况，以及当前需求不需要该项的依据。替换则引用候选实现的文件与符号，或与当前版本匹配的 API/文档，说明能力与语义为何适用。
- **行为保持依据与验证方式**：说明删除或替换后如何保持当前需求、接口语义及相关兼容、并发和失败处理约束，并指出可复用的测试或必要的验证方式；区分已有验证证据与待验证判断。

证据不足时明确缺口，不直接断言应删除。普通简化归为建议改进；只有违反明确约束或存在可证实影响时，
才按影响列为必须修复，不能让个人风格偏好阻塞发布。没有发现时明确写一句“本次 diff 未发现有证据支持的重复实现或可避免工程债”。

有依据的保留或延期决定随评审处理结果写入现有研发上下文，说明理由、适用局限和明确的重访触发条件；
不得借延期绕过阻塞正确性或安全的问题。采纳建议并修改业务代码后，仍按 build → validate → review 重新验证和评审。

## 合并结论

1. 按稳定指纹去重同一问题，包括上述检查与各角色重复报告的发现。
2. 区分必须修复、建议改进和信息项；检查每项业务代码改动是否能映射到 Task 或验收条件，将无关的重构、格式化或清理作为 scope drift 报告。
3. 把结论与处理结果写入研发上下文。
4. 存在必须修复项时，在 orchestrated mode 请求；只有独立、不在主 Agent 编排中的 standalone mode 才执行：

```bash
lifecycle_state.py --repo <repo> record-review \
  --feature-id <feature-id> --decision changes_requested --by <reviewer>
```

修复后重新验证，再重新评审。

5. 没有未处理的必须修复项时，在 orchestrated mode 请求；只有独立、不在主 Agent 编排中的 standalone mode 才执行：

```bash
lifecycle_state.py --repo <repo> record-review \
  --feature-id <feature-id> --decision approved --by <reviewer>
```

评审决定只对应 validation commit。研发上下文和 state 的后续提交不改变该实现版本。通过后进入 `sdlc-ship`。
