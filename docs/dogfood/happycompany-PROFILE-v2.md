# Project Profile: 顶果医疗 (dingguo-happycompany)

> DOGFOOD ARTIFACT v2 — produced by executing the **R7-aware** `sdlc-onboard` playbook
> (Phase A 采证 → B 类型+入口 → C surface-map → D 写 PROFILE) against
> `corp/dingguo-happycompany`. Deliberately written here (workspace docs/dogfood/),
> NOT into the target repo's `.sdlc/`, per the review task instructions.
> Compare with v1: `happycompany-PROFILE.md`.

tech-stack: [claude-code-agent-platform, declarative-json-config, yaml-employee-specs, skill-md-defs, python-stdlib-cli, sqlite]
test-commands: { unit: "none — 项目无测试套件（零 test/spec/pytest/conftest）", coverage: "none — 无覆盖率配置", e2e: "none automated — 仅 med_crm CLI 手动 smoke", typecheck: "none — 声明式 JSON/YAML 无类型门；med_crm 有类型注解但无 mypy/pyright 配置", build: "none — 无构建步骤，平台直接读静态定义文件" }

## Tech stack

| 层 | 技术 | 选它的原因（推断，仅据仓内可查证事实） |
|----|------|-----------|
| Agent 平台 | Claude Code "AI 公司"租户约定（`app.json`/`installed.json`/`.claude/skills/`/`agents/*/CLAUDE.md`） | 整仓是一家由 AI 数字员工运营的公司：员工=agent，能力=skill，权限=role，编排=workflow/process |
| 组织/权限定义 | 声明式 JSON（`roles.json` 角色→授权工具矩阵 + users 绑定；`people.json` 21 名钉钉同步用户） | 平台读静态文件装配组织、人员、入口路由（`entryEmployee`/`routingMode`） |
| 员工 persona 定义 | YAML（`employees/*.yaml`，4 名员工：含 model/systemPrompt/tools/role/schedule/allowedTargets） + 镜像 `agents/<id>/CLAUDE.md` | 声明式定义每个数字员工的人格、授权工具、定时触发与协作目标 |
| 流程编排定义 | JSON（`workflows/contract-service-chain.json` 字段+handoff schema；`processes/contract-service-chain.json` 节点图 nodes/edges） | 把"销售签约→维修执行→财务结算"三步跨员工链路声明化，含 handoffPayloadSchema |
| 能力/工具定义 | SKILL.md frontmatter + `tools.json`（med_crm 9 个工具的 name/riskLevel/参数 schema；collaborate/human-acceptance/human-invoice 三个流程型 skill） | 平台据 SKILL.md + tools.json 注入受控工具；riskLevel 分级（read/internal_write） |
| 业务数据门（唯一真实代码） | Python stdlib CLI（`med_crm/cli.py` argparse → `server.py` handler，sqlite3） | 受控数据门：禁止 agent 直接碰 DB/文件，所有业务读写经此 CLI |
| 数据存储 | SQLite（`crm.db`，6.2MB） | 实际存于 `corp/dingguo/cdata/crm.db`（**仓外**，见 Known risks） |

## Surface map

> 取值字典（单一事实源 = role-routing §3/§4）：
> roles = client-dev | server-dev | design | qa | big-data（security 不进 roles[]，敏感面由 server-dev/qa 卡的 security 子节承载）
> modes = correctness | e2e:Web | e2e:OpenAPI | e2e:App | eval-bench
> 项目类型 = **配置/agent 定义型**（R7）：主体是声明式 JSON/YAML/SKILL.md，验证靠 schema/契约一致性校验，**不跑 eval-bench**；内嵌真实代码按其类型单独归面。

