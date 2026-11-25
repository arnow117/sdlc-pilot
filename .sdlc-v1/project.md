# Project Context: sdlc-pilot

## 项目定位

`sdlc-pilot` 是一个可移植、纯文件的 SDLC 技能集合。它让 Agent 以阶段技能和角色卡协作；目标仓库的 Git、`.sdlc-v1/state.json` 与 Markdown 上下文分别保存历史、最小生命周期进度与可读决策。它不启动常驻服务，也不维护第二套事件、消息或进度存储。源码版本以 [`.claude-plugin/plugin.json`](../.claude-plugin/plugin.json) 和 [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) 为准。

## 技术栈及选择原因

| 区域 | 技术 | 已验证依据 |
|---|---|---|
| 生命周期与投影 | Python 标准库 CLI | `scripts/lifecycle_state.py`、`backlog.py`、`board.py`；本机当前检查在 Python 3.15.2 通过 |
| 技能与说明 | Markdown、YAML frontmatter、Bash | `skills/**/SKILL.md` 与 `scripts/validate-skills` |
| 原型运行时 | 原生 JavaScript 资产 + Node 内置测试 | `skills/sdlc-prototype/assets/**`，`docs/testing.md` 的 Node 命令 |
| 进度与协作 | Git、JSON、Markdown | `state_format=sdlc-lightweight-state-v1`、`state_version=3`，context 位于 `.sdlc-v1/context/*.md` |
| 本地审阅页面 | Python `http.server`、原生 HTML/CSS/JavaScript | `skills/sdlc/references/web-review/**`；无第三方 UI 或网络字体 |
| 离线实验工具 | Python 标准库 oracle/host | `scripts/vibe_test.py`、`vibe_host.py`；不执行不可信模型输出，无 MCP/模型/认证调用 |
| 外部系统 | Git；Claude Code 插件市场、Codex 技能目录 | README 的安装方式：Claude Code 走 marketplace，Codex 克隆后软链全部 `skills/*` |

没有 `pyproject.toml`、requirements 文件、Node 包清单、Makefile、`justfile` 或 CI workflow（无 `.github/`）。Python 脚本当前只导入标准库。

## 启动与代码入口

| 用途 | 路径或命令 | 说明 |
|---|---|---|
| 生命周期状态 CLI | `python3 scripts/lifecycle_state.py --repo . status` | 唯一生命周期状态实现；只读查询为 `status`、`next`、`readyqueue`、`product-projection`、`feature-projection`、`verify-acceptance`，其余为显式 mutation 子命令 |
| 只读状态投影 | `python3 scripts/backlog.py readyqueue --root .` | `backlog.py`/`board.py` 提供 `readyqueue/coverage/lint/tree/board`，只读、不反写状态 |
| 阶段入口 | `skills/sdlc/SKILL.md` | 根据用户意图、state 和 diff 路由阶段与角色 |
| 本地 Markdown 审阅页 | `python3 skills/sdlc/references/web-review/build.py README.md /tmp/sdlc-review` | 生成自包含审阅页和本地回收服务器资产 |
| 本地审阅服务器 | `python3 skills/sdlc/references/web-review/server.py [port]` | 提供静态文件、`/feedback` 与 `/wait` 长轮询 |
| 插件发布元数据 | `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` | 发布时核对插件、市场清单和 Git 标签的版本。 |

## 测试、构建与类型检查命令

测试范围、按改动选检查和场景契约的权威来源是 [`docs/testing.md`](../docs/testing.md)，此处只列入口、不复制计数。

```yaml
commands:
  unit: "bash scripts/validate-skills && git diff --check"
  prototype_runtime: >-
    node --test skills/sdlc-prototype/assets/shared-state/runtime.test.cjs &&
    node --test skills/sdlc-prototype/assets/review-console/*.test.cjs
  local_web_integration: "复制 skills/sdlc/references/web-review/ 到临时目录后运行副本中的 test_live.py"
  lint: "bash scripts/validate-skills && git diff --check"
  typecheck: "none"
  coverage: "none"
  release_build: "none"
```

