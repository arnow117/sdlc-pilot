# 工程上下文：FEAT-security-scan

## 当前有效方案

### 架构设计

**Requirement**：`REQ-security-scan`；产品规则与验收场景唯一见对应产品上下文。
**规划基线**：2026-11-15，仓库 `main` 的 `3093e85725a30078f2666886766ef4175bfb1d20`；开始时业务工作树干净。`project.md` 的历史版本/测试数是旧事实，不视为当前检查结果。
**执行环境**：当前 T3 Codex 为 `gpt-6.1-terra / max`；用户在已知限制后要求当前会话继续。阶段工作按可用的串行路径进行，不将该路径称为独立验证或独立评审。
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
- 首选实现 provider 与独立执行环境在当前会话未建立；当前用户要求直接推进不构成对外额度、安装、发布、提交或伪称独立验证的授权。真实调用、正式 commit 绑定及独立评审存在缺口时停止相关完成声明。

### 实施计划

一个纵向 Task 覆盖用户场景 1–5：先实现只读依赖探针与缺失/候选测试，作为最早可检验结果；再接通入口提醒、风险路由、validate/review 和工具适配。以 `scripts/validate-skills`、探针行为测试和 `git diff --check` 验证本次快照；测试替身不证明真实扫描效果。

| 产品验收 | 设计/契约 | 计划验证 |
|---|---|---|
| 依赖缺失、候选与未知不混淆，按需提示安装 | 只读探针 + 选用 Codex Security 时检查 + 适配说明 | 隔离 PATH 的进程测试；直接运行本机探针，人工核对非适用场景不要求检查 |
| 安全扫描按风险执行，验证与 review 复用证据 | role routing、security-scan mode、Codex Security 适配与阶段引用 | 仓库结构/引用检查，按实际文件审查成功、缺口和失败场景 |
| 不泄露凭据、不把未运行写通过 | 探针不读取/显示凭据；验证归因与报告纪律 | 敏感环境变量测试、规则与失败场景核对 |
| 已有生命周期兼容 | 不修改 state schema 和验证 CLI | 现有生命周期回归；检查 diff |
| 发布候选版本一致 | `CHANGELOG.md` 与两个 `.claude-plugin` 元数据 | 解析 JSON 并核对三个版本值与 CHANGELOG 的 7.0.0 记录；候选未通过验证前不发布 |

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

当前缺口：正式独立 Validate 所需的干净业务代码 commit 尚无；CLI/插件、登录与真实扫描未运行；Agent 是否实际按提示完成检查尚无真实演练。实际安全扫描和模型调用必须按既有授权另行执行。

### 2026-11-15 验证尝试 — f11241a6d6d5506dce8230b3c5034dc3cb529fff

- `git archive` 从上述提交生成新解包目录，在该目录执行 `bash scripts/validate-skills`：exit 0，176 项测试通过；包内探针可运行。该检查由实现者串行执行，不是独立 Validate。
- `ENV_BLOCKED`：当前 T3 Codex 会话受项目既有 no-spawn 约束，尚无符合角色要求且与实现者独立的验证执行者；当前实际模型为 `gpt-6.1-terra / max`。
- `INCONCLUSIVE`：真实 Codex Security CLI、认证、模型调用以及 Agent 对按需提醒的实际行为尚无本版本运行证据；本机探针未发现 CLI，插件与认证未检查。之前的源码和合成测试不能代替真实执行。
- `IMPLEMENTATION_FAILED`：用户现要求将行为变更发布到 main，但两个插件元数据仍为 6.0.0，新增记录仍在 `Unreleased`。本仓库 `CLAUDE.md` 要求发布行为变化时按语义化版本同步元数据；须先准备候选版本并重新验证。
- 本轮不满足全部必要条件，整体未通过；不进入 Review/Ship，也不把前述检查称为独立验证。
- 后续修正：在同一执行者的未提交 7.0.0 候选上，版本 JSON 与 CHANGELOG 一致性检查 exit 0，`git diff --check` exit 0，`bash scripts/validate-skills` exit 0、176 项测试通过。原执行者的 Build 检查不能代替独立 Validate；真实扫描和 Agent 演练仍未运行。

## 评审记录

已由实现者对相关代码、路由、权限和缺口做串行自查；不称独立评审。正式 Review 为 `NOT_RUN`，当前会话不具备符合项目要求的独立评审上下文。

## 发布与观察记录

NOT_RUN；产品观察计划见对应产品上下文。
