# Evolve loop：轻量维护 SDLC 技能

> distilled-from: kb-manage, distillation-loop, session:sdlc-evolve-design-2026-06-06

`/sdlc evolve` 用于修改 sdlc-pilot 自身。它只负责定位真实源码、编辑、做最小校验并汇报，不建立独立生命周期状态。

当 evolve 使用多 Agent 编排时，主 Agent、执行子 Agent 和独立评审的职责，以及串行、brief、结果和验收规则，
唯一遵循 [`stage-agent-protocol.md`](stage-agent-protocol.md)。evolve 没有 Requirement/Feature ID 时在 brief 中明确
`not-applicable`；它不因此创建 state、Plan、inbox 或子生命周期。默认主 Agent 只派一个实际执行子 Agent，完成并汇总后
才可按需要派只读独立评审。运行时不支持独立评审时，必须披露 fallback，不能声称独立。

## 1. 定位可写源码

按顺序检查：

1. 当前工作区是否就是 sdlc-pilot Git 仓库。
2. 项目或用户 skill 链接指向的真实路径，例如 `readlink` 结果。
3. 用户明确给出的 clone 路径。

只有真实、可写的 Git 源码可以修改。插件缓存或只读安装目录只用于定位版本；找不到可写源码时，说明需要 clone/fork 的位置后停止。

不要因为当前工作树已有用户改动而清理、恢复或覆盖它们。先用 `git status` 和 `git diff` 确认本次可安全编辑的文件；有重叠时向用户说明。

## 2. 判断改动范围

| 类型 | 例子 | 处理 |
|---|---|---|
| 局部改动 | 调整一张角色卡、一个阶段说明、一个命令示例 | 直接编辑对应文件 |
| 结构改动 | 新增/删除技能、改变路由、状态 schema 或公共命令 | 明确列出受影响入口后再编辑相关文件 |

这个分类用于控制修改范围和发布影响，不强制切换到另一套流程，也不生成额外计划或状态文件。

需要把外部方法合并进角色卡、验证方式或语言卡时，复用 `distillation-loop.md` 的定位原则；普通修正不必完整执行蒸馏流程。

## 3. 编辑原则

- 修改真实来源，不改生成缓存。
- 优先更新已有文件，避免为一条规则新建孤立 reference。
- 同一规则只保留一个权威定义，其他文件链接引用。
- 保留与当前目标无关的用户修改。
- 命令、路径和引用必须与仓库当前实现一致。
- 不建立 evolve inbox、临时账本或第二套进度。
- 不强制创建临时分支；用户希望隔离时才使用普通 Git 分支。

## 4. 最小校验

编辑完成后只运行：

~~~bash
bash scripts/validate-skills
git diff --check
~~~

然后阅读 `git diff -- <本次文件>`，确认：

- 只修改了预期文件。
- 没有断开的相对链接或 frontmatter 问题。
- 没有空白错误。
- 没有误删与本次目标无关的内容。

校验失败时继续修正当前改动并重跑。不要自动恢复整个工作树；需要撤销时只处理本次明确创建的改动，并先取得用户授权。

## 5. 版本与 CHANGELOG

根据发布影响决定，不要求每次 evolve 都升版：

| 改动 | 版本 / CHANGELOG |
|---|---|
| 仅本地使用、文字修正、内部 reference 调整 | 默认不升版；CHANGELOG 可省略 |
| 会随插件发布的行为变化或新能力 | 按现有 SemVer 约定更新版本，并写简短 CHANGELOG |
| 破坏公共命令、状态 schema 或兼容性 | 明确说明影响，按现有规则选择 major/minor，并写迁移说明 |

只有真正准备发布插件时才同步相关插件元数据。不要为了维持“一次修改一次版本”而制造无意义版本。

## 6. Git 权限

- 是否 commit、push 或创建 PR 完全服从用户授权和当前仓库 Git 规则。
- 不自动合并主分支，不自动 push，不以 dry-run 推送探测权限。
- 用户未授权时，只保留工作区修改并汇报差异。
- 用户授权 commit 时，提交内容只包含本次修改。
- 用户授权 push/PR 时，再按现有 remote 和分支执行。

## 7. 输出

完成后简要返回：

- 修改了哪些文件及行为。
- `validate-skills` 和 `git diff --check` 的结果。
- 是否更新版本与 CHANGELOG，以及判断依据。
- Git 工作树状态；若未获授权，明确说明没有 commit/push。

evolve 不编辑目标项目的 `.sdlc-v1/state.json`，也不生成自己的进度文件。
