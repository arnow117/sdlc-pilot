# Build loop — 测试驱动的批量 Feature 循环

> distilled-from: sdlc-backlog, sdlc-build, Reflexion, AlphaCodium, Anthropic building-effective-agents

`/sdlc loop` 串行消费 lightweight ready queue，复用现有阶段技能，不定义第二套流程。

## 1. 何时使用

| 场景 | 选择 |
|---|---|
| 有多个 ready Requirement，希望连续推进 | `/sdlc loop` |
| 只做一个 Feature | 普通 `/sdlc` |
| 没有 Requirement | 先用 `sdlc-backlog` 捕获 |

循环自动选择下一项和恢复进度，但不会跳过产品确认、测试、评审或发布授权。默认一次只推进一个 Feature；
阶段 Agent 的编排、状态所有权和 fallback 见 [`stage-agent-protocol.md`](stage-agent-protocol.md)。

用户已授权“完成所有需求”等连续执行范围时，在该范围内自动推进后续阶段和 ready Requirement，
不新增逐阶段审批。仅在缺少影响范围、验收或外部操作的必要决策/授权，或满足下文停止条件时暂停；
已有授权继续有效，明确要求逐阶段确认时遵从该要求。

## 2. 外层循环

```bash
python3 <sdlc-pilot-root>/scripts/lifecycle_state.py --repo <repo> readyqueue
```

1. 队列非空时取优先级最高且依赖已满足的 Requirement。
2. 读取其 `product_context_ref`。
3. 主 Agent 运行 plan 阶段，验证其结果后执行请求的 `start-feature` 和 `add-task` mutation。
4. 完成单 Feature 内循环。
5. 发布成功后重新读取 ready queue。

队列为空时，读取完整状态：

- 没有未发布 Requirement：循环完成。
- 仍有未发布 Requirement：报告未满足依赖、被取消项或其他阻塞原因，不声称完成。

## 3. 单 Feature 内循环

```text
plan
  → build（逐 Task TDD）
  → validate
  → review
  → completion check
  → ship
```

每一轮按 [`stage-agent-protocol.md`](stage-agent-protocol.md) 派工、等待、验收和推进状态；该协议也唯一规定
同阶段修正、跨 Feature 交接、证据复用、检查点和并行资格。研发上下文保存设计、Task 细节、测试策略、失败教训和
决策；`state.json` 只保存状态和引用。Plan 不记录派工、催补、调试或重跑日志。

### completion check

发布前同时满足：

1. 所有有效 Task 为 `done`。
2. 产品上下文中的每条验收条件都有实际检查结果。
3. 必要测试与静态检查本轮真实执行成功。
4. review 已批准 validation commit。
5. validation commit 到当前 HEAD 在 `.sdlc-v1/**` 之外无差异，且业务代码工作树干净。

未满足时列出具体缺口：实现或测试缺口回 build；验证过期回 validate；评审问题回 build 后重新 validate/review。

重复派工、修正、评审或重测的停止与恢复条件唯一遵循
[`stage-agent-protocol.md`](stage-agent-protocol.md#5-evidence-git-and-mandatory-stop)。

## 4. 可恢复性

任意时刻中断后：

1. 运行 `status` 和 `feature-projection`。
2. 读取 `project.md`、`product_context_ref` 和 `engineering_context_ref`；只有存在按 canonical protocol 创建的按需
   checkpoint 时才读取它。
3. 从第一个未完成 Task 或当前 Feature 状态继续。

不要依赖对话历史恢复目标，也不要重新生成已存在的 Feature 或 Task。checkpoint 与 HEAD/分支/workspace 不一致时，
先重新判断证据；Feature 完成后删除 checkpoint。

## 5. 每轮复述目标

进入一个 Feature、回到 build 或上下文变长时，重新读取：

- 产品验收条件；
- 当前 Task 完成条件；
- 未完成 Task 与依赖；
- 最近一次失败的根因和下一假设。

这只是恢复注意力，不是重新规划。

## 6. 有价值的失败结论

只有实质方案变化、已确认根因，或最终验证/验收证据有长期价值时，才写入现有工程上下文的相应设计或
验证/验收章节。不要按每次调试失败、派工或重跑追加日志；没有足够事实时保留为当前未解项，不写成确认结论。

## 7. 强化测试

除计划中的测试外，按风险补充空值、边界、并发、失败恢复和非法输入测试。新增测试进入项目正常测试集，并在 validate 阶段运行。

已经通过的测试是回归基线；修复新缺口不能让它们变红。completion check 之后若产生代码或测试 diff，必须重新 validate 和 review。

## 8. 独立复核

运行时支持时，主 Agent 使用与实现者不同的新 Agent，只读检查 diff 是否满足产品验收条件。不可用时按相同角色顺序
串行评审并说明 fallback，且不称其独立。只有可定位、可复现的问题才进入修复列表；判断分歧且缺少事实时交给用户决定。

## 9. 停止条件

- ready queue 为空且没有未发布 Requirement：完成。
- 达到用户设置的 Feature 数量或时间范围：停止并汇报进度。
- 测试基础设施不可用、产品问题未决或需要新的外部授权：停止当前循环并给出所需输入；重复工作无新证据时按
  canonical protocol 的强制停止处理。
- 每次通过判断都必须来自本轮实际命令、输出和 exit code；没有运行就不能声称通过。
- `next` 要求选择、需要用户决策/外部授权、或阶段结果缺少证据时暂停当前 Feature，不执行 transition。
