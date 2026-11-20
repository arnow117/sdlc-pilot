---
name: sdlc-validate
description: >
  验证阶段。根据项目 surface、产品验收条件和研发测试策略运行必要检查，
  并将结果绑定到当前 Git commit。
---

# sdlc-validate — 验证实现

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。validate Agent 按
[correctness 的候选边界](../sdlc/references/validate-modes/correctness.md#核心原则)执行检查，不修改被测候选或 state，只记录验证证据并请求
`record-validation`；主 Agent 核对运行输出、当前 commit 与工作树后执行。产品 `eval-bench` 仍按实际
改动面选择，不增加新的行为评估流程。配置运行时支持独立执行者时，由与实现者不同的执行者实际运行当前候选的必要检查；
模型映射与不可用 fallback 按协议的[运行时选择](../sdlc/references/stage-agent-protocol.md#runtime-selection)读取所选适配；T3 run 完成不能代替独立验证。

## 输入

- Feature projection 及其两个上下文。
- 当前 Git diff 和 `.sdlc-v1/project.md` 的测试命令、surface map。
- `correctness | e2e:Web | e2e:OpenAPI | e2e:App | eval-bench | security-scan` 中与改动相关的方式。

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

## 验收条件与证据对应

在现有研发上下文的验证/证据部分，对当前有效的验收条件写明结果与证据或缺口。取消或延后 Task 不会移除其验收条件；已授权的条件替换需保留变更依据，再对应替换后的当前条件，不把已被替代的旧文本冻结成历史必选项。

- 单一简单条件可用一句话同时写出结果和证据。若既有报告或检查清单已清楚对应，引用它即可，不重抄、不重新排版，也不需为验收条件新增编号。
- 跨客户端、服务端、兼容性、持久化/并发/恢复情景，或多条件需要各自证据时，使用紧凑的“验收条件 | 结果 | 证据或缺口”表。共享的被测版本、配置或环境信息可写在表前，但不能取代上述必须记录的实际命令、exit 结果、时间和相关配置。

对应方式服从本节既有的 `PASS`、`IMPLEMENTATION_FAILED`、`ENV_BLOCKED` 和 `INCONCLUSIVE` 语义；表格只在确有区分证据的需要时才使用，不是新的通过前提。

- 同时核对当前 Task 完成条件中的命令、期望退出码及关键输出/行为是否实际满足，并关联到现有验收证据，不重建第二张完成表。自动检查通过不能替代已声明的人工、视觉或实际使用条件；必要观察尚缺时保持未通过并标明缺口。涉及项目级架构约束的验收条件按
  [`§2 项目级架构约束`](../sdlc/references/lifecycles/software-delivery.md#项目级架构约束)区分命令结果与人工观察：
  自动检查通过不证明架构已获人批准，必要的人工职责判断缺失时如实保留缺口，不汇总成全部满足。
- 计划命令不存在、环境不可用或判据无法执行时，按验证归因报告事实；不擅自删除条件、降低阈值或用仅检查文件存在的命令冒充行为验证。等效检查改变验证策略时，先按阶段协议处理方案和 brief。

验证之后如果产品或工程上下文的文字发生实质语义变化，主 Agent 按
[context-prose-and-evidence-applicability](../sdlc/references/stage-agent-protocol.md#context-prose-and-evidence-applicability)
判断既有结果对当前要求是否仍适用；本节不创建额外状态或自动失效规则。

## 验收归属与真人交接

每条验收条件按
[阶段协议的按需人工验收与验证历史](../sdlc/references/stage-agent-protocol.md#按需人工验收与验证历史)
确定验收归属。Agent 能可靠自验证的（可复现 Bug、请求与响应行为、有明确判据的客观 UI）
由 Agent 在适用环境取得可靠证据后直接完成适用验证，不要求用户试用；确需真人判断的
（用户明确要求、已确认条件已约定真人义务，或存在 Agent 无法替代的具体人类观察）才
交接真人。客观 UI 判据可由实际运行或可靠检查证明；缺环境或缺可信证据按验证缺口处理，
不改判为真人义务。用户主动试用可以收集意见，是否属于正式验收条件按当前约定判断。

### 交接内容

必要的人工交接复用当前对话和现有工程验证记录，包含：

- 旅程与涉及的 Feature；
- 可打开的入口或产物引用；
- 可核对的候选身份（版本、commit 或快照）；
- 操作步骤与每步的预期结果；
- 已检查项与尚未检查的缺口，及缺口对试用和发布的影响；
- 负责观察的人，以及需要其判断的具体问题。

先完成适用预检并固定候选或隔离后续修改，无法固定时说明证据影响。提前展示的未提交
候选和模拟结果按实际身份标示，只在其实际覆盖范围内作为证据。

### 等待期间

首次正式验收的其他必要检查均已通过、唯一待项是约定的真人操作或答复时，保留
`validation.result=pending`，并在既有工程记录注明待验项、候选和接续方式。沉默、普通
等待超时、泛化“继续”、模拟结果和客观检查通过都不填补真人证据，也不触发重复催问或
无变化的重验。同一候选、判据和责任人未变时不重复询问。符合 `pending` 等待条件时，
orchestrated mode 返回 `incomplete` 和空的 `requested_transitions`；standalone mode
不写通过或失败状态。

汇总前先按
[验证历史](../sdlc/references/stage-agent-protocol.md#按需人工验收与验证历史)区分首次、
已知历史的重开候选和历史不完整，三者的报告方式不同。已确认的失败、环境阻塞或实际
结案按实际原因处置，不被“等待中”遮蔽。

## 流程

1. 确认所有非取消 Task 均为 `done`。
2. 读取 [`Global usage-document, story, and parameter contract`](../sdlc/references/lifecycles/software-delivery.md#11-global-usage-document-story-and-parameter-contract)，并为受影响的故事按当前文档选择代表目标、参数来源和实际操作证据。
3. 按“验收归属与真人交接”确定每条验收条件由谁验证，再根据 [`role-routing.md`](../sdlc/references/role-routing.md) 选择验证方式，并读取对应 `validate-modes/*.md`。
   选择 `security-scan` 时按其契约检查实际执行、版本、范围、原生产物和未覆盖项；需要 Codex Security 时读取其适配说明，不能以依赖探针或 dry-run 代替扫描。
4. 优先在当前候选验证主流程的实际结果，按“验收条件与证据对应”核对必要边界及其他产品条件。执行适用的单元测试、类型检查、构建、端到端检查和项目要求的完整回归。根据[覆盖率规则](../sdlc/references/validate-modes/correctness.md#5-覆盖率阈值)确定覆盖率是否必检。合成或局部真实检查按实际环境和数据记录结果，不外推为 live、部署或真人试用通过。覆盖率命令实际运行了完整相关单元套件时，同一证据可支持两项检查。Build 的通过不能替代独立验证，按阶段协议核对证据适用性和重验范围。
   若检查会启动服务、浏览器、模拟器、容器、VM 或明显占用主机资源，按唯一的
   [验证资源生命周期](../sdlc/references/stage-agent-protocol.md#verification-resource-lifecycle)记录必要的收尾和资源状态。
5. 按上面的归因规则记录本轮证据到研发上下文。需要真人观察时按“交接内容”一次性集中交接，不拆成多轮零散提问。
6. 除上述满足条件且没有生效旧 `pass` 的真人等待外，任一必要检查失败、受阻或证据不足，都请求 `record-validation --result fail`；实际执行过时附 `--test-command <command>`，全部未运行时省略该参数并在上下文写明原因。这里的 `fail` 只表示未通过必要验证，不代表已证明代码有错。主 Agent 记录后按归因解决问题。仅需修复临时环境时保留原 Task 状态，补验受影响的检查。已确认需要修改候选实现、仓库内测试或被测配置时，按[Task 状态错误输出与恢复](../sdlc/references/lightweight-runtime.md#task-状态错误输出与恢复)恢复相关 Task，由原实现者修正并验证新版。
7. 全部必要检查通过，且 `.sdlc-v1/**` 之外的业务代码工作树干净时，在 orchestrated mode 请求；只有独立、
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

没有生效旧 `pass`，且其余必要检查通过、只待约定真人观察时，可按上面的验证历史沿用当前
`pending`，不因普通等待写入新的 `fail`。若旧 `pass` 仍在状态中生效，本轮必要重验缺少
真人证据时，仍须先按本节记录 `fail` 使旧通过及下游批准失效。明确人工拒绝、本轮验收实际
结束仍缺必要证据，或另一项必要检查失败或受阻时，也按实际原因记录 `fail`；只把实际执行过
的检查写进 `--test-command`。

## 跨会话续接与多 Feature

恢复时核对候选、环境、判据、原授权和已明确的答复，复用实际适用的证据；变化时只重验受影响项。
同一候选、判据和责任人未变时不重复询问已答且仍适用的事项。

多个 Feature 共享同一候选时，各 Feature 独立关联自己的验收条件、覆盖范围和集成缺口。一次
原观察可以同时关联多个 Feature，但每个 Feature 保留自己的状态、Task 和验证义务；某一项未通过
不把其他项伪装为通过，也不让一个已完成项隐去集成缺口。跨 clone 引用须能定位到已同步的原证据。

## 完成条件

- 产品验收条件有对应结果。
- 选择的验证方式覆盖实际变更区域。
- 没有把未运行的检查写成通过。
- 验证记录对应测试时的当前集成 commit。

通过后进入 `sdlc-review`。
