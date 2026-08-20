# Lightweight SDLC 1.1

- **日期**：2026-08-17
- **状态**：Accepted
- **版本**：1.1.0

## 1. 问题

0.x 后期在流程技能之外叠加了多套状态、协作和校验机制。它们分别有合理来源，但叠加后出现三个问题：

1. agent 推进一次普通工程修改时，需要反复证明并同步同一个事实；
2. 本机状态、目标仓库状态和 Git 状态之间容易出现不必要的分叉；
3. 多 clone 协作本应由 Git 解决，却又要理解一套独立传输与并发协议。

1.0 的目标不是减少产品设计、测试或评审质量，而是让同一个事实只保存一次。

## 2. 设计原则

1. **一个机器状态源**：目标仓库 `.sdlc-v1/state.json`。
2. **一个协作机制**：普通 Git branch、commit、push、pull/merge。
3. **上下文保持可读且可定位**：产品、工程上下文写在 `.sdlc-v1/context/*.md`，由 state 显式引用。
4. **方法论按需加载**：阶段 skill 决定流程，角色卡提供专业视角。
5. **不把语义伪装成校验值**：产品判断和评审结论由人/agent 明确记录，不用内容哈希代替理解。
6. **只保留高收益一致性检查**：状态 schema、合法转换、依赖、当前 Git HEAD 与验证/发布记录的一致性。
7. **长期上下文与当前迭代分层**：可选的 repository context 只提供当前 commit 已验证的路径索引；当前 Requirement/Feature 的决策、证据和发布后效果只写 lifecycle context。

## 3. 存储模型

```text
<target-repo>/.sdlc-v1/
├── state.json               # sdlc-lightweight-state-v1, state_version=3
└── context/                 # Requirement/Feature 必填引用只能落在这里
    ├── product.md
    ├── engineering.md
    └── decisions.md
```

### 3.1 state.json

状态只包含：

- Requirement：id、标题、简述、领域、优先级、依赖、状态、产品上下文引用和关联 Feature；
- Feature：id、Requirement、branch、状态、工程上下文引用、Task、validation、review、release；
- Task：id、标题、依赖和状态；
- validation/review/release 的最小摘要。

状态不包含 PRD 全文、设计全文、完整测试日志或完整评审意见。

### 3.2 Markdown 上下文

上下文文件没有固定正文模板，但路径和引用有强约束：

- `product_context_ref` / `engineering_context_ref` 必须是规范化的仓库相对路径；
- 路径必须以 `.sdlc-v1/context/` 开头、以 `.md` 结尾；
- 文件必须已经存在，是普通文件且路径中没有符号链接；
- 项目其他文档可以继续存在，但不能直接充当 lifecycle context ref。

正文建议按问题拆文件：

- 产品：用户问题、行为场景、范围、验收标准、领域语言；
- 工程：架构方案、接口、数据迁移、测试策略、可靠性与安全判断；
- 决策：仍有效的取舍、原因和后续约束。

### 3.3 长期工程上下文（可选）

仓库可以同时维护 `AGENTS.md`、目标/产品/架构/开发文档，以及由 `repo-context-creator` 生成的
`.repo-context/evidence.json` 和 `manifest.yaml`。SDLC 不依赖其脚本、格式或写入能力：`sdlc-onboard` 只有在
manifest/evidence 的 `analyzedCommit`、`evidenceDigest` 彼此一致且等于当前 `HEAD` 时，才把其中的 canonical 路径索引到
`project.md`。其他情况记录 `stale` 或 `none` 并回退到源码扫描。

两类内容的所有权固定如下：

- 长期文档：项目方向、产品契约、架构、可复用工程约束和贡献说明；
- `.sdlc-v1/context/*.product.md`：当前 Requirement 对长期方向的引用、预期结果、指标和验收；
- `.sdlc-v1/context/*.engineering.md`：当前 Feature 的设计/Task、验证/发布证据和发布后效果观察；
- `.sdlc-v1/state.json`：唯一机器进度状态，不由 repo-context 读取或写入。

## 4. 生命周期

### 4.1 产品侧

