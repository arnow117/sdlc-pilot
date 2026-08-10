# sdlc-pilot — 维护契约

> 本文件被 Claude Code 自动加载；`AGENTS.md` 指向本文件，供其他 coding agent 使用。用户向导见 `README.md`。

## 这是什么

一套自洽、可移植、纯文件的 SDLC 技能族。核心模型是：

- Roles = 专业视角知识卡；
- Skills = 生命周期入口或流程阶段；
- `.sdlc-v1/state.json`（`state_version=3`）= 唯一机器可读进度；
- Git = 唯一跨 clone 传输和历史机制；
- Markdown = 产品、工程和项目上下文。

## 维护原则

1. **保持单一路径。** 不重新引入第二状态源、第二版本历史、第二运行时或技能自评估运行时。
2. **状态保持小。** `state.json` 只追踪 Requirement、Feature、Task 与验证/评审/发布摘要；长篇 PRD、设计、ADR、测试报告放 Markdown。
3. **普通 Git 协作。** 跨机器交接使用 commit/push/pull/merge；不要构造第二套并发、历史或身份协议。
4. **按需加载。** 生命周期只加载当前阶段、相关角色卡和验证模式，避免每轮重读全套方法论。
5. **可移植。** 不硬依赖 Workflow、AskUserQuestion 或 subagent；交互可退化为纯文本，并行可退化为串行。
6. **Skill 写约束和原则。** 环境特定命令放语言包或部署目标卡，不把流程 skill 写成 shell cookbook。

## 结构

```text
skills/
├── sdlc/                         # driver + 共享 references
├── sdlc-product-design/          # 产品生命周期入口
├── sdlc-software-delivery/       # 研发交付入口
└── sdlc-{onboard,backlog,spec,plan,build,validate,review,ship}/

scripts/
├── lifecycle_state.py            # 唯一状态实现
├── backlog.py / board.py         # state 的只读投影（readyqueue/coverage/lint/tree/board）
├── contrast_check.py             # 设计对比度检查
├── test_*.py                     # 三组小测试
└── validate-skills               # 快速结构检查 + 小测试
```

共享 role、routing、validate mode、language、deploy target 和 playbook 只放在
`skills/sdlc/references/`，阶段技能引用它们，不复制一份。

## 常见改动要同步什么

| 改动 | 同步项 |
|---|---|
| 加角色卡 | `references/roles/<role>.md` → `role-routing.md` 登记 → `validate-skills` |
| 加 validate 模式 | `references/validate-modes/<mode>.md` → `role-routing.md` → `sdlc-validate/SKILL.md` |
| 改路由规则 | 只改 `role-routing.md`；driver 不内联同一张映射 |
| 改生命周期状态 | `lifecycle_state.py` → `test_lifecycle_state.py` → 生命周期/阶段 skill → README/设计 spec |
| 改 backlog/board | 保持只读 projection；`backlog.py`/`board.py` → `test_backlog.py` → `sdlc-backlog/SKILL.md` |
| 改阶段行为 | 对应 `sdlc-<stage>/SKILL.md`；确认引用存在并保持可移植 |
| 改工具自身 | `skill-maintainer` 角色 + `evolve-loop.md`；结构性改动走完整 SDLC |

## 提交前

```bash
bash scripts/validate-skills
git diff --check
```

同时更新 `CHANGELOG.md`；发布行为变化时按语义化版本同步
`.claude-plugin/plugin.json` 和 `.claude-plugin/marketplace.json`。

## 状态与上下文约定

- `.sdlc-v1/state.json` 必须纳入目标仓库 Git，不要加入 `.gitignore`。
- Requirement/Feature 的 context ref 必填，且只能指向已存在、非符号链接的 `.sdlc-v1/context/*.md`。
- 不把 Markdown 正文、完整测试输出或评审全文塞进 `state.json`。
- `next` 是公开 state 查询：单候选返回下一阶段，多候选返回 `needs_selection`，不得静默任选一条。
- backlog/board 只能读取 state 并生成 `readyqueue/coverage/lint/tree/board` 投影；禁止反写 lifecycle 状态。
- validation 前 state 必须已 tracked、无 unmerged index entry 且未 staged，当前 context 必须已 tracked 且无冲突，
  业务代码工作树必须干净；之后只提交 `.sdlc-v1/**` 不使验证失效，其他路径变化后必须重新验证。
- `init` 检出旧 sdlc-pilot copied hooks 时必须停止并给出路径；只能人工检查/清理，不能自动覆盖团队 hooks。
- 多人冲突按普通 Git 冲突处理；同步并解决冲突后重跑测试和状态检查。
- 本仓现有 `.sdlc/archive/` 属于项目历史，不代表 1.0 运行时协议。

## 测试边界

结构检查只验证 frontmatter、关键共享文件和本地引用；行为测试只覆盖仍存在的轻量实现。
`validate-modes/eval-bench.md` 用于验证业务产品内的 AI 功能，应保留。Web Review Live 模式用于本地文档批注，
也应保留。两者都是与 lifecycle state 正交的普通能力。
