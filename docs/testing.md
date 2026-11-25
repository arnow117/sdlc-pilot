# 测试与场景索引

维护插件时，从仓库根目录运行下面的检查，再按改动补充场景。查业务项目的验收流程，见 [Validate 阶段](../skills/sdlc-validate/SKILL.md)。

## 当前入口

从仓库根目录运行快速检查：

```bash
bash scripts/validate-skills
git diff --check
```

前者检查结构、引用和协议文本，并运行八组 Python 测试：

- [lifecycle](../scripts/test_lifecycle_state.py)：状态转换、Git 版本、恢复及多 clone；
- [backlog](../scripts/test_backlog.py)：只读投影、看板和 HTML 转义；
- [共享场景](../scripts/test_scenarios.py)：六个初始仓库、参考操作及正确和错误结果断言；按需人工验收、批准型重记与发布登记的可观察行为断言；
- [contrast](../scripts/test_contrast_check.py)：颜色解析、对比度和 CLI；
- [Hallmark catalog](../scripts/test_hallmark_catalog.py)：目录、召回、同步及失败保护。
- [vibe test 核心](../scripts/test_vibe_test.py)：离线 oracle、反例、合成报告、统计与路径保护；
- [vibe test host](../scripts/test_vibe_host.py)：受控回调、原生字段映射、预算及评分绑定的 stub 合同。
- [安全扫描依赖探针](../scripts/test_security_dependency.py)：隔离 PATH 中的缺失、候选和重名情况；检查不执行候选程序、不输出凭据，不能证明真实扫描或 Agent 提醒行为。

快速检查使用确定性脚本。需要核对 Agent 如何提问、委托或判断证据时，按下节选场景，并记录实际运行的配置和结果。离线对照测试使用合成输入和 stub；真实模型实验的准备条件见[对照测量指南](vibe-tests.md)。

修改原型运行时或审阅控制台时，从仓库根目录运行对应的 Node 测试：

```bash
node --test skills/sdlc-prototype/assets/shared-state/runtime.test.cjs
node --test skills/sdlc-prototype/assets/review-console/*.test.cjs
```

[Web Review Live 测试](../skills/sdlc/references/web-review/test_live.py)覆盖本地服务的长轮询、并发和超时。它在脚本所在目录写反馈和历史记录。将整个 `skills/sdlc/references/web-review/` 复制到临时目录，再运行副本中的 `test_live.py`，这样原目录的反馈记录会保留。

## 按改动选择检查与复用

维护 SDLC 自身时，先根据实际行为变化选择证据。默认快速检查仍是上面的 `validate-skills`；其中的场景脚本是确定性测试，
不自动启动真实 Agent。下表用于确定需要哪些功能演练或比较，不新增生命周期阶段、模型运行器或每次发布都要跑完六题的条件。