```text
captured → ready → in_delivery → validated → released
```

- `capture-requirement` 捕获一条产品需求，并绑定已有的 `.sdlc-v1/context/*.md` 产品上下文；
- `revise-requirement` 修订尚未绑定 Feature 的 `captured` Requirement；
- `cancel-requirement` 取消尚未绑定 Feature 且没有活动依赖方的 backlog 项，并保留历史；
- BDD/战略 DDD 澄清后，用 `mark-requirement-ready` 表示可以交付；
- 产品侧读取 Feature 投影了解研发进展，不维护第二份研发状态。

### 4.2 研发侧

```text
Feature: planned → in_progress → validated → reviewed → released
Task:    todo ↔ in_progress → done
```

- `start-feature` 把一个 ready Requirement 绑定到实际开发分支和已有的 `.sdlc-v1/context/*.md` 工程上下文；
- `add-task` / `set-task-status` 维护实现任务与依赖；
- SDD/TDD 的正文和测试仍在普通项目文件中；
- `record-validation`、`record-review`、`record-release` 只记录最小结果；
  `released` 表示声明发布目标及其约定 smoke、观测完成，不等于合入主分支。
  发布目标可以是明确约定的源码分发，也可以是环境部署。
- `retract-release` 只纠正历史误记：要求原因，把 Feature 恢复为
  `reviewed`、Requirement 恢复为 `validated`，不替代正常发布失败或回滚。

一个 state 可以同时容纳多条 Requirement、Feature 和 Task。实现层只约束“一条 Requirement 只能绑定一个
Feature”，不限制整个项目同时追踪的需求数量。

## 5. Skill 加载

`sdlc` driver 只判断三件事：用户意图、当前 state 投影、Git 改动面。

```text
用户意图 / state
       │
       ├─ 产品问题 ──> sdlc-product-design ──> backlog/spec
       └─ 研发动作 ──> sdlc-software-delivery ──> plan/build/validate/review/ship
                                                │
                                                └─ 按 diff 加载相关角色卡和验证模式
```

普通阶段技能仍可直接调用。生命周期入口是编排层，不复制 spec、plan、build 等阶段的正文。

角色路由仍以 `references/role-routing.md` 为单一事实源。改前端加载 client-dev/design；改 API 加载
server-dev；跨多个面加载 architect；验证阶段按 correctness/e2e/eval-bench 选择 playbook。

### 5.1 查询与只读投影

`lifecycle_state.py next` 是公开恢复查询：

- 没有 Requirement 时返回 `intake`；
- 只有一个活动候选时按状态返回 `spec/plan/build/validate/review/ship`；
- 多个活动 Feature 或同状态 Requirement 并存时返回 `needs_selection` 和稳定排序的 candidates；
- 全部 Requirement 终态时返回 `done`。

`backlog.py` 只读取 state，提供 `readyqueue`、`coverage`、`lint`、`tree`、`board` 五个 projection。前四个不写文件；
`board` 只写可重建 HTML，不得改变 state。`lint` 检查 state/context 是否存在并已由 Git 追踪。

## 6. Git 协作

### 6.1 A 提需求，B 实现

1. A 在产品上下文中写清需求并更新 state 到 `ready`。
2. A 将上下文和 `.sdlc-v1/state.json` 一起 commit/push。
3. B 在另一 clone pull，执行 `start-feature`，建立 Feature/Task 并开发。
4. B 提交业务代码，在该 commit 上验证，再提交 state、工程上下文和验证证据并 push。
5. 评审者 pull，确认 validation commit 到当前 HEAD 没有 `.sdlc-v1/**` 之外的差异，记录 review 后提交并 push。
6. 发布者 pull，发布 validation commit；成功后记录 release。

### 6.2 同时修改

state 是普通 JSON。如果两条分支修改不同记录但产生文本冲突，合并者按业务事实解决冲突，再运行
`test_lifecycle_state.py` 或完整 `validate-skills`。不引入额外协调服务或专用分支协议。

### 6.3 本地连续迭代

同一工作会话内可以连续更新 state，不要求每次状态变化都提交。需要跨机器交接、团队同步或形成代码里程碑时，
再和相关代码/文档一起 commit。这样 Git 历史保持有意义，而不是充满机械状态事件。

