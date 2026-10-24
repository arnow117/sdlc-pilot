# sdlc-prototype — 包内产品原型适配

`sdlc-prototype` 是随 sdlc-pilot 分发的可交互原型制作方法。它可以独立使用，也可以由产品或规格阶段按需使用；已明确
计划的原型迭代由 plan 消费、评估和记录，并由 build 更新。它不创建生命周期、角色、状态字段、manifest 或第二份产品/工程
上下文。主 Agent 拥有编排和生命周期；当前 stage 保持既有边界与输出，原型只是其中的方法。本参考是 SDLC 的原型选择策略和
接口唯一权威来源；当前 `product_context_ref` 拥有产品意图和 confirmed 规则。

## 1. 选择策略与包内发现

在首次 UI 或交互设计没有充分已确认的设计或原型 baseline 时，默认使用 `sdlc-prototype`。信息架构、导航、核心旅程、
角色、状态反馈或跨端联动发生实质变化时，评估受影响范围并更新相应原型和场景映射，复用未受影响的 baseline。

以下情况不强制原型：用户明确跳过、已有充分已确认的设计或原型可以复用、后端工作、已有明确场景的普通实现、文案修改和
小范围样式调整。原型是否适用只由本节判断；其他 router、stage 和角色卡引用本参考，不复制另一套触发策略。

方法和所需 references、共享状态 assets 均位于包内 [`sdlc-prototype`](../../../sdlc-prototype/SKILL.md)。当前宿主尚未发现本地新技能时，不能声称
`/sdlc-prototype` 已可调用；安装或刷新宿主索引后，插件身份为 `sdlc-pilot:sdlc-prototype`，本地发现名称为
`sdlc-prototype`。包内链接缺失是分发包缺口，不发现、安装或恢复外部旧 `product-prototype` 技能。

## 2. 既有 brief 和结果中的接口

不新增 schema、manifest 或状态记录。需要原型时，当前 stage 的既有 brief（见
[stage-agent-protocol.md](../stage-agent-protocol.md)）明确：

- 权威 `product_context_ref`，以及 confirmed、观察事实、假设和开放问题的区分；
- 场景范围及已有 `SCN-*`、`RULE-*` 等标识，现有原型的路径和版本；
- 目标终端形态、品牌或设计系统、演示/同步范围；
- 项目约定的原型产物目录、可写边界、完成条件和验收方式。

沿用既有 stage result/交接格式返回：产物路径及版本、hash 或 commit；场景到原型锚点的映射；实际执行的证据和限制；
候选决定与开放问题；以及可供工程规划评估的组件、token、fixture 或代码复用候选。原型不把观察或演示假设升级为
confirmed，也不直接修改 `.sdlc-v1/state.json` 或请求新的生命周期操作。

产品或规格阶段展示候选时，主 Agent 给出可打开的入口、版本、可走通的核心旅程、需要用户尝试的具体动作、实际检查范围、
模拟部分和仍待决定的选择。反馈面向可见行为，而不是泛问是否满意。确认、明确委托和开放项仍记录在现有产品上下文：反馈影响行为时，
更新受影响原型版本、场景映射和决定的替代关系，并让 plan 更新受影响设计与计划验证。原型存在、点击检查或未收到反馈不自动确认
产品意图，也不构成生产实现、validation、review 或 release 证据。

## 3. 阶段边界与证据归属

| 阶段 | 使用方式与写入边界 |
|---|---|
| product-design / spec | 按本参考的选择策略，在 brief 明确命名的项目约定目录创建或更新有界 demo 原型；目录在 `.sdlc-v1` 外，且不改生产代码。产品上下文保留产品意图、confirmed 来源、场景映射、原型 baseline 及产品阶段实际证据/限制。阶段 Agent 不自行 fan out。 |
| plan | 读取已确认的原型输入，决定组件、token、fixture 或代码是否复用，并只将适用的 confirmed 场景映射到生产验收与计划验证；演示假设和开放替代项仍是候选。当前有效方案明确记录有界原型迭代的资产范围，由 build 更新。工程上下文记录复用/实现决定和引用的版本；引用原始产物，不复制报告。 |
| build | 只按计划中明确的生产实现和/或原型资产范围工作；原型不是第二套实现或状态来源。`.sdlc-v1` 外受跟踪原型资产变化需要新的业务验证 baseline。实现遵循既有仓库角色路由和主 Agent 派工，stage Agent 不自行 fan out。需要调整产品行为时回到既有产品/规格流程。 |
| validate / review | 只读当前实现和已有原型输入。原型点击或模拟结果不能证明生产持久化、并发、认证/授权或其他正式实现行为；正式实现重新验证相关语义场景。`.sdlc-v1` 外的受跟踪产物（包括原型资产）变更必须走既有 build/validate 路径并建立新的验证基线，不能因标为 demo 而沿用旧结论。只有产品/工程上下文的语义变化，才按[既有证据适用规则](../stage-agent-protocol.md#context-prose-and-evidence-applicability)判断覆盖：能复用时记录理由，否则走既有 plan/build/validate 路径。发现修正需求时按既有 plan/build 流程返回。 |

demo 需要更复杂运行时行为时，在允许的原型产物内使用可替换的模块与 mock adapter；这不改变生命周期、状态归属或生产实现边界。

产品确认时，以原型版本和覆盖场景建立 baseline。受影响旅程变化，或已有授权的视觉/demo 展示工作更新原型时，只刷新相关范围并记录适用版本与覆盖场景；不把原型与生产 UI 维护成永久的全量双份界面。Feature 的实现选择、正式验证与 review 证据属于工程上下文，原始原型产物只由该上下文引用。

直接调用 `sdlc-prototype` 创建、分析或迭代与当前 tracked Requirement/Feature/Task 无关的原型时，不初始化 state，也不启动无关生命周期。已跟踪工作直接调用时仍读取当前 stage、brief 和产物目录，并遵守本表的写入边界。