`validate-skills` 检查结构、引用和协议文本，并运行八组标准库 Python 测试（lifecycle、backlog、共享场景、contrast、Hallmark catalog、vibe test 核心、vibe host、安全依赖探针）；测试数量随代码变化，以 [`docs/testing.md`](../docs/testing.md) 的分组说明和实际运行输出为准。在当前 HEAD 与工作树上实测该命令通过。`test_live.py` 是本地长轮询集成测试，会在脚本所在目录写反馈与历史文件，必须先整体复制 `web-review/` 到临时目录再运行副本。

## 验证工具、测试资产、产物归档与准备缺口

| 项目 | 已验证设置或缺口 |
|---|---|
| `correctness` | `scripts/validate-skills` 是仓库标准检查；测试资产为 `scripts/test_*.py`（含共享 Git fixture helper `scripts/test_support.py`）与上节 Node 测试。 |
| 共享场景与真实 Agent 证据 | 六个共享场景（B01–B05 及变体）的可复现 fixture 在 `scripts/test_scenarios.py` 与 `examples/`；确定性断言之外的真实 Agent 演练记录见 [`docs/history/agent-runs-2026-11.md`](../docs/history/agent-runs-2026-11.md)，仅覆盖其标注的日期与配置。 |
| 离线对照实验 | `scripts/vibe_test.py`/`vibe_host.py` 及 `examples/vibe-*` fixture 服务于对照测量，使用合成输入和 stub；准备条件见 [`docs/vibe-tests.md`](../docs/vibe-tests.md)。 |
| Web 本地集成 | `web-review/test_live.py` 以 loopback HTTP 覆盖长轮询唤醒、并发响应、超时和先提交后等待；运行前按上节复制到临时目录。 |
| `e2e:Web` / `e2e:App` | 无本仓库自身的端到端旅程、tester-army 配置、Maestro Flow 或报告归档；`e2e`/`eval-bench` 目前是面向目标产品验证的模式文档（`skills/sdlc/references/validate-modes/`）。 |
| 构建与报告归档 | 无 CI workflow、coverage 门控或稳定报告归档。`_board.html` 与 web-review feedback 文件在 `.gitignore` 中，属可再生成或运行时产物。 |

## Surface map

```yaml
surfaces:
  - name: lifecycle-runtime
    globs:
      - scripts/lifecycle_state.py
      - scripts/backlog.py
      - scripts/board.py
      - scripts/contrast_check.py
    roles: [server-dev, qa]
    modes: [correctness]
  - name: lifecycle-and-tool-tests
    globs: [scripts/test_*.py, scripts/validate-skills, docs/testing.md]
    roles: [qa]
    modes: [correctness]
  - name: skill-system-and-plugin-release
    globs: [skills/**, .claude-plugin/**]
    roles: [skill-maintainer]
    modes: [correctness]
  - name: prototype-runtime
    globs: [skills/sdlc-prototype/assets/**]
    roles: [skill-maintainer, client-dev, qa]
    modes: [correctness]
  - name: local-web-review
    globs: [skills/sdlc/references/web-review/**]
    roles: [skill-maintainer, client-dev, server-dev, qa]
    modes: [correctness, e2e:Web]
  - name: documentation-and-fixtures
    globs: [README.md, DESIGN.md, CHANGELOG.md, CLAUDE.md, AGENTS.md, docs/**, examples/**]
    roles: [skill-maintainer, ai-readiness]
    modes: [correctness]
```

`.sdlc/archive/**` 及 `.sdlc/EVOLUTION.md`、`.sdlc/PROFILE.md` 是项目自身 0.x 历史资料（文件头自注"0.x 历史记录"并指向本文件）；它们不代表当前 runtime，也不作为 lifecycle surface。`LICENSE` 和 `.gitignore` 是辅助仓库元数据，修改时按受影响的 surface 选择角色和验证。

## 工程约定与禁止事项

