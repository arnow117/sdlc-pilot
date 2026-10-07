# Impeccable — design 可选适配

Impeccable 是 `design` 角色在适用前端工作中可选使用的方法，不是新的 SDLC skill、角色、验证方式或进度字段。
本参考定义唯一的接入规则；当前版本的 Impeccable `SKILL.md` 及其按需加载的参考仍定义具体命令和工作步骤。

## 1. 选择 design 与检查可用性

当请求或产品上下文涉及页面、组件、表单、导航、空态、loading/error 反馈、响应式、无障碍或视觉方向时，选择
`design`，即使当前尚无 UI diff。纯后端且不影响用户可见交互时，不加载本参考，也不输出安装提醒。服务端改动若会
改变界面反馈或用户旅程，仍按实际影响选择 `design`。

在一个目标业务项目的会话中，主 Agent 于首次适用时检查一次能力，并把结果、限制和是否已提醒传入后续 stage brief。
standalone 调用时，当前 Agent 承担相同职责。后续阶段复用该 brief/session 信息；目标项目、运行时能力或安装环境变化后
可以重新检查。不要把可用性缓存、提醒去重标记或新增 state 字段写入 `.sdlc-v1/**`，也不要建立“未安装”的持久缓存。
实际使用或验证中未执行的原因、能力限制和证据，仍按阶段写入既有研发上下文的相应章节。

检查顺序如下：

1. 查询当前运行时可加载的 skill；再检查可解析的 Impeccable `SKILL.md`。本地文件存在不等于运行时能够加载。
2. 仅在实际需要 Impeccable context 的阶段，确认相应 launcher 是否可用。普通能力检查不得运行会下载引擎的命令，
   不得因探测自动安装或联网下载。
3. 仅在 build 需要自动反馈时检查目标项目 Hooks 的状态和信任。manifest 存在不能证明 Hook 已启用或已获信任。

