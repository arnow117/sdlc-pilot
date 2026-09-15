---
name: sdlc-onboard
description: >
  测绘已有项目并创建 .sdlc-v1/project.md。记录技术栈、入口、约定、测试命令、surface map、
  风险和部署线索，供后续角色与验证方式选择。只读源码，不推进 Requirement 或 Feature。
---

# sdlc-onboard — 建立项目上下文

唯一交付物是 `<repo>/.sdlc-v1/project.md`。已有文件时做局部刷新，保留仍成立的事实。

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。若尚未初始化，主 Agent 先执行
`init`；onboard Agent 只写 `project.md` 并返回证据和上下文候选，不改 `state.json`。

## 输入与边界

- 目标仓库必须明确。
- 采集阶段只读源码、配置与项目说明；不要顺手修代码。
- 不创建 Requirement、Feature 或 Task。
- 当前 onboard Agent 自行完成采集并只写 `project.md`；若主 Agent 需要额外有界分析，派工规则由
  [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md) 决定。
- `repo-context-creator` 是可选的长期工程上下文提供者；缺失、过期或格式不兼容时不阻塞 onboard，也不写入 `.repo-context/`。

## 流程

1. 若 `.sdlc-v1/state.json` 不存在，先调用 `lifecycle_state.py --repo <repo> init`。
2. 先读根 `AGENTS.md` 和当前代码范围内最近的 scoped `AGENTS.md`。若同时存在 `.repo-context/manifest.yaml` 与 `.repo-context/evidence.json`，读取当前 `HEAD`，并只在两份文件声明相同 `analyzedCommit`、相同 `evidenceDigest` 且该 commit 等于当前 `HEAD` 时，将它们作为已验证的长期上下文索引：读取其中列出的既有 canonical 文档路径。缺失、无法解析或不匹配时，标记为 `none` 或 `stale`，继续从源码和配置采集；不要调用、依赖或改写 repo-context 的脚本和文件。
3. 收集可验证事实：
   - 语言、框架、依赖和外部系统；
   - 启动入口、路由、CLI、数据入口；
   - 测试、构建、类型检查和部署命令；
   - 目录约定、项目指令、敏感区域和已知风险。
4. 将代码区域归纳为 surface map：`name → globs → roles → validate modes`。
5. 按 [`role-routing.md`](../sdlc/references/role-routing.md) 检查角色和验证方式是否合法。
6. 按下节的项目上下文结构写入 `.sdlc-v1/project.md`；可复用
   [`PROJECT.md`](../sdlc/references/templates/PROJECT.md) 模板。
7. 向用户展示 surface map、长期上下文来源和不确定项；确认后定稿。

## project.md 必备内容

```text
项目定位
技术栈及选择原因
启动与代码入口
测试/构建/类型检查命令
surface map
工程约定与禁止事项
已知风险
部署目标与配置位置
长期工程上下文来源（AGENTS、canonical 文档路径、evidence commit，或 `none`/`stale`）
```

surface map 中的角色取值来自角色卡目录，验证方式来自 `validate-modes/`。项目特化规则优先于通用路径规则。

## 完成条件

- `project.md` 中没有占位符和未经标记的猜测。
- 每个主要代码目录已归入一个 surface，或明确列为未归类。
- 每个 surface 都有有效 globs、角色和验证方式。
- 实际存在的测试、构建与类型检查命令均已记录；不存在时明确写 `none` 并记为风险。
- 长期工程上下文只记录已验证路径与 commit，不复制正文；不可用时明确原因。
- 只修改了 `.sdlc-v1/project.md`。

完成后返回项目上下文路径、surface 数量、主要测试命令和建议的下一阶段。
