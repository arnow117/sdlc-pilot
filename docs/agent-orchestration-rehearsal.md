# 跨模块 Agent 编排演练

> 2026-09-15；使用临时 Git fixture 验证，不新增生产模块、消息系统或 lifecycle state 字段。

本演练的需求是“任务所有者可从客户端取消活跃任务；其他用户被拒绝”。它同时覆盖客户端调用、服务端状态改变、
权限隔离和恢复检查。

## 实际执行的 fixture 证据

临时仓库通过 `mktemp -d /private/tmp/sdlc-orchestration-rehearsal.XXXXXX` 创建，并用当前
`scripts/lifecycle_state.py` 初始化。以下是实际结果：

| 动作 | 命令或 revision | 结果 |
|---|---|---|
| 初始化 | `lifecycle_state.py --repo . init` | exit 0；`state_version: 3` |
| 需求到 Task | `capture-requirement` → `mark-requirement-ready` → `start-feature` → `add-task` | exit 0；`REQ-001` 绑定 `FEAT-001/TASK-001` |
| 基线 | `e14b4e8 chore: initialize cancellation feature` | state 和两个 context 已提交 |
| 实现 | `a50525d feat: cancel active task` | `client.py` 调用 `TaskService.cancel`；服务端仅允许 owner 改为 `cancelled` |
| 必要测试 | `python3 -m unittest discover -s tests -v` | exit 0；2 tests passed（成功旅程与权限隔离） |
| 验证记录 | `record-validation --result pass --test-command ...` | exit 0；validation commit 为 `a50525d` |
| 暂停记录 | `42e633e chore: record validation checkpoint` | 生成唯一 `FEAT-001` checkpoint，Feature 仍为 `validated`，review/release pending |
| 版本不一致 | checkpoint 记录 `a50525d`，当前 HEAD `42e633e` | `fixture_head=$(git rev-parse HEAD); checkpoint_head=$(git show HEAD:.sdlc-v1/checkpoints/FEAT-001.md \| rg -o '[0-9a-f]{40}' \| head -n 1); test "$fixture_head" != "$checkpoint_head"` exit 0；恢复前必须重判证据 |
| 分支不一致修正 | 先发现 Git 分支为 `main`，但 state/checkpoint 记录 `feature/cancel-task`；执行 `git branch -m main feature/cancel-task` | exit 0；随后 `git branch --show-current`、Feature projection 与 checkpoint 均为 `feature/cancel-task` |

fixture 中的最后一项是 `.sdlc-v1/**` 证据提交，因此 validation 的业务实现版本仍是 `a50525d`。这份演练没有
执行主 Agent 验收、review、release、push 或 merge；上表是可供主 Agent 验收的实际证据，不是自称的独立验收。

首次恢复检查因分支和 HEAD 都不一致而必须拒绝恢复；上表保留了该错误和修正过程。修正分支后，checkpoint 与
当前 HEAD 仍不一致，因此恢复仍须重判证据。fixture 的 `TASK-001: done` 和 `FEAT-001: validated` 来自直接调用
`lifecycle_state.py` 的 standalone CLI 兼容性测试，不表示子 Agent 可以自行推进或已经获得主 Agent 接受。

## 书面编排情景

以下内容说明协议应如何使用。它不是额外的运行时记录。

### 1. 从领域分析到唯一有效 Plan

主 Agent 先串行收集两个有界分析：

| 分析边界 | 返回事实 | 主 Agent 结论 |
|---|---|---|
| 客户端 | 客户端只需要稳定的取消结果；不拥有权限判断 | 调用服务端，不在本地推断 owner |
| 服务端/风险 | `task_id`、`actor_id` 和 `status` 是共享接口；失败路径必须保持任务 active | 服务端拥有权限与状态转换；`PermissionError` 是权限隔离证据 |

主 Agent 将冲突消解为一个 Plan：`TaskService.cancel(task_id, actor_id)` 返回
`{task_id, status}`；`TaskClient.cancel_task(task_id)` 只显示 `status`；验收覆盖 owner 旅程、拒绝后状态不变和恢复时
版本核对。两份分析稿不会独立生效。

### 2. 初始完整 brief 与串行判断