- `lifecycle_state.py` 是唯一状态实现；编排模式下仅主 Agent 可修改 `state.json` 或执行 lifecycle mutation，阶段 Agent 只返回 artifact 与证据。
- 生命周期 state 与当前 context 必须以普通、Git 跟踪的文件存在；context ref 只接受 `.sdlc-v1/context/*.md`。验证要求 state/context 无冲突、state 未暂存且业务工作树干净。
- 使用普通 Git branch、commit、push、pull/merge 传递历史；不要增加第二状态源、事件运行时或本地结果存储。
- 修改 lifecycle 状态、角色、验证方式、阶段编排或顶层技能时，按 `CLAUDE.md` 的关联文件同步，并运行 `bash scripts/validate-skills` 与 `git diff --check`。改变公开插件行为时同步 `CHANGELOG.md` 和两个插件元数据版本。
- 根 `AGENTS.md` 是指向 `CLAUDE.md` 的符号链接。安装与技能发现目录以 README 为准：Claude Code 走插件市场，Codex 克隆后将 `skills/*` 软链到 `~/.agents/skills`；本仓库不含项目本地 `.agents/skills/` 链接。

## 已知风险

| 风险 | 受影响区域 | 当前处理 |
|---|---|---|
| lifecycle state/context 的 Git 前置条件 | `.sdlc-v1/**` | 验证前必须 tracked、无冲突，state 未 staged；当前进度只通过 state CLI 查询，不在 project.md 复制。 |
| 在途未提交改动阻碍 clean-worktree 验证 | 当前 checkout | 未提交的文档/技能改动必须先由其写入方提交，验证绑定步骤才能建立证据；不自动纳入提交、忽略或删除。 |
| 软链安装方式使未提交技能改动立即生效 | 采用 symlink 安装的用户环境 | 未提交的技能改动会立即被该环境的 Claude/Codex 发现；发布仍以 Git 与插件元数据为准。 |
| 本仓库无自身 Web/App 端到端资产 | web-review 与未来用户旅程 | 修改 web-review 用户旅程时按 `skills/sdlc/references/validate-modes/e2e.md` 补齐对应验证；本地集成测试不能替代该验证。 |

## 部署目标与配置位置

```yaml
target: "Claude Code marketplace plugin and local skill symlink distribution"
config_paths:
  - .claude-plugin/plugin.json
  - .claude-plugin/marketplace.json
  - README.md
environments:
  dev: "local checkout; optional skill symlinks per README 安装节"
  staging: "none"
  canary: "none"
  full: "marketplace/plugin release outside this onboard stage"
health_check: "bash scripts/validate-skills && git diff --check"
```

## 长期工程上下文来源

```yaml
root_guidance: AGENTS.md -> CLAUDE.md
scoped_guidance: []
canonical_documents:
  - README.md
  - CLAUDE.md
  - DESIGN.md
  - CHANGELOG.md
  - docs/README.md
  - docs/testing.md
  - docs/specs/2026-08-10-lightweight-sdlc.md
  - docs/agent-orchestration-rehearsal.md
  - docs/vibe-tests.md
repo_context:
  status: none
  analyzed_commit: b9833a0
evidence_head: b9833a0
evidence_ref: "测绘基线为 b9833a0，并核对了 8.0.1 文档更新。"
```

未发现 `.repo-context/manifest.yaml` 或 `.repo-context/evidence.json`，因此没有使用 repo-context 的 canonical 索引。README 的文档导航入口是 `docs/README.md`；`docs/specs/2026-06-*.md` 与 `docs/specs/board-0.16.0.md` 仅用于历史背景，`docs/history/` 保存有界的历史运行记录。

## AI 可读性

根维护契约、阶段技能、角色路由、测试索引（`docs/testing.md`）、文档导航（`docs/README.md`）与 CLI 入口均在仓库中可直接发现。主要缺口是无依赖/CI/typecheck 声明、无本仓库自身的 Web/App E2E 资产，以及 symlink 安装方式下未提交改动即时生效的固有特性。
