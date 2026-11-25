# sdlc-pilot — 维护契约

本约定适用于维护 sdlc-pilot 插件的 Agent。Claude Code 自动读取本文件，其他 Agent 通过 `AGENTS.md` 读取同一份约定。在业务项目中使用插件，请从[用户指南](README.md)开始。

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
7. **阶段执行集中编排。** 默认主 Agent 使用 `next` 派发一个阶段 Agent，验证 artifact/evidence 后才执行其有序 transition 请求；协议只定义在 `references/stage-agent-protocol.md`，阶段 skill 不复制 schema。

## 常见改动要同步什么

先定位要改的行为，再检查受它影响的入口。目标项目里运行 SDLC 从[阶段路由](skills/sdlc/SKILL.md)进入；本仓库的维护任务按下表定位。

| 改动 | 权威文件或入口 | 同步与验证 |
|---|---|---|
| 角色卡、语言或验证模式 | [角色与模式路由](skills/sdlc/references/role-routing.md)及其引用的共享卡片 | 新增角色或模式时登记路由。验证模式另核对 [Validate](skills/sdlc-validate/SKILL.md)，运行结构和引用检查。 |
| 产品设计或软件交付阶段 | [产品设计](skills/sdlc-product-design/SKILL.md)、[软件交付](skills/sdlc-software-delivery/SKILL.md)引用的阶段技能 | 在对应阶段修改行为，核对其他阶段的交接与可移植性。共享规则只在 `skills/sdlc/references/` 维护。 |
| 独立原型或阶段内原型 | [原型技能](skills/sdlc-prototype/SKILL.md)、[产品阶段适配](skills/sdlc/references/integrations/product-prototype.md) | 核对独立调用与阶段内使用各自的输入、产物。资产改动按[测试指南](docs/testing.md)选择组件测试。 |
| 生命周期状态和查询 | [状态 CLI](scripts/lifecycle_state.py) | 核对[状态测试](scripts/test_lifecycle_state.py)、受影响阶段、[用户指南](README.md)和[基础设计](docs/specs/2026-08-10-lightweight-sdlc.md)。 |
| Backlog 投影或看板 | [投影](scripts/backlog.py)、[HTML 看板](scripts/board.py) | 保持状态只读，核对 [Backlog 技能](skills/sdlc-backlog/SKILL.md)，运行[投影测试](scripts/test_backlog.py)。 |
| 阶段派工、执行权限或恢复 | [阶段协议](skills/sdlc/references/stage-agent-protocol.md) | 核对 driver、运行时适配、[任务模板](skills/sdlc/references/templates/TASK.md)和各阶段引用。 |
| 插件维护与发布 | [维护角色](skills/sdlc/references/roles/skill-maintainer.md)、[维护与发布流程](skills/sdlc/references/evolve-loop.md) | 按[改动范围判定](skills/sdlc/references/evolve-loop.md#2-判断改动范围)选择局部维护或完整 SDLC。 |

## 提交前

```bash
bash scripts/validate-skills
git diff --check
```

测试范围和按需检查见[测试指南](docs/testing.md)。同时更新 `CHANGELOG.md`；发布行为变化时按语义化版本同步
`.claude-plugin/plugin.json` 和 `.claude-plugin/marketplace.json`。

## 状态与上下文约定

- `.sdlc-v1/state.json` 必须纳入目标仓库 Git，不要加入 `.gitignore`。
- Requirement/Feature 的 context ref 必填，且只能指向已存在、非符号链接的 `.sdlc-v1/context/*.md`。
- 不把 Markdown 正文、完整测试输出或评审全文塞进 `state.json`。
- `next` 是公开 state 查询：单候选返回下一阶段，多候选返回 `needs_selection`，不得静默任选一条。
- orchestrated mode 中只有主 Agent 可运行 lifecycle mutation 或写 `state.json`；阶段 Agent 返回 artifact、证据、上下文候选和有序 `requested_transitions`。缺少证据、用户决定或外部授权时暂停；无子 Agent 能力时串行 inline fallback。
- backlog/board 只能读取 state 并生成 `readyqueue/coverage/lint/tree/board` 投影；禁止反写 lifecycle 状态。
- validation 前 state 必须已 tracked、无 unmerged index entry 且未 staged，当前 context 必须已 tracked 且无冲突，
  业务代码工作树必须干净；之后只提交 `.sdlc-v1/**` 不使验证失效，其他路径变化后必须重新验证。
- `project.md` 可索引当前 commit 已验证的 `AGENTS.md`、架构、目标、产品和开发文档；缺失或过期的 `.repo-context/`
  索引不阻塞 onboard，且 SDLC 不读取或写入 repo-context 的状态。
- `.sdlc-v1/context/*.product.md` / `*.engineering.md` 只承载当前 Requirement/Feature；产品上下文维护方向来源、结果观察计划及 Requirement 回流，
  工程上下文引用该计划，记录技术发布准备、实际发布/观测结果、反馈证据与缺口。长期文档不复制进 lifecycle context。
- repo-context 的文档或指导改动不属于 `.sdlc-v1/**`，所以 validation 后修改它们必须建立独立维护 Requirement 或重新验证。
- `init` 检出旧 sdlc-pilot copied hooks 时必须停止并给出路径；只能人工检查/清理，不能自动覆盖团队 hooks。
- 多人冲突按普通 Git 冲突处理；同步并解决冲突后重跑测试和状态检查。
- 本仓现有 `.sdlc/archive/` 属于项目历史，不代表 1.0 运行时协议。

## 测试边界

结构检查只验证 frontmatter、关键共享文件和本地引用；行为测试只覆盖仍存在的轻量实现。
`validate-modes/eval-bench.md` 用于验证业务产品内的 AI 功能，应保留。Web Review Live 模式用于本地文档批注，
也应保留。两者都是与 lifecycle state 正交的普通能力；不要把阶段 Agent 协作扩展成新的行为 Eval、事件 runtime 或自动 retrospective。
