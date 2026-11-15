# 工程上下文：FEAT-security-scan

## 当前有效方案

### 架构设计

**Requirement**：`REQ-security-scan`；产品规则与验收场景唯一见对应产品上下文。
**规划基线**：2026-11-15，仓库 `main` 的 `3093e85725a30078f2666886766ef4175bfb1d20`；开始时业务工作树干净。`project.md` 的历史版本/测试数是旧事实，不视为当前检查结果。
**执行环境**：当前主会话为 T3 Codex `gpt-6.1-terra / max`。用户明确允许通过 T3 `delegate_task` 调度不同执行上下文；原生 `spawn_agent` / `followup_task` 限制仍然适用。独立验证和评审须核对实际执行上下文及模型信息，宿主未提供的实际模型元数据标为未知。
**方向来源**：用户当前请求及 `workspace/20261115-codex-security-sdlc-integration/方案.md` 的只读调研；后者是候选依据，不替代当前契约和实际测试。

#### 复用评估

| 候选 | 覆盖与取舍 | 选择 |
|---|---|---|
| 扩展现有 role routing、validate/review 和按需 integration | 保持技能族的便携式阶段、单一 state 与证据所有权；可直接通过已安装的供应商入口执行 | 采用 |
| 全面嵌入 Codex Security runtime 或重写扫描器 | 耦合外部运行时、凭据和模型；本次无需维护其执行引擎 | 不采用 |
| 定义通用跨工具规范化器和新结果数据库 | 需要版本化格式、迁移和更广的真实性验证；不是启动定向扫描的必要前置 | 本次不新增；保留原生结果与范围证据 |

此前 `decision-context` 的相关卡为外部主张，适用范围和反例在调研方案 C3；本次使用当前仓库和供应商源码核对接口，不把知识卡直接当运行证据。

#### 组件与边界

- `skills/sdlc/SKILL.md` 只在当前阶段实际需要使用 Codex Security 时安排只读能力检查和普通提示；能力细则、风险、安装入口和实际扫描调用放入 `integrations/codex-security.md`，不把供应商规则复制进各阶段。
- `skills/sdlc/scripts/check_security_dependency.py` 只使用 Python 标准库探测 PATH 中的候选 CLI 和 Node/npm，不执行候选可执行文件、网络、登录或模型。探针明确报告插件、认证、版本和扫描均未检查；宿主对插件的发现与实际运行准备由 Agent 分别核实。只有 `cs` 时作为有歧义的候选，不认定它就是 Codex Security。
- `validate-modes/security-scan.md` 定义风险选择、输入、原生证据、四类归因与 review 复用；`integrations/codex-security.md` 定义经版本/权限/预算检查后使用供应商 CLI/插件及保留原始结果的步骤。CLI 具体命令和参数必须先由当前安装的版本帮助信息核实；本次机器缺 CLI，不声称真实命令已运行。
- `role-routing.md`、`sdlc-validate`、`sdlc-review`、`sdlc-onboard`、`roles/security.md` 与必要的 README/CHANGELOG 引用同一 mode/适配说明。生命周期 state 结构和 `record-validation` 接口不变。
- 扫描范围、原生产物、候选 commit、工具版本、预算、退出、缺口与关键反证保存在既有工程证据；原始报告不进入 state。真实运行前按现有授权和资源生命周期检查；不自动 patch、上传或发布。
- 用户要求发布到 main 后，将两个插件元数据和 CHANGELOG 准备为 `7.0.0` 候选。依据：本次对部分安全敏感变更新增必要验证义务，可能阻塞旧工作流；仓库 6.0.0 对新增必要验证义务使用 major 版本。候选版本不表示已合并、打 tag 或发布。

#### 风险与停止条件

