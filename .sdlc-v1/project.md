# Project Context: sdlc-pilot

## 项目定位

`sdlc-pilot` 是一个可移植、纯文件的 SDLC 技能集合。它让 Agent 以阶段技能和角色卡协作；目标仓库的 Git、`.sdlc-v1/state.json` 与 Markdown 上下文分别保存历史、最小生命周期进度与可读决策。它不启动常驻服务，也不维护第二套事件、消息或进度存储。

## 技术栈及选择原因

| 区域 | 技术 | 已验证依据 |
|---|---|---|
| 生命周期与投影 | Python 标准库 CLI | `scripts/lifecycle_state.py`、`backlog.py`、`board.py`；当前检查使用 Python 3.9.6 |
| 技能与说明 | Markdown、YAML frontmatter、Bash | `skills/**/SKILL.md` 与 `scripts/validate-skills` |
| 进度与协作 | Git、JSON、Markdown | `state_version=3`，context 位于 `.sdlc-v1/context/*.md` |
| 本地审阅页面 | Python `http.server`、原生 HTML/CSS/JavaScript | `skills/sdlc/references/web-review/**`；无第三方 UI 或网络字体 |
| 外部系统 | Git；Claude Code/Codex 的技能发现目录 | README 的本地安装方式为把 `skills/sdlc*` 软链到两个发现目录 |

没有 `pyproject.toml`、requirements 文件、Node 包清单、Makefile、`justfile` 或 CI workflow。Python 脚本当前只导入标准库。

## 启动与代码入口

| 用途 | 路径或命令 | 说明 |
|---|---|---|
| 生命周期状态 CLI | `python3 scripts/lifecycle_state.py --repo . status` | 唯一生命周期状态实现；公开只读命令包括 `status`、`next`、`readyqueue` 和两个 projection |
| 只读状态投影 | `python3 scripts/backlog.py readyqueue --root .` | `board` 只生成可重建 HTML；其余命令不写状态 |
| 阶段入口 | `skills/sdlc/SKILL.md` | 根据用户意图、state 和 diff 路由阶段与角色 |
| 本地 Markdown 审阅页 | `python3 skills/sdlc/references/web-review/build.py README.md /tmp/sdlc-review` | 生成自包含审阅页和本地回收服务器资产 |
| 本地审阅服务器 | `python3 skills/sdlc/references/web-review/server.py [port]` | 提供静态文件、`/feedback` 与 `/wait` 长轮询 |
| 插件发布元数据 | `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` | 两处版本均为 `2.0.0`，与 `HEAD` 的 `v2.0.0` tag 一致 |

## 测试、构建与类型检查命令

```yaml
commands:
  unit: "bash scripts/validate-skills"
  focused_tests: "python3 scripts/test_lifecycle_state.py; python3 scripts/test_backlog.py; python3 scripts/test_contrast_check.py"
  local_web_integration: "python3 skills/sdlc/references/web-review/test_live.py"
  lint: "bash scripts/validate-skills; git diff --check"
  typecheck: "none"
  coverage: "none"
  release_build: "none"
```

`validate-skills` 检查技能结构、引用、角色/验证方式登记、阶段编排形状和可移植性，并运行三组标准库测试。对当前 `a034dc6cddf3784fb257890e1d09d2c79d4e65f3` 快照，它通过了 15 个 lifecycle、7 个 backlog 和 36 个 contrast 测试。`test_live.py` 是本地长轮询集成测试，未纳入该命令。

## 验证工具、测试资产、产物归档与准备缺口

