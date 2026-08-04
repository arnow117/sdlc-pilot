# Project Profile: sdlc-pilot

tech-stack: [python3-stdlib, markdown-skills, html-css-js-inline]
test-commands: { unit: "python3 scripts/test_backlog.py", coverage: "none — 纯 stdlib 脚本无覆盖率门控;靠 test_backlog.py 全绿 + 用例随 op 增长", e2e: "none — 无独立前端;看板 Live mode 由 web-review/test_live.py 覆盖", typecheck: "none — 无类型注解工具链", build: "bash scripts/validate-skills" }


## Tech stack

| 层 | 技术 | 选它的原因 |
|----|------|-----------|
| 流程知识 | Markdown SKILL.md（9 个 skill）+ references/ | 纯文件可移植铁律:Claude/Codex 都靠 Read 加载,不依赖运行时 |
| 派生脚本 | Python 3 纯标准库（`scripts/backlog.py`） | 零依赖即可在任何 caller 跑;need 不引第三方包(可移植) |
| 看板前端 | HTML/CSS/JS **内联在 `backlog.py` 的 `render_board`** | 单文件自包含,`board` op 直接吐出自洽 HTML,无独立前端构建 |
| 实时协作 | `references/web-review/server.py`（stdlib http） | 划词批注 + Live mode（/wait /feedback /rev）,spec/plan/看板复用 |
| 校验 | `scripts/validate-skills`（bash） | skill frontmatter/结构体检,充当本项目的 "build" 门 |

## Surface map

<!-- 本仓 = sdlc-pilot 技能体系自身 → 改其知识/脚本由 skill-maintainer(R10) 承载(非普通目标项目)。 -->

- scripts-core:   globs[ scripts/backlog.py, scripts/control*.py, scripts/test_backlog.py, scripts/test_control.py ]   roles[skill-maintainer, qa, architect]   modes[correctness]
- board-render:   globs[ scripts/board.py ]                              roles[skill-maintainer, design]   modes[correctness]   # 看板 HTML/CSS/JS(0.16.0 从 backlog.py 抽出,守 800 行),改渲染叠 design 透镜
- skill-prose:    globs[ skills/**/SKILL.md, skills/sdlc/references/**/*.md ]   roles[skill-maintainer]   modes[correctness]
- web-review:     globs[ skills/sdlc/references/web-review/** ]           roles[skill-maintainer, server-dev]   modes[correctness]
- tooling:        globs[ scripts/validate-skills, scripts/test_hooks.py, skills/sdlc/scripts/sdlc-guard, skills/sdlc/references/templates/hooks/** ]   roles[skill-maintainer, qa]   modes[correctness]
- plugin-meta:    globs[ .claude-plugin/**, CHANGELOG.md ]               roles[skill-maintainer]   modes[correctness]

## Conventions

- **三铁律**（改任何东西都守，见 CLAUDE.md/EVOLUTION.md）：① 不轻易加顶层 skill（优先扩角色卡/模式/语言/部署适配器）；② 可移植纯文件（text_mode + Task-or-sequential，Codex 也能跑）；③ 纯文件 + 单写者（`STATE.md` 只 driver 写）。
- **不可变 / 显式错误**：脚本里返回新对象不就地变更；frontmatter 改写用 `re.sub(count=1)` 精确改首行。
- **共享 references 单一物理位置**：所有 `references/...` 只在 `skills/sdlc/references/` 下，各流程 skill 经此引用（不在自己目录里放副本）。
- **提交规范**：约定式提交（feat/fix/docs/chore/refactor…）；语义化版本（`.claude-plugin/plugin.json` 的 `version`）。
- **每次提交前**跑 `python3 scripts/test_control.py` + `python3 scripts/test_backlog.py` + `python3 scripts/test_hooks.py` + `bash scripts/validate-skills`。
- **dogfood**：用它自己的 `/sdlc` 流程开发自己；feature 分支用完即删；退场走 backlog Retire op（归档 + 回流 EVOLUTION + 清栈）。

## Entry points

- **driver 入口** = `/sdlc intake`（捕获/拆需求）+ `/sdlc deliver`（领取 ready leaf）+ `/sdlc`（智能恢复/路由）。
- **控制记录** = `python3 scripts/control.py <op>`；Git fast-forward transaction 在 `scripts/control_store.py`。
- **需求树脚本** = `python3 scripts/backlog.py <op> --root <.sdlc/requirements>`；op = readyqueue/coverage/lint/tree/board/move/retire/write-tree（注册见 `backlog.py:695` `main()`）。
- **看板渲染** = `backlog.py board --root <req-root> [--out _board.html]`；HTML 生成在 `render_board`（`backlog.py:376`），聊天 JS 在 `CHAT_JS`（`:255`）。
- **单测** = `python3 scripts/test_backlog.py`；**skill 体检** = `bash scripts/validate-skills`。
- **状态机渲染锚点**（本特性相关）：状态 CSS 类在 `backlog.py:194-199`（captured/specd/planned/built/validated/shipped）；`status` 常量只有 `SHIPPED`（`:31`）；lint 在 `cmd_lint`（`:475`）**当前不校验 status 取值**。

## Known risks

- **shared-control 依赖 Git remote 可用性**：远端不可达时不能声明跨 clone 唯一领取；只能显式降级 local-serial，不能假装已发布 claim。
- **local-serial 只保证当前仓库 CAS**：它不提供跨 clone 排他；团队协作必须使用 shared-control。
- **Git hooks 可被人工绕过**：`--no-verify`/删除 hook 会绕过本地检查；control adapter 自身仍必须验证 schema、ref baseline 与证据。
- **看板仍使用 HTML 字符串渲染**：所有控制字段必须继续经过 `_safe_json_for_html` 与 `esc()`；新增字段要补 XSS payload 回归。
- **无覆盖率/类型检查基线**：纯 stdlib 脚本依靠 control/backlog/hooks 三套行为测试；新增操作必须同步覆盖错误路径与 legacy 回归。

## Deploy

- target-type: 未知（none — 尚未配置部署）
- config 位置: 无 vercel.json / Dockerfile / .github/workflows
- 分发方式: Claude Code plugin（`.claude-plugin/{plugin,marketplace}.json`）；owner `arnow117` 直推 `github.com/arnow117/sdlc-pilot` main，安装方 git pull / 软链到 `~/.claude/skills/`。
- 密钥来源: 无（纯本地工具，无密钥）

## Evolution log

> 演进史（append-only，每特性退场由 sdlc-backlog 的 Retire op 追加）见**同目录 `EVOLUTION.md`**。
> 本文件只留此指针——Evolution log 是无界流水，独立成文件。
> 与 `Known risks` 区别：Known risks = onboard 测绘的静态风险快照；EVOLUTION.md = 已完成特性沉淀的动态决策/教训。
