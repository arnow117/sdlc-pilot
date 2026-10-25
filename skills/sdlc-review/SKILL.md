---
name: sdlc-review
description: >
  评审阶段。根据已验证 commit 的 diff 动态加载产品、架构、客户端、服务端、数据、设计、
  质量与安全角色，检查重复实现与可避免工程债，合并发现并记录评审决定。
distilled-from: [DietrichGebert/ponytail, Zts0hg/codexspec]
updated: 2026-09-05
---

# sdlc-review — 多角色代码评审

> CodexSpec 的评审输入与范围方法改编自其固定版本
> [change-review.md](https://github.com/Zts0hg/codexspec/blob/d76d358a9f79a9b131bb2eccb85670e5d81b7dca/templates/review-code/change-review.md)。

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。运行时支持时，主 Agent 使用与实现者不同的
新 review Agent；否则按相同检查串行完成并披露 fallback。review Agent 不修改实现或 state，只返回发现、证据和
`record-review` 请求，由主 Agent 验证后执行。Codex 的独立 Sol 角色映射和不可用 fallback 见
[runtime adapter](../sdlc/references/runtime-adapters/codex.md)，专业角色卡不替代该独立性。

## Review input and scope

主 Agent 给独立 review Agent（或串行 fallback）提供已确认的产品 artifact、当前有效方案中的实际设计理由和适用契约、
validation commit/diff，以及选定的原始环境、配置和变更事实。它同时列出中性的未完成验证义务或已知证据缺口，并引用现有
Validation/证据位置。

不提供实现对话中的推理过程、早先的正确性结论，或“修复已经成功”的声明来预设结论。评审者自己依据当前 artifact 和原始事实
判断；运行时 fallback 不改变这项输入纪律，也不能称为独立评审。

只读评审记录本次相关契约、调用链和正常失败场景的覆盖情况与实质缺口，并引用现有 Validation 结果或缺口；不重建验收条件、
结果和证据表，也不新增独立评审报告或评分。

## 入口

- Feature 必须已通过验证。
- validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外不能有差异。
- 当前业务代码工作树必须干净；仅 `.sdlc-v1/**` 可以有待提交的上下文或状态修改。
- 读取项目、产品和研发上下文，但只加载与本次 diff 有关的部分。
- 上下文含相关图示时，按[图示辅助对齐](../sdlc/references/lifecycles/software-delivery.md#图示辅助对齐)核对图、正文、实现与已有证据；不以图的数量代替覆盖判断。
- 读取 [`sdlc-validate`](../sdlc-validate/SKILL.md#验收条件与证据对应) 对研发上下文验证/证据部分的要求，核对当前有效验收条件的覆盖缺口与实现版本；不复制或重建验收条件/结果/证据表。
- 依照 [context-prose-and-evidence-applicability](../sdlc/references/stage-agent-protocol.md#context-prose-and-evidence-applicability)
  由主 Agent 先判断验证证据是否仍覆盖当前产品决定和当前有效方案；不把未变的业务 commit 当作自动证明。
- 对用户可见改动，读取 [`Global usage-document, story, and parameter contract`](../sdlc/references/lifecycles/software-delivery.md#11-global-usage-document-story-and-parameter-contract)，核对 guide → story → parameter source → actual-use evidence；缺少真实范围不得被测试、截图或 doccheck 掩盖。

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

若 finding 显示可重复的根因，围绕本次 diff 的契约、模块或调用链做有界的相关实例搜索，并记录搜索范围、命中或未命中和它对结论的影响。不要把这类搜索扩大为全仓清理；只有有证据的相关实例进入本次评审或后续有界工作。

批量处置评审意见和返修时，遵循共享的 [`receiving-feedback`](../sdlc/references/receiving-feedback.md) 纪律。它是意见的核实、归类和证据记录权威来源；本评审不复制其流程。

有依据的保留或延期决定随评审处理结果写入现有研发上下文，说明理由、适用局限和明确的重访触发条件；
不得借延期绕过阻塞正确性或安全的问题。采纳建议并修改业务代码后，仍按 build → validate → review 重新验证和评审。

## 合并结论

1. 检查问题的位置、触发条件和根因，合并同一问题的重复报告，包括上述检查与各角色的发现。
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
