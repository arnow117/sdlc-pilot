---
name: sdlc-ship
description: >
  发布阶段。读取已评审 Feature、项目部署配置和对应 commit，执行部署前检查、发布、smoke、
  观测与必要回滚；成功后记录 released 状态。
---

# sdlc-ship — 发布已验证 Feature

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。ship Agent 准备发布和 smoke 证据；
按协议的[运行时选择](../sdlc/references/stage-agent-protocol.md#runtime-selection)读取所选适配并遵守配置的模型职责。
外部副作用及 `record-release`/`retract-release` 均由取得用户授权的主 Agent 执行；未授权时返回阻塞原因。协议允许把已经验收的源码交付/打包单元交给拥有明确写入范围的新最小上下文执行者；它不能取代原实现者完成未验收的实现或修正。

## 先恢复未决交付

恢复可能已执行或结果不明的交付时，先于下面的正常入口条件和任何部署、回滚或其他外部动作，
先按[阶段协议 §6](../sdlc/references/stage-agent-protocol.md#6-context-and-checkpoints)读取可用检查点，
定位待核对操作及证据；没有检查点时沿用该节的恢复路径。然后按
[阶段协议 §5 的发布前登记预检与中断去重](../sdlc/references/stage-agent-protocol.md#发布前登记预检与中断去重)
只读核对各操作记录、可取得的回执、目标实际版本与当前 Feature 状态；`next=ship`、`next=done`
或目标碰巧已有该版本都不证明此次动作尚未执行或已经成功。确认某一步已执行时不重发该步，先补
其欠缺的 smoke、验证或观察；若原计划还有明确约定且已授权的后续阶段，核对每段前置条件、目标
与授权，分别预检并记录后继续。全部必需阶段成功后才登记。结果不明或仍在执行时暂停该动作及其
依赖步骤。只有确认原动作未生效且不在执行，才在原授权仍适用时进入该动作的正常预检与流程。
登记回执丢失时，即使状态已是 `released`，也可对明确选中的 Feature 按此入口只读核对现行记录；
若登记已成功且结果完整，确认现有记录，不重复登记。已记录 `released` 但必要目标或 smoke
实际未完成时，按下方纠错流程处理，不把缺失结果写成通过。

## 入口条件

- Feature 状态为 `reviewed`。
- validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外无差异。
- 当前业务代码工作树干净；仅 `.sdlc-v1/**` 可以有待提交的发布记录。
- `.sdlc-v1/project.md` 已记录发布目标或用户明确给出目标；目标可以是明确
  约定的源码分发，也可以是环境部署。
- 生产发布、外部消息、数据删除等不可逆动作仍需获得用户明确授权。
- 对用户可见改动，读取 [`Global usage-document, story, and parameter contract`](../sdlc/references/lifecycles/software-delivery.md#11-global-usage-document-story-and-parameter-contract)，以所选目标版本的真实可用条件为准；本地 synthetic 结果不能替代部署、live 或真人试用要求。

## 流程

1. 读取 [`deployment-patterns.md`](../sdlc/references/deployment-patterns.md)。
2. 根据目标选择 `deploy-targets/static-site.md`、`container.md` 或 `vps.md`。目标卡中的结果
   写入步骤按[部署证据规则](../sdlc/references/deployment-patterns.md#9-状态与证据)执行；
   如果正文已绑定，使用既有稳定引用，不因目标卡的命令骨架直接追加绑定正文。
3. 确认构建产物、配置、密钥来源、数据变更和可执行回滚方案；产物版本使用 validation commit，不使用后续只含 SDLC 文件的 HEAD。
4. 确认当前 last-good commit 或产物版本及其已授权、可访问的记录位置。使用稳定引用时，
   引用须已在绑定正文中，或在候选获正式验证和评审前准备好；不得为发布中途记录结果而
   使已批准正文漂移。若无法保留可访问的证据及准确登记版本，暂停外部动作。
5. 以当前批准源和适用的正式验证及评审证据核对交付内容。发布前完成本目标明确约定的专项，例如按[覆盖率规则](../sdlc/references/validate-modes/correctness.md#5-覆盖率阈值)约定的大版本覆盖率。
   复用当前候选的适用证据。专项未通过时暂停该发布，保留仍适用的 Validate 和 Review 结论，其他已授权且无依赖的工作可继续。
6. 执行外部动作前，按[阶段协议 §5 的发布前登记预检与中断去重](../sdlc/references/stage-agent-protocol.md#发布前登记预检与中断去重)
   做只读预检：用实际仓库、worktree、登记分支、HEAD、`validation.commit` 和现有目标配置
   核对候选与身份，确认 Feature 为 `reviewed` 且拟交付 commit 与 `validation.commit` 相同，
   业务路径干净、全仓等价、state 和两个上下文已跟踪且无冲突、state 未暂存。预检不通过、
   证据存疑或实际目标不明时先暂停外部动作。执行前还须在可访问的既有证据记录中保存该操作的
   可核对标识、目标原版本、预期版本和回执查询入口，并保护候选、状态和绑定正文。
7. 预检通过且已取得所需授权后，按约定完成环境部署，或完成仓库、版本或制品交接，每一步使用
   可复现命令。源码分发在新解包的交付目录运行 health、smoke 和关键业务探测；部署在既有
   已授权目标核对本次实际版本后运行必要的 health/smoke。两者都观察约定指标，不把旧工作
   目录的通过结果当作本次交付 smoke，也不隐含新建环境、目标或外部授权。
8. 保存技术发布后观察记录：关联产品上下文的结果观察计划，记录技术发布准备、信号位置、实际观测
   结果、反馈证据和缺口。若正文已被依赖的验收点绑定，使用其中已有的稳定引用保存结果，不改变
   已绑定正文或现行候选；旧记录未绑定时仍须核对现有证据适用性。没有生产观测能力时记录技术原因、
   下次技术检查时间和缺口；不要重复产品指标或 Requirement 回流计划。
9. 失败时停止扩大范围。发布已产生副作用且需要恢复时，执行回滚，并在同一可访问记录保存结果。
10. 成功后由主 Agent 调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  record-release --feature-id <feature-id> --commit <validation-commit>
```

`--commit` 取实际交付并被验证的版本。`validation.commit=A` 而 HEAD 已因仅状态/上下文交接
变为 B 且全仓等价时，仍登记 A；在 B 重记 Validation 会改绑 B，不能事后把已交付的 A 填成 B。

如果历史记录把“合入主分支”或“发布准备完成”误写成 `released`，先将事实和原因保存到
Feature 工程上下文或其中已有的稳定证据引用，再由主 Agent 调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  retract-release --feature-id <feature-id> --reason <why-the-release-record-was-invalid>
```

该命令是纠错操作，不是失败发布的正常回滚路径；真实发布失败保持
`reviewed`，不调用 `record-release`。若纠错时必须修改已绑定正文，纠错后按指纹与证据适用性
规则处理受影响的 `stale` 点，不因纠错而默认为旧验证或评审重新获批。

## 完成输出

返回一份紧凑交付摘要：批准来源、内容核对、入口、实现版本（validation commit）、环境/产物版本、测试与 smoke、技术观测、产品观察计划引用、证据缺口、回滚状态和下一步。引用既有正式证据位置，不复制整段历史。分别标明最早增量、交付成立和全部请求完成所依据的实际证据；不把必要报告或检查移出已记录的经过时间。`record-release`
记录 validation commit 作为发布实现版本，且只记录成功发布；失败或只完成发布准备时保持原状态。
