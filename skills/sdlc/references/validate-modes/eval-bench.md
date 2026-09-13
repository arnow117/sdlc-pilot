---
mode: eval-bench
triggers: [models/**, strategy/**, "*.prompt*", ai/**, evals/**, prompts/**, agents/**]
distilled-from: [ai-evals.md, gsd-eval-review, benchmark, benchmark-models, tb-run-analyzer, tb-task-operator]
---

# Validate mode: eval-bench

eval-bench 判断模型、提示、检索、agent 或策略改动相对当前基线是改善、持平还是回归。详细正文只写当前 Feature 研发上下文，机器进度只写 lifecycle state。

## 输入与记录位置

- 产品上下文中的失败模式、质量属性和验收阈值。
- 当前 Feature 研发上下文中的 rubric、数据集引用、测量方式和性能预算。
- 项目原生 `evals/`、benchmark 配置与版本化 baseline。
- 当前 Git diff，以及本轮评估将绑定的实现 commit。

详细结果追加到 `.sdlc-v1/context/<FEAT>.engineering.md` 的 `## Validation` / `### Eval Bench`。数据集、runner 输出和 baseline 可以继续放在项目自己的 `evals/` 或测试产物目录；它们是可复现测试资产，不保存生命周期进度。

## 适用范围

触发：

- 模型、prompt、system instruction、tool definition、agent 编排或检索策略变化。
- 数据管道变化会直接影响模型输入或质量评分。
- 产品上下文明确要求常驻 AI 回归评估。

纯 UI、CRUD 或确定性业务逻辑不运行本模式。

## 核心方法

1. 产品评估优先于通用模型基准。
2. 测量优先级为 deterministic code → calibrated judge → human。
3. judge 必须先和人类评分校准；建议相关性至少 0.7。
4. 先验证评估装置能区分已知好样本与已知坏样本，再运行真实候选。
5. 质量判断看相对 baseline 的变化，并同时检查绝对业务阈值。
6. provider、超时、限流或环境失败属于 invalid run，不计入质量分。
7. 灾难性失败模式单独检查，不能被平均分掩盖。

## 执行方法

### 1. 确认评估契约

研发上下文应包含：

- 3–5 个不可接受的失败模式。
- 每个维度的 rubric 与 1/3/5 或等价锚点。
- 每个维度采用 code、judge 或 human。
- reference dataset 的路径、构成和版本。
- 质量、延迟和成本阈值。

缺少这些内容时，只能做最佳实践检查并标 `PARTIAL`；回到 spec/plan 补齐后再给出发布结论。

### 2. 检查数据集

优先维护 10–20 个高质量代表样本，再逐步扩展。至少覆盖：

- 关键成功场景。
- 常见用户工作流。
- 已知边界。
- 历史失败模式。

数据集应版本化并避免包含未授权敏感数据。

### 3. 自检评估装置

- 1–2 个已知好样本应得到高分。
- 1–2 个已知坏样本应得到低分。
- 任一方向不符合预期时，先修 runner、rubric 或数据，不输出候选质量分。

### 4. 校准 judge

使用 LLM judge 时：

- prompt 中写入 rubric 锚点和领域正反例。
- 抽样由人类独立评分。
- 相关性低于约定阈值时，judge 结果只作参考；关键维度改用 code 或 human。

### 5. 运行与有效性分类

对每个样本保留必要的输出、工具调用和中间轨迹。多模型比较必须使用同一输入、rubric 和 judge 设置。

每条运行分类为：

| 类别 | 是否计分 |
|---|---|
| pass | 是 |
| valid failure：模型或策略本身失败 | 是 |
| invalid：认证、限流、超时、环境或 runner 失败 | 否，修复环境后重试 |

多 provider 或高成本批量运行前，先确认认证状态、样本数、模型、预计并发和成本；没有明确授权时不启动会消耗外部额度的批量任务。

### 6. baseline 与阈值

使用项目已有 baseline；首跑时把当前可复现结果作为项目原生 eval 资产提交。比较：

- 各维度分数。
- 灾难性失败数量。
- p50/p95 延迟。
- 单次或批次成本。
- valid/invalid 数量。

默认参考值可被产品上下文覆盖：

| 指标 | warning | regression |
|---|---|---|
| 质量相对下降 | 大于 5% | 大于 10% |
| 延迟相对增加 | 大于 20% | 大于 50% 或大于 500ms |
| 成本相对增加 | 大于 10% | 大于 25% |
| 灾难性失败模式 | 不适用 | 任一新增失败 |

阈值必须服务于业务决策，不为追求分数而无限增加样本或指标。

## 必要条件

eval-bench 通过需要：

- 评估装置自检正常。
- 使用的 judge 达到项目校准阈值，或关键维度已改用其他测量。
- 有足够 valid observations。
- 没有达到 regression 阈值的维度。
- 灾难性失败模式全部通过。
- 无法运行或未覆盖的部分已明确标 `PARTIAL` 或 `UNVERIFIABLE`。

关键质量或验收条件确实不满足时返回 `sdlc-build` 或 spec/plan；环境阻塞与原因未明按统一归因规则处理，解决后重新评估。

## 写入研发上下文

统一遵循 [sdlc-validate 的验证归因](../../../sdlc-validate/SKILL.md#验证归因)，在下列小节记录每项检查的
outcome、分类依据、执行时间和脱敏环境信息；混合问题分开记录。这里的覆盖/质量指标不替代验证归因。


在 `.sdlc-v1/context/<FEAT>.engineering.md` 更新：

~~~markdown
## Validation

### Eval Bench — <commit>

Dataset: <path and version>
Baseline: <path and version>
Harness check: PASS/FAIL
Judge calibration: <value or not used>
Runs: <total / valid / invalid>

| dimension | method | current | baseline | delta | threshold result |
|---|---|---:|---:|---:|---|
| <dimension> | code/judge/human | <value> | <value> | <value> | PASS/WARNING/REGRESSION |

Critical failures: <none or samples>
Performance: <latency/cost summary>
Verdict: PASS/PARTIAL/FAIL/UNVERIFIABLE
Next action: <none or concrete correction>
~~~

同一 commit 重跑时更新对应小节。不要创建 eval report、SDLC baseline 或额外状态字段。

## 状态更新

eval-bench 不直接编辑 `state.json`。所有选定验证方式合并后，由 `sdlc-validate` 调用一次 `record-validation`。评审和发布分别只通过 `record-review` 与 `record-release` 更新机器状态。

## 常见错误

- 用通用模型基准代替产品评估。
- 信任未校准 judge。
- 把 provider 或环境失败算成模型失败。
- 只看最终输出，不保留必要轨迹。
- 只看绝对分，不比较 baseline。
- 让平均分掩盖灾难性失败。
- 把 runner 输出或 baseline 当作第二份生命周期状态。
