# sdlc-pilot

> 一套轻量、可移植、纯文件的 SDLC 技能族：用阶段技能推进工作，用角色卡补充专业视角，用 Git 共享状态与上下文。

## 核心模型

1. **产品上下文**用 Markdown 记录问题、范围、行为场景、领域判断和验收标准。
2. **工程上下文**用 Markdown 记录设计、任务拆分、测试策略、评审结论和发布说明。
3. **共享进度**只写目标仓库的 `.sdlc-v1/state.json`。
4. **协作与历史**使用普通 Git branch、commit、push、pull/merge；不再维护第二套版本历史。
5. **长期工程上下文**可由仓库自己的 `AGENTS.md`、架构/产品文档及可选的 repo-context 索引提供；SDLC 只在 `project.md` 记录已验证路径，不复制它们的正文或状态。

默认运行时由主 Agent 使用 `next` 选择一个阶段、派发一个阶段 Agent、验证返回的文件与命令证据，再更新 state 并继续。
阶段 Agent 不编辑 `state.json`；没有子 Agent 能力时按同一顺序串行执行。完整约定见
[`stage-agent-protocol.md`](skills/sdlc/references/stage-agent-protocol.md)，它不引入新的 runtime、事件记录、行为 Eval 或自动 retrospective。

产品与研发是同一个生命周期的两个视角，不是两套相互同步的存储系统：

```text
Requirement: captured → ready → in_delivery → validated → released
                              │
                              └─ Feature: planned → in_progress → validated → reviewed → released
                                             └─ Task: todo ↔ in_progress → done
```

一条 Requirement 关联一个 Feature；Feature 下可以有多个 Task。仓库可以同时保存多条 Requirement 和 Feature，
因此并不限制为“同时只能追踪一个需求”。

## 文件放在哪里

```text
<target-repo>/
├── .sdlc-v1/
│   ├── state.json          # sdlc-lightweight-state-v1，state_version=3；必须纳入 Git
│   └── context/            # state 引用的产品/工程上下文；必须放在这里
│       ├── product.md
│       ├── engineering.md
│       └── decisions.md
└── <source code>
```

`state.json` 只保存 Requirement、Feature、Task、上下文引用及验证/评审/发布摘要，不复制长篇需求和设计文档。
每条 Requirement 的 `product_context_ref` 和每个 Feature 的 `engineering_context_ref` 都是必填项，只接受
`.sdlc-v1/context/*.md` 下已存在的仓库相对 Markdown 文件；不能引用仓库外路径、符号链接或项目 `docs/`。
项目原有文档仍可保留，但需把当前生命周期直接引用的上下文整理进 `.sdlc-v1/context/`。

## 与长期工程上下文协作

`sdlc-onboard` 总会读取仓库 `AGENTS.md`；若同时发现当前 commit 对齐的 `.repo-context/evidence.json` 和
`.repo-context/manifest.yaml`，会将其中的 canonical 文档路径写入 `project.md` 的索引。两份 repo-context
文件缺失、过期或无法读取时，onboard 继续从源码和配置建立项目上下文，不产生运行时依赖。

职责保持分离：长期目标、产品、架构与开发说明由仓库文档维护；`.sdlc-v1/context/*.product.md` 和
`*.engineering.md` 仅维护当前 Requirement/Feature 的行为、实现、验证、发布后观察和新需求回流。研发上下文需要
记录预期结果、可观察指标（或不可观测原因）、观察窗口、负责人和反馈应创建或更新的 Requirement。

repo-context 的 `sync`/`refine` 若会改动业务路径或长期文档，应在当前 Feature 的 validation 前完成；若在 validation
之后进行，则建立单独的维护 Requirement，或在评审/发布前重新验证。SDLC 的 state 校验规则不为这些路径提供例外。

## 技能体系

