---
name: sdlc-backlog
description: >
  捕获、拆分、排序和查询产品 Requirement。产品正文写入 .sdlc-v1/context/<requirement-id>.product.md，
  进度与依赖写入 .sdlc-v1/state.json。适用于存量代码审计来源、intake、ready queue 和需求状态查询。
---

# sdlc-backlog — Requirement intake

本技能维护多个 Requirement，但不做工程实现。

## Orchestrated mode

遵循 [`stage-agent-protocol.md`](../sdlc/references/stage-agent-protocol.md)。Agent 创建或修订产品上下文，返回
有序 `requested_transitions`；主 Agent 验证后执行 Requirement mutation。只有没有当前主 Agent 编排的独立直接调用
才保留本技能的 standalone 命令；编排中的直接调用仍遵循 orchestrated mode。
当主 Agent 已按协议判定准备批次合格时，本阶段只返回自己的 canonical 候选块；不得将 Spec 或 Plan 候选当成已接受状态。

## 存量代码审计来源

用户要求存量代码体检或改进建议时，按[存量代码审计](../sdlc/references/codebase-audit.md)只读形成和核验发现。本方法不是新的 lifecycle stage；审计本身不要求 state 或 project 已存在，不调用 lifecycle mutation，不修改源码、测试、配置或项目上下文。

需要委托时沿用阶段协议的有界只读分析；本轮只返回发现、证据、未审计范围和待选择项，`allowed_transitions` 为 `[]`。没有子 Agent 能力时按协议披露并串行完成，不把自查称为独立审计。

选中项按可独立确认和交付的结果去重、合并或拆分，不机械地一条 finding 建一个 Requirement。已有授权和确认来源继续有效；选择仍不明确时只确认会改变范围或验收的部分，不把审计授权当作批量交付授权。

进入捕获时，在产品上下文的原始请求与问题中保留审计范围、被查版本/工作区事实、finding 证据、影响、置信度及选择来源；相关拒绝、合并和依赖说明随同记录。已有外部 plan 只作为工程候选来源，由 `sdlc-plan` 重新核对，不能据此跳过 Spec、ready 或当前有效方案。

方向建议保留为有证据的选项；尚未确认的产品方向或关键假设先进入产品澄清或有界调查，不直接转成实现全部建议的 Task。已 ready 或进入交付的目标若发生实际范围变化，仍按“修订、合并与取消”创建合法的新 Requirement 及依赖，不改写旧目标。

## 捕获需求

1. 保留用户原始请求，分清目标、用户、范围和主要约束。
2. 一个 Requirement 对应一个可独立确认和交付的产品结果。过大则拆分；重复则合并或建立依赖。
3. 创建 `.sdlc-v1/context/<requirement-id>.product.md`，至少包含：
   - 原始请求与问题；
   - 用户和期望结果；
   - 范围内 / 范围外；
   - 已知业务规则；
   - 验收条件草案；
   - 未决问题。
4. 调用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  capture-requirement --id <REQ-id> --title <title> \
  --description <summary> --domain <domain> --priority <P0-P3> \
  --product-context-ref .sdlc-v1/context/<REQ-id>.product.md
```

存在依赖时追加 `--depends-on <REQ-id>`。不要直接编辑 `state.json`。

## 修订、合并与取消

需求仍处于 `captured` 且尚未绑定 Feature 时，可以保留原 ID 修订标题、
摘要、领域、优先级、上下文引用或依赖：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  revise-requirement --requirement-id <REQ-id> --priority <P0-P3> \
  --depends-on <REQ-id-a,REQ-id-b>
```

显式传入空的 `--depends-on ""` 可清空依赖。已经 ready 或进入交付的需求
不得回写；如范围变化，创建新 Requirement 并建立依赖。

被更具体需求替代或不再交付的未绑定需求使用：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  cancel-requirement --requirement-id <REQ-id> --reason <why>
```

取消前先处理仍引用它的活动 Requirement，并在产品上下文说明替代关系。
不要删除历史记录，也不要直接编辑 `state.json`。

## 需求澄清与 ready

调用 `sdlc-product-design` 或 `sdlc-spec` 完善产品上下文。满足以下条件后执行：

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> \
  mark-requirement-ready --requirement-id <REQ-id>
```

ready 的必要信息：问题与用户明确、范围明确、关键规则和异常路径明确、验收条件可验证、依赖已满足或已列出。

## 查询与排序

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> readyqueue
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> product-projection --requirement-id <REQ-id>
```

ready queue 按优先级和依赖返回可进入研发的 Requirement。看板可以读取同一状态文件，但不是第二个进度源。

## 完成输出

返回 Requirement ID、产品上下文路径、状态、依赖、下一建议动作。捕获完成通常进入 `sdlc-spec`；ready 后通常进入 `sdlc-plan`。
