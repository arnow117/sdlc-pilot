# 文档导航

| 要做的事 | 从这里开始 |
|---|---|
| 安装插件、开始或继续一个需求 | [安装与首次使用](../README.md#安装) |
| 在已有项目里接入 SDLC | [项目测绘示例](../examples/onboard-output-sample.md)展示要找的代码入口、测试方式和待补条件。 |
| 写需求或拆任务 | [小项目示例](../examples/small-project-context.md)展示同一需求的产品文档和工程计划。[产品模板](../skills/sdlc/references/templates/PRODUCT.md)和[工程模板](../skills/sdlc/references/templates/ENGINEERING.md)用于实际填写。 |
| 查看下一步、交接分支或恢复中断的操作 | [运行时操作指南](../skills/sdlc/references/lightweight-runtime.md)列出状态命令、适用条件和恢复步骤。 |
| 了解版本变化或从旧版升级 | [版本记录](../CHANGELOG.md) · [从 0.x 迁移](specs/2026-08-10-lightweight-sdlc.md#8-0x-升级边界) |

## 在目标项目中运行 Agent

从[阶段路由](../skills/sdlc/SKILL.md#2-入口)判断请求属于查询、局部修改还是跟踪中的工作。产品侧按[产品设计流程](../skills/sdlc-product-design/SKILL.md)收敛范围和验收标准，研发侧按[软件交付流程](../skills/sdlc-software-delivery/SKILL.md)推进实现、验证、评审和发布。

阶段之间传递哪些产物、谁能更新状态、恢复时如何核对证据，见[阶段执行与交接协议](../skills/sdlc/references/stage-agent-protocol.md)。需要了解状态、文档与 Git 为什么这样分工，可读[轻量 SDLC 设计](specs/2026-08-10-lightweight-sdlc.md)。

### 遇到具体问题时

| 问题 | 操作依据 |
|---|---|
| 验收需要人实际操作，交给谁、交什么？ | [验收归属与真人交接](../skills/sdlc-validate/SKILL.md#验收归属与真人交接) |
| 什么时候做安全扫描，缺少工具怎么办？ | [选择扫描与处理证据](../skills/sdlc/references/validate-modes/security-scan.md) |
| 第一次做原型或调整已有界面，要准备哪些输入？ | [原型任务与输入](../skills/sdlc-prototype/SKILL.md#识别任务) |
| 开发分支登记错误，怎样修正并确认写入结果？ | [开发分支登记迁移](../skills/sdlc/references/lightweight-runtime.md#51-开发分支登记迁移) |
| T3 的阶段执行者能否继续派工？ | [阶段边界](../skills/sdlc/references/stage-agent-protocol.md#t3-layer-boundary)及 [T3 适配说明](../skills/sdlc/references/runtime-adapters/t3-code.md) |

## 维护 sdlc-pilot

- 修改插件本身，先读[仓库维护约定](../CLAUDE.md)，再按[本次改动选择检查](testing.md#按改动选择检查与复用)。需要核对需求时，可从[使用路径追溯验收依据](testing.md#从使用路径追溯验收依据)。
- 修改看板时核对[当前看板设计](../DESIGN.md#当前看板实现与评审范围)。比较技能或上下文对实验结果的影响，使用[离线对照实验指南](vibe-tests.md)。
- 追溯设计来源可查[方法来源记录](distillation-source-map.md)、[早期吸收评估](absorption-completeness.md)和[跨模块编排演练](agent-orchestration-rehearsal.md)。这些记录对应各自标注的版本或实验。
