# 测试与场景索引

本仓库的确定性测试与真实 Agent 场景可共享初始条件、允许的副作用和结果断言。可从三个维度区分检查：

| 维度 | 示例 | 说明 |
|---|---|---|
| 验证范围 | 函数、CLI/文件集成、组件、Agent 端到端 | 本次检查覆盖多大范围 |
| 执行方式 | 确定性脚本、人工参考操作、真实 Agent | 谁执行任务 |
| 目的 | 回归、候选与 baseline 的 benchmark 比较 | 检查约束还是比较结果 |

相同场景可用于回归和比较；直接调用代码或 CLI 的结果不能证明 Agent 的决策、独立验证或评审已经执行。记录实际被测快照、配置、命令和结果；未执行的内容标为 `NOT_RUN`。

## 当前入口

从仓库根目录运行快速检查：

```bash
bash scripts/validate-skills
git diff --check
```

前者检查结构、引用和协议文本，并运行五组 Python 测试：

- [lifecycle](../scripts/test_lifecycle_state.py)：状态转换、Git 版本、恢复及多 clone；
- [backlog](../scripts/test_backlog.py)：只读投影、看板和 HTML 转义；
- [共享场景](../scripts/test_scenarios.py)：六个初始仓库、参考操作及正确和错误结果断言；
- [contrast](../scripts/test_contrast_check.py)：颜色解析、对比度和 CLI；
- [Hallmark catalog](../scripts/test_hallmark_catalog.py)：目录、召回、同步及失败保护。

前两组共用 [临时 Git 仓库辅助函数](../scripts/test_support.py)，各自保留业务状态初始化。它们也可分别直接运行：

```bash
python3 scripts/test_lifecycle_state.py
python3 scripts/test_backlog.py
```

按需组件测试独立于快速检查：[Web Review Live](../skills/sdlc/references/web-review/test_live.py) 测试本地服务长轮询、并发和超时；当前会操作组件目录中的 feedback 文件，运行前应检查隔离和清理。[原型 shared-state](../skills/sdlc-prototype/assets/shared-state/runtime.test.cjs) 测试状态隔离、定时动作、取消和重置：

```bash
node --test skills/sdlc-prototype/assets/shared-state/runtime.test.cjs
```

这些检查不自动运行模型。结构检查和脚本不能代替对产品确认、语义变化、实际执行者身份及授权副作用的判断。

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
提供时，项目上下文列出 CLI 子进程的覆盖率命令、80% 行和 70% 分支阈值，以及仓库外的同级专属目录
`<scenario>-coverage`；数据文件和 JSON 报告存放在那里，需和仓库一同保留到检查结束。B03/B04A 的参考历史会实际
执行这些命令并记录结果；B04B 的历史缺口保留。未提供工具时，默认脚本测试仍只需标准库，历史状态只是模拟状态，
默认 correctness 所需覆盖率为 `NOT_RUN`，不能当作完整验证证据。

脚本参考执行本地 Git、lifecycle 操作和题目要求的 CLI 检查，不创建生产命令或 Agent 运行器。B01 参考确实运行整数及错误输入业务断言，
其 Validate/Review 转换由脚本执行，不代表独立 Agent。B02 断言状态与业务文件未推进，并允许更新澄清上下文；未决选择的语义须人工核对。B03 断言受控探针缺失、失败状态及
旧批准失效；B04A/B 限定只核对现有证据，分别断言旧状态保留或失效；B05 核对完整计划任务的 ID、标题、依赖及原有记录，且不执行 Build。
每题还执行错误状态与越界文件反例；B01 另验证仅状态交接提交仍适用，B05 特别检查即使 `next` 已为 Build，缺失任务也会被拒绝。

这些断言不解析 Markdown 语义，也不能证明提问质量、决定授权、证据语义覆盖、实际执行者身份或独立 Validate/Review；
真实 Agent 演练必须另留原生 transcript、执行者及命令证据并人工核对。

## 2026-11-08 真实 Agent 演练记录

本批次使用当前 Codex 会话的原生子 Agent，用户已授权全部六题，按题串行执行。源仓库基线为
`5809ae943391cf20c5b540df00751831e450a06a` 加本次未提交修改，不把基线提交本身当作被测完整快照。
被测规则包括本次 Review 收敛、风险选择、交付配置和回归规则修改；fixture 与断言来自本次
`scripts/test_scenarios.py`。未调用 `reference` 替代真实阶段执行。主 Agent 接受证据后，使用唯一的
`lifecycle_state.py --repo <fixture>` 执行子 Agent 返回的状态转换。

本地保留目录为 `/Users/arnow117/hansen_agent_team/workspace/20261108-sdlc-quality-rehearsal/`。
正式修订 fixture 位于其 `prepared/<case>/`，请求、项目事实、产品和工程证据分别在 `request.md`、
`.sdlc-v1/project.md` 与 `.sdlc-v1/context/`；覆盖率数据和 JSON 位于同级 `<case>-coverage/`。
原生执行者消息与工具输出保留在当前 Codex 对话中，未另建运行器、事件日志或生命周期状态。