- agent-defs:      globs[ employees/**.yaml, agents/**/CLAUDE.md ]                              roles[server-dev]            modes[correctness]   # 数字员工 persona/指令声明：systemPrompt、授权 tools、role、schedule、handoff 结构
- workflow-defs:   globs[ workflows/**.json, processes/**.json ]                                roles[server-dev, qa]        modes[correctness]   # 跨员工流程编排：节点图 + 字段 schema + handoffPayloadSchema（契约一致性是验证重点）
- role-access:     globs[ roles.json, people.json ]                                             roles[server-dev]            modes[correctness]   # ★权限/工具授权矩阵 = 敏感面（B2，security 子节）；users→role 绑定 + 入口路由
- skill-defs:      globs[ .claude/skills/**/SKILL.md, .claude/skills/med_crm/tools.json ]       roles[server-dev]            modes[correctness]   # 能力/工具契约声明：tool name/riskLevel/参数 schema + 流程型 skill 定义
- platform-config: globs[ app.json, installed.json, agents/**/installed.json ]                 roles[server-dev]            modes[correctness]   # 平台/租户装配配置（应用清单、租户根路径）
- embedded-crm-cli: globs[ .claude/skills/med_crm/med_crm/**.py ]                               roles[server-dev]            modes[correctness]   # 内嵌真实代码：sqlite + argparse 数据门 CLI（R7→按 R3 服务端路由，但无 HTTP 端点故不取 e2e:OpenAPI）
- 未归类:          globs[ agents/**/.session-*.json, memory/** ]                                roles[—]                     modes[—]             # 运行时会话快照（32 个），非源码/非定义，不参与路由

## Conventions

- **声明式优先**：组织/人员/角色/流程/能力都是静态 JSON/YAML/SKILL.md，平台读它们装配运行时；改"行为"= 改定义文件，而非改代码。
- **角色即权限**：`roles.json` 把每个角色映射到一组授权工具名（`med_crm:*` / `human-invoice`）；员工 YAML 的 `tools[]` 必须是其 `role` 在 roles.json 里被授权工具的子集（这是一条可机检的契约）。
- **业务数据只经 CLI**：禁止 agent 用 Read/Write/Edit/Grep/Glob 直接碰 DB/Excel/JSON 业务源（见 `med_crm/SKILL.md` 调用规则 4）。
- **工具风险分级**：`tools.json`/SKILL.md 每个工具带 `riskLevel`（read / internal_write）；写操作必须用角色授权工具。
- **handoff 结构契约**：员工 YAML/CLAUDE.md 里声明的 handoff payload（如 sales→maintenance 的合同字段）应与 `workflows/*.json` 的 `handoffPayloadSchema` 对齐。
- **CLI 设计纪律**：thin + deterministic，parse → call handler → print JSON（见 `cli.py` docstring）。
- **流程数据溯源**：workflow `source` 字段记录真实 OCR 合同样本来源；金额/日期入库前需人工复核。
- **员工工作边界**：每个 agent 只在自己 workspace 内读写 memory，不跨员工目录、不探测运行环境（见各 `agents/*/CLAUDE.md` 工作边界节）。

## Entry points

- **租户装配入口** = `app.json`（公司名/行业模板）+ `installed.json`（租户根路径，**已 stale**，见风险）。
- **组织/权限装配入口** = `roles.json`（roles 矩阵 + users 绑定 + 入口路由 `entryEmployee`/`routingMode`）+ `people.json`（21 名同步用户）。
- **数字员工入口** = `employees/<id>.yaml`（权威 persona 定义）+ 镜像 `agents/<id>/CLAUDE.md`（4 名：sales-zhangsan / maintenance-lisi / finance-wangwu / admin-workplace）。
- **跨员工流程入口** = `workflows/contract-service-chain.json`（字段+handoff schema）与 `processes/contract-service-chain.json`（节点图：销售→维修→财务 6 节点 5 边）。
- **能力/工具入口** = `.claude/skills/<name>/SKILL.md`（med_crm + collaborate + human-acceptance + human-invoice）。
- **业务数据门 CLI（已实测可跑）** = `cd .claude/skills/med_crm && DINGGUO_CRM_DB=../../../../dingguo/cdata/crm.db python3 -m med_crm.cli <tool> [args]`（`global_search --keyword 江山` 返回真实 JSON 命中）。CLI 实现 = `med_crm/cli.py`（argparse 子命令）→ 动态加载 `server.py` 的 `handle`。

## Known risks

- **类型与 v1 框架范围错位（已由 R7 解决）**：本仓是配置/agent 定义型工程，v1 路由表（Python+Web 代码假设）原本无对应行；R7 引入后才有干净归面（见 dogfood 评估）。
- **跨定义契约无自动校验（最大债）**：以下一致性全靠人工，仓内无任何 schema/契约校验机制：
  - `roles.json` 角色授权的工具名 ↔ `tools.json` 实际 tool name 是否对得上；
  - 员工 YAML `tools[]` ↔ 其 `role` 在 roles.json 的授权集是否为子集；
  - 员工 YAML/CLAUDE.md handoff payload ↔ workflow `handoffPayloadSchema` 是否对齐；
  - workflow.json ↔ process.json 的 steps/nodes、roles、agentId 是否一致（两文件描述同一条链路）。
  → 这正是 R7 "correctness via schema/契约一致性校验" 应覆盖的核心验证面，建议作为首个 feature 的 baseline。
- **`installed.json` path 全部 stale**：根 `installed.json` 与各 `agents/*/installed.json` 都指向 `/Users/.../happycompany/corp/dingguo`（与真实 `corp/dingguo-happycompany` 及 `corp/dingguo` 都不符）。
- **DB 在仓外、路径脆弱**：`med_crm/SKILL.md` 用相对路径 `../../../../dingguo/cdata/crm.db` 指向 `corp/dingguo/cdata/crm.db`（另一目录）。本仓不自包含，无法独立测试。DB 实际存在且可读（6.2MB）。
- **零自动化测试**：无 test/spec/pytest/conftest；`server.py`（348 行）是最大文件且无测试覆盖 → correctness 只能 CLI smoke。
- **本仓未被独立 git 跟踪**：在父仓 `hansen_agent_team` 里整目录是 untracked（`??`），无嵌套 `.git`；`git ls-files` 对它返回空，须用 `find` 判非空（入口门已用 `rev-parse --is-inside-work-tree` + find fallback 正确处理）。
- **会话快照混入仓内**：`agents/*/.session-*.json` 共 32 个（sales 23 / finance 6 / maintenance 3），是运行时产物非源码，已归"未归类"不参与路由。

---

## Dogfood note — onboard playbook v2 实跑记录（非 PROFILE 正文）

按 R7-aware `sdlc-onboard` 四阶段实跑：

- **Phase A 采证**：bash 命中 42 json / 8 md / 4 yaml / 3 py；框架信号仅 `server.py` 命中 sqlite；无 test、无大文件（最大 server.py 348 行）；敏感面命中 roles.json / workflow / process / cli.py。
- **Phase B 类型判定**：声明式定义文件（JSON/YAML/SKILL.md）数量与权重压倒性高于真实代码（3 py，其中 1 个是 `__init__.py`），无包管理清单、无构建、无测试 → 判为 **配置/agent 定义型**（R7）。med_crm Python 是真实可执行代码 → 单独归 `embedded-crm-cli` 面（server-dev/correctness），不混入定义面。
- **入口门 §1**：`git ls-files` 返回空（untracked），改用 `rev-parse --is-inside-work-tree`=true + `find` 探到 `roles.json` → 正确判为"非空、新建模式"。v1 在这里会误判，v2 路径已修。
- **出口门**：test-commands 各槽位无套件，按出口门规则显式标 `none — <原因>`，并在 Known risks 记覆盖率缺口 → 合法通过，不卡门。surface-map 7 面全部覆盖、取值合法、roles 无 security 野值（security 退化为 role-access 面的子节）。