- CLI 路径存在不能证明版本、认证或模型可用；插件能力不能从 CLI 缺失反推。若 status 查询可能导入认证，不能作为每次入口的无副作用探针。
- 上游 committed-diff 扫描要求相应 checkout 和范围满足其自身条件；`B` 与 `H` 必须固定，不能用移动的分支名冒充稳定证据。工具退出成功不等于覆盖足够或没有漏洞。
- 未安装、未授权、预算耗尽、超时、扫描不完整或原生产物缺失，按已观察事实分类并保留缺口；环境阻塞不自动将 Task 退回实现。
- 用户已授权完成验证、评审并发布到 main；真实模型扫描、安装及其他外部资源消耗仍遵守此前约定的单独确认要求。不能将未执行的真实扫描或同一执行者的自查写成已通过的独立验证。

### 实施计划

一个纵向 Task 覆盖用户场景 1–5：先实现只读依赖探针与缺失/候选测试，作为最早可检验结果；再接通入口提醒、风险路由、validate/review 和工具适配。以 `scripts/validate-skills`、探针行为测试和 `git diff --check` 验证本次快照；测试替身不证明真实扫描效果。

| 产品验收 | 设计/契约 | 计划验证 |
|---|---|---|
| 依赖缺失、候选与未知不混淆，按需提示安装 | 只读探针 + 选用 Codex Security 时检查 + 适配说明；README 以稳定场景 ID 导航到产品场景 | 隔离 PATH 的进程测试；核对 README 导航；实际 Agent 演练普通工作、其他工具及选用 Codex Security 时的提醒行为 |
| 安全扫描按风险执行，验证与 review 复用证据 | role routing、security-scan mode、Codex Security 适配与阶段引用 | 仓库结构/引用检查；实际 Agent 消费标明为 synthetic 的完整、缺失和版本不匹配样本，检查缺口归因及 review 不重复扫描 |
| 不泄露凭据、不把未运行写通过 | 探针不读取/显示凭据；验证归因与报告纪律 | 敏感环境变量测试、规则与失败场景核对 |
| 已有生命周期兼容 | 不修改 state schema 和验证 CLI | 现有生命周期回归；检查 diff |
| 发布候选版本一致 | `CHANGELOG.md` 与两个 `.claude-plugin` 元数据 | 解析 JSON 并核对三个版本值与 CHANGELOG 的 7.0.0 记录；候选未通过验证前不发布 |

提醒行为演练需保留 Agent 输入、加载的技能路径和完整工具轨迹：普通工作及选择其他工具时不检查或提示 Codex Security；实际需要且 CLI 缺失时运行只读探针，结合宿主实际插件发现能力作普通提示，未知项保持未知，不安装、登录或扫描。合成扫描产物只能证明消费者行为，不能证明真实扫描通过。

### 工程任务

`TASK-security-scan`：在上述路径实现探针、安全验证方式、Codex Security 接入、依赖提醒和相应检查；按发布目标补充两个插件元数据与 CHANGELOG 的候选版本，由同一执行者完成相关修正。禁止修改 unrelated Feature 或外层工作树；若依赖真实运行才能判断产物语义，保留未验证事实并停止虚假的成功声明。

## 实现记录

- 已增加只读 CLI 候选探针、按需依赖提示、安全扫描方式、Codex Security 适配和 validate/review 路由。未改变 lifecycle state schema 或自动安装、登录、扫描和发布。
- 用户随后明确将每次首次进入时的强烈提醒改为实际需要 Codex Security 时的普通提示；当前任务重新打开并按此修改，历史测试不自动代替修改后的回归。
- 根据 2026-11-15 的发布请求，已将插件和 marketplace 元数据同步至 7.0.0 候选，并把本次变化移入 CHANGELOG 的 7.0.0 条目；此举不代表候选已获正式验证或发布。
- 分支登记迁移决定：当前执行者完成写入和测试后，按用户批准将 `FEAT-security-scan` 从 `main` 迁到本地 `feat/codex-security`，预期 HEAD 为 `3093e85725a30078f2666886766ef4175bfb1d20`；完整参数为 `--feature-id FEAT-security-scan --expected-branch main --branch feat/codex-security --expected-head 3093e85725a30078f2666886766ef4175bfb1d20 --reason 用户批准创建功能分支以提交本次改动`。迁移不会提交、验证或发布。
- 迁移结果：2026-11-15T04:41:31Z，CLI 在本仓库返回 `main → feat/codex-security`，实际 HEAD 与预期一致；Task 为 `done`，validation/review/release 保持 `pending`。
- 最早增量以隔离 PATH 测试完成；项目 `.agents/skills/sdlc` 经 `.claude/skills/sdlc` 指向本规范 checkout，已通过该链接执行探针。
- Manus 同步 `--check` 返回非零：12 个目标均为现有符号链接而不是该工具管理的真实副本；未替换这些链接。

