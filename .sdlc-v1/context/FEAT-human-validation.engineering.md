# 工程上下文 · FEAT-human-validation 按需人工验收与自主推进

## 当前有效方案

### 架构设计

- **关联产品上下文** [REQ-human-validation.product.md](REQ-human-validation.product.md)
- **工程上下文** `.sdlc-v1/context/FEAT-human-validation.engineering.md`
- **已确认需求** `REQ-human-validation` 的 confirmed 条目及 SCN-01–12，实施授权见产品确认日志及 2026-11-20 编排约定。
- **创建日期** 2026-11-20
- **状态** 待主 Agent 验收

#### 背景

让 SDLC 使用者用自然请求规划、交付和续接。交付目标是已授权工作能自行推进，适用证据只核对一次，确需真人时交接可操作候选并准确恢复。长期方向来自已确认的 NEED-001/002 与目标仓库的维护契约，结果观察以产品上下文为准。外部 PLAN 提供卡片和场景候选，本方案以实际源码与产品上下文确定范围。文本原型复用当前对话及现有验证记录。涉及的 UI 是消费项目可能验证的对象，本 Feature 的实际表面是 SDLC 对话和既有 CLI。[产品规格](REQ-human-validation.product.md) · [维护契约](../../AGENTS.md)

#### 架构与组件

##### 阶段编排