| 层 | 内容 | 作用 |
|---|---|---|
| Driver | `sdlc` | 根据当前状态和用户意图恢复、路由、编排与推进 |
| 生命周期 | `sdlc-product-design`、`sdlc-software-delivery` | 分别组织产品澄清和研发交付 |
| 阶段技能 | onboard、backlog、spec、plan、build、validate、review、ship | 在需要时只加载当前阶段 |
| 角色卡 | product-owner、domain-expert、architect、client-dev、server-dev、qa、design、security 等 | 按改动面补充检查视角 |
| 验证模式 | correctness、e2e、eval-bench | 由 validate 阶段按项目类型选用 |

方法论仍然保留 BDD、战略 DDD、SDD、TDD、可靠性检查、多角色评审和发布纪律；它们是阶段内按需加载的
工作方式，不要求为每一步生成额外的机器记录。

## 状态命令

状态工具只有一个入口：

```bash
python3 scripts/lifecycle_state.py --repo <target-repo> init
python3 scripts/lifecycle_state.py --repo <target-repo> status
```

`init` 会检查目标仓库 Git hooks。若发现 0.x 安装时复制进去的 sdlc-pilot hook/guard，会返回具体 hooks 目录并停止；
先人工检查该目录，只删除旧 SDLC 代码（混有团队逻辑的 hook 应编辑而不是整文件误删），再重新执行 `init`。
初始化后先建立 `.sdlc-v1/context/*.md`，再捕获需求；进入 validation 前必须把 state 和上下文纳入 Git。

产品侧：

```bash
python3 scripts/lifecycle_state.py --repo <target-repo> capture-requirement \
  --id REQ-001 --title "导出财务数据" --priority P1 \
  --product-context-ref .sdlc-v1/context/product.md
python3 scripts/lifecycle_state.py --repo <target-repo> revise-requirement \
  --requirement-id REQ-001 --priority P0 --depends-on ""
python3 scripts/lifecycle_state.py --repo <target-repo> mark-requirement-ready \
  --requirement-id REQ-001
```

未绑定 Feature 的 `captured` Requirement 可以用 `revise-requirement` 修订；
不再交付的 `captured`/`ready` Requirement 使用 `cancel-requirement --reason <why>`
保留历史。取消前必须先处理活动依赖方。

研发侧：

```bash
python3 scripts/lifecycle_state.py --repo <target-repo> start-feature \
  --requirement-id REQ-001 --feature-id FEAT-001 --branch feature/export-data \
  --engineering-context-ref .sdlc-v1/context/engineering.md
python3 scripts/lifecycle_state.py --repo <target-repo> add-task \
  --feature-id FEAT-001 --task-id TASK-001 --title "实现导出接口"
python3 scripts/lifecycle_state.py --repo <target-repo> set-task-status \
  --feature-id FEAT-001 --task-id TASK-001 --status done
python3 scripts/lifecycle_state.py --repo <target-repo> record-validation \
  --feature-id FEAT-001 --result pass --test-command "pytest"
python3 scripts/lifecycle_state.py --repo <target-repo> record-review \
  --feature-id FEAT-001 --decision approved --by reviewer
python3 scripts/lifecycle_state.py --repo <target-repo> record-release \
  --feature-id FEAT-001
```

`released` 只表示声明的发布目标及该目标要求的 smoke、观测已经完成；
发布目标可以是明确约定的源码分发，也可以是环境部署。它不表示代码仅仅
合入了主分支。若历史记录误把合并或发布准备当成发布，先在工程上下文
记录原因，再纠正机器状态：

```bash
python3 scripts/lifecycle_state.py --repo <target-repo> retract-release \
  --feature-id FEAT-001 --reason "recorded after merge without deployment smoke"
```

公开查询命令为 `status`、`next`、`readyqueue`、`product-projection` 和 `feature-projection`。`next` 在只有一个
候选时返回下一阶段；存在多个活动 Feature/Requirement 时返回 `needs_selection` 和候选列表，不替用户猜测。

backlog/board 是 `.sdlc-v1/state.json` 的只读投影，不维护第二份需求状态：