## 验证记录

2026-11-15，以下为同一执行者对基线 `3093e85725a30078f2666886766ef4175bfb1d20` 加当前未提交业务 diff 的 Build 检查，不能冒充独立 Validate：

| 命令或检查 | 结果与范围 |
|---|---|
| `bash scripts/validate-skills` | exit 0；结构/引用检查和 176 个 unittest 通过。Hallmark 测试有一条现有 HTTPError 资源警告，不影响退出结果。 |
| `python3 -B scripts/test_security_dependency.py` | exit 0；3 项隔离 PATH、短名歧义、不执行候选程序和不输出测试凭据检查通过。 |
| `uv run --offline --no-project --with coverage` 驱动探针测试 | 测试 exit 0；合并子进程数据后探针 20/20 行、5/6 分支覆盖，coverage 综合 96%。父进程因仅统计子进程源码产生 `no-data-collected` 提示；子进程数据实际合并。仅使用本机离线缓存。 |
| 通过本项目 `.agents/skills/sdlc` 链接运行依赖探针 | exit 0；未发现 CLI，Node/npm 在 PATH，插件、版本和认证未检查，扫描 `NOT_RUN`。 |
| `scripts/sync-sdlc-skills-for-manus --check` | exit 1；现有 12 个目标为符号链接，Manus 生成副本未建立；不影响已核实的本机符号链接路径。 |

用户将提示改为按需之后，重新运行 `bash scripts/validate-skills`：exit 0，176 项测试通过；重新运行离线 coverage，
探针仍为 20/20 行、5/6 分支，综合 96%。依赖检查和普通工作不触发提醒的文本契约已自查；未进行真实 Agent 演练。

首轮 Build 检查时的缺口：正式独立 Validate 所需的干净业务代码 commit 尚无；CLI/插件、登录与真实扫描未运行；Agent 是否实际按提示完成检查尚无真实演练。后续候选 commit 和当前验证状态见下文。

### 2026-11-15 验证尝试 — f11241a6d6d5506dce8230b3c5034dc3cb529fff

- `git archive` 从上述提交生成新解包目录，在该目录执行 `bash scripts/validate-skills`：exit 0，176 项测试通过；包内探针可运行。该检查由实现者串行执行，不是独立 Validate。
- `ENV_BLOCKED`：当前 T3 Codex 会话受项目既有 no-spawn 约束，尚无符合角色要求且与实现者独立的验证执行者；当前实际模型为 `gpt-6.1-terra / max`。
- `INCONCLUSIVE`：真实 Codex Security CLI、认证、模型调用以及 Agent 对按需提醒的实际行为尚无本版本运行证据；本机探针未发现 CLI，插件与认证未检查。之前的源码和合成测试不能代替真实执行。
- `IMPLEMENTATION_FAILED`：用户现要求将行为变更发布到 main，但两个插件元数据仍为 6.0.0，新增记录仍在 `Unreleased`。本仓库 `CLAUDE.md` 要求发布行为变化时按语义化版本同步元数据；须先准备候选版本并重新验证。
- 本轮不满足全部必要条件，整体未通过；不进入 Review/Ship，也不把前述检查称为独立验证。
- 后续修正：在同一执行者的未提交 7.0.0 候选上，版本 JSON 与 CHANGELOG 一致性检查 exit 0，`git diff --check` exit 0，`bash scripts/validate-skills` exit 0、176 项测试通过。原执行者的 Build 检查不能代替独立 Validate；真实扫描和 Agent 演练仍未运行。