## 7. 一致性规则

保留以下轻量规则：

- JSON schema 和 ID/status 取值必须合法；
- state schema 固定为 `sdlc-lightweight-state-v1` / `state_version=3`；
- Requirement/Task 依赖必须存在并满足顺序；
- Feature 必须来自 ready Requirement；
- 产品/工程 context ref 必须位于 `.sdlc-v1/context/*.md` 且目标文件真实存在；
- validation 通过前 Task 必须完成；
- validation 前 state 必须已由 Git 追踪、没有 unmerged index entry 且未 staged；
- validation 保存测试时的 Git HEAD；review/release 要求当前业务代码与该 commit 一致；
- `.sdlc-v1/**` 的状态/上下文交接提交不使验证失效，其他路径变化后必须重新验证；
- repo-context、`AGENTS.md` 或长期文档的变更不属于 `.sdlc-v1/**`；若属于当前 Feature，须在 validation 前完成，否则单列维护 Requirement 或重新验证；
- validation/review/release 时业务代码工作树必须干净，state 和当前 context 必须已追踪且无冲突；
- 写入采用本机文件锁和原子替换，避免同一 clone 的并发进程破坏 JSON；
- 已 staged 的 state 不被后台写入覆盖。

这些规则保护当前事实，不创造第二套历史系统。

### 7.1 初始化时的旧 hook 检测

`init` 必须定位目标仓库的实际 Git hooks 目录，检查 `pre-commit`、`pre-push`、`post-checkout` 和 `sdlc-guard`。
发现 0.x sdlc-pilot copied hook 标记时返回名称与目录并停止，不自动删除或覆盖。用户必须人工检查：纯旧副本可以删除；
混有团队逻辑的 hook 只移除旧 SDLC 片段，保留其他内容，再重新执行 `init`。

## 8. 0.x 升级边界

1.0 不执行 0.x 协议，也不做自动迁移。旧文件是普通历史资料，不读取、不改写、不删除。升级时由用户挑选仍有
价值的内容，整理到 `.sdlc-v1/context/*.md`，人工清理 `init` 报告的旧 copied hooks，再初始化 state 并重新建立
当前 Requirement/Feature。具体移除项只在 `CHANGELOG.md` 保留。

## 9. 验证策略

提交前只运行：

```bash
bash scripts/validate-skills
git diff --check
```

`validate-skills` 包含：

1. 关键运行时、阶段、角色和验证模式存在性；
2. SKILL frontmatter；
3. role/mode/language 路由登记；
4. 本地 Markdown 引用；
5. 可移植性文本检查；
6. lifecycle state、backlog/board、contrast 三组测试。

产品内 AI 功能的 `eval-bench` 与本地 Web Review Live 仍是有效方法论/体验。

## 10. 验收标准

- 新 Git 项目可由 `init` 创建 `state_version=3` 的 `.sdlc-v1/state.json`；
- 捕获 Requirement/开始 Feature 前，相关 `.sdlc-v1/context/*.md` 已存在并被 state 引用；
- A 在机器 1 提交 ready Requirement，B 在机器 2 pull 后可直接 start Feature；
- state 可同时追踪多条产品需求和研发任务；
- `next` 对单候选确定路由、对多候选明确请求选择；
- backlog/board 五个命令只生成 projection；
- validation 前 state 已 tracked、无 unmerged entry 且未 staged，当前 context 已 tracked 且无冲突；
- validation 后只提交 `.sdlc-v1/**` 可继续 review/release，业务代码变化则要求重新验证；
- onboard 可在有或没有 repo-context 的仓库工作；当前 commit 对齐时只读取其路径索引，过期时回退源码扫描；
- 产品/工程上下文分别记录方向来源和发布后效果观察，且不重复长期文档正文；
- 遗留 copied hooks 未清理时 `init` 明确停止且不改写 hook；
- 所有 stage skill、role card、validate mode 和上下文 Markdown 能继续独立使用；
- 仓库结构检查与三组核心测试在本地快速完成。