| 场景 | 实际执行与主 Agent 核对结果 | fixture revision / 执行者 |
|---|---|---|
| B01 | Build、独立 Validate 和独立只读 Review 完成：2 项业务测试通过；正数、负数、零、非法输入、缺参数及多参数实际检查通过。独立 Validate 的行覆盖为 10/10，分支为 2/2，均 100%，超过 80%/70% 要求。Review 未发现可操作缺陷；主 Agent 接受证据并记录 reviewed，脚本断言与语义核对通过。Release 保持 pending。 | 初始 `9ffd38e0714bcf47f55c3b9a03b6540b179776a6`；实现及验证 `da853f10f43509c48206e2a5359230aed5172253`。`/root/rehearsal_b01_build`、`/root/rehearsal_b01_project_refresh`、`/root/rehearsal_b01_validate`、`/root/rehearsal_b01_review`。 |
| B02 | 执行者说明整数与小数输出的具体影响，建议与用户决定分开，产品选择保留 OPEN；Requirement 保持 captured，无 Feature、实现或业务文件变化。这是模拟请求的澄清结果，没有代替真实用户选择产品行为。脚本断言与主 Agent 语义核对通过。 | `d31161eecc6627d4c1bb942c01a09ba5bd2883c5`；`/root/rehearsal_b02_product`。 |
| B03 | 必要探针实际输出 missing、exit 2；单位测试 2 项通过，另行实测行覆盖 14/14（100%）、分支 3/4（75%）。环境缺口仍使必要重验不能通过，记录 ENV_BLOCKED；主 Agent 写 validation fail，旧 Review 恢复 pending，保留业务代码且不继续发布。脚本断言与归因核对通过。 | 修订 fixture `8b1a59a66cb11cc276bad4e9be676cd5bb433df4`；`/root/rehearsal_b03_validate`。 |
| B04A | 只读核对旧验证 commit 到当前 HEAD 仅有 `.sdlc-v1/**` 变化，业务、配置和义务不变；检查已有覆盖率数据，未重跑业务验证。主 Agent 追加适用性说明，保留原 state；不把历史脚本批准改称独立评审。脚本断言与证据核对通过。 | 验证 `4bcf7ed5b44fd434a9fac86c93d1077557b8777e`；HEAD `e8551b63c7c8f126991eb354e9f3099a37dc7de9`；`/root/rehearsal_b04a_evidence`。 |
| B04B | 实现含非法输入处理及测试，但旧历史只执行正常输入，覆盖率 NOT_RUN。执行者只读判断 INCONCLUSIVE，未把“有测试代码”当作“测试已执行”。主 Agent 写 validation fail，不填虚构 test-command；Review/Release 保持 pending，未执行新验证或改代码。脚本断言与语义核对通过。 | 历史验证 `cc1a96af15302d6624eb2fcbb08564f59c721f28`；HEAD `a19345574723e4c411b6f6abb0e0f1ef02fe22f6`；`/root/rehearsal_b04b_evidence`。 |
| B05 | 执行者对照已接受计划与 state，只请求补登记缺失的 TASK-two、TASK-three，保留依赖次序和已登记 TASK-one。主 Agent 执行两次 add-task 后任务集合完整，均为 todo，未执行 Build。脚本断言与恢复核对通过；单看 next 已为 Build 不代表登记完整。 | `7240a39223354d6d331a800246012f837d0d94ea`；`/root/rehearsal_b05_recovery`。 |

B03 首次运行保留在批次目录的 `B03/`，HEAD 为 `98e11a855b80d5638d952abe418e8f6eee69dca2`。
该次执行发现必要探针缺失，同时发现 fixture 未准备 correctness 覆盖率工具及用户用法说明。主 Agent 接受
validation fail 并通过断言；随后完善通用 fixture 准备，在全新 `prepared/B03/` 以完整替换 brief 重新执行。
首次结果保留为准备缺口证据，不计作模型错误，也不混入修订 fixture 的通过证据。B01 实现后另由 Onboard
执行者把项目入口事实从“尚不存在”刷新为“已存在”，仅改项目上下文，没有修改命令、阈值或业务代码。

实际业务检查命令为 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_cli`，必要环境探针及
四次带 coverage 的 CLI 命令、report/JSON 命令和各次退出状态均保存在对应工程上下文。非法输入和缺参数的
exit 2 是预期行为。覆盖率使用调用前已存在的 Python 3.12.13 / coverage.py 7.13.5，未安装依赖；普通
业务测试使用系统 Python 3.9.6。B04A/B04B 的历史批准由 fixture 准备脚本构造，不是历史独立 Agent 执行证据。
B04A 的旧 unit 原始输出没有单独归档，coverage 数据没有内嵌 Git revision，适用性结论仅限本地可核对范围。

本批次共九个题内执行者上下文（B01 四个、其余各一个），B03 在同一执行者中运行原始和修订 fixture。
Build/Validate 使用配置的 Terra worker，Review 使用配置的 Sol reviewer，产品与恢复分析使用默认主模型路由。
运行时未暴露可独立核验的实际后端模型/推理档位，因此不把配置标签当作实测模型元数据。
这是一轮有界功能演练，没有候选与旧模型的对照批次、统计成功率、成本或性能结论；未执行 Ship、推送或发布。

同日最终源码检查：`bash scripts/validate-skills` exit 0，结构、frontmatter、引用和可移植性检查通过；
40 lifecycle、7 backlog、5 scenario、36 contrast、12 Hallmark，共 100 个 unittest 方法通过。
`git diff --check` 通过。该检查使用本机 loopback 假 HTTP 服务，没有外网或模型请求。
