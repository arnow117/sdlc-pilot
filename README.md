# sdlc-pilot

sdlc-pilot 是一组供 Claude Code 和 Codex 使用的技能。你可以让 Agent 把需求整理成验收标准，按任务实现，在具体的 Git 提交上验证、评审并记录发布结果。进度和设计都保存在项目仓库里，换人或换机器后也能接着做。

## 安装

**Claude Code**　在会话中从插件市场安装：

```text
/plugin marketplace add arnow117/sdlc-pilot
/plugin install sdlc-pilot@sdlc-pilot
```

**Codex**　在终端克隆仓库，将技能链接到本地技能目录，然后打开新的项目会话：

```bash
git clone https://github.com/arnow117/sdlc-pilot.git
cd sdlc-pilot
mkdir -p "$HOME/.agents/skills"
for skill in "$PWD"/skills/*/; do
  ln -sfn "$skill" "$HOME/.agents/skills/$(basename "$skill")"
done
```

## 第一次使用

在**要开发的项目**里打开会话，按你的安装方式输入一条请求。

**Claude Code**

```text
/sdlc-pilot:sdlc 为订单列表增加 CSV 导出。先和我确认导出的字段、权限和验收标准。
```

**Codex**

```text
$sdlc 为订单列表增加 CSV 导出。先和我确认导出的字段、权限和验收标准。
```

第一轮先确认规则。例如，列表按月份筛选后，CSV 应包含当月订单还是全部订单？确认后，Agent 会把约定写进产品上下文，作为实现和验收的依据。想看一份填写好的样例，可以参考[本地待办 CLI 的需求与交付计划](examples/small-project-context.md)。

| 你想做什么 | 可以这样说 |
|---|---|
| 查看进度 | “看看订单导出做到哪一步了。” 查询只读取已有记录。 |
| 继续已有需求 | “继续订单导出，从上次停下的地方做。” Agent 根据仓库里的进度和上下文恢复。 |
| 先看交互效果 | “用 sdlc-prototype 把这份需求做成可点击的原型。” [原型技能](skills/sdlc-prototype/SKILL.md)可独立使用。 |

## 工作流程

一条需求（Requirement）描述要解决的问题和验收标准。进入交付时，为它建立一个交付项（Feature），再拆成实现任务（Task）。同一仓库可以并行跟踪多条需求。

```text
产品设计    收集需求 → 明确范围和验收标准
                              ↓
软件交付                    制定计划 → 实现任务 → 验证 → 评审 → 发布
```

尚未纳入跟踪的小型、局部、可逆修改，可以直接实现并验证。已有跟踪项、明确要求完整交付的工作，以及涉及跨端协作、公共协议、持久化或并发恢复的变更，按对应阶段推进。[阶段选择规则](skills/sdlc/SKILL.md#2-入口)

需要你判断的产品选择、真实体验或外部授权，会在相应步骤交给你确认。Agent 可以自行验证的部分，会按已确认的范围继续推进。[产品设计](skills/sdlc-product-design/SKILL.md) · [软件交付](skills/sdlc-software-delivery/SKILL.md)

## 进度与交接

| 目标项目中的文件 | 记录内容 |
|---|---|
| `.sdlc-v1/project.md` | 项目入口、技术栈、测试命令和已有架构文档的位置 |
| `.sdlc-v1/context/*.product.md` | 当前需求的场景、范围、业务规则和验收标准 |
| `.sdlc-v1/context/*.engineering.md` | 当前交付项的设计、任务、验证和发布证据 |
| `.sdlc-v1/state.json` | 需求、交付项和任务的进度，以及对应文档的引用 |

将状态和上下文随代码一起纳入 Git。交接前提交并推送，接手者拉取同一分支即可查询进度。

### 状态命令

从 sdlc-pilot 源码目录执行，将路径替换为目标项目的实际位置：

```bash
python3 scripts/lifecycle_state.py --repo /path/to/project status
python3 scripts/lifecycle_state.py --repo /path/to/project next
```

`status` 查看共享进度，`next` 查询下一步。有多个候选项时，先选择要推进的工作。[状态与恢复指南](skills/sdlc/references/lightweight-runtime.md) · [修正开发分支登记](skills/sdlc/references/lightweight-runtime.md#51-开发分支登记迁移)

## 进一步阅读

- 验证交付结果：[Web / App 端到端验证](skills/sdlc/references/validate-modes/e2e.md) · [安全扫描](skills/sdlc/references/validate-modes/security-scan.md)
- 团队共用的工程规范由项目负责人确认，规划、实现和评审时引用原文。[项目级架构约束](skills/sdlc/references/lifecycles/software-delivery.md#项目级架构约束)
- 配置阶段协作：[阶段执行协议](skills/sdlc/references/stage-agent-protocol.md) · [T3 派工边界](skills/sdlc/references/stage-agent-protocol.md#t3-layer-boundary)
- 升级或维护插件：[版本与升级记录](CHANGELOG.md) · [文档导航](docs/README.md)
