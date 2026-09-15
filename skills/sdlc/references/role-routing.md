# role-routing — diff + project context → roles + validate modes

角色和验证方式每次根据当前上下文与 Git diff 动态计算，不写入进度状态。它们只决定当前阶段需要的专业视角和
验证方式；派工、子 Agent 层级、验收、检查点和 lifecycle mutation 唯一遵循
[`stage-agent-protocol.md`](stage-agent-protocol.md)。

```text
Decision = resolve(
  current lifecycle stage
  × product / engineering context
  × git diff
  × project.md surface map
  × fallback rules
)
```

`.sdlc-v1/project.md` 的 surface map 是项目特化输入，优先于本文件的通用规则。本文件负责未覆盖路径和跨区域补充。

## 1. 解析算法

1. 取得改动文件：工作区使用 `git diff --name-only HEAD`；已提交分支使用 `git diff --name-only <base>...HEAD`。
2. 每个路径先匹配 `project.md` surface map，合并其 roles 与 modes。
3. 未匹配的路径使用下表；一条路径可命中多条规则，结果取并集。
4. 任意代码 diff 至少加入 `qa + correctness`。
5. 命中两个以上不同 surface，或需要 full-chain e2e 时加入 `architect`。
6. 认证、授权、支付、密钥、个人数据、原始 SQL、文件系统或外部输入发生变化时加入 `security`。
7. 产品澄清阶段默认加入 `product-owner`；术语、业务规则或归属复杂时加入 `domain-expert`。
8. 去重后只加载选中的角色卡、验证方式和与扩展名匹配的语言参考。
9. 未归类路径应提示刷新 `project.md` 的 surface map，但不阻止当前工作。

解析结果只用于当前执行。下一次 diff 变化后重新计算。

## 2. 通用路径规则

| 改动路径或信号 | 角色 | validate modes | 说明 |
|---|---|---|---|
| `**/*.tsx`、`**/*.jsx`、`**/*.vue`、`**/*.svelte`、`**/*.css`、`**/components/**`、`**/pages/**` | `client-dev`, `design` | `correctness`, `e2e:Web` | Web 行为、视觉、响应式与无障碍 |
| `**/*.swift`、`**/*.kt`、`**/*.dart`、`ios/**`、`android/**`、`mobile/**` | `client-dev`, `design` | `correctness`, `e2e:App` | 原生或跨端应用 |
| `**/api/**`、`**/handlers/**`、`**/routes/**`、`**/endpoints/**`、`**/controllers/**` | `server-dev` | `correctness`, `e2e:OpenAPI` | API 行为和接口兼容性 |
| `**/models/**`、`**/strategy/**`、`**/prompts/**`、`**/ai/**`、`**/evals/**`、`**/llm/**` | `server-dev`, `qa` | `correctness`, `eval-bench` | AI、模型、提示或评估代码 |
| `**/*.sql`、`**/pipelines/**`、`**/etl/**`、`**/dbt/**`、`**/warehouse/**`、`**/migrations/**` | `big-data` | `correctness` | 数据、回填、lineage 和一致性 |
| `**/*.test.*`、`**/*.spec.*`、`**/test/**`、`**/tests/**`、`**/e2e/**` | `qa` | `correctness`，按被测面补 e2e | 测试本身发生变化 |
| `**/agents/**/*.json`、`**/workflows/**/*.json`、`**/processes/**/*.json`、`**/employees/**/*.{yaml,yml}`、`**/SKILL.md` | `server-dev` | `correctness` | 声明式配置和技能定义；涉及权限矩阵时补 `security` |
| `CLAUDE.md`、`AGENTS.md`、`.claude/**`、`justfile`、`Makefile`、`tsconfig.json`、`.github/**` | `ai-readiness` | `correctness` | AI 工程上下文、构建和自动化配置 |
| 当前仓库的 `skills/**`、`.claude-plugin/**` | `skill-maintainer` | `correctness` | 维护 SDLC 技能体系自身 |

## 3. 跨区域规则

- diff 命中客户端、服务端、数据、AI、声明式配置中两个以上类别：加入 `architect`。
- 公共 API、持久化格式、跨机器交互或不可逆外部行为变化：加入 `architect`，必要时进行一次独立复核。
- 敏感区域变化：加入 `security`，不得仅依赖其他角色顺带检查。
- 用户可见行为变化：即使只改服务端，也应根据产品场景决定是否补 `design` 或对应 e2e。

## 4. 角色字典

| 角色 | 文件 | 关注点 |
|---|---|---|
| `product-owner` | `roles/product-owner.md` | 问题、用户、结果、范围和取舍 |
| `domain-expert` | `roles/domain-expert.md` | 术语、规则、不变量、业务归属 |
| `qa` | `roles/qa.md` | 验收追溯、回归、失败路径和测试真实性 |
| `client-dev` | `roles/client-dev.md` | Web、移动端、状态、性能和无障碍 |
| `server-dev` | `roles/server-dev.md` | 服务端、API、性能和输入边界 |
| `design` | `roles/design.md` | 视觉、交互、状态和用户旅程 |
| `big-data` | `roles/big-data.md` | 管道、数仓、幂等、分区和 lineage |
| `architect` | `roles/architect.md` | 跨区域结构、依赖方向、契约和影响范围 |
| `security` | `roles/security.md` | 认证、授权、数据保护、供应链和滥用风险 |
| `ai-readiness` | `roles/ai-readiness.md` | 项目对 AI 执行者的可理解性和可验证性 |
| `skill-maintainer` | `roles/skill-maintainer.md` | 技能结构、重复规则、可移植性和发布质量 |

## 5. validate mode 字典

| 模式 | 参考 | 适用范围 |
|---|---|---|
| `correctness` | `validate-modes/correctness.md` | 每次代码变更 |
| `e2e:Web` | `validate-modes/e2e.md` | Web 用户旅程 |
| `e2e:OpenAPI` | `validate-modes/e2e.md` | API 行为 |
| `e2e:App` | `validate-modes/e2e.md` | 移动端用户旅程 |
| `eval-bench` | `validate-modes/eval-bench.md` | 模型、策略、提示或数据质量评估 |

## 6. 语言参考

按改动扩展名加载，不把语言细节重复写进角色卡：

| 扩展名 | 参考 |
|---|---|
| `*.py` | `languages/python.md` |
| `*.ts`, `*.tsx`, `*.js`, `*.jsx` | `languages/typescript.md` |
| `*.go` | `languages/go.md` |
| `*.rs` | `languages/rust.md` |
| `*.kt` | `languages/kotlin.md` |
| `*.swift` | `languages/swift.md` |
| `*.java` | `languages/java-spring.md` |

新增角色、验证方式或语言参考时，先更新本文件字典，再更新使用它的 onboard、validate 与 review 技能，避免多处定义不同取值。