- **职责** 主 Agent 区分只读状态、仅规划、已授权实施及需另外授权的外部动作。计划接受后先核对完整 Task、依赖、版本和写入者，再按当前授权行动。仅规划交回计划，登记权仍以该次 brief 为准。可一起判断的实质问题集中交给各责任人，每项有独立答复与影响，复杂或相互依赖的选择可逐题。保留显式暂停、宿主等待、独立阶段和 §5 非收敛规则，强制停止的升级仍指向一个具体决定。状态查询依据所选 Feature 投影和相关工程记录，保持只读；续接按 §6 先定位可用 checkpoint，再核对实际现场。展示实际阶段、候选、已查、待项、责任和下一动作，只有当前宿主证据能证明仍在执行。
- **接口** 现有 router 的入口及恢复引用落到共享协议，由协议定义上述行为。多个活动项保留选择及各自分支、Task 和写入者；等待期间继续独立且已授权的工作，候选变化则重新核对适用性。沿用现有阶段结果、授权和证据承载。
- **覆盖** REQ-001、003、005。[共享协议](../../skills/sdlc/references/stage-agent-protocol.md) · [恢复入口](../../skills/sdlc/SKILL.md#5-恢复与交接)

##### 验证与候选交接

- **职责** Plan 按验收条件记录 Agent 能可靠检查的判据，或具体的真人义务、观察者及前提，简单项允许引用已有判据。真人义务来自明确请求、已确认条件或可说明的不可替代观察。客观 UI 判据可由实际运行或可靠检查证明，缺环境或证据按验证缺口处理。用户主动试用可以收集意见，正式义务以当前约定为准。
- **接口** Build 可提供标明实际身份的早期候选。Validate 的必要人工交接复用对话和工程验证记录，包含旅程/Feature、入口、版本或快照、步骤与预期、已查与缺口、观察者及具体反馈。先预检并固定候选或隔离修改，无法固定时说明证据影响。按既有反馈纪律逐项核实、关联、处理，职责内修正后只补受影响检查。独立 Validate 对最终候选核对所有必要条件；早期或模拟结果仅提供实际覆盖的证据。
- **覆盖** REQ-001–005。[Validate](../../skills/sdlc-validate/SKILL.md) · [反馈处理](../../skills/sdlc/references/receiving-feedback.md)

##### Git 与生命周期记录

- **职责** Markdown 保存设计、证据和批准来源，Git 提供版本及历史，v3 `state.json` 保存机器进度及现有指纹。调用方向为 Agent 读取上下文与证据、以既有 CLI 查询并由主 Agent 写状态、再读取实际结果。CLI 执行现有 Git/状态前置条件和机械指纹检查。阶段技能链接共享规则。验证、评审、发布各用自己的适用证据。
- **接口** README 是用户导航入口。添加稳定全局故事入口 `SCN-human-validation`，链接已确认的故事和场景，示例覆盖仅规划、授权交付、交接、状态及恢复。所选 Feature、验收及观察者来源为当前上下文和已授权角色，候选、分支、HEAD 来自投影和 Git，CLI 参数由原 CLI 和运行时指南负责。缺失或不明结果给出现有恢复路径。正式使用验证从该入口按下文选择代表性请求。
- **覆盖** REQ-003–007。[README 状态命令](../../README.md#状态命令) · [全局用法约定](../../skills/sdlc/references/lifecycles/software-delivery.md#11-global-usage-document-story-and-parameter-contract)

#### 关键设计决定

##### 决定 1 · 用现有验证状态区分首次、重验与历史不足

**选择** 对满足正式候选和 Task 前提、必要机器检查实际通过、仅待约定者观察或答复的情况，先从当前投影及可访问的正式记录、Git 和交接证据核对历史。集中交接一次，工程记录注明候选、待项、观察人和接续动作，返回 `incomplete` 与 `requested_transitions: []`。同一候选、判据和责任人未变时，沉默、普通等待超时、泛化“继续”、模拟和客观检查通过都不会填补真人证据，也不触发重复询问或重跑。

- **已核实首次** 从未有过正式验证结果时，适用 REQ-003 / SCN-05，沿用 `validation.result=pending`。
- **已知历史的重开候选** Task 重开可清除 validation/review 记录及指纹。若已知上一候选有正式 fail，已修复且当前候选仅待约定真人，就保留原失败及修复证据，说明当前新候选仍在验收，沿用此时 CLI 的 `pending`，保留失败候选和修复后候选的区分。若已知之前通过而重开清除了结果，按新候选完成必要重验，当前 pass 不从历史恢复。两种情况都不能按首次报告，也不因普通等待写入新的 fail。
- **历史不完整** 未提交的 pass 在重开并 done 后可能不见于 Git 或当前投影。此时首次资格未知，明确没有当前可用 pass，只暂停依赖该结论的动作，等待足够真实证据或权限。当前候选的已知失败、环境阻塞或实际结案仍缺证据仍须处置。

任一分支一旦发生明确人工拒绝、本轮验证实际结束仍缺必要证据或必要检查失败/环境阻塞，按实际原因请求 `record-validation --result fail`。只为实际执行过的检查填 `--test-command`。已有仍在状态中生效的 pass，必要重验遇到缺证或未通过时须先使旧 pass 及下游批准失效，阻止 Review/Ship。状态写入被拒时保留证据并停止该 Feature 的后续调度，结果不明先读回实际状态。已 released 沿用维护或误记录纠正流程。

获得适用真人答复后按 §5 核对候选、环境、判据、授权、原独立执行事实及必要检查的覆盖。跨会话可复用仍适用的命令、结果和版本，仅补因变化或缺证而必要的检查。`build-loop.md` 的完成及停止规则都引用此处的证据适用性，保留独立 Validate 和 Review 的实际义务。正式通过须有全部必要证据。

**取舍** 本次交付使用 Agent 协议约束、Git、Markdown 和标准库测试。引入外部审批服务或 CLI 人工状态会新增身份、迁移和同步义务，超出 CON-001/002 与当前维护契约。裸 `next` 继续给出 `validate` 等既有阶段，裸 CLI 或绕过 Agent 的调用者没有人工检查的语义执法。受支持变体为同一 v3 schema 下的自主验证、真人观察及原约定续接。当前项目已有相应运行时和场景工具，外部依赖与更广调研无实际缺口。

##### 决定 2 · 先证明适用性与权限，再按依赖顺序重记

1. 按验收点选择唯一有效选择器。Feature 尚未登记时，用 `verify-acceptance --requirement-id <REQ> --point spec_ready` 核对 Spec；只有登记后才可用 `verify-acceptance --feature-id <FEAT> --point spec_ready` 通过其投影核对关联 Requirement。其余 `plan`、`validation`、`review` 点使用已登记的 `--feature-id`。`match` 只证明内容指纹一致，`missing` 说明未绑定并按旧约定判断，二者都要核实实际证据与权限。`stale` 暂停依赖动作，记录绑定路径和差异原因。审批身份或证据的归属须另核对。
2. 对仅追加证据的主张，在实际接受各验收点时保留可访问的原批准正文引用。优先使用已获 Git 授权的 `commit:path`、同一验收点的既有结果或原有证据中的可访问版本。续接时按保存的指纹、文件绑定集合和 `context-v1` 核对每份必要原文。可从 `git show <approved-commit>:<bound-path>` 取得原始字节，在只读核对中用既有 `_context_digest` 计算并比较 `expected_digest`，保留旧正文引用及比较结果。避免通过当前 HEAD 猜测批准正文，避免用普通文件 SHA-256 代替归一化算法。原文不可取、指纹不符、授权来历不明或存在实质变更时保留缺口，按原范围变更或补验流程处理受影响动作；已触发必要重验时按决定 1 处理失效。
3. 对通过上述核对的证据添加，逐点比较正文差异、审批对象、判据、版本、相关环境及原批准权限。记录原责任人、委托来源和允许其重记的具体点及变动范围、当前复核责任人与结果。原批准责任人可显式重记，主 Agent 可按其已有且可证明的委托履行职责；旧批准人保留该决定时由其明确批准。新 Plan 可将既有 Plan 验收职权内的纯证据追加复核写入接受记录，明确只覆盖 `plan` 的当前绑定内容和同一产品/设计契约。该限定不转授产品批准、真人观察、独立验证、评审或发布授权。普通继续或 Git 同步不会产生委托。正文与批准引用用于核对，原答复仍归原观察者。
4. **固定本次核准对象并交接写入**。主 Agent 在核准当前正文前识别产品/工程文件、绑定引用、候选工作树/HEAD 与状态的实际写者。通过既有写者交接确认其他执行者或外部协作者停止写入，或使用经授权、版本和状态正确关联、可确认独占的隔离候选。从核准当前正文到命令后读回，保持同一受控写者、绑定引用及候选，暂停受影响路径的其他写入。每个重记都按该顺序操作，期间出现新写入须重新审核。仅看到 HEAD 或 `git status` 一致、state 文件加锁、子 Agent 无输出，均不足以证明独占。共享路径或活动写者无法排除时暂停重记，保留证据并等现有交接条件成立。
5. **核准、落盘及读回逐项核对**。主 Agent 先固定已审阅的验收点、原快照及当前预期映射（每个绑定路径及其 `context-v1` digest）、Feature/Requirement 投影身份、实际 worktree、HEAD、与本次相关的验证或拟交付 commit。用本决定第 1 项的有效查询取得结构化 `files`，用现有归一化函数核对内容。任何依赖此映射的批准型重记调用前，按下文持久保存并本机读回核准记录，独占下紧邻 CLI 再核对实际值。调用后读回 Feature/Requirement 投影与相应 `verify-acceptance`，逐项比较已保存的路径集合、`expected_digest`、`current_digest`、绑定身份及相关候选。`match` 仅表示已存内容等于这次查询读到的内容，不能替代与事先核准值的比较。若事先比对失败则不调用。读回不符、结果不明或丢失独占时，立即停止依赖该记录的 Validate/Review/Ship 动作，保留原快照、核准映射、实际回执和版本差异，按下文从检查点和原记录重建核准对象，再核对实际状态并在授权内修正。不得自动重试、重签现存内容、回滚他人文件或仅凭后续 `match` 恢复。CLI 的 state 锁和内部多次读取没有提供跨核准与写入的原子 compare-and-swap。
6. **按验收点重记并区分评审结果**。仅追加适用证据须集中文字写入。`spec_ready`/`plan` 用已有 `--refresh-acceptance`。Plan 的 `--requirement-id`、`--feature-id`、`--branch`、`--engineering-context-ref` 取当前指定 Feature projection 的已登记身份，产品路径也从当前 Requirement 核对。已有迁移从 `main` 到 `feature/fix` 时传新登记值，原批准正文与授权仍追溯至原点。当前登记或 worktree 不一致按既有迁移规则处理，不自动 checkout 或变更 branch。`validation`/`review` 用现有 `record-*`。拟批准 Review 时，若写入评审结论使验证指纹漂移，先证明覆盖与授权，处理所需验收点并按 validation → review 顺序恢复。`record-validation` 会清旧 Review 和 Release。只可根据实际独立评审证据和适用权限恢复原决定、评审人和候选覆盖，否则需补评审。重记 Validation 的 `--commit` 只能等于当前 HEAD。优先在原实现 HEAD 上完成，若 HEAD 已变，先按 §5 证明候选等价并保留实际执行的原 commit、命令和环境，否则重验。给新 HEAD 绑定时据实说明复用，保留旧测试版本。
7. **有必须修复发现时优先拒绝**。已有 `reviewed` 时，新的实际必须修复项可以先保存在工程评审记录。即使写该记录使 validation 指纹 `stale`，只要 Git 前提满足且具相应评审权限，先记 `record-review --decision changes_requested`，撤销旧评审和其快照，Release 维持 pending。该操作不会清掉 `validation.result=pass` 或补签其指纹，发现仍按 Build、Validate、Review 正常修复和重验。拒绝路径不从 stale validation 继承通过，也不等待原验证者上线；Review 的通过路径仍要求适用验证。CLI 前提不满足或拒绝写入时，保存已确认的阻塞发现并停止该 Feature 后续调度，旧 approved 不可用于发布。只读核对实际状态后处理阻塞。
**覆盖** REQ-003、005–007。[指纹与现有查询](../../skills/sdlc/references/lightweight-runtime.md#71-验收内容指纹核对) · [语义适用性](../../skills/sdlc/references/stage-agent-protocol.md#context-prose-and-evidence-applicability)

###### 批准型重记的中断检查点

- 扩展 §6 的现有检查点触发时机，仅为可能改写批准指纹、且恢复必须比对核准映射的重记预先保存恢复信息。普通查询、正常等待和常规状态推进沿用原触发条件。主 Agent 独占写 `.sdlc-v1/checkpoints/<feature-id>.md`，保存后从磁盘读回确认可用，再调用 CLI。一个 Feature 一个文件、既有五节和 60 行限制全部保留。原位追加简要条目，不覆盖既有未完成事项；无法在限制内无损保存时暂停该次重记。
- 在「定位」记录实际工作树、branch、HEAD、Requirement/Feature 身份和必要 Task。在「已确认」记录核准的验收点、路径集合及每个路径的 `context-v1` digest、相关 validation/交付 commit。在「未完成」标记待执行或结果仍待核对的重记及顺序，保留待恢复的旧 Review。「下一步」给出对应操作和读回条件。「必要引用」定位原快照、原批准正文、权限，以及实际旧评审的决定、reviewer 和证据。只存必要的脱敏引用。若 `spec_ready` 重记发生在登记前，只使用现有 brief 已固定的 Feature ID 定位同一检查点，明确其未登记并保存实际 Requirement 投影；CLI 仍用 Requirement 选择器。没有可定位的选定 ID 时，先按既有选择流程固定目标再重记。
- 恢复先定位未完成重记及事先核准映射，再取得写者独占并查询实际状态、正文、引用及 Git。与保存的核准值和原快照比对每个路径及对应点。若已写入且一致，确认结果，不重复调用；若 validation 已重记且清掉 Review，核对原评审、覆盖和权限后只处理仍待完成的 Review。若确认原记录从未改变且重记未发生，重新核对候选、权限和独占后才执行该原动作。任何不一致、缺 checkpoint/原记录、未知的写入结果或缺权限都停止依赖该结论，直到现有恢复流程取得充分证据。已知或疑似有未核对的批准重记时不能按普通 `match` 继续。处理成功后只清理或更新本次条目，保留其他未完成事项，文件按原规则清理。
- 换环境或 clone 只复用已经获授权同步并且当场可读的检查点、原文和证据引用。依赖此次重记的结论须能追溯到中断检查点或已完结的核对记录。相关核准与读回来源无法辨明时只读报告当前值，暂停依赖动作。不把本机文件或内存当成跨机器持久记录。检查点承载核对所需的出处和事实，当前进度及批准仍以有效状态与原证据为准。读回比较及交接不能把现有 CLI 变成原子 CAS。[恢复协议](../../skills/sdlc/references/stage-agent-protocol.md#6-context-and-checkpoints) · [检查点模板](../../skills/sdlc/references/templates/CHECKPOINT.md)

##### 决定 3 · 发布前确认可按实际版本登记，中断后先核实目标

1. **只读预检** 从当前 Feature/Requirement 投影和现有目标配置核对仓库、worktree、登记分支、对应的有效状态与 Feature/目标环境身份。读取 HEAD 的实际 commit、现行 `validation.commit`、适用的 validation/review 内容、批准来源及必需证据。Feature 须为 `reviewed`，拟交付和拟登记 commit 必须与 `validation.commit` 相同。用 `git rev-parse --is-inside-work-tree` 和 `git rev-parse --verify 'HEAD^{commit}'` 确认实际候选，用 `git status --porcelain=v1 --untracked-files=all -- . ':(glob,exclude).sdlc-v1/**'` 确认业务路径干净，用 `git diff --quiet <validation-commit> HEAD -- . ':(glob,exclude).sdlc-v1/**'` 确认全仓实现等价。随后逐个用 `git ls-files --error-unmatch -- <ref>` 核对 state、产品和工程正文已跟踪，用 `git ls-files -u -- <三个路径>` 确认无冲突。`git diff --cached --quiet -- .sdlc-v1/state.json` 须退出 0，`git check-ignore -q -- .sdlc-v1/state.json` 须退出 1。用现有只读 CLI 确认 state 可读、有效且投影身份一致，逐个验证绑定路径并实际读取正文，沿用常规文件及禁止符号链接等约束。然后核对适用的指纹和 §5 的语义条件。旧 v3 的未绑定点沿用原有证据规则。任何必要证据、Git 前置、外部权限或实际目标存疑，先暂停外部动作。仓库 clean 和预检通过只反映当时事实；从外部动作到登记要保护候选、索引、状态和相关绑定的受控写入，继续核对实际目标和版本。预检不会保证最终写入、锁、磁盘或宿主回执成功。
2. **用稳定引用保留实际交付证据**。当 `validation.commit=A`，仅状态/上下文交接后 `HEAD=B`，全仓等价且上述条件成立时，实际交付、smoke 和显式 `record-release --commit A` 都绑定 A。`sdlc-ship` 与 `deployment-patterns.md` 共同使用已授权、可访问且可与操作和版本关联的既有证据记录，例如原流水线部署记录及其稳定引用。提前核对恢复执行者及实际交付环境能读取，使用原正文已有定位，或在新候选获正式批准前放好稳定引用。每段保留实际部署/回滚、last-good、环境、版本和 smoke/health/观测，结果保存不改变已绑定正文或现行候选。若无法兼顾证据跨环境可用性、批准绑定和准确登记，先暂停，或对获授权的可一致交付与登记的新候选完成所需独立验证及评审后再行动。在 B 重记 Validation 会改绑 B，不能事后把已交付的 A 填成 B。历史 closed 记录沿用只读审计和维护流程。
3. **中断后查明真实结果再继续**。执行外部动作前用原有阶段/平台证据记录保存该操作和目标环境的可核对标识、目标原版本、预期版本/变更及回执查询入口。需要时使用原有检查点定位该引用，执行和登记结果未知时保留原记录。重启即使 `next=ship`，也先只读比对该操作记录、可取得的执行回执、目标实际版本与环境变更，确认它们属于同一次授权动作；目标碰巧已是 A 不证明本次动作成功。若确认已执行，只补原授权覆盖且未完成的 smoke/验证及登记，检查已经成功的步骤和现行 state，若已正确记录 A 则直接确认结果。若登记被拒或回执未知，保留真实交付证据，读回并修复现有前置条件后只处理登记。若动作仍在执行或结果无法确认，停止推进该外部动作并标记缺证，不重发、不扩大范围；仅当已证实原动作未生效也不在执行，且预检和原授权仍覆盖时，才执行原计划动作。本轮用本地受控模拟覆盖，不进行真实部署或发布。[Ship](../../skills/sdlc-ship/SKILL.md) · [部署证据](../../skills/sdlc/references/deployment-patterns.md#9-状态与证据)

**覆盖** REQ-003、005、006。

#### 数据模型与关键实体

工程记录每条必要观察的 Feature、验收项、实际候选或版本、环境/相关配置、观察者身份或角色及授权来源、实际观察、结果和后续责任。答复可用现有对话、截图或其他证据，注明候选与可访问的原始引用。联合试用共享一次原观察，但逐 Feature 核对覆盖、集成缺口、分支、Task 及验证义务。可以引用同一参与 Feature 的已授权记录，跨 clone 用已同步 Git ref、路径和小节定位，不能只留下对方无法读的本地路径或私有对话。相关实现、环境、配置、范围或判据变化重验受影响项，仍适用的明确答复可复用。未证实的批准不得跨 Feature 或跨会话传播。候选是可定位事实，Markdown 的待体验、已确认和待处理描述不新增机器状态。

共享同一 checkout 的 A、B 先保留共同候选干净，分别按各自观察、集成义务和独立检查记录可接受的结果，再修复 B。若 A 自身条件通过但自己必需的集成检查未完成，A 仍保留缺口。若须并行修复，只有原授权覆盖且写者、登记分支、状态及被测版本都正确关联的隔离候选才可使用。B 先产生非 `.sdlc-v1/**` 的工作树差异会阻止 A 的正式写入，此时保留 A 的可复用证据并暂停依赖动作。B 的后续业务 commit 即使与 A 的界面或文件无交集，也要按现有全仓判断 validation commit 到 HEAD 是否在该目录之外等价，并对不等价候选按 Validate/Review 规则重验。人类观察仍可在等价可证的范围内复用，不能因此跳过对当前集成候选的正式检查。

#### 需求覆盖

以下由计划 `TASK-human-validation` 一次交付，场景运行范围见实施计划。

| 验收条件 | 设计或契约 | 计划检查 |
|---|---|---|
| REQ-001 / SCN-01–03 | 阶段编排与按验收项选验证方式 | B01 自验证自然请求；B02、B05 反例；客观 UI 和环境缺口走查 |
| REQ-002 / SCN-04 | 预检、固定候选、对话交接 | B01 真人变体；早期候选及模拟证据反例 |
| REQ-003 / SCN-05–06 | 首次、已知历史重验及历史不足，当前失败优先、旧通过失效 | B01 首次和重开三变体，B03 写入及拒写，B04B 缺证据和再评审拒绝 |
| REQ-004 / SCN-07 | 多 Feature 条件映射与反馈，先记录干净候选 | 同仓 A/B 候选、B dirty 后拒写、B 业务 commit 后重验和集成缺口 |
| REQ-005 / SCN-08–09 | 状态说明、适用证据续接、发布预检和结果恢复 | B01 真人与 Build loop，B04A 的 A→B→记录 A、模拟部署与中断及 Git 拒写，B04B 与 B05 |
| REQ-006 / SCN-10–11 | 原文权限、独占交接、核准落盘与读回、评审拒绝 | B04A/B、调用前插入和调用后中断、缺检查点/原文/委托、迁移后按投影刷新 |
| REQ-007 / SCN-12 | 原有 v3、CLI 和旧批准范围 | 旧 v3、`missing`、clone 原生回归，B05 的 Spec 选择器与无写入对照 |

### 实施计划

- **关联产品上下文** [REQ-human-validation.product.md](REQ-human-validation.product.md)
- **关联设计** 本文架构设计和需求覆盖
- **规划基线** `e587eb1a2abf6ca40b3f0b790f902f3c64e349c6`，2026-11-20
- **规划工作区** `/Users/mac/hansen_agent_team/external/sdlc-pilot`，`main`（本地投影 `main...origin/main`）

#### 背景与源码摘录

- 修订开始时已有本方案候选及原有 25 个工作树条目。原有条目为 14 个未暂存修改、11 个未跟踪文件，暂存区为空。其中 23 个在 `.sdlc-v1/**` 外，涉及 `skills/sdlc/SKILL.md`、`skills/sdlc-spec/SKILL.md`、`skills/sdlc-product-design/SKILL.md`、`skills/sdlc-prototype/**` 和共享 `lifecycles/product-design.md`、`integrations/product-prototype.md`。按受保护输入对待，未判断其归属。另有已跟踪且未暂存的 `.sdlc-v1/state.json` 与未跟踪的 `REQ-human-validation.product.md`。只读投影显示该 Requirement 为 ready 且尚无 Feature，`spec_ready` 为 match。全局 `next` 当前指向已有的 `FEAT-branch-registration` 的 Ship，本轮只使用指定 Requirement。外部 PLAN 与历史 `project.md` 的快照、环境和发布元数据不作当前测试结论。
- `lifecycle_state.py:633` 的 `_normalize_context_v1` 保留其余字节，因此追加验证或评审证据会让同一个工程文件上的一个或多个已绑定点变 stale。`:1146` 的 `_code_head` 检查受跟踪且无冲突的 state/context、未暂存 state 的前置检查由现有 mutation 路径处理，并拒绝 `.sdlc-v1/**` 之外的工作树差异。`:1742` 的 `_reset_delivery_checks` 清除验证和评审结果及快照。`:1910` 的 `record_validation` 只接受 pass/fail，pass 要求有效 Task 完成，两种结果均重置 Review/Release。`:1966` 的 `record_review` 要求现行 validation 且实现等价。`:2015` 的 `record_release` 经 `_mutate` 与 `_code_head` 核对索引和实现，要求 `reviewed` 与正确 commit。`:2156` 的 `verify_acceptance` 只读，Requirement 选择器只接受 `spec_ready`，Feature 选择器需读到已存在登记。`:2211` 的 `_feature_next_stage` 按状态/Task 路由。[生命周期实现](../../scripts/lifecycle_state.py)
- `stage-agent-protocol.md` 的 Continuation、Judgment、§5、§6 已有自主推进、停办、写入权与指纹引用。router 工作树 diff 集中于包内原型小节，现有 §2.1、§5 已把编排与验收恢复指向共享规则。其“重新获批”可由有权责任人显式复核，具体覆盖仍由已有指纹指南链接说明。Review 已引用适用性且会写入当前工程上下文；Ship 目前会直接写 last-good、实际观察和回滚。部署方法的 §1、§4、§6、§9 同样要求直接写正文，`:156` 的每段追加与 A 的稳定引用路径冲突。阶段协议 §6 和现有模板仅在暂停、跨会话或环境变化时生成检查点，需同步加入批准型重记预写，保留原形状。[部署方法](../../skills/sdlc/references/deployment-patterns.md) · [检查点模板](../../skills/sdlc/references/templates/CHECKPOINT.md)[阶段协议](../../skills/sdlc/references/stage-agent-protocol.md) · [Review](../../skills/sdlc-review/SKILL.md) · [Ship](../../skills/sdlc-ship/SKILL.md)
- `build-loop.md:59–69` 的 completion check 以及 `:112` 的停止条件都写“本轮”执行。两处改为引用共享证据适用性规则。保留 `:99` 的代码或测试变化后重新 Validate/Review 约束。[Build loop](../../skills/sdlc/references/build-loop.md#completion-check)
- `scripts/test_scenarios.py` 的 `prepare`、`reference`、`assert_result` 已建立 B01/B02/B03/B04A/B/B05。B03 已包含 dirty 候选拒绝 fail、旧状态原样保留的反例。B04A 现有参考只追加说明，oracle 要求 state 完全相等，不能覆盖有权重记及恢复 Review。B04B 的历史只执行正常输入，这是证据缺口；测试文件存在不能证明已运行。原生测试已有指纹三态、旧 v3 读取、Git clone、重开失效及 Feature 隔离。`validate-skills` 已调用两组测试。[场景](../../scripts/test_scenarios.py) · [原生测试](../../scripts/test_lifecycle_state.py) · [标准检查](../../scripts/validate-skills)

#### 目标、范围与复核

- **目标** 通过现有 `/sdlc` 与 README 用法完成授权推进、按需交接及正常恢复。实现采用现有 Markdown 技能、Python 标准库测试、Bash 和 Git。消费项目的 Web/App、正式独立 Validate/Review 或发布要求按其原约定执行。
- **基线复核范围** 核对实际 worktree、branch、完整 HEAD、允许路径及其直接依赖 `AGENTS.md`、`skills/sdlc/SKILL.md` 的上述引用、`sdlc-software-delivery`、`lifecycles/software-delivery.md`、`receiving-feedback.md`、`lifecycle_state.py`、`test_lifecycle_state.py`、`test_support.py`、`validate-skills`、相关 state/context、既有 Build loop 完成/停止规则、检查点格式与校验、部署证据写入、版本和场景环境。主 Agent 派发前、实现者首次写前分别查基线到当前 HEAD 的相关 diff，及暂存、未暂存和未跟踪事实。只有确认兼容的已有变化可沿用。依赖受保护路径的实质改动须由主 Agent 重新协调范围。
- **正式候选** 清洁度由实际状态检查判定。用户已同意在文件所有者正常交接后，将既定范围提交为本地 `main` 验证候选；候选实际 commit、已跟踪上下文、state 和工作树仍须在正式验证时逐项核对。不同开发分支须经既有 branch 登记迁移程序，不能偷换登记或从只含基线的 clone 假定包含未提交记录。只跟踪获授权的上下文，state 无冲突且未暂存，候选其余路径干净。不得用整树暂存、清理、重置或忽略他人文件制造 clean。工具加载也指向冻结版本，避免真演练误用活跃 checkout 的技能软链接。push、部署和发布未获授权。

#### 实施阶段与检查

1. **最早真实增量** 在唯一 `TASK-human-validation` 中先联通阶段协议、Plan、Validate、Build loop 和 README 的用户入口。以隔离 B01 的已确认范围和实施授权进入 Build，从实际 CLI 入口运行正常及错误输入检查。随后逐项走通同候选的必要真人交接、已知历史和恢复，检查适用的测试结果可继续使用。自验证路径无需用户试用，真人变体只在已有义务时交接。B01 自验证自然试次可用于观察最早增量，在最终候选仅按 §5 所需的等价核对复用。最早结果仍属当前实现增量。
2. **保护重记、拒绝和发布边界** 阶段协议 §5/§6 定义证据适用性、写者交接、预写核准记录和恢复读回。同步 `CHECKPOINT.md` 的触发及五节内提示，运行时 §6/§7.1 同步选择器、核对步骤、迁移后的参数及拒绝时清除的快照。Review 明确批准与拒绝路径。Ship 和 `deployment-patterns.md` 的发布前检查、每段留证、回滚、观测和登记执行决定 3，引用共同的现有可访问记录。所有写入证据的指导都允许同一稳定引用路径。工程模板在现有证据章节提示记录或引用材料。Validate 按决定 1 处理历史与实际失败，README 保持短用法一致。`build-loop.md` 的完成与停止处引用共享证据适用性，保留实质变化必需重验。
3. **检查与记录** `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_scenarios.py`、`bash scripts/validate-skills`、`git diff --check` 均期望退出 0，标准检查关键输出 `RESULT: PASS`。标准检查已含 v3 原生测试。另核对实际集成 diff、未跟踪文件及其空白，两种范围的证据分别记录。`docs/testing.md` 补充下述变体、确定性断言和实测边界，保留历史结果。本轮是本地迭代。`CHANGELOG.md`、插件元数据和版本不在用户确认的本地候选路径内；push、发布和其他外部动作未获授权。旧计划的义务与本次明确批准的范围调整继续适用。

#### 确定性场景与语义走查

沿用 `scripts/test_scenarios.py` 的 `prepare`、`reference`、`assert_result` 和临时 Git 仓库。下表为实现后的可运行检查，新增变体集中在该文件，按相同命令运行。复用原生分支迁移、指纹竞争、旧 v3、Task 重开及跨 clone 断言。fixture 中的 Git 操作、模拟实际交付和状态 mutation 只针对可丢弃的本地测试仓库。选取直接可观察的反例，不比对生产文案，也不在脚本中另实现 Agent 授权流程。

| 场景 | fixture 步骤和预期断言 | 需要走查的行为 |
|---|---|---|
| B01 真人等待与恢复 | 从已完成 Task 与机器检查的初次候选起步，读回 pending 和裸 `next=validate`。一份变体记录真实 CLI fail 并在 fixture 保留失败回执，一份变体记录未提交的 pass 和 approved 并在接手前让恢复者无法访问原 pass 回执和交接记录。都走 `done → todo → in_progress → done`，断言 validation.result 和 review.decision 均为 pending、验收快照 missing；后一变体当前 Git/投影无原 pass。等待结果 oracle 对误写 pass/fail 判错。另令当前必要探针失败或环境阻塞，在可写的 fixture 中按实际归因记录 fail。 | 区分首次、可识别前次 fail 的新候选、历史不足三种解释，记录仍待真人的真正理由。当前已证实失败/阻塞不得被历史未知遮蔽。普通超时仍不写 fail；适用真人答复与相关输入变化分别核对复用和必要重验。 |
| B04A 原文与核准内容 | 用 `git show <approved-ref>:<path>` 还原原文并核对真实归一化指纹。从 B04A 派生两个独立临时仓库。纯追加对照在固定全部预期路径/digest 后调用重记，读回映射完全相等，必要时测试按 validation → review 恢复并保留测试原 commit。插入反例在预审和临近调用核对后、CLI 自身读取之前顺序插入实质产品条件，再直接调用原 CLI 拿到成功及 `match`。断言已保存 digest 与核准 digest 不同，批准结果的比较检测出偏离。 | 无独占、原文或委托时停止重记。核对失败禁止依赖旧或新快照，核对实际状态写入结果后恢复。fixture 故意绕过流程，能证明 CLI 边界及读回比较价值，不能证明 CLI 预防竞争或 Agent 总能取得独占。 |
| B04A 重记检查点 | 沿用前述 B04A 竞争输入，用临时五节检查点保存事先路径/digest、候选与原评审引用，并留一条已有未完成事项。分别模拟未落盘、已落盘未调用、validation 重记后未读回三种中断，另复用插入变体与未同步检查点的 clone。读 CLI 的真实快照、Review 状态，并比对磁盘中的预审值。断言不落盘/未调用时原快照不变，成功重记时只 validation 匹配新摘要且 Review 被清，插入变体虽返回 match 但与预审摘要不符。 | 逐例检查调用前主 Agent 写入并读回、本机失败时零调用、恢复先定位检查点、已完成重记不重复执行、有权且证据完整才恢复旧 Review。记录缺失/不可读、与核准值不符或无写者独占时停止依赖动作，保留已有未完成事项。 |
| B04B/B03 拒绝及失效 | 继续验证旧 pass 缺证（B04B）和环境阻塞/拒写（B03）的状态。用 B04A 已 reviewed 的派生场景追加必须修复发现，查到 validation stale 后直接 `record-review --decision changes_requested`。期望该命令成功、状态回 in_progress、review 快照消失、release pending，且验证记录未重签。另在 dirty 候选运行相同命令，期望前置拒绝、持久状态不变。 | 按权限记录拒绝优先于通过型重记，即使原验证者离线。CLI 拒写仍停止该 Feature 下游，不能用旧 approved 继续发布。 |
| B04A 发布 commit | 用两份独立 B04A 临时仓库得到 A 的正式验证及仅状态/上下文交接后的 B，断言 A≠B、全仓等价。正例保持 validation/review 的绑定正文，按既有引用保存本地从 A 用 `git archive` 解包至仓库外专属临时目录的制品来源及 smoke 结果（`python3 -B cli.py 3` 输出 `6`、退出 0），调用 `record-release --commit A`，断言实际来源、`validation.commit`、`release.commit` 均为 A。反例追加绑定证据后在 B 重记 validation 再恢复 approved，显式记录 A 应返回 `release-commit-does-not-match-validation`，无发布记录。 | 第一组验证可执行路径。第二组只观察 CLI 后果，在实际外部动作前应发现登记路径不可行并暂停，不能事后把 A 写成 B。 |
| B04A Git 预检与部署恢复 | 业务 clean 且 state staged 的 B04A 应在登记返回 `state-is-staged-commit-or-unstage-before-update`，前后状态不变。另做 context 从索引移除和冲突索引变体，分别证明已跟踪/无冲突是独立前提。在 A→B 的可登记对照中，用标准库本地临时目标和既有 fixture 部署记录模拟部署。只执行一次应用 A，记录操作 ID 与环境并更新可只读核对的目标版本，模拟在本地回执和登记前中断。此时裸 `next=ship` 且目标已是 A；恢复对照确认必需 smoke 和 `record-release --commit A` 后，应用次数仍为 1，绑定正文不变且 release.commit 为 A。覆盖已写入登记但未收到回执，与目标/操作证据无法对应两种反例。 | 证据存在时只补缺失的已授权步骤并避免重复调用。证据不明或写入前置失败时暂停，已执行的动作不重发。按部署方法逐段走查 last-good、回滚、smoke/观测证据和跨环境读取路径，验证无需追加绑定正文。无法提前固定引用或登记将改绑 B 时，外部动作应为零。仅模拟，不访问真实环境。 |
| B01 同仓双 Feature | 在同一临时仓库和干净 HEAD 建立 A、B，各有追踪的产品/工程上下文。当 A 自身通过且其必要集成检查完整、B 仍有未通过项时，先记录 A；A 绑定共享候选，B 保留自己的结果。独立反例在记录 A 前写入 B 的业务变更，A 的 `record-validation --result pass` 应按 clean-worktree 前置拒绝，A/B 记录及 branch 不变。再从有 A 通过的干净起点提交 B 的业务变更，断言 `git diff --quiet <A-validation> HEAD -- . ':(glob,exclude).sdlc-v1/**'` 返回 1，对已有验证/批准的 A 调用相应 Review/Release 应拒绝 commit 不等价，原记录不变。 | 联合答复按 Feature 逐项关联。集成检查仍缺的子例不能写 A 的 pass，即使 A 自身观察通过且裸 CLI 允许。工作树污染和新业务 HEAD 均保留事实，隔离或重验时不得擅改登记分支。 |
| B04A 迁移后刷新 | 指定初始登记 `main`。保存原批准正文/指纹，使用现有迁移把已检出的同一 HEAD 和登记一起核对至 `feature/fix`，然后做适用证据追加。传历史 main 的 `start-feature --refresh-acceptance` 应为 identity mismatch 且 state 不变。用当前 `feature-projection` 的四个身份参数重记，读回 branch、Task、进度和各点记录，只有 plan 快照及其相关时间更新。验证/评审的已存快照保持原值，即使正文追加使其查询变 stale。 | 原批准来源仍是原验收点，不从迁移推出新授权。首次登记本 Feature 继续使用固定 main。 |

用独立准备 fixture 对照 Spec 选择器。未登记 Feature 时实际 CLI `verify-acceptance --requirement-id <REQ> --point spec_ready` 返回 0/`match`。同点使用未登记的 `--feature-id` 返回 2/`feature-not-found`，用 Requirement 查 plan 返回 2/`invalid-acceptance-point`。登记 Feature 的对照用两个合法选择器查 `spec_ready`，断言得到同一产品文件的路径和摘要、不同的 target_type、state 与上下文无写入。命令沿用现有接口，不改裸 CLI。

旧 B02 未委托选择、B05 部分登记、B03 必要环境和拒写、旧 v3 `missing` 沿用现有断言与协议走查。表中的数字、时间和版本断言必须来自实际 CLI/Git 输出。权威、适用性、是否重复催问和是否错误派发由主 Agent 对照输入及操作记录逐例核对。实现后的独立正式 Review 核查第二轮发现的修复和验证证据。[场景入口](../../docs/testing.md#手动准备与检查场景) · [测试选择](../../docs/testing.md#按改动选择检查与复用)

#### 自然请求与实际证据

选三个最小真实 Agent 试次，串行，均从冻结候选的 README 入口进行。其余风险使用上述 fixture、对照走查及实现后的独立正式 Review，未实测的路径标记为 `NOT_RUN`。

| 次序 | 试次与实际判据 |
|---|---|
| 1 | **B01 自验证** “按已对齐的整数翻倍方案继续实现并验证，非法输入应失败。”观察按已获授权继续、真实正常/异常命令结果、没有阶段切换确认或用户试用要求。 |
| 2 | **B01 真人** “我需要亲自操作这个 CLI。准备好后给我候选和步骤，其他检查照常。”观察一次可操作交接、当时 `pending`，恢复仍能定位候选及待项，泛化“继续”不形成通过。在同一试次中有适用真人答复时才能检查如何复用命令/版本及完成必要检查。真人或可用证据缺失时，只记录实际覆盖。 |
| 3 | **B04B 旧通过缺证** “核对现有证据是否覆盖非法输入。缺证据时可以撤销旧通过，暂不运行新验证。”观察旧 pass 失效及无 Review/Ship 调度。无外部动作。 |

主 Agent 预检宿主能力、负载、可用授权/费用和角色配置，固定初始 Git ref、实际工具/技能加载位置、fixture 及其可写范围。2026-11-20 用户同意以联合比较的 14 个试次、计划最多 31 个模型 run、并发 1 替代原 60,000 计费 token 硬上限；宿主不能保证单次在途运行的 token 或墙钟硬上限。前三次以原 30 分钟为启动控制目标，超时后不再启动该组新试次，并如实记录仍在运行的任务；比较组按已记录的 75 分钟启动控制目标处理。每次结束后记录可取得的原生用量与身份，实际费用无法核实时标未知。每次保留原生脱敏对话、实际调用、退出码、候选、执行者与缺口，核对实际独立阶段，清理仅由本任务创建的可丢弃环境和资源。失败和未运行分别保留。批准范围、随机竞争、真实发布、跨 clone 的私有引用与效率改善均不可从本地演练外推。[资源生命周期](../../skills/sdlc/references/stage-agent-protocol.md#verification-resource-lifecycle) · [联合比较执行清单](../../workspace/20261120-sdlc-combined-acceptance/benchmark-runbook.md)

### 工程任务

#### TASK-human-validation [US1–US3] 实现按需人工验收与自主推进

- **目标与依赖** 一个完整 Task，由同一实现者交付上述阶段规则、场景与普通修正。无前置 Task。两轮独立对抗复审已结束。主 Agent 已核对首轮七项与第二轮六项发现，并已向用户说明升级。此修订供主 Agent 验收，第二轮发现仍须在实现中逐项修复、经适用验证和正式 Review。接受后按 brief 先在 `main` 登记 `FEAT-human-validation`，再登记唯一 Task（标题同上）。核对标识、依赖和全量登记后进入 Build。主 Agent 负责整合和最终验收，后续独立 Validate 与 Review 按现有协议。
- **允许修改路径** `skills/sdlc/SKILL.md`、`skills/sdlc/references/stage-agent-protocol.md`、`skills/sdlc-plan/SKILL.md`、`skills/sdlc-build/SKILL.md`、`skills/sdlc-validate/SKILL.md`、`skills/sdlc/references/lightweight-runtime.md`、`skills/sdlc/references/templates/ENGINEERING.md`、`skills/sdlc/references/templates/CHECKPOINT.md`、`skills/sdlc/references/build-loop.md`、`skills/sdlc/references/deployment-patterns.md`、`skills/sdlc-review/SKILL.md`、`skills/sdlc-ship/SKILL.md`、`scripts/test_scenarios.py`、`docs/testing.md`、`README.md`。Router 限已选 Feature 的未决交付恢复入口和 stale 权限说明，保留原有原型召回改动。Build 限 Task 完成与交接给 Validate 的条件，Build loop 限完成/停止处证据适用性。Review 限批准与拒绝路径。Ship 与部署方法限交付预检、稳定证据路径、恢复和登记一致性。检查点模板限触发时机及既有五节内的提示。工程上下文的实际证据按现有阶段职责与主 Agent 指定的写入范围回填。`CHANGELOG.md` 和插件元数据留待已授权的提交或发布准备，均排除于本地迭代及允许路径。
- **禁止范围** 本 Task 的生产 CLI/测试框架不变更，`scripts/lifecycle_state.py`、`scripts/validate-skills` 和 `scripts/test_lifecycle_state.py` 作为既有验证，新增可观察回归集中在 `test_scenarios.py`。保留 Router 的原型召回改动、Spec、Product Design、Prototype 及所有其他已有未提交内容，产品上下文和 state 由原职责维护。不引入 schema、命令、指纹忽略区域、第二账本或常驻服务。用户已授权将本次两个迭代的既定 40 路径作为本地 `main` 验证候选提交；push、发布及外部动作仍未获授权。禁止借验证改生产状态、通知外部或处理其他人的工作。
- **完成条件** 按实施阶段与需求覆盖执行检查。主 Agent 核对完整 diff、fixture 初始和实际结果、语义反例与各试次真实覆盖。命令通过和模拟输入各自记录；仍缺必要实际行为证据时依阶段规则报告。与实现相关的修正交同一实现者，独立阶段的职责仍由原角色完成。
- **停止与回退** 缺可读核准检查点或原记录、写者未交接、核准与读回不符、Git 预检失败、拟交付与登记版本不一致、或实际外部动作状态不明时，暂停依赖动作，保存核准映射、已知事实和已有独立证据。CLI 拒写按阶段协议 §4、§6 停止该 Feature 后续调度。与试用无关且独立授权的工作可继续。风险导致方案、授权或验证策略实质变化时才发完整 `supersedes`。§5 的非收敛历史及有界诊断沿用原规则。需回退时，只在获授权后恢复本 Task 自己的修改或使用前一已获批准候选，按当前证据重新确认适用性。不得覆写其他文件、手改 state、重复外部交付或复活旧 pass。

## 实现记录（实际）

- 2026-11-20 用户对上一条明确列出的两项请求回复“没问题”：同意 Build/Router 的有限范围调整、既定 40 路径的本地 `main` 候选提交，以及以计划 14 个试次、最多 31 个模型 run、串行和可取得用量记录替代原 token 硬上限。该答复不授权 push、部署或发布。原始计划正文与当前范围差异及审阅清单见[联合验收前置条件](../../workspace/20261120-sdlc-combined-acceptance/acceptance-preconditions.md)。
- 2026-11-20 独立实现评审发现：原 Build 文字可能等待留给 Validate 的真人验收，形成阶段循环；因此将原本干净的 `skills/sdlc-build/SKILL.md` 加入上面的有限写入范围，仅明确 Task 完成与 Validate 义务的交接，不改变既定产品条件。Ship 恢复入口、证据记录和确定性场景也需修正。主 Agent 修正文档并向原实现者发送覆盖测试缺口的 `supersedes` brief；本 Task 暂未接受，后续需独立复核当前候选。
- 返修复核进一步确认：多段交付中断后须逐操作恢复；登记回执丢失时已发布 Feature 的裸 `next` 为 `done`，因此扩展 Router 的有限写入范围以支持对明确选中 Feature 的只读恢复，并澄清 stale 的委托处理。原型召回正文保留；原执行者继续修正可证伪的 fixture 缺口。上述调整不新增发布授权或改变产品验收条件。
- 已按本 Task 的允许路径实现共享协议、Plan/Validate 条件与验收卡片、检查点批准重记预写与恢复读回、旧验证重签授权与写者独占、并发映射误绑定防护、拒绝路径、历史未知与已知失败后重开、Build loop 证据适用性、跨 Feature 同候选隔离、发布前登记预检与中断去重、deployment-patterns 证据引用一致性和 README 用户入口。
- 权威来源保持单一：`stage-agent-protocol.md` §5 承载按需人工验收与验证历史、多 Feature 同候选、批准型重记与独占读回、发布前登记预检与中断去重；§6 承载批准型重记的中断检查点。`sdlc-validate` 引用其历史与交接规则，`sdlc-plan` 引用其验证方式判定，`sdlc-review` 引用拒绝路径，`sdlc-ship` 与 `deployment-patterns` 引用发布预检与证据引用一致性，`lightweight-runtime` §6/§7.1 承载选择器、重记参数、迁移后身份和拒绝时清除的快照，`build-loop` 引用共享证据适用性。
- 未新增 schema、CLI、指纹算法、常驻服务或第二状态库。`scripts/lifecycle_state.py`、`scripts/validate-skills`、`scripts/test_lifecycle_state.py` 未改动。README 新增 `SCN-human-validation` 入口，链接当前 Requirement 的已确认故事与场景。
- `scripts/test_scenarios.py` 新增 `HumanAcceptanceTest`，用一次性临时 Git 仓库断言原 CLI 的可观察行为：首次等待保持 pending、已知失败与已知通过后重开、历史不完整、旧通过必要重验缺证与拒写、核准映射竞争下 CLI 返回 match 但摘要偏离、拒绝优先、同仓双 Feature 的脏候选与新 commit 限制、state 已暂存、状态交接后登记实际交付版本、改绑 Validation 后误登记被拒、部署中断不重复应用、迁移后 refresh 身份和 Spec 选择器。

## 验证记录（实际）

- 规划核对基线、写入/重记约束、Requirement 投影、`spec_ready=match` 和登记/迁移/验证/发布 CLI help。主 Agent 提供的标准基线为 `bash scripts/validate-skills` PASS。
- 主 Agent 已在临时 B04A fixture 做调用前内容插入探针。先算已审阅的纯证据追加目标 digest，再在直接调用 `start_feature(refresh_acceptance=True)` 前插入实质产品条件。已保存的 plan digest 与预审目标不同，而随后 `verify_acceptance(point=plan)` 返回 `match`。因此需要写者独占及与事先核准映射逐项读回，现有 CLI 没有原子授权核验。
- 主 Agent 已另用两份独立临时 B04A 仓库核对发布因果。对照组 `validation.commit=A`、仅状态交接后的 `HEAD=B` 且 A≠B，`record_release(commit=A)` 成功并记录 A。实验组相同 A→B，在追加工程证据后先 `record_validation(pass)`、`record_review(approved)`，再以 A 调用 `record_release` 得到 `release-commit-does-not-match-validation`。以上探针是主 Agent 提供的现状合成证据。
- 主 Agent 的追加探针确认 B04A 业务路径 clean 时，暂存 state 仍使 `record_release` 以 `state-is-staged-commit-or-unstage-before-update` 拒绝。B01 记录 fail 后按既有转换重开并完成，validation.result 和 review.decision 都变为 pending。已知的历史 fail 仍属于前一候选。上述所有探针均在自动清理的临时 fixture 中完成，无目标仓修改或真实发布。
- 本次只读检查确认登记前用 Requirement 查 `spec_ready` 返回 match，用未登记 Feature 查同点返回 2，用 Requirement 查 plan 同样返回 2。已有 Feature 的对照、实现后回归、正式 Validate/Review、真实 Agent 演练和真人观察尚未运行。
- 本 Task 实现后的本地检查：`PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/test_scenarios.py` 退出 0，33 个测试通过（8 个共享场景、6 个 T3 合同、19 个 `HumanAcceptanceTest` 用例）；`bash scripts/validate-skills` 退出 0、`RESULT: PASS`（其中 lifecycle 90、backlog 7、场景 33、contrast 36、Hallmark 12、vibe 核心 19、vibe host 4、安全依赖探针 6 个测试方法全部通过，54 项结构检查通过）；`git diff --check` 退出 0。检查使用本机 Python 3.15.2 与 git 2.56.0 和临时 Git 仓库，无外部服务、模型请求或真实发布。独立评审指出这些通过尚未覆盖方案中全部重记、发布恢复和双 Feature 用例，修正进行中。
- 新增用例实测到的 CLI 事实：首次等待保持 `pending`；已知失败与已知通过后重开都使 `validation` 回到 `pending` 且指纹为 `missing`；未提交的 `pass` 在重开后既不在投影也不在 Git 提交中；脏工作树下 `record-validation --result fail` 以 `validation-and-release-require-clean-worktree` 被拒且 state 与业务文件逐字节不变；调用前插入实质产品条件后 `start-feature --refresh-acceptance` 成功且 `verify-acceptance --point plan` 返回 `match`，但已核准摘要与新绑定摘要不同；追加工程记录使 validation 指纹 `stale` 时 `record-review --decision changes_requested` 成功、旧评审快照消失、Release 保持 `pending`、`validation.result` 仍为 `pass`；同仓另一 Feature 的未提交业务变更使正式写入被拒、业务 commit 落地后 Review/Release 以 commit 不等价被拒；state 已暂存时 `record-release` 以 `state-is-staged-commit-or-unstage-before-update` 被拒；仅状态交接后 `record-release --commit A` 仍登记 A，改绑 Validation 后登记 A 得到 `release-commit-does-not-match-validation`；分支迁移后用历史 branch 重记返回 `feature-identity-mismatch`。
- 本次追加实现与验证记录使工程上下文的 `plan` 指纹变为 `stale`（`content-drift`），产品上下文仍为 `match`。这是 `context-v1` 归一化覆盖全文的既有行为，不是本 Task 新增的失效规则。按[批准型重记、独占与读回](../../skills/sdlc/references/stage-agent-protocol.md#批准型重记独占与读回)，主 Agent 接受本 Task 后需按写者交接、核准映射预写和读回比较重记 `plan` 点；本 Task 未自行调用任何 lifecycle mutation。
- 未覆盖项：真实 Agent 演练（三个试次）、正式独立 Validate 与 Review、真人观察、真实部署与发布、跨 clone 的私有引用复核均未运行。确定性用例只证明原 CLI 的机械边界与状态后果，不证明 Agent 是否按协议提问、等待、交接、取得独占或执行读回比较。
- 2026-11-20 后续返修：Sol 独立复核定位旧 Review 原记录缺失、失败检查被标为通过、已发布恢复入口顺序和两个 fixture 条件缺口；主 Agent 补了可复现反例并做局部修正。`bash scripts/validate-skills` 对最终源码候选退出 0、`RESULT: PASS`，含 lifecycle 90、backlog 7、场景 58；`/usr/bin/python3 -B scripts/test_scenarios.py` 在 Python 3.9.6 下 58 项通过；`git diff --check` 退出 0。原型组件 127 项通过。原始记录见[联合验收准备](../../workspace/20261120-sdlc-combined-acceptance/preparation.md)。这些检查仍不替代真实 Agent 轨迹或正式独立 Validate/Review。

## 评审记录（实际）

- 两轮独立只读对抗复审已结束。首轮七项保留，第二轮六项已转入本方案的实现和验证义务；第二轮发现尚未验证修复。按主 Agent 已说明的升级方案收束，不开启第三轮。实现后的正式独立 Review 待适用验证。

## 发布与观察记录（实际）

- 本轮为本地迭代，版本准备、交付及实际观察均需后续适用授权与证据。指标、窗口和反馈回流见产品上下文。[发布后观察计划](REQ-human-validation.product.md#发布后观察计划sdlc-补充)
