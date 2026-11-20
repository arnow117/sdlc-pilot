# Lightweight lifecycle runtime

## 1. 目标

`.sdlc-v1` 只负责跨会话、跨协作者和跨 clone 的最小交接信息。Git 是历史与同步机制，Markdown 是产品和研发正文，`state.json` 是进度索引。

```text
.sdlc-v1/
├── state.json
├── project.md
└── context/
    ├── <requirement-id>.product.md
    └── <feature-id>.engineering.md
```

所有文件都由 Git 跟踪。不要为每次状态变化单独提交；在交接、同步、验证或发布节点，与相关文档和代码一起正常提交。

暂停、跨对话恢复或更换执行环境时，才可额外使用唯一的
`.sdlc-v1/checkpoints/<feature-id>.md`。它不是默认目录成员、进度状态或日志；固定形状、恢复核对和删除条件只见
[`stage-agent-protocol.md`](stage-agent-protocol.md#6-context-and-checkpoints)。

## 2. 职责边界

| 文件 | 保存什么 | 谁维护 |
|---|---|---|
| `state.json` | ID、关系、状态、分支、上下文引用、validation commit、review/release 摘要 | `lifecycle_state.py` |
| `project.md` | 技术栈、入口、约定、surface map、测试命令、风险、部署线索 | `sdlc-onboard` |
| `*.product.md` | 用户问题、场景、规则、范围、质量要求、验收条件 | 产品侧 |
| `*.engineering.md` | 设计、代码位置、Task、测试策略、风险、工程决策与交付摘要 | 研发侧 |

`state.json` 不复制 Markdown 正文；Markdown 不声明进度。进度查询永远读取 state CLI 的输出。

## 3. 初始化

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> init
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> status
```

已有源码的项目随后运行 `sdlc-onboard` 创建 `project.md`。若 `init` 报告旧版 sdlc-pilot Git hook，先按错误给出的 hooks 目录手动删除对应文件，再重新初始化。

## 4. 产品侧

先创建 `.sdlc-v1/context/<REQ-id>.product.md`，再登记 Requirement：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  capture-requirement --id <REQ-id> --title <title> \
  --description <summary> --domain <domain> --priority <P0-P3> \
  --product-context-ref .sdlc-v1/context/<REQ-id>.product.md
```

依赖使用 `--depends-on <REQ-id>`。产品上下文通过确认后：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  mark-requirement-ready --requirement-id <REQ-id>
```

## 5. 研发侧

先创建 `.sdlc-v1/context/<FEAT-id>.engineering.md`，再关联 ready Requirement：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  start-feature --requirement-id <REQ-id> --feature-id <FEAT-id> \
  --branch <branch> \
  --engineering-context-ref .sdlc-v1/context/<FEAT-id>.engineering.md
```

建立与推进 Task：

```bash
lifecycle_state.py --repo <repo> add-task \
  --feature-id <FEAT-id> --task-id <TASK-id> --title <title>

lifecycle_state.py --repo <repo> set-task-status \
  --feature-id <FEAT-id> --task-id <TASK-id> --status in_progress

lifecycle_state.py --repo <repo> set-task-status \
  --feature-id <FEAT-id> --task-id <TASK-id> --status done
```

Task 可带 `--depends-on <TASK-id>`。依赖未完成时不能开始下游 Task。

### Task 状态错误输出与恢复

`set-task-status` 的 `LifecycleStateError` 继续在 stderr 首行输出既有错误码，格式为
`lifecycle-state-error: <existing-code>`，退出码仍为 `2`，且不写 stdout。该命令的失败会紧随其后输出一行
`error-details: <JSON>`，供人和调用方判断恢复步骤；其他命令的成功 JSON 和错误输出不因此改变。

JSON 始终包含 `message`、`hint`、`effect`、`operation`、`feature_id`、`task_id`、`current_status`、
`requested_status`、`allowed_next` 与 `state_changed`。可选的 `feature_status` 和 `unmet_dependencies` 分别说明
Feature 已关闭和未完成的前置 Task。Python API 继续以原错误码作为 `str(exc)`，详情仅是附加信息。

- `state_changed: false` 只表示明确的写入前拒绝：非法 Task 转换、未完成依赖或关闭的 Feature。`allowed_next` 是当前
  Feature 状态和依赖约束下可行的下一状态，按字母顺序排列，不包含幂等的当前状态；未完成依赖会排除 `in_progress` 和
  `done`，已关闭 Feature 或已取消 Task 则为 `[]`。这类拒绝不会写入 state。
- `state_changed: "unknown"` 表示写入结果无法确认，例如原子替换已经完成后目录同步失败。它不是“没有可行转换”：
  `current_status` 和 `allowed_next` 会是 `null`。先执行 `feature-projection` 和 `next` 的只读查询，再决定是否继续；
  不要根据退出码或错误码名称推断 state 未变化，也不要按旧参数盲目重试。

Task 从 `done` 重新开始必须先走合法的 `done → todo → in_progress`。`done → todo` 会清除该 Feature 的
validation、review 和 release 记录，之后需要重新完成交付检查。review 返回 `changes_requested` 时，`next` 会进入
build，但不应自动重开 Task；只有确认需要实现修复时才按上述转换重开相关 Task。validation 为 `fail` 而所有有效
Task 仍为 `done` 时，`next` 仍是 validate，用于补充证据或解决环境问题；`ENV_BLOCKED` 不自动要求重做实现。

### 5.1 开发分支登记迁移

Feature 的 `branch` 是协作登记，不是 checkout 指令。登记与实际开发 worktree 不一致时，主 Agent 或独立维护者先让同一
Feature 的活动写入者交接或停止，并在该 Feature 工程上下文的实施决定/证据中预先保存迁移决定、完整参数、原因和预期
HEAD；随后才可在实际目标 worktree 执行：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  migrate-feature-branch --feature-id <FEAT-id> \
  --expected-branch <stored-old-branch> --branch <checked-out-local-branch> \
  --expected-head <full-current-commit-id> --reason <pre-recorded-decision>
```

命令不 checkout 代码、不接受 Task、不修改 Markdown。它只对未 `released`/`cancelled` 的 Feature 生效：旧登记必须精确匹配
`--expected-branch`，新 branch 必须是不同的、已检出的显式本地分支，`--repo` 必须是实际 Git worktree 根目录，且当前附着
branch 和完整 HEAD 必须与参数匹配。它拒绝 detached/unborn checkout、Git 的仓库/index/对象/config 重定向环境，以及缺失或
符号链接的工程上下文；普通 linked worktree 可以使用。

既有 state 锁、staged/unmerged 拒绝、文件身份检查和原子替换继续适用；锁内再次检查旧登记与 worktree 身份。成功时只修改
目标 Feature 的 `branch` 和 `updated_at`，返回旧/新 branch、实际 HEAD、规范根目录、原因、时间和工程上下文引用，不重置
Task、validation、review 或 release。写入前的拒绝保持 state 不变；原子替换后的目录 fsync 或 CLI 输出失败可能已经写入，必须
先只读查询 state 与 Git 再恢复，不能把错误退出自动重试为旧值迁移。成功后把返回的实际结果追加到同一工程上下文。

查询和现有 validation/review/release 不要求登记 branch 与当前 checkout 一致；它们仍按被验证实现 commit 的既有规则判断。
若迁移后的实现不同，review/release 仍会要求适用的重新验证，不能借迁移绕过版本检查。

| 执行用途 | 分支与版本如何核对 |
|---|---|
| 只读查询/恢复定位 | 读取 state 和上下文；当前分支不同或 detached 不阻止查询，也不自动迁移。 |
| 开发/Build | 登记 branch 表示本 Feature 的开发位置；核对实际 root、branch、HEAD，必要时交接并显式迁移后再派工。 |
| 发布目标 | 是声明的源码分发或部署目标；目标分支可以不同于开发分支，按 validation commit、代码差异和 smoke/观测要求验收，不为发布统一改历史 branch。 |
| detached 验证/评审环境 | 使用明确的实现 commit，继续满足 tracked/clean-worktree 等既有条件；不把 detached 当成待登记的开发分支。 |

派工 brief 分别写明登记的开发分支、实际执行 root/branch（或 detached）/HEAD、执行用途和发布目标；不要用一个 branch 字段替代这些信息。
迁移前保持目标 worktree 身份稳定，等待或停止同 Feature 写入者并处理未验收结果；现有 state 文件锁不锁 Git，也不提供跨 clone 的事务。

## 6. 验证、评审与发布

```bash
lifecycle_state.py --repo <repo> record-validation \
  --feature-id <FEAT-id> --result pass --test-command <command>

lifecycle_state.py --repo <repo> record-review \
  --feature-id <FEAT-id> --decision approved --by <reviewer>

lifecycle_state.py --repo <repo> record-release --feature-id <FEAT-id>
```

- 验证前，`state.json`、产品上下文和研发上下文必须已经纳入 Git，且 state 没有合并冲突。
- 通过验证前，全部有效 Task 必须完成。
- 验证保存当前 Git commit 作为实现版本；业务代码工作树必须干净。
- 验证后可以提交 `.sdlc-v1/**` 来交接状态、上下文和证据；这种提交不使验证失效。
- 评审和发布要求 validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外没有代码差异。
- 代码变化或 Task 重新打开后，需要重新验证。
- Feature 分支是协作提示；最终事实是被验证和发布的 commit。
- `record-release --commit` 显式登记实际交付并被验证的版本。它必须等于 `validation.commit`；
  不匹配时返回 `release-commit-does-not-match-validation`，不写发布记录。`validation.commit=A`
  而 HEAD 仅因状态/上下文交接变为 B 且全仓等价时，仍登记 A。

### 6.1 记录拒绝时清除的快照

各验收点的指纹快照随对应结论一起存在，记录拒绝或重开时按既有规则清除：

| 操作 | 清除的快照 | 保留 |
|---|---|---|
| `record-validation --result fail` | `validation`、`review` | `plan`、`spec_ready` |
| `record-validation --result pass` | `review`（并重置 review/release 记录） | `plan`、`spec_ready`，新增 `validation` |
| `record-review --decision changes_requested` | `review` | `validation`（即使因追加记录而 `stale`）、`plan`、`spec_ready` |
| `record-review --decision approved` | 无 | 全部，并新增 `review` |
| Task `done → todo` 重开 | `validation`、`review` | `plan`、`spec_ready` |

因此拒绝路径可以先于通过型重记执行：写评审记录使 `validation` 指纹 `stale` 时，
`record-review --decision changes_requested` 仍可成功，它不清掉 `validation.result=pass`，
也不补签 `validation` 快照。

## 7. 查询与恢复

```bash
lifecycle_state.py --repo <repo> status
lifecycle_state.py --repo <repo> next
lifecycle_state.py --repo <repo> readyqueue
lifecycle_state.py --repo <repo> product-projection --requirement-id <REQ-id>
lifecycle_state.py --repo <repo> feature-projection --feature-id <FEAT-id>
```

`next` 在只有一个明确目标时返回下一阶段；并行工作超过一个时返回 `needs_selection` 和候选项，不替用户猜选。恢复加载顺序遵循[阶段协议 §6](stage-agent-protocol.md#6-context-and-checkpoints)；上述查询仍可用于普通只读定位。

### 7.1 验收内容指纹核对

四个验收点（`spec_ready`、`plan`、`validation`、`review`）在对应合法操作发生时，把该点实际引用的
product/engineering context 内容快照（SHA-256，`normalization: context-v1`）记入 state：`spec_ready`
绑定该 Requirement 的 product context；`plan`/`validation`/`review` 绑定同一对 product/engineering
context。归一化只排除指定生命周期元数据位置（frontmatter 顶层的 `updated_at`/`status`/`document_status`
单行标量、首个正文标题后的 `- 文档状态：`/`**状态**：`/`**上次确认**：` 整行），其余内容字节敏感参与比较。

引用已验收结论前先做只读核对：

```bash
lifecycle_state.py --repo <repo> verify-acceptance --requirement-id <REQ-id>
lifecycle_state.py --repo <repo> verify-acceptance --feature-id <FEAT-id> --point plan
```

`--requirement-id` 与 `--feature-id` 互斥且必须给一个；requirement 目标只查 `spec_ready`，feature
目标默认查全部四点，`--point` 可选单点。查询不写 state、context、缓存或锁文件，不初始化缺失目录。

结果 JSON 形状为 `{target_type, target_id, result, points}`；`points` 每项是 `{point, result, files}`，
`files` 每项含 `path`、`expected_digest`、`current_digest`（文件缺失时为 `null`）和 `reason`
（`match`/`content-drift`/`ref-added`/`ref-removed`/`missing-file`）。总体 `result` 按 `stale` >
`missing` > `match` 聚合：`stale` 退出码为 1（JSON 仍输出到 stdout），`match`/`missing` 为 0；
argparse 参数错误（缺少选择器、非法 `--point` 等）以 usage/error 形式报告并以退出码 2 退出，不带
`lifecycle-state-error:` 前缀；状态与读取错误沿用 `lifecycle-state-error:` 前缀及退出码 2。消费方应解析
JSON，不靠退出码 0 推断 `match`。

| 结果 | 含义与后续动作 |
|---|---|
| `match` | 该点有合法记录，绑定内容与验收时一致；可继续引用，仍须满足既有测试、授权与代码 commit 绑定条件。 |
| `stale` | 绑定文件内容、路径或引用集合漂移；工具返回结果与退出码 1，暂停依赖该旧结论的工作，列出 `files` 中的漂移文件与原因。按[批准归属与委托](stage-agent-protocol.md#批准型重记独占与读回)核对原批准及权限：原责任人可重新批准，主 Agent 在已有且可证明的委托范围内可复核重记；缺少适用权限时再请求责任人决定。 |
| `missing` | 该点没有指纹记录（旧 Feature 或该点尚未发生）；明示"未绑定内容，未验证当前适用性"，不报错也不阻断既有流程，不当作已核验，不自动补记录。 |

恢复故事：引用批准 → `verify-acceptance` 查询 → `match` 继续、`stale` 暂停并说明差异、`missing`
如实说明未绑定 → 有权责任人按适用批准或可证明的委托显式重记或补验。显式重记只对已有快照的同一验收点生效：

```bash
lifecycle_state.py --repo <repo> mark-requirement-ready --requirement-id <REQ-id> --refresh-acceptance

lifecycle_state.py --repo <repo> start-feature --requirement-id <REQ-id> --feature-id <FEAT-id> \
  --branch <branch> --engineering-context-ref .sdlc-v1/context/<FEAT-id>.engineering.md \
  --refresh-acceptance
```

#### 选择器与重记参数

按验收点选择适用的选择器：

| 验收点 | 选择器 | 说明 |
|---|---|---|
| `spec_ready`（Feature 尚未登记） | `--requirement-id <REQ-id>` | Requirement 选择器只接受 `spec_ready` |
| `spec_ready`（Feature 已登记） | `--requirement-id <REQ-id>` 或 `--feature-id <FEAT-id>` | 两者均可；Feature 选择器通过其投影核对关联 Requirement 的产品正文 |
| `plan` / `validation` / `review` | `--feature-id <FEAT-id>` | Feature 必须已登记 |

`--requirement-id` 配 `--point plan` 返回 `invalid-acceptance-point`；未登记的 `--feature-id`
返回 `feature-not-found`。两种合法选择器查同一 `spec_ready` 时得到同一产品文件的路径和摘要，
只是 `target_type` 不同，且都不写 state 或上下文。

`start-feature --refresh-acceptance` 要求 `--requirement-id`、`--feature-id`、`--branch` 和
`--engineering-context-ref` 与现有登记完全相同，否则返回 `feature-identity-mismatch` 且 state
不变。已有分支迁移后（例如从 `main` 迁到 `feature/fix`），重记必须传**新登记值**；传历史
`main` 会得到 identity mismatch。原批准正文与授权仍追溯至原点，不因迁移产生新授权。

#### 重记前的核对步骤

重记是批准型操作，按
[阶段协议 §5 的批准型重记、独占与读回](stage-agent-protocol.md#批准型重记独占与读回)执行。
CLI 侧的机械事实：

1. 用上表的有效选择器查询，取得结构化 `files`（每个绑定路径的 `expected_digest`、
   `current_digest` 和 `reason`）。
2. 对仅追加证据的主张，从 `git show <approved-commit>:<bound-path>` 取原始字节，用既有
   `_context_digest` 计算并与 `expected_digest` 比较；不通过当前 HEAD 猜测批准正文。
3. 写者独占由主 Agent 通过既有写者交接确认，不由 CLI 强制。
4. 调用后读回 Feature/Requirement 投影与相应 `verify-acceptance`，逐项比较保存的路径集合、
   `expected_digest`、`current_digest` 和绑定身份。`match` 只表示已存内容等于这次查询读到的
   内容，不能替代与事先核准值的比较。

CLI 的 state 锁和内部多次读取不提供跨核准与写入的原子 compare-and-swap；并发写入造成的
映射误绑定只能靠主 Agent 的独占与读回比较发现，不能靠 CLI 预防。

`--refresh-acceptance` 只刷新既有 `spec_ready`/`plan` 快照：不改变进度、Task 或 Feature 登记身份
（start-feature 重记要求全部参数与现有登记完全相同），不创建新 Feature，不填补 missing 历史，也不
替代未覆盖的验证义务；真正的产品范围变化按既有 backlog 规则新建 Requirement。validation 失败、
`changes_requested` 或 Task reopen 撤销通过记录时同步移除对应快照；重记 spec/plan 不清除下游快照，
让后续核对仍能看到 stale。

指纹是机械漂移检测：`match` 只证明本次读取的 context 内容自验收后未变，不证明测试已执行、批准已获
授权或语义仍覆盖当前要求；语义适用性判断与授权仍按
[阶段协议](stage-agent-protocol.md#context-prose-and-evidence-applicability)执行。并行编辑不受 state
锁约束，核对通过只证明本次读取；正式引用前主 Agent 重查。旧版工具不保证读取含 acceptance 字段的
state，跨机器消费指纹记录前先同步工具版本。

## 8. 两台机器交接

```text
机器 A：更新产品上下文 → Requirement ready → commit → push
机器 B：pull → 创建 Feature/研发上下文 → 实现 → commit → 验证 → 提交 state/context → push
机器 A 或 B：pull → 评审 → 提交 state/context → pull → 发布
```

若两台机器同时修改 `state.json`，使用普通 Git 合并冲突流程处理；不要另外生成第二份状态文件。
