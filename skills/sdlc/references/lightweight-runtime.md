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

## 7. 查询与恢复

```bash
lifecycle_state.py --repo <repo> status
lifecycle_state.py --repo <repo> next
lifecycle_state.py --repo <repo> readyqueue
lifecycle_state.py --repo <repo> product-projection --requirement-id <REQ-id>
lifecycle_state.py --repo <repo> feature-projection --feature-id <FEAT-id>
```

`next` 在只有一个明确目标时返回下一阶段；并行工作超过一个时返回 `needs_selection` 和候选项，不替用户猜选。恢复工作时先查询 projection，再只读取其中引用的项目、产品和研发上下文。

## 8. 两台机器交接

```text
机器 A：更新产品上下文 → Requirement ready → commit → push
机器 B：pull → 创建 Feature/研发上下文 → 实现 → commit → 验证 → 提交 state/context → push
机器 A 或 B：pull → 评审 → 提交 state/context → pull → 发布
```

若两台机器同时修改 `state.json`，使用普通 Git 合并冲突流程处理；不要另外生成第二份状态文件。
