---
name: sdlc
description: >
  SDLC 总入口与流程路由器。读取 .sdlc-v1/state.json、project.md，以及当前 Requirement/Feature
  引用的产品与研发 Markdown，根据进度和代码改动加载一个主阶段技能与必要角色卡。
  它负责定位、路由和交接，不代替产品设计、实现、验证、评审或发布。
---

# sdlc — router / handoff

`/sdlc` 只做四件事：读取、判断、加载、交接。实际工作由阶段技能完成。

## 1. 唯一目录

目标项目只使用以下结构：

```text
.sdlc-v1/
├── state.json
├── project.md
└── context/
    ├── <requirement-id>.product.md
    └── <feature-id>.engineering.md
```

- `state.json`：Requirement、Feature、Task 的进度与上下文引用；只能通过 `lifecycle_state.py` 修改。
- `project.md`：技术栈、入口、约定、测试命令、surface map、部署线索，以及可选的长期工程上下文索引；由 `sdlc-onboard` 维护。
- `context/*.product.md`：问题、用户场景、业务规则、范围、质量属性和验收条件；由产品侧维护。
- `context/*.engineering.md`：设计、任务、代码位置、测试策略、风险和实施决策；由研发侧维护。

Git 保存历史并负责跨 clone 同步。状态变化可以与相关文档或代码合并为一次正常提交；在交给另一位协作者或另一台机器前提交并推送。

## 2. 入口

1. 确认目标仓库。
2. 若 `.sdlc-v1/state.json` 不存在，执行 `lifecycle_state.py --repo <repo> init`。
3. 若项目已有源码而 `.sdlc-v1/project.md` 不存在，进入 `sdlc-onboard`。
4. 读取 `state.json`，再读取当前记录引用的上下文；若 `project.md` 列出当前 commit 已验证的长期工程上下文，再按需读取其中相关路径；不要扫描无关历史文件。
5. `/sdlc next` 根据当前状态直接进入下一阶段。

## 3. 路由

| 当前意图或状态 | 主技能 | 主要输入 |
|---|---|---|
| 首次理解已有工程 | `sdlc-onboard` | 仓库源码 |
| 捕获、拆分、排序需求 | `sdlc-backlog` | 用户请求、产品上下文 |
| Requirement 尚未 ready | `sdlc-spec` 或 `sdlc-product-design` | `product_context_ref` |
| Requirement ready，尚无 Feature | `sdlc-plan` 或 `sdlc-software-delivery` | 产品上下文、项目上下文 |
| Feature 有未完成 Task | `sdlc-build` | `engineering_context_ref`、代码 |
| Task 全部完成，尚未验证 | `sdlc-validate` | 当前 Git commit、测试命令 |
| Feature 已验证 | `sdlc-review` | validation commit、diff、角色卡 |
| Feature 已评审 | `sdlc-ship` | 已验证 commit、部署配置 |

产品阶段加载 `sdlc-product-design` 的方法；研发阶段加载 `sdlc-software-delivery` 的方法。每次只加载一个主技能。角色卡由
[`role-routing.md`](references/role-routing.md) 根据 `project.md` 的 surface map、当前上下文和 Git diff 选择；只有明确相关时才补充角色。

两个正交命令不改变阶段定义：

- `/sdlc loop`：加载 [`build-loop.md`](references/build-loop.md)，串行消费 ready Requirement。
- `/sdlc evolve`：加载 [`evolve-loop.md`](references/evolve-loop.md) 和 `skill-maintainer`，改进 SDLC 技能体系自身。

## 4. 状态写入

不要直接编辑 `state.json`。阶段技能调用以下命令完成状态变化：

```text
capture-requirement
revise-requirement
cancel-requirement
mark-requirement-ready
start-feature
add-task
set-task-status
record-validation
record-review
record-release
retract-release
```

`revise-requirement` 只修改尚未绑定 Feature 的 `captured` Requirement；
`cancel-requirement` 只取消未绑定且没有活动依赖方的 backlog 项。两者保留
原 ID 和 Git 历史，不能用来改写已进入交付的需求。

`retract-release` 只用于纠正尚未完成声明发布目标及该目标要求的 smoke、
观测，却误写成 `released` 的记录；发布目标可以是明确约定的源码分发，
也可以是环境部署。它要求说明原因，并把 Feature 恢复为 `reviewed`、
Requirement 恢复为 `validated`。正文证据写入 Feature 工程上下文，Git
保留原记录与纠正历史。普通发布失败不得先 `record-release` 再撤回。

产品或研发正文直接编辑其 Markdown；`state.json` 只保存 `product_context_ref`、`engineering_context_ref` 和进度字段。上下文路径必须是 `.sdlc-v1/context/*.md` 下的仓库相对路径。

## 5. 恢复与交接

- 恢复工作时先读 `status` 或具体 projection，再读它引用的上下文。
- `record-validation` 记录测试时的业务代码 commit；评审和发布始终对应这个实现版本。
- 验证后允许提交仅修改 `.sdlc-v1/**` 的状态、上下文和证据。若 validation commit 到当前 HEAD 在该目录之外有差异，或业务代码工作树不干净，则回到 build/validate。
- `project.md` 只索引长期工程上下文，不复制其正文；`.sdlc-v1/context/*.md` 只记录当前 Requirement/Feature 的决定、证据和发布后观察。二者通过路径引用协作，不共享状态文件。
- 完成一次跨人或跨机器交接时，给出 Requirement、Feature、分支、当前阶段、下一动作和需要拉取的 Git ref。

本路由器不复制 BDD、领域建模、SDD、TDD、验证或部署方法；这些正文只在对应阶段加载。