```bash
python3 scripts/backlog.py readyqueue --root <target-repo>
python3 scripts/backlog.py coverage --root <target-repo>
python3 scripts/backlog.py lint --root <target-repo>
python3 scripts/backlog.py tree --root <target-repo>
python3 scripts/backlog.py board --root <target-repo> --out ./_board.html
```

`board` 只写可重新生成的 HTML；其余命令不写文件。`lint` 会检查 state 和所有 context ref 是否存在且已被 Git
追踪。validation 保存测试时的 Git HEAD 作为实现版本；在 validation 前，state 必须已被 Git 追踪、没有
unmerged index entry 且未 staged（先 commit 或 unstage），当前产品/研发上下文也必须已追踪且无冲突，业务代码
工作树必须干净。之后可以单独提交 `.sdlc-v1/**` 来同步状态和证据；如果其他路径相对 validation commit 有变化，
review/release 会要求重新验证。

## 多人、多机器协作

把 `.sdlc-v1/state.json`、相关上下文 Markdown 和代码当作同一批普通 Git 变更：

1. A 捕获需求、补产品上下文并将 Requirement 标记为 `ready`。
2. A commit/push；B 在另一台机器 pull。
3. B 创建 Feature/Task、实现并提交业务代码，在该 commit 上运行验证。
4. B 记录 validation，把 state、研发上下文和证据 commit/push。
5. 评审者 pull 后记录 review，再提交 `.sdlc-v1/**`；发布者 pull 后发布 validation commit 并记录 release。

两个人同时修改状态时，处理方式与同时修改普通 JSON 文件相同：先同步分支，解决冲突，确认 state 已追踪且无
unmerged entry，再运行状态测试。
不使用本机串行文件或隐藏服务协调多个 clone。

## 安装

作为 Claude Code 插件：

```text
/plugin marketplace add arnow117/sdlc-pilot
/plugin install sdlc-pilot
```

本地开发或 Codex 使用可以克隆后软链全部技能：

```bash
git clone git@github.com:arnow117/sdlc-pilot.git
cd sdlc-pilot
SDLC_SKILLS="$PWD/skills"

mkdir -p "$HOME/.claude/skills" "$HOME/.codex/skills"
for d in "$SDLC_SKILLS"/*/; do
  ln -sfn "$d" "$HOME/.claude/skills/$(basename "$d")"
  ln -sfn "$d" "$HOME/.codex/skills/$(basename "$d")"
done

bash scripts/validate-skills
```

## 测试

```bash
bash scripts/validate-skills
git diff --check
```

`validate-skills` 只做快速结构/frontmatter/引用检查，并运行三组小测试：

- `test_lifecycle_state.py`：Requirement → Feature → Task → validation/review/release；
- `test_backlog.py`：需求树与看板；
- `test_contrast_check.py`：设计对比度检查。

`eval-bench` 用于验证产品内 AI 功能效果；Web Review Live 用于本地文档批注。两者都是保留的普通能力。

## 从 0.x 升级

1.0.0 是一次有意的主版本断代，不执行 0.x 协议，也不做自动迁移。历史文件不会被自动读取、转换或删除；
人工把仍有效的产品/工程内容整理到 `.sdlc-v1/context/*.md`，清理 `init` 报出的旧 sdlc-pilot copied hooks，
再初始化 state 并重新建立当前 Requirement → Feature 关联。移除项详见 `CHANGELOG.md`。

## 设计与维护

- 当前设计：[`docs/specs/2026-08-10-lightweight-sdlc.md`](docs/specs/2026-08-10-lightweight-sdlc.md)
- 蒸馏源地图：[`docs/distillation-source-map.md`](docs/distillation-source-map.md)
- 维护契约：[`CLAUDE.md`](CLAUDE.md)

`docs/specs/2026-06-*.md` 全部是 0.x 历史设计，只用于理解演进背景；其中的状态路径、hook、命令和完成条件
均已被 2026-08-10 active contract 取代，不得作为 1.0 实现依据。