| 观察结果 | 处理 |
|---|---|
| 未发现可加载的 Skill | 每个目标项目、每次会话一次中文提醒：`这个前端任务适合使用 Impeccable，但当前环境未检测到可加载的技能。我会继续按现有设计规范和 E2E 完成 SDLC；安装后可以补充视觉与交互质量检查。` 提供 [官方安装入口](https://impeccable.style/docs/)，等待明确安装指令；继续现有 `design`、组件库和 E2E 流程。 |
| 文件存在但运行时未识别 | 说明“发现本地文件，但运行时尚未识别为可加载技能”，按运行时支持直接读取或提示刷新/新开会话；不要误报为未安装。 |
| Skill 可读、launcher 不可用或被拒绝 | 在下一次工具调用前单独声明：`Context loading did not run; I’ll read the existing project context directly.` 然后读取已有 `PRODUCT.md`、`DESIGN.md` 和上下文，不虚构缺失事实，并继续允许的方法。 |
| 引擎可用、Hooks 缺失或关闭 | 仅在 build 说明自动反馈不可用；可以使用已具备的手动检测和真实页面检查。 |
| Hook 信任未知或被拒绝 | 如实说明需要运行时原生授权，不能自动信任、绕过或借检查安装 Hook。 |

缺少 Impeccable 不阻断 SDLC，也不免除现有必要验证要求。必要检查不可运行时，按既有 validate 规则记录未通过；
`INFERRED` 不能写成 `TESTED` 或验收通过。用户明确要求的验收能力确实不可用时，报告该具体缺口，不能写成已经验证。
已有授权的安装任务仍按其授权执行；本参考不新增安装、下载、Hook 信任或第三方访问授权。

## 2. 实际使用的共同约束

真正调用 Impeccable 时，按运行时解析到的 Skill base directory 调用当前 `SKILL.md`，以目标业务项目为 cwd，并带上已知
source file 或 route。不得硬编码用户目录，也不得混淆 npm 安装器、Skill 与引擎的版本。每个目标项目会话按原 Skill
setup 加载一次 context；能力检查本身不应触发可能下载引擎的 launcher。若实际调用的 launcher 可能联网下载，先按
当前授权和运行时规则处理该外部效果，而不是把它伪装成无副作用的检测。

已确认的产品事实、视觉方向、`DESIGN.md`、组件/token 和 surface brief 优先。缺少 `PRODUCT.md` 不要求小范围优化
自动 `init`；只有稳定产品事实确有缺口且产品阶段已确认时才使用 `init`。同样，`document` 仅整理已观察到的设计系统，
不凭空生成 token 或覆盖既有 `DESIGN.md`。不要为已经确认的事实重复 `shape`/`init` 访谈，也不要以普通优化改变业务范围、
事实文案或已确认品牌。

每个受影响 surface 选择适合其使用目标的 `Operate`、`Persuade`、`Read` 或 `Experience` 模式，并只将该模式和必要
视觉约定保留在该 surface brief。品牌 brief 优先于 detector 的通用提示；例如已确认的字体或渐变可以保留，但需要记录
判断依据。过期上下文按 Impeccable 约束报告，不顺带修复用户未要求的产物漂移。

## 3. 阶段映射与证据位置

按需借用方法，不把 `shape`、`polish` 等工作方法当作未经验证的 launcher 子命令，也不机械执行全部命令。

| 阶段 | 适配方法 | 输出与边界 |
|---|---|---|
| product-design / spec | 借用 `shape` 的任务发现和体验方向：用户、结果、信息架构、旅程、状态、响应式与无障碍。只补充会改变体验方向或验收的缺口。 | 需求正文唯一写入 `.sdlc-v1/context/<REQ>.product.md`；方向确认并入现有产品确认。 |
| plan | 读取已确认方向、设计系统、组件/token 与 surface brief，把体验约束转换为 Task、可检查验收和验证策略。 | Feature 正文唯一写入 `.sdlc-v1/context/<FEAT>.engineering.md`；不另开产品访谈。 |
| build | UI 编辑前读取当前 Skill 的 `craft-floor`；以现有组件和设计系统为先，按实际缺陷选择 `clarify`、`adapt`、`harden` 或 `polish` 等方法。 | 页面修改、`init`、`document`、`polish` 和需要生成产物的操作只在 build 或已授权的上下文准备阶段进行，并进入验证基线。 |
| validate | 借用 `audit` 的技术检查维度，并结合真实 E2E、键盘、断点、对比、状态和设备检查。原生 App 读取原生参考，不以 Web detector 代替。 | validate 只读实现；实际运行才标 `TESTED`，无浏览器/设备时标 `INFERRED` 并给出人工步骤。 |
| review | 借用 `critique` 的设计判断维度，检查当前 UI diff、产品意图、设计系统一致性和已有渲染证据。 | review 只记录发现；需要改代码或设计产物时回到 build，然后重新进行适用的 validate/review。 |

产品行为、场景、规则和体验约束只在 Requirement 产品正文；Feature 的 Plan、设计发现、`Validation / Design` 和
`Review / Design` 只在工程正文。截图、trace 与 Impeccable 原始产物可保留在项目既有目录并由工程正文引用，不创建
并行的设计结论报告。

若 build 或授权的上下文准备生成了 `.sdlc-v1/**` 以外的受跟踪文件，既有 validation 结论不能继续使用；按现有协议
回到 build 并重新验证。Hook 的反馈、Stop 修正请求和 detector 提示不是 SDLC 验收，不得通过关闭 Hook 或无限打磨来
规避验收。

## 4. 完整 critique 的额外编排

通常阶段只借用 `critique` 的判断维度，不能宣称已执行完整 Impeccable critique。完整调用要遵守当前运行时
`reference/critique.md` 的全部前置条件和产物约束，包括运行时许可、两个隔离评估、先完成 Assessment A 再向汇总
上下文暴露 detector 结果、detector/browser 证据、报告 provenance 或降级标识、快照/趋势与最后的用户问题。

确有必要完整 critique 时，主 Agent 必须先记录原因、目标、两个只读评估任务、资源限制与汇总责任，并在 SDLC 协议
允许的层级内编排。复用已经取得的 sub-agent 或运行时许可，不重复索取；当前版本仍要求新的许可时再按其规则处理。
阶段子 Agent 不自行 fan out。能力不足或执行失败时，按当前 critique 参考明确标记降级和限制，不能伪称双评估或完整
报告。快照及其可能产生的受跟踪产物必须在 validation 基线前形成。

有限检查、失败处理与不收敛停止仍唯一遵循 `stage-agent-protocol.md`；本适配不增加 critique/polish 循环。
