# 2026 年 11 月 Agent 演练记录

以下记录对应当时的工具、权限和 fixture。当前仓库的测试命令及选用条件见[测试指南](../testing.md)。

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

## T3 Code MCP 有界实测记录（历史 top-level Scratch，非当前 child 合同）

2026-11-10 使用 T3 Code 0.1.8 与已连接的原生 MCP/OAuth，按授权在 Scratch 启动空闲线程，显式选择 Claude provider 实例、目录模型 `glm-5.3-flash[1M]`、low effort 和 `auto-accept-edits`。核对绑定后发送一次任务：读取输入中的 31 和 11，只写 `result.txt`，内容为 42 和一个行末换行。该 run 约 11.4 秒完成；活动记录包含实际 Read 与结果文件创建 diff（T3 将 Write 归一化为 `file_change`），输入 hash 未变，没有其他新增 artifact。settle 回执仅包含 sequence；后续线程读取显示 `settled=true`、`activeRunId=null`，该任务的 Claude 进程退出，共享 T3 服务仍运行。配置或报告的 GLM 标识不构成 Anthropic 模型身份认证。

该证据覆盖一次 Scratch 的启动、发送、等待、文件核对和完成后资源回收；不覆盖仓库项目注册、真实阶段验收、独立 Validate/Review、主动运行中取消、传输丢失恢复或模型身份认证。项目注册在该权限级别返回 `capability_denied`；不通过提升权限绕过。不得将此一次实测外推为其他环境的可用性或性能保证。必要时按当前授权和环境另行验证，不把历史记录当作当前版本的自动测试。