### 2026-11-15 验证状态 — 90f9698def2bb3793c6cb58203d301f16f7880ff

- 7.0.0 候选已提交；提交前执行者的检查见上一条，不冒充另一执行者的正式 Validate。
- 从该候选提交生成新的离线源码包后，包内 `python3 -B scripts/test_security_dependency.py` exit 0、3 项通过；两个插件元数据和 CHANGELOG 均为 7.0.0，包内探针可运行。这是同一执行者的打包检查，不是独立 Validate 或真实扫描。
- `ENV_BLOCKED`：当前 T3 Codex 会话没有符合项目约束的独立验证执行者；Review 也没有独立执行上下文。未声称验证或评审已独立完成。
- `INCONCLUSIVE`：真实扫描链路和 Agent 按需提醒仍未实际演练；本机 CLI 未发现，插件、认证及外部模型可用性未验证。
- 必要验证未满足，记录为 fail；保留 Task `done`，不因执行环境缺口重开实现。等待满足条件后重验，再评审和发布。

### 2026-11-15 独立验证 — f220f6b0f4e459c3bd65d1cafab1c92a2bdf7a74

- 验证执行者是主会话通过 T3 `delegate_task` 启动的不同执行上下文；宿主回显 `codex / gpt-6.1-terra / xhigh`，但未提供 `executedModel`，实际模型标为未验证。验证前后仓库干净，HEAD 与 `90f9698def2bb3793c6cb58203d301f16f7880ff` 在 `.sdlc-v1/**` 外无差异。
- 16:42:41–16:43:31 +08:00，`PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills` exit 0，176 项测试通过；有一条既有 HTTPError 清理 `ResourceWarning`。`python3 -B scripts/test_security_dependency.py` exit 0，3 项通过；`git diff --check 3093e85725a30078f2666886766ef4175bfb1d20 HEAD` exit 0。
- 使用本机离线缓存的 coverage.py 7.17.2 和临时配置执行探针测试、合并和报告，均 exit 0：20/20 行、5/6 分支，综合 96%；父进程有 `no-data-collected` 提示，子进程数据已合并。`git archive HEAD` 的临时源码包内探针测试通过，版本元数据及 CHANGELOG 均为 7.0.0；临时目录已清理。
- `IMPLEMENTATION_FAILED`：README 安全扫描使用入口缺少稳定 story/scenario ID 和指向对应产品故事的导航，与软件交付全局 usage 契约不符，需补充后重验。
- `INCONCLUSIVE`：实际 Agent 在普通工作、选用其他工具及需要 Codex Security 三种情况下的提醒行为，以及扫描证据消费和 review 复用，尚未演练。离线探针和文本检查不能代替这些行为证据。
- 真实模型扫描 `NOT_RUN`：产品成功标准未自动要求本 Feature 运行真实模型扫描；若后续按实际风险选择其为必要项，仍须实际完成或提供契约允许的等效证据。CLI 未发现，插件、版本及认证未知。
- 纠正此前环境归因：Codex 原生子代理限制不等于 T3 无法调度独立子任务，本轮验证实际通过 T3 子任务执行；该事实不自动证明独立 Review 或验证通过。按本轮结果通过 lifecycle CLI 记录 `fail`，Review / Release 保持 pending。

### 2026-11-15 修复与实际 Agent 场景 — 44bfc27e58278a38ec28a4eeb24f27a33917bb91