```yaml
stage: build
feature_id: FEAT-001
plan_task_id: TASK-001
goal: 实现客户端发起、服务端授权的任务取消
out_of_scope: [task deletion, retry queue, production release]
settled_interfaces: [TaskService.cancel(task_id, actor_id) -> {task_id, status}]
context_refs: [.sdlc-v1/context/REQ-001.product.md, .sdlc-v1/context/FEAT-001.engineering.md]
write_scope: [client.py, server.py, tests/test_cancellation.py]
dependencies: []
completion_conditions: [owner can cancel, other user is rejected without state change]
required_verification: [python3 -m unittest discover -s tests -v]
expected_result: [changed_files, commands, revision, workspace_status, unresolved_items]
authorization: implementation and local verification only; no push, merge, or release
supersedes: none
```

主 Agent 选择串行：客户端和服务端共用取消响应与权限语义，尚不能证明写入和验收独立。执行子 Agent 不得再派生
客户端或服务端子 Agent。

### 3. 接口变化时替换完整 brief

若主 Agent 决定接口还需返回 `cancelled_at`，它先更新有效 Plan，再发送下列完整替换 brief，而不是追加一条消息：

```yaml
stage: build
feature_id: FEAT-001
plan_task_id: TASK-001
goal: 实现带取消时间的客户端发起、服务端授权的任务取消
out_of_scope: [task deletion, retry queue, production release]
settled_interfaces: [TaskService.cancel(task_id, actor_id) -> {task_id, status, cancelled_at}]
context_refs: [.sdlc-v1/context/REQ-001.product.md, .sdlc-v1/context/FEAT-001.engineering.md]
write_scope: [client.py, server.py, tests/test_cancellation.py]
dependencies: [updated FEAT-001 Plan]
completion_conditions: [owner sees cancelled status and timestamp, other user is rejected without state change]
required_verification: [python3 -m unittest discover -s tests -v]
expected_result: [changed_files, commands, revision, workspace_status, unresolved_items]
authorization: implementation and local verification only; no push, merge, or release
supersedes: FEAT-001/TASK-001 build brief v1
```

### 4. 故意缺少必要测试时拒收

这个反例表示子 Agent 错误地返回：

```yaml
status: awaiting_acceptance
artifacts: {changed_files: [client.py, server.py]}
evidence:
  commands: [{command: python3 -m unittest discover -s tests -v, exit_code: NOT_RUN, result: missing}]
  revision: <implementation-sha>
  workspace_status: clean
unresolved_items: [permission-isolation test not run]
```

主 Agent 必须拒收：`required_verification` 缺失，不能执行 `set-task-status done`、validation 或后续 review。
它把这个事实作为纠正边界；同一 work item 两次未验收后，应诊断接口、边界、环境或执行方式，而不是原样催补。

### 5. 暂停与恢复

fixture 的 checkpoint 只有 `定位`、`已确认`、`未完成`、`下一步`、`必要引用` 五节。首次恢复检查还发现 Git 分支
`main` 与 state/checkpoint 的 `feature/cancel-task` 不一致，因此拒绝恢复。分支修正后，恢复者仍先比较 Feature 分支、
HEAD 和 workspace。checkpoint 的 `a50525d` 与当前 `42e633e` 不同，因此先重新判断测试和 validation 证据，再决定
是否进入只读 review。Feature 完成后删除该 checkpoint；Plan、state 和 Git 仍分别是设计、进度和历史的权威。

## 子 Agent 待验收结果

```yaml
status: awaiting_acceptance # 待验收
artifacts:
  changed_files:
    - docs/agent-orchestration-rehearsal.md
evidence:
  commands:
    - command: python3 -m unittest discover -s tests -v
      exit_code: 0
      result: 2 fixture tests passed
    - command: lifecycle_state.py --repo . feature-projection --feature-id FEAT-001
      exit_code: 0
      result: fixture is validated; review and release are pending
    - command: >-
        fixture_head=$(git rev-parse HEAD); checkpoint_head=$(git show
        HEAD:.sdlc-v1/checkpoints/FEAT-001.md | rg -o '[0-9a-f]{40}' | head -n 1);
        test "$fixture_head" != "$checkpoint_head"
      exit_code: 0
      result: version mismatch detected before recovery
  revision: fixture implementation a50525d; fixture evidence checkpoint 42e633e
  workspace_status: fixture clean after checkpoint commit
unresolved_items:
  - Main Agent must decide whether the fixture evidence is accepted; this document does not claim that decision.
```
