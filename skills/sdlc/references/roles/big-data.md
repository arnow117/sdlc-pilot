---
role: big-data
triggers: ["*.sql", "**/pipelines/**", "**/dbt/**", "**/spark/**", "**/etl/**", "**/migrations/**", "models/**/*.sql", "**/airflow/**", "**/dags/**"]
distilled-from: [engineering-data-engineer, engineering-database-optimizer, engineering-ai-data-remediation-engineer, review/specialists/data-migration]
---

# big-data 角色卡

数据工程视角关注幂等、契约、可观测、可追溯和零静默丢失。它提供专业检查，不维护独立报告。

## 分层与数据契约

- Bronze 保留原始、不可变、只追加的数据及摄入元数据。
- Silver 负责清洗、去重、标准化和跨域关联。
- Gold 面向业务查询、SLA 和聚合，不应直接读取 Bronze。
- 生产者与消费者之间有显式 schema、主键、空值和兼容性约定。
- schema 漂移应触发告警或明确失败，不能静默改变下游语义。

## 幂等、增量与成本

- [ ] 重跑相同输入得到相同结果，不重复、不丢失。
- [ ] merge/upsert 按稳定主键执行，避免无条件 append 或清空重插。
- [ ] CDC 或增量处理优先于无界全表扫描。
- [ ] 流式管道声明 exactly-once 或 at-least-once，并处理迟到数据和 checkpoint。
- [ ] 关键全量回填有批次大小、速率、暂停和恢复方案。

## 数据质量与 lineage

- [ ] 空值按字段规则 impute、flag 或 reject，不隐式流入 Gold。
- [ ] 关键字段有 not-null、unique、relationships 或等价检查。
- [ ] 任一 Gold 记录能够追溯到上游来源和 transformation。
- [ ] 批处理满足“源记录数 = 成功记录数 + 隔离记录数”。
- [ ] 质量异常有 owner、SLA 和告警。

## 查询与性能

- [ ] 外键、常用 WHERE/ORDER BY 和复合查询有适当索引。
- [ ] 关键查询实际运行 `EXPLAIN ANALYZE`，关注 Seq Scan、估算偏差和排序/回表成本。
- [ ] 避免 `SELECT *`、循环查库、N+1 和无界结果集。
- [ ] 分区、聚簇或预聚合与实际查询模式一致。

## 迁移安全

- [ ] 有可执行的 rollback/down，或明确说明纯加法为何可回退。
- [ ] 删除列、类型收窄和重命名有弃用与兼容期。
- [ ] 新 NOT NULL 列先回填，再增加约束。
- [ ] 大表索引或 ALTER 控制锁时间，支持在线或分批执行。
- [ ] 滚动发布期间旧代码与新 schema 可以共存。
- [ ] forward 和 rollback 已在接近生产规模的数据上演练。

## AI 数据修复

- AI 生成可检查的 transformation，系统执行；模型不直接写生产数据。
- 生成代码经过语法、允许列表和危险调用检查。
- PII 留在获授权环境，不发送到未批准 provider。
- 相似度判断叠加稳定主键约束，避免语义相似导致错误合并。
- 低置信结果进入人工隔离，不自动覆盖。
- 每次修复保留行 ID、旧值、新值、规则、模型版本、置信度和时间，支持回放和撤销。

## 阶段贡献

| 阶段 | big-data 视角 |
|---|---|
| onboard | 将数据面、关键命令、契约和风险记录到 `.sdlc-v1/project.md` |
| spec | 定义 schema、SLA、质量指标、对账和回滚要求 |
| plan | 将幂等、回填、索引、迁移顺序和测试拆成 Task |
| build | 先写数据质量与 schema 测试，再实现管道或迁移 |
| validate | 运行 dbt/data quality/schema/对账检查；AI 质量改动追加 eval-bench |
| review | 检查数据丢失、锁时长、兼容性、lineage 和查询退化 |

## 验证方法

1. 从 diff 找到 pipeline、model、migration 和关键查询。
2. 运行项目已有 parse、schema test、data quality test 与对账命令。
3. 对迁移检查 forward、rollback、锁与回填方案。
4. 对关键查询保存实际 plan 摘要和行数。
5. 对 AI 数据处理检查 transformation、隔离和对账。
6. 失败时返回 build 修复并重新验证。

必要条件：

- 确定的数据丢失风险为零。
- 对账无缺口。
- 迁移可回退且滚动发布兼容。
- AI 不直接修改生产数据，PII 不离开获授权环境。
- 未验证部分有明确原因和人工检查步骤。

## 记录方式

详细证据写入当前 `.sdlc-v1/context/<FEAT>.engineering.md`：

- `## Validation` / `### Data`：命令、exit code、schema 结果、对账数字、查询计划和未验证项。
- `## Review` / `### Data`：严重级别、文件与行、风险、证据和建议修复。

big-data、migration 与 correctness 的正文只写上述研发上下文，不新增 migration-safety 等进度字段。`sdlc-validate` 和 `sdlc-review` 汇总所有角色后，分别调用一次 `record-validation` 或 `record-review`。

## 常见错误

- Bronze 就地转换或 Gold 越层读取。
- schema 漂移被静默接受。
- 非幂等 append 导致重复。
- 空值无规则地流入业务层。
- 大表无界扫描或回填。
- 索引和查询优化只靠静态推断，没有实际 plan。
- 迁移不可回退或与旧代码不兼容。
- AI 直接改生产数据或把 PII 发往未批准环境。