- 修复 README：`SCN-security-scan` 导航至既有用户场景和成功标准。修复时 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills` exit 0、176 项测试通过；README 场景 ID、两个链接及对应标题检查通过，`git diff --check` exit 0。这是 Build 检查，仍须独立重验。
- 普通 Feature 状态查询：实际 T3 Agent 在该候选版本读取 `skills/sdlc/SKILL.md` 并查询状态，轨迹中未运行 Codex Security 探针，回复没有安装提醒。[轨迹](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Afafbc420-4f41-4062-827b-070dc4ecb589)。
- 选择 Semgrep 的只读验证准备：实际 T3 Agent 读取 `sdlc-validate` 和 `security-scan` 等文件，轨迹中未运行 Codex Security 探针，回复没有安装提醒；轨迹未见单独读取 router 正文。[轨迹](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3A2adf4859-66e9-4b2c-a424-59c8c5512e28)。
- 实际选用 Codex Security 的准备检查：Agent 读取 router 与适配说明，运行 `PYTHONDONTWRITEBYTECODE=1 python3 skills/sdlc/scripts/check_security_dependency.py`，输出 CLI `not_found`、插件/版本/认证 `not_checked`、扫描 `not_run`；回复给出普通安装入口，并保留版本及认证未知。轨迹中未见安装、登录或扫描。[轨迹](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Ab90315fe-28dc-4020-a112-b5fda1139c75)。探针没有检查插件；Agent 的插件状态说明不代替可加载性验证。
- Synthetic 结果消费：Agent 读取上游示例并核对产物 SHA-256，指出覆盖和处置缺口；目标版本不匹配或缺少产物均为 `INCONCLUSIVE`，同版本 review 复用适用证据而不默认重复扫描。[完整和版本不匹配场景](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Ab40b726b-ac3c-46bd-9777-84e9552c54d8)；[实际缺失 manifest/findings 场景](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Af7c90763-a085-413b-a50c-e2ce5c203d9f)。缺失样本由上游 `173483d7c658be7a512c93d9559bf01a05d5b196` 示例分别复制并省略一文件构造；自建临时目录已核对并清理。
- 以上各场景均请求 `codex / gpt-6.1-terra / xhigh`，宿主未提供 `executedModel`，实际模型未知。T3 轨迹由当前宿主持有，跨宿主可访问性未验证。合成产物和这些 Agent 行为不证明真实扫描已运行或通过；真实扫描仍为 `NOT_RUN`。

### 2026-11-15 独立重验 — 44bfc27e58278a38ec28a4eeb24f27a33917bb91

- 17:20:31–17:21:20 +08:00，独立 T3 上下文执行 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills`，exit 0，176 项测试及结构检查通过；既有 HTTPError 清理 `ResourceWarning` 仍出现。`python3 -B scripts/test_security_dependency.py`、`git diff --check`、README 场景 ID/链接核对、源码包内探针测试与 7.0.0 版本一致性核对均通过。
- 验证者复核了上述实际 Agent 轨迹及 synthetic 消费边界，确认 README 导航缺口已修复；真实扫描仍为 `NOT_RUN`。当前宿主报告的执行上下文为 `codex / gpt-6.1-terra / xhigh`，但 `executedModel` 为 null，实际后端模型未证实。
- `INCONCLUSIVE`：验证者认为实际模型元数据缺失导致必要执行者条件尚不能确认，按其请求记录 validation `fail`；没有发现新的 `IMPLEMENTATION_FAILED`。完整检查时间、命令和结果见[独立重验轨迹](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3A16e5cada-5bff-48d9-8308-fafce8d3f34e%3Adelegate-task%3Ae02d7050-a36d-4103-a80e-bc4533cca934)，跨宿主可访问性未知。

## 评审记录

已由实现者对相关代码、路由、权限和缺口做串行自查；不称独立评审。正式 Review 为 `NOT_RUN`，当前会话不具备符合项目要求的独立评审上下文。

## 发布与观察记录

NOT_RUN；产品观察计划见对应产品上下文。