| 项目 | 已验证设置或缺口 |
|---|---|
| `correctness` | `scripts/validate-skills` 是仓库标准检查；测试资产位于 `scripts/test_*.py`。 |
| Web 本地集成 | `web-review/test_live.py` 以 loopback HTTP 启动 `server.py`，覆盖长轮询唤醒、并发响应、超时和先提交后等待。该测试会生成已忽略的 feedback history，宜在隔离工作区运行或清理后检查状态。 |
| `e2e:Web` | 无 tester-army/e2e 配置、已提交旅程或报告归档位置。修改 web-review 的用户旅程前须按 2.0.0 契约补齐。上面的本地集成测试不能替代该验证。 |
| `e2e:App` | 无移动端源码、Maestro Flow、被测构建或设备设置。 |
| `eval-bench` | 无产品模型评估资产或运行配置。 |
| 构建与报告归档 | 无 CI workflow、coverage 配置或稳定报告归档。`_board.html` 和 web-review feedback 文件在 `.gitignore` 中，作为可再生成或运行时产物。 |

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
    globs: [scripts/test_*.py]
    roles: [qa]
    modes: [correctness]
  - name: skill-system-and-plugin-release
    globs: [skills/**, .claude-plugin/**]
    roles: [skill-maintainer]
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

`.sdlc/archive/**` 是项目自身的历史资料，不是 1.x/2.x runtime；它未被当作当前 lifecycle surface。`LICENSE` 和 `.gitignore` 是辅助仓库元数据，修改时按受影响的 surface 选择角色和验证。

## 工程约定与禁止事项

- `lifecycle_state.py` 是唯一状态实现；编排模式下仅主 Agent 可修改 `state.json` 或执行 lifecycle mutation，阶段 Agent 只返回 artifact 与证据。
- 生命周期 state 与当前 context 必须以普通、Git 跟踪的文件存在；context ref 只接受 `.sdlc-v1/context/*.md`。验证要求 state/context 无冲突、state 未暂存且业务工作树干净。
- 使用普通 Git branch、commit、push、pull/merge 传递历史；不要增加第二状态源、事件运行时或本地结果存储。
- 修改 lifecycle 状态、角色、验证方式、阶段编排或顶层技能时，按 `CLAUDE.md` 的关联文件同步，并运行 `bash scripts/validate-skills` 与 `git diff --check`。改变公开插件行为时同步 `CHANGELOG.md` 和两个插件元数据版本。
- 根 `AGENTS.md` 是指向 `CLAUDE.md` 的符号链接。当前安装的 11 个 `~/.claude/skills/sdlc*` 和 11 个 `~/.codex/skills/sdlc*` 链接均指向此 checkout 的 `skills/sdlc*`；未发现项目本地 `.agents/skills/sdlc*` 链接。

## 已知风险

| 风险 | 受影响区域 | 当前处理 |
|---|---|---|
| lifecycle state/context 的 Git 前置条件 | `.sdlc-v1/**` | 验证前必须 tracked、无冲突，state 未 staged；当前进度只通过 state CLI 查询，不在 project.md 复制。 |
| 无关未跟踪文件阻碍 clean-worktree 验证 | 当前 checkout | 后续验证前由文件所有者处理；不自动纳入提交、忽略或删除。 |
| 全局发现链接直指工作 checkout | 已安装 `sdlc*` 技能 | 未提交的技能改动会立即被本机 Claude/Codex 发现；发布仍以 Git 与插件元数据为准。 |
| 2.0.0 的 Web/App 必要验证没有仓库级资产 | web-review 与未来用户旅程 | 当前只记录缺口；Build/Validate 必须准备对应 engine/Flow、断言、fixture 和报告证据。 |

## 部署目标与配置位置

```yaml
target: "Claude Code marketplace plugin and local skill symlink distribution"
config_paths:
  - .claude-plugin/plugin.json
  - .claude-plugin/marketplace.json
  - README.md
environments:
  dev: "local checkout with ~/.claude/skills and ~/.codex/skills symlinks"
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
  - docs/specs/2026-08-10-lightweight-sdlc.md
  - docs/agent-orchestration-rehearsal.md
repo_context:
  status: none
  analyzed_commit: none
evidence_head: a034dc6cddf3784fb257890e1d09d2c79d4e65f3
evidence_ref: "main; tag v2.0.0; origin/main"
```

未发现 `.repo-context/manifest.yaml` 或 `.repo-context/evidence.json`，因此没有使用 repo-context 的 canonical 索引。README 将 `docs/specs/2026-08-10-lightweight-sdlc.md` 指定为当前设计；`docs/specs/2026-06-*.md` 仅用于历史背景。

## AI 可读性

根维护契约、阶段技能、角色路由、标准检查与 CLI 入口均在仓库中可直接发现。主要缺口是无依赖/CI/typecheck 声明、无已准备的 Web/App E2E 资产，以及本地安装链接直接指向工作 checkout。