| 改动或发现 | 确定性检查与场景选择 |
|---|---|
| 错字、链接、排版，且行为含义未变 | 标准结构与引用检查；无须仅因文档修改发起模型运行。 |
| 项目级架构约束的集成、规范引用或阶段检查入口文字 | 标准结构与引用检查（含共享小节锚点防漏）；语义覆盖按 [项目级架构约束](../skills/sdlc/references/lifecycles/software-delivery.md#项目级架构约束)人工走查文档契约：沿用 B02 的未决选择边界与 B04A/B 的证据适用性边界核对场景路径。文档契约走查不证明真实 Agent 行为、真人确认、跨 Feature 采用或债务改善。 |
| lifecycle、backlog、共享测试 helper 或场景断言 | 标准检查及受影响的原生测试；场景断言改变时先检查参考和错误结果，不能直接沿用旧评分。 |
| 产品确认、委托或准备阶段的选择处理 | 选择 B02；影响正常交付推进时补 B01。 |
| 验证归因、旧通过失效、证据适用性或上下文交接 | 按影响选择 B03、B04A/B；修改复用判断时保留 B04A/B 成对比较，兼顾漏验与不必要重跑。按需人工验收、批准型重记独占与读回、发布登记预检或中断去重变更时，另跑[按需人工验收、批准型重记与发布登记变体](#按需人工验收批准型重记与发布登记变体)。 |
| 主流程、必要边界和覆盖率规则 | 标准检查与规则走查。按 B01 检查行为和回归通过且未约定数值时的验收，按 B04B 检查主流程通过但缺少必要边界证据时的判定。再核对明确要求覆盖率的发布在未达标时保持未发布。 |
| 安全扫描接入或依赖提醒 | 运行标准检查中的依赖探针测试，人工核对风险选择、未运行归因、原生产物与 review 复用；真实扫描与 Agent 提醒需各自的实际执行证据。 |
| T3 阶段派发、进一步派工、等待或局部停止合同 | 标准检查覆盖共享边界引用、缺失或错误锚点及旧无条件禁令反例；B03 检查 fail 撤销旧批准与拒绝时状态保留，B05 检查部分登记恢复。逐例人工走查授权、逐层结果、模型证据、Desktop 静态兼容、独立检查与停止动作；这些不证明 live 多层 child、取消、恢复、native 或资源释放。真实运行与独立接受另需相应证据。 |
| 准备批次、部分成功或恢复登记 | 选择 B05；影响完整链路时补 B01。 |
| 独立评审、集成或实际交付配置 | B01 可检查基础交付；多端兼容、并发、返修 delta 和 feature flags 等风险仍需相应原生测试或有界专项，不能把六题通过外推为全部覆盖。 |
| 更换模型、通用工具权限或整体编排 | 对实际受影响能力选择代表集；整体路径改变时以六题为起点。只改配置标签而未实跑，记录 NOT_RUN，不宣称性能改善。 |
| 实战出现可复现缺陷 | 优先增加最小原生回归、反例或既有场景变体；只有需要评价 Agent 判断时才安排真实执行。 |

选定真实 Agent 批次后，先固定任务、初始 fixture、规则和实现快照、模型/推理配置、工具权限、环境与预算；列出次数、并发、
成本或额度范围、停止方式及证据保存位置，遵循已有授权。已覆盖同一批次的授权不重复询问；新的批次不能从旧记录推断授权。
这项选择随相关改动进行，不按时间自动触发，也不为普通业务 Feature 重跑 SDLC 的整套演练。

复用证据前，核对被测代码、配置、环境、当前义务、场景及断言是否仍适用。仅提交 SHA、发布版本号或不影响行为的说明变化，
不自动使证据失效；任一相关输入改变时补受影响的检查。实际阶段要求的独立 Validate/Review 仍按原协议执行。
先前失败、缺失或无法核对的证据不能按“复用”记为通过；局部覆盖和原始 fixture 的准备缺口须保留在结论中。

真实执行逐题记录结果、适用限制和可取得的实际命令、版本及执行者信息，语义项按后文说明人工核对。
一轮六题功能演练不能替代效率 benchmark：比较质量、耗时或 token 时，应在固定条件下重复运行，逐题列出退步和严重失败，
并区分有效任务失败与非预期环境故障。没有完整耗时、用量或实际后端模型元数据时，明确未测，不从配置标签或脚本结果估算。

### 从使用路径追溯验收依据

变更涉及下列使用路径时，从用户能找到的操作说明出发，再对照对应的故事、参数与验收条件。

| 使用路径 | 维护者核对的依据 |
|---|---|
| [T3 阶段派工](../skills/sdlc/references/runtime-adapters/t3-code.md) | [SCN-t3-stage-dispatch](../.sdlc-v1/context/REQ-t3-stage-dispatch.product.md) · [SCN-t3-nested-delegation](../.sdlc-v1/context/REQ-t3-nested-delegation.product.md) |
| [交给真人验收](../skills/sdlc-validate/SKILL.md#验收归属与真人交接) | [SCN-human-validation](../.sdlc-v1/context/REQ-human-validation.product.md) |
| [安全扫描](../skills/sdlc/references/validate-modes/security-scan.md) | [SCN-security-scan](../.sdlc-v1/context/REQ-security-scan.product.md) |
| [首次设计或迭代原型](../skills/sdlc-prototype/SKILL.md) | [SCN-sdlc-prototype](../.sdlc-v1/context/REQ-bundled-prototype.product.md) |
| [修正分支登记](../skills/sdlc/references/lightweight-runtime.md#51-开发分支登记迁移) | [SCN-branch-registration](../.sdlc-v1/context/REQ-branch-registration.product.md) |
| 建立、引用或修订项目架构规范 | [SCN-project-architecture](../skills/sdlc/references/lifecycles/software-delivery.md#项目级架构约束) |
| 比较技能和上下文对结果的影响 | [SCN-vibe-test](vibe-tests.md#acceptance-coverage) |

## 首批共享场景契约

以下是五个能力族、六个共享场景；各有可复现的初始仓库、任务请求、允许修改范围、独立结果断言和代表性反例。场景规则引用 [阶段协议](../skills/sdlc/references/stage-agent-protocol.md) 与 [Validate 归因规则](../skills/sdlc-validate/SKILL.md)，不另建生产规则。表中列出自动断言的范围；2026-11-08 的真实 Agent 执行与人工语义核对记录见后文。

| 场景 | 初始条件与可观察结果 | 当前证据与缺口 |
|---|---|---|
| B01 小型交付 | 已确认范围的单模块 Python CLI 功能从不存在推进至可用代码和 `reviewed`；必要检查实际通过，独立 Validate/Review 有执行者证据，代码、状态和版本一致。 | [小项目示例](../examples/small-project-context.md) 是假设且 NOT_RUN；`LifecycleStateTest.test_next_routes_the_full_single_feature_lifecycle`（[源码](../scripts/test_lifecycle_state.py)）只测试状态路由。实际执行还须核对各阶段身份、验证证据及当前版本。 |
| B02 未决产品选择 | 影响产品行为的选择仍 open；用户仅说“继续”，且未委托选择。提出具体问题及影响，保持 open，不推进依赖工作；可继续无依赖工作。 | [示例的确认与委托](../examples/small-project-context.md) 为书面设计；脚本检查状态和业务文件未推进，允许记录澄清；需人工核对提问、选择是否仍 open 及决定来源。 |
| B03 必要重验受环境阻塞 | 未发布 Feature 曾通过验证；必要重验遇到受控且可证实的环境缺口，且状态写入前提成立。记录环境证据及 `ENV_BLOCKED`，通过既有 CLI 记录 validation fail 使旧通过失效；不盲改业务实现，不继续 Review/Ship。 | [Validate 规则](../skills/sdlc-validate/SKILL.md)定义归因与失效；现有验证前提代码测试不覆盖此完整场景。脚本检查受控缺口、失效状态及代码保留；实际归因仍需人工核对。 |
| B04A 证据仍适用 | 实现、配置、环境和要求不变，仅补充 `.sdlc-v1` 证据说明，原证据完整可访问。说明适用依据并保留引用；不因 HEAD 改变就要求重验。 | `LifecycleStateTest.test_product_to_release_allows_state_only_handoff_commits`（[源码](../scripts/test_lifecycle_state.py)）覆盖状态交接的一部分；[演练](agent-orchestration-rehearsal.md)区分实际 CLI fixture 和书面情景。脚本检查证据状态保留；语义判断及实际重跑次数需人工核对。 |
| B04B 新义务缺证据 | 业务 commit 未变，但合法确认的新要求或义务未被旧验证覆盖。指出具体缺口和必要下一步；在适用规划、实现和验证条件满足前不批准 Review/Ship。 | [阶段协议的证据适用性](../skills/sdlc/references/stage-agent-protocol.md#context-prose-and-evidence-applicability)要求语义判断；CLI 不解析上下文。本题限定只核对已有证据、不执行新增验证；脚本检查旧批准被撤销，语义覆盖需人工核对。实际范围变更涉及 ready/in-delivery Requirement 时创建带依赖的后续 Requirement；其他义务变化按当前协议处理。 |
| B05 部分登记恢复 | 准备批次中断，Requirement、Feature 及部分 Task 已成功登记，部分回执不完整。核对 state、工程计划与 Git，补齐计划中所有 Task 后停在可开始 Build；不重复登记、漏项、提前验证或实施业务代码。 | [准备批次恢复协议](../skills/sdlc/references/stage-agent-protocol.md#bounded-preparation-batch-for-small-projects)定义核对方式；现有状态构造仅提供基础，脚本检查完整 Task 集合、依赖、原计划和未实施状态。 |

每题已用脚本参考操作和代表性错误结果检验断言；交互和独立执行等 Agent 专有证据需另行核对。模型参与的 benchmark 批次应先准备具体运行范围、配置和成本，并遵循现有授权规则；已有授权覆盖该批次时无需重复请求。实际运行需保留证据，现有示例和 fixture 不是 Agent baseline。


## 手动准备与检查场景

从仓库根目录启动 `PYTHONPATH=scripts python3`，在同一个 Python 会话中执行下列操作：

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from test_scenarios import prepare, reference, assert_result

temporary = TemporaryDirectory()
repo = Path(temporary.name) / "scenario"
initial = prepare(repo, "B04A")  # 也可选 B01、B02、B03、B04B、B05
print(repo, (repo / "request.md").read_text())
reference(repo, "B04A")  # 仅用于脚本参考；Agent 演练时由 Agent 操作，省略此行
assert_result(unittest.TestCase(), repo, "B04A", initial)
```

`prepare` 需要不存在的目标目录，返回原始状态和内容快照；保留会话与 `temporary` 直到检查结束。实际 Agent 演练应把
打印的初始仓库和请求交给受控执行者，再回到同一会话运行 `assert_result`；手动检查结束后可调用 `temporary.cleanup()`。
初始仓库的 `.sdlc-v1/project.md` 随 Git 跟踪，记录实际检出分支、Python 标准库 CLI、现有业务测试命令、
`qa`/`correctness` surface 和无发布目标；项目事实不表示当前实现已经通过测试。B03 还记录必要环境探针的命令与存在条件；
B04B 的工程上下文保留已确认产品范围并指出历史验证证据缺口，本题只核查证据。
初始 README 记录 CLI 的用户故事、参数来源、用法和错误行为；B02 的输出格式仍未决。

`prepare` 可接受 `coverage_python=Path(...)`，指向调用者已有、安装了 coverage 的 Python；不会安装依赖。
提供时，题目为该项目明确要求 CLI 子进程的行覆盖率 80% 和分支覆盖率 70%，并给出命令及仓库外的同级专属目录
`<scenario>-coverage`；数据文件和 JSON 报告存放在那里，需和仓库一同保留到检查结束。B03/B04A 的参考历史会实际
执行这些命令并记录结果；B04B 的历史缺口保留。未提供工具时，题目无数值覆盖率要求，默认脚本测试仍只需标准库。
脚本生成的历史状态用于检查生命周期转换。真实 Agent 的验收和评审需单独取得实际证据。

B01 的真人等待试次可在 Agent 交接后调用 `assert_human_wait(unittest.TestCase(), repo)`：它检查
Task 已完成、候选 commit 可定位、业务工作树干净且验证、评审和发布仍为 pending。该断言不创建
真人答复，也不验证是否正确提问或复用了证据；这些仍须核对实际轨迹。

脚本参考执行本地 Git、lifecycle 操作和题目要求的 CLI 检查，不创建生产命令或 Agent 运行器。B01 脚本参考仅用于没有覆盖率阈值的 fixture，
实际运行整数及错误输入业务断言，Validate/Review 转换由脚本执行。B02 断言状态与业务文件未推进，并允许更新澄清上下文；未决选择的语义须人工核对。B03 断言受控探针缺失、失败状态及
旧批准失效；B04A/B 限定只核对现有证据，分别断言旧状态保留或失效；B05 核对完整计划任务的 ID、标题、依赖及原有记录，且不执行 Build。
每题还执行错误状态与越界文件反例；B01 另验证仅状态交接提交仍适用，B05 特别检查即使 `next` 已为 Build，缺失任务也会被拒绝。

这些断言不解析 Markdown 语义，也不能证明提问质量、决定授权、证据语义覆盖、实际执行者身份或独立 Validate/Review；
真实 Agent 演练必须另留原生 transcript、执行者及命令证据并人工核对。

## 按需人工验收、批准型重记与发布登记变体

`scripts/test_scenarios.py` 中的 `HumanAcceptanceTest` 在一次性临时 Git 仓库里，用同一组
`prepare_human` / `human_complete_task` / `human_pass_and_review` fixture 断言原 CLI 的可观察行为。
这些变体只断言状态、指纹、退出码和错误码，不解析 Markdown 语义，也不模拟 Agent 的提问或等待。

| 变体 | 实际检查 | 当前证据与缺口 |
|---|---|---|
| 首次等待 | Task 完成后 `validation.result`、`review.decision`、`release.status` 均为 `pending`，`next` 为 `validate`；连续查询不写 state；未记录的验收点为 `missing` | 断言 CLI 的 pending 语义。是否真的问了人、是否只问一次、是否在等待时催问，须由真实 Agent 试次核对。 |
| 已知失败后重开 | 真实 CLI 测试失败并记录 `fail`，重开和修复后 `validation`/`review`/`release` 回到 `pending`，旧失败可从 Git 读取，修复前后的 CLI 内容不同 | 断言重开及历史候选的机械事实。失败与修复的归因仍须人工核对。 |
| 已知通过后重开 | 旧 `pass` 不从历史恢复，重开后仍为 `pending` | 断言当前候选需重新验证。语义覆盖判断须人工核对。 |
| 历史不完整 | 未提交的 `pass` 在重开后既不在当前投影也不在 Git 提交中 | 断言首次资格未知时的可观察事实。不能证明 Agent 会据此报告而非按首次处理。 |
| 旧通过必要重验 | 缺证据时记录 `fail` 使旧 `pass`、`review` 快照同时失效，Feature 回到 `in_progress` | 断言失效顺序。归因措辞须人工核对。 |
| 重验记录被拒 | 脏工作树下 `record-validation --result fail` 被拒，state 与业务文件逐字节不变，旧 `approved` 仍在 | 断言拒绝后的持久状态。停止该 Feature 调度是 Agent 行为，须人工核对。 |
| 核准映射竞争 | 调用前插入实质产品条件后，CLI 仍返回 `match`，但已核准摘要与新绑定摘要不同 | 证明 CLI 的 `match` 不能替代与事先核准值的比较。独占获取与读回比较由 Agent 执行，须人工核对。 |
| 拒绝优先 | 追加工程记录使 validation 指纹 `stale` 时，`record-review --decision changes_requested` 仍成功；旧评审快照消失、Release 保持 `pending`、`validation.result` 仍为 `pass` | 断言拒绝路径不依赖指纹新鲜。脏候选下同一命令被拒且 state 不变，另有一例反例。 |
| 同仓双 Feature | 一个 Feature 的未提交业务变更使另一个 Feature 的正式写入被拒；业务 commit 落地后 Review/Release 以 commit 不等价被拒，原记录不变 | 断言 clean-worktree 与 commit 等价前置。多 Feature 各自判据、覆盖与集成缺口属于 Agent 语义。 |
| state 已暂存 | 业务路径干净但 state 已暂存时，`record-release` 以 `state-is-staged-commit-or-unstage-before-update` 被拒，前后状态不变 | 断言暂存前置。 |
| 状态交接后登记 | 仅状态交接使 HEAD 前移，保持绑定正文不变；从 A 的归档实际运行 CLI，`record-release --commit A` 仍登记 A。把 Validation 改绑到 B 后再登记 A 被拒且无发布记录 | 断言本地制品来源、smoke 和登记版本一致。真实部署未发生。 |
| 部署中断 | 本地一次性目标目录记录已应用版本；回执无法对应时不重复应用，对应后只补登记，应用次数保持 1 | 仅模拟投递计数，不访问真实环境，不能证明真实部署幂等或回执查询可用。 |
| 迁移后 refresh | 分支迁移后用历史 branch 重记返回 `feature-identity-mismatch`，用新登记值成功 | 断言身份参数与登记一致。授权来源是否可追溯须人工核对。 |
| Spec 选择器 | Requirement 选择器查 `spec_ready` 返回 `match`；未登记 Feature 返回 `feature-not-found`；Requirement 查 `plan` 返回 `invalid-acceptance-point`；查询不写 state 或上下文 | 断言选择器与只读性。 |

这些变体证明 CLI 的机械边界和状态后果，不能证明 Agent 是否按协议提问、等待、交接、取得独占或
执行读回比较；真实 Agent 演练和正式独立 Validate/Review 仍需各自的实际证据。部署变体使用可丢弃的
本地临时目录，不执行真实发布。

## 2026-11-08 真实 Agent 演练记录

[六个共享场景的结果、配置和证据范围](history/agent-runs-2026-11.md#2026-11-08-真实-agent-演练记录)。

## T3 Code MCP 有界实测记录（历史 top-level Scratch，非当前 child 合同）

[2026-11-10 Scratch 线程实测与限制](history/agent-runs-2026-11.md#t3-code-mcp-有界实测记录历史-top-level-scratch非当前-child-合同)。
