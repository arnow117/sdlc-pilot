# Project Profile: 顶果医疗 (dingguo-happycompany)

> DOGFOOD ARTIFACT — produced by executing the `sdlc-onboard` playbook against
> `corp/dingguo-happycompany`. Deliberately written here (workspace docs/dogfood/),
> NOT into the target repo's `.sdlc/`, per the review task instructions.

tech-stack: [claude-code-agent-platform, python-stdlib, sqlite, json-config, yaml-employee-specs]
test-commands: { unit: "(none — no test suite present)", coverage: "(none)", e2e: "(none automated; manual CLI smoke)", typecheck: "(n/a — no typed config)", build: "(none — no build step)" }

## Tech stack

| 层 | 技术 | 选它的原因（推断，仅据仓内可查证事实） |
|----|------|-----------|
| Agent 平台 | Claude Code skill/agent 约定（`.claude/skills/`, `agents/*/CLAUDE.md`, `installed.json`） | 这是一个 Claude Code "AI 公司"租户：员工=agent，能力=skill，权限=role |
| 业务数据访问 | Python stdlib CLI (`med_crm.cli` → `server.py`，argparse + sqlite3) | 受控 CLI，禁止 agent 直接读写 DB；CLI 即唯一数据门 |
| 数据存储 | SQLite (`crm.db`，6.2MB) | 跨仓存放于 `corp/dingguo/cdata/crm.db`（**不在本仓内**，见 Known risks） |
| 配置/编排 | JSON (`roles.json`/`people.json`/`app.json`/`workflows/`/`processes/`) + YAML (`employees/*.yaml`) | 平台读这些静态文件装配角色、人员、流程 |

## Surface map

> 取值字典：roles = client-dev | server-dev | design | qa | big-data | security；
> modes = correctness | e2e:Web | e2e:OpenAPI | e2e:App | eval-bench
> 注意：本仓是 agentic-config 仓，**与 role-routing v1（Python+Web 代码仓假设）匹配很差**——
> 下面是“尽力映射”，多处需要 onboard 师人工裁决（见 dogfood 评估）。

- med-crm-cli:    globs[ .claude/skills/med_crm/med_crm/**.py ]   roles[server-dev]        modes[correctness]   # 唯一真实可执行代码；sqlite + argparse 数据门
- crm-tool-spec:  globs[ .claude/skills/med_crm/tools.json, .claude/skills/med_crm/SKILL.md ]  roles[server-dev, qa]  modes[correctness]  # 工具契约（名/risk/参数 schema）
- agent-skills:   globs[ .claude/skills/{collaborate,human-acceptance,human-invoice}/SKILL.md ]  roles[server-dev]  modes[correctness]  # 流程型 skill 定义（无代码）
- workflow-defs:  globs[ workflows/**.json, processes/**.json ]   roles[server-dev, qa]   modes[correctness]   # 跨员工流程编排 + 字段/handoff schema
- role-access:    globs[ roles.json, people.json ]                roles[server-dev, security]  modes[correctness]  # ★权限/工具授权矩阵 = 敏感面（B2）
- employee-specs: globs[ employees/**.yaml, agents/**/CLAUDE.md ] roles[server-dev]       modes[correctness]   # 员工 persona / agent 指令
- 未归类:         globs[ memory/**, archive/**, agents/**/.session-*.json ]   roles[—]   modes[—]   # 运行时产物 / 会话快照，非源码

## Conventions

- 业务数据读写**只能**经 `med_crm` CLI，禁止 agent 用 Read/Write/Edit/Grep/Glob 直接碰 DB/Excel/JSON 源（见 `med_crm/SKILL.md`「调用规则」4）。
- 角色即权限：`roles.json` 把每个角色映射到一组授权工具名（`med_crm:*` / `human-invoice`），写操作必须用角色授权工具。
- 工具风险分级：`tools.json`/`SKILL.md` 每个工具带 `riskLevel`（read / internal_write）。
- CLI 设计纪律：thin + deterministic，parse → call handler → print JSON（见 `cli.py` docstring）。
- 流程产物来自真实 OCR 合同样本，金额/日期入库前需人工复核（见 workflow `source.notes`）。

## Entry points

- 数据门 CLI = `cd .claude/skills/med_crm && DINGGUO_CRM_DB=<path>/crm.db python -m med_crm.cli <tool> [args]`（已实测可跑：`global_search --keyword 江山` 返回 JSON）。
- CLI 实现入口 = `.claude/skills/med_crm/med_crm/cli.py`（argparse 子命令）→ 动态加载 `server.py` 的 `handle`。
- 角色/权限装配入口 = `roles.json`（roles + users）+ `people.json`。
- 跨员工流程入口 = `workflows/contract-service-chain.json`（销售→维修→财务三步 + handoff schema）。
- 员工 agent 入口 = `agents/<employee>/CLAUDE.md`（各 agent 的指令）+ `employees/<employee>.yaml`。

## Known risks

- **DB 在仓外、路径脆弱**：`med_crm/SKILL.md` 用 `../../../../dingguo/cdata/crm.db` 相对路径指向 `corp/dingguo/cdata/crm.db`（另一个仓）。本仓无 DB，无法自包含测试。
- **`installed.json` path 已 stale**：指向 `/Users/arnow117/hansen_agent_team/happycompany/corp/dingguo`（与真实 `corp/dingguo-happycompany` / `corp/dingguo` 都不一致）。
- **零自动化测试**：无任何 test/spec 文件、无 pytest/vitest 配置；`server.py`(348 行)是最大文件且无测试覆盖 → correctness 模式没有套件可跑，只能 CLI smoke。
- **敏感面 = 权限矩阵**：`roles.json` 是访问控制核心；改动它属安全敏感（B2），但仓里无任何校验它一致性的机制（如 `roles.json` 引用的工具名 vs `tools.json` 实际工具名是否对得上）。
- **本仓未被 git 跟踪**：在父仓 `hansen_agent_team` 里整目录是 untracked（`??`），无独立 `.git`。

---

## Dogfood note — onboard playbook 实跑记录（非 PROFILE 正文）

实际按 `sdlc-onboard` 四阶段跑下来，命中的阻塞/卡点（详见 review findings）：
1. **入口门 §1 用 `git ls-files` 判 repo 非空 → 返回 0**（本仓 untracked），会把一个有 57 个文件的真实项目误判为空/greenfield。
2. **Phase A 多条 bash 用未加引号的 `--include=*.py`**，在 zsh 下触发 `no matches found` 直接报错中断（需 `--include='*.py'`）。
3. **Phase A focus=arch 第 1 条 `git ls-files | awk -F/ '{print $1"/"$2}'`** 同样依赖 git 跟踪，untracked 仓拿不到结构。
4. **surface-map 取值字典 vs role-routing 不一致**：PROFILE 模板/skill §C 字典含 `security`，但 role-routing §3 角色字典**不含** security（§2 B2 注里说 v1 不单列 security 卡）。onboard 出口门「每个 surface 的角色落在 role-routing 字典内」对 security 会判失败 / 自相矛盾。
5. **test-commands 出口门**要求“至少有 unit”，但真实项目可以**完全没有测试**（本仓即是）；skill 没给“合法地标记 none”的出口，会卡在门口。
6. **本仓类型超出 v1 范围**：onboard 的信号→surface 映射表全是 Python/Web 代码仓假设（frontend/api/models/pipelines），对 agentic-config 仓（skill/role/workflow JSON）**无任何对应行**，所有面都落进“尽力硬塞 server-dev”，surface-map 区分度低、可用性弱。
