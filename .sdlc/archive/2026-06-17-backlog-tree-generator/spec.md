# Spec: 工程代码 → backlog 需求树 自动生成器（capability 主轴 + 4 交叉视图）

> Date: 2026-06-16
> Status: approved
> Target surface(s): backlog 工具（sdlc-backlog Seed 升级 + scripts/backlog.py + 叶 schema）
> Active roles (anticipated): skill-maintainer (R10), qa, architect（子系统设计/数据模型变更）
> Validate modes (anticipated): correctness（+ dogfood 验证于 vendor-research）

## 1. 问题 / 目标

`sdlc-backlog` 的 Seed 现在只建**空骨架**（domain/subdomain 目录），叶子全靠人 Ingest。目标：让 sdlc 能**分析一个工程 codebase → 自动 gen 出有叶子的 backlog 需求树**，叶可直接喂 #4 看板 + ready-queue，形成"已有项目 → 需求树 → 看板 → 选叶起特性"的闭环。

**用途约束（a2，决定轴）**：这棵树主要用于 **PM ↔ 业务对齐**（不是工程内部视角）→ 主轴必须**业务/PM 可读**。

**轴决策（本特性核心，发散收敛产出，见 §4）**：主轴 `domain_path` = **功能/用户故事**（PM 对齐场景驱动）——domain = 功能域/epic（入驻/商品/订单/结算/集成…），叶 = 一条**业务可读的用户故事/功能**（"作为<角色>，我要<能力>，以便<价值>"），**不用工程术语**；engineering 的状态跃迁(B)只**内部辅助定粒度**、不主导叶标题。外加 **4 个交叉视图**作叶元数据：参与者(D，天然内含在用户故事里)、失败代价类(F)、契约面(E)、数据所有权(G)。

## 2. 非目标（YAGNI）

- ❌ **不做轴自动判定**（"扫项目→提议最佳主轴"）——本期主轴**锁定业务能力流**；自动判定记 Deferred。
- ✅（范围内·a1 调整）**#4 看板叶详情面板显示这 4 个交叉字段**——生成器写了就得看得见，否则交互价值兑现不了。基本显示纳入本特性（详情面板已渲染叶字段，加 4 行是小改）。仅**高级交互**（按 actor 筛选、按 failure_class 着色）留 Deferred。
- ❌ **不重造代码分析轮子**——复用 `sdlc-onboard` 的 surface-map 当骨架输入（无 PROFILE 则先 onboard）。
- ❌ 不加顶层 skill（挂 sdlc-backlog 的 Seed 升级 / 派生 op）；不动 stage 枚举。
- ❌ 不做 runtime AI 系统（生成是 agent-playbook，像 onboard；质量靠 §6 correctness 判据，非 eval-bench）。
- ❌ 本轮**只出获批 spec（设计定案）**，不 plan/build（用户明确"先设计机制"）。

## 3. 现状摘要（Explore 产出）

- **复用底座**：`sdlc-onboard`（253 行）四阶段管道（采证→类型→**Phase C 自建 surface-map**：模块/面→globs→角色→模式→Phase D 写 PROFILE）。surface-map 已把 codebase 切成"有意义的面" + 带描述注释——**已是准需求骨架**。
- **叶数据模型**（sdlc-backlog §1.2）：10 必填字段（id/title/domain_path/cross_link/old_system_ref/new_domain_path/status/priority/depends_on/risk_level）+ 正文 3 段。`status` 状态机 captured→spec'd→planned→built→validated→shipped。`backlog.py` `parse_frontmatter`/`load_leaves`/`lint`(REQUIRED_FIELDS)。
- **Seed 现状**（§2）：只建骨架不造叶（"待覆盖清单"靠 Ingest 填）。
- **验证目标** `workspace/20260615-vendor-research`：pnpm TS monorepo，**已被 onboard**（`.sdlc/PROFILE.md` 有丰富 surface-map：api-identity/api-modules/supplier-web/admin-web/shared-kernel/contracts/...，注释含"product·order·settlement(空骨架)/supplier(半成品)/真实保留"= 现成状态信号）。`contracts/`(OpenAPI provided/consumed)= 天然契约视图源。完美闭环验证。

## 4. 方案与决策

### 4.1 轴决策（发散收敛产出）
跑了 5 框架发散（监管者/物流/竞争者/移除假设/最大主义）共 ~30 候选，聚 8 簇。**关键洞察**：backlog schema 本就 `domain_path`(主)+`cross_link`(次)+双视图 → 答案是**一主轴 + 多交叉视图**，非单轴。

| 决策 | 选择 | 被否/降级 |
|------|------|-----------|
| **主轴 domain_path** | **功能/用户故事**（PM↔业务对齐场景驱动；domain=功能域/epic，叶=用户故事；是 A 业务能力流的 **PM 可读化**） | B 状态机迁移/E 契约/C 事件/F 失败代价**作主轴**=陷阱（工程视角、PM 读不懂、叶归属暧昧、不通用）→ 降为叶粒度参考或交叉视图 |
| **叶粒度** | 自适应="一条可独立交付的用户故事/功能"（业务可读标题）；**内部用状态跃迁(B)辅助定粒度（depends_on 天然无环）但不主导标题** + 每 domain 叶数上限防碎片化 | 细到 endpoint/实体（~200 叶噪声）；粗到 surface 1:1（不够可操作）；用工程术语命名叶（PM 读不懂） |
| **交叉视图（叶可选元数据）** | **D 参与者 + F 失败代价 + E 契约面 + G 数据所有权** 全挂 | — |

**★ 借用的非显而易见洞察**：叶=可交付能力但**尽量对齐状态跃迁**（B）使 `depends_on` 无环；**F 失败代价**当 tag 可驱动 per-domain 不同 validate 严苛度 + review 透镜（不当主轴）。

### 4.2 实现形态
**agent-playbook（判断性分析，**多 agent 并行**见 §5.6）+ backlog.py 脚本（机械落盘+lint）混合**，同 onboard：agent 读码蒸馏出树结构 → 脚本写叶文件 + lint。**挂 sdlc-backlog 的 Seed 升级**（`Seed` 从"只建骨架"扩为"可生成带叶的树"），不加顶层 skill。

### 4.3 叶 schema 扩展（4 可选交叉字段）
给叶 frontmatter 加 **4 个可选字段**（非必填，存量树不填仍 lint clean；生成器能推断则填）：`actor`(参与者)、`failure_class`(失败代价类)、`contract_refs`(契约面)、`data_owner`(数据所有权真相源)。lint 不强制这 4 个（REQUIRED_FIELDS 不变），但**校验取值合法性**（若存在）。

### 4.4 范围姿态
**EXPAND**：值得做大（这是把 sdlc 从"管已收敛需求"扩到"从代码逆向出需求全景"的能力跃迁），但严格 EXCLUDE 轴自动判定 + 看板渲染新字段（Deferred），防爆量。

## 5. 设计（4 段机制）

### 5.1 数据流总览
```
① 盘/采证：有 PROFILE → 读 surface-map 当骨架；无 → 先跑 sdlc-onboard。
            深读：contracts/(OpenAPI 端点)、模块子目录、db/schema(实体)、CLAUDE.md/docs(业务意图)。
② 主轴映射：agent 从 surface-map 模块名 + 业务线索 + 契约，归纳【业务能力域】(入驻/商品/订单/结算/集成)
            → domain/subdomain。不照搬 app/package 结构（A 轴：能力跨 app）。
③ 造叶 + 推断：每 domain 下，叶 = 可独立交付能力（对齐状态跃迁，受 per-domain 上限约束）。
            填 10 必填字段 + 4 可选交叉字段：
            - status：从代码状态推断（空骨架→captured / 半成品→built / 真实保留→shipped）
            - old_system_ref / new_domain_path：从 contracts/模块路径填双视图
            - actor(D)/failure_class(F)/contract_refs(E)/data_owner(G)：能推断则填
            - depends_on：按状态跃迁/能力先后（创建先于履约），保持无环
④ 人审落盘：agent 蒸馏出**树预览** → 复用 #4 看板 / 网页审让人划词改 → 确认后
            脚本写叶文件 + `backlog.py lint` 必须 clean。
```

### 5.1b 看板显示（a1：基本显示纳入范围）
#4 看板的叶详情面板（`render_board` 的 `leaf-data` + `## sdlc 记录` 那块）增加渲染 4 个交叉字段（actor/failure_class/contract_refs/data_owner），有值才显示、无值隐藏（与可选字段一致）。**只做"看得见"**；按 actor 筛/按 failure_class 着色等高级交互 → Deferred。

### 5.2 实现切分（agent vs 脚本）
- **agent-playbook**（判断性，写进 sdlc-backlog SKILL）：盘项目、归纳能力域、定叶粒度、推断 status/交叉字段、控制叶数。
- **脚本**（机械性，backlog.py）：① 校验/写叶文件（可能新增 `seed-gen` 子命令承载"批量写叶 + lint"，或复用 Ingest 的写叶逻辑）；② lint 扩展校验 4 可选字段取值合法。

### 5.3 防碎片化 + 防噪声 + PM 可读（核心风险控制）
- **叶标题/描述 = 业务可读用户故事**（"作为<角色>，我要<能力>，以便<价值>" 或功能名），**禁工程术语**（不叫"实现 OrderService.settle()"，叫"运营能对已履约订单发起结算"）。这是 PM↔业务对齐场景的硬要求（a2）。engineering 的状态跃迁/契约只进 `## 老系统行为参照` 或交叉字段，不进标题。
- 每 domain 叶数**软上限**（如 ≤12），超则 agent 必须合并/上提到 subdomain，或在预览里标"是否过细"。
- 叶必须是"可独立交付的用户故事/功能"（能写出验收线索 + 有 actor），不是"一个端点/一个文件/一个类方法"。
- 预览人审是**硬闸**：生成质量不稳时，人在落盘前剪枝。

### 5.6 运行时并行（多 agent · a3：串行太慢）
分析大 codebase 必须并行。复用 sdlc 既有 **Task-or-sequential + 单写者**原语（同 sdlc-review 的"一角色一 agent、各写各文件、orchestrator 合并"），**不引新编排基建**：

```
两阶段:
  阶段1 (orchestrator 单趟,便宜): 读 surface-map + 业务线索/契约 → 归纳【功能域列表】(domain 骨架)。
  阶段2 (fan-out, 并行): **一功能域一 agent**,各自深读该域相关代码/契约 → 产该域的用户故事叶
         (含 status/depends_on/4 交叉字段),**各写各的草稿** `<tmp>/gen/<domain>.json`,**互相隔离**(不把
         一个域的产出喂给另一个,避免锚定;同 divergence 隔离纪律)。
  合并 (orchestrator,单写者): 跨域去重 + 跨域 cross_link(一个故事跨 2 域) + 跨域 depends_on 保无环
         + 每域叶数上限 → 汇成全树。
  → 人审预览(§①④) → 脚本写叶 + lint。
```
- **并行单元 = 功能域**（域间弱耦合可独立分析、域内故事内聚——粒度合适；不是一文件一 agent 的过细，也不是整仓一 agent 的过慢）。
- **可移植降级**：有 Task → fan-out 一域一 agent；无（Codex/无并行）→ 串行 inline 逐域跑**同一份 playbook**。两档同纪律。
- **单写者铁律**：fan-out 的域 agent 只写**各自草稿**；只有 orchestrator 合并后写最终树 + STATE，绝不并发写同一文件（防竞态，同 sdlc 全家）。
- 阶段1 必须先于 fan-out（每个 agent 需被分配一个"它负责的域"）；域列表本身也可人审一眼再 fan-out（防分析方向跑偏后白跑 N 个 agent）。

### 5.4 错误处理 / 降级
- 无 PROFILE 且用户不想 onboard → 降级：仅从顶层结构 + contracts 粗粒度生成，标 PARTIAL，提示 onboard 后可细化。
- 推断不出某交叉字段 → 留空（可选字段，不阻断）。
- lint 不过 → 不落盘，回报问题清单（同现有 lint 纪律）。

### 5.5 验证策略
- correctness：backlog.py 新逻辑（写叶/lint 扩展）单测；4 可选字段的 lint 校验 TDD。
- dogfood 验证（§6）：对 vendor-research 真跑生成器 → 出树 → lint clean + 人工核对覆盖 apps/packages/contracts 不漏、能力域合理、不碎片化。

## 6. 怎么算 done（前置验收）

机制设计（本轮 spec 终点）：
- [ ] spec 把"轴/粒度/输入/交叉字段/人审/降级/验收"定清且获批。

实现（下期 build 的验收，先记此）：
- [ ] 对 vendor-research 跑生成器 → 产出 `.sdlc/requirements/` 树：主轴是业务能力域（非 app/package 结构）。
- [ ] 树 `backlog.py lint` clean；叶含 4 可选交叉字段（能推断处已填）。
- [ ] 覆盖项目真实 surface：apps/packages/contracts 的业务面不漏（人工核对清单）。
- [ ] 不过度碎片化（每 domain 叶数在上限内）；叶都是"可独立交付的用户故事/功能"（有验收线索 + actor）。
- [ ] **叶标题业务可读（PM↔业务对齐场景）**：抽样核对叶标题是用户故事/功能口吻、无工程术语（a2）。
- [ ] status 推断合理（空骨架=captured、真实=shipped）；depends_on 无环。
- [ ] 人审预览闸可用（复用 #4 看板/网页审）。
- [ ] #4 看板叶详情显示 4 交叉字段（有值即见）。

## 7. Eval 契约
N/A — 生成是 **agent-playbook**（Claude 读码产树，同 onboard），非 runtime 模型调用。其"产得好不好"= §6 的 correctness/覆盖/不碎片化判据（产出查判据），不是 eval-bench rubric。

## 7b. 设计契约
N/A — 人审预览**复用 #4 看板**（仓根 DESIGN.md 已覆盖）；本期不新增 UI。

## 8. Deferred Ideas

- **轴自动判定**：生成器扫项目→提议最佳主轴（业务 app→能力流 / 数据管道→数据流 / 库→契约面）→人确认。
  - Why：不同项目类型最契合的主轴不同，写死 A 对非业务项目可能不贴。
  - Trigger：A 轴在多类项目上验证后，若发现明显错配。
  - 线索（去哪找细节）：发散簇 G(数据流)/E(契约面) 即备选主轴；onboard 的项目类型识别(Phase B)可复用为判定输入。
- **#4 看板交叉字段高级交互**（基本显示已纳入本期，见 §5.1b；此处仅高级部分）：按 actor 筛选、按 failure_class 着色分组、按 contract_refs 反查震动面。
  - Why：基本显示让人看见字段；筛选/着色让人**按交叉视图操作**树，价值更大但非必需。
  - Trigger：基本显示 ship、用户用过后想按维度切。
  - 线索：#4 board 的 `render_board`/`leaf-data`（scripts/backlog.py）+ DESIGN.md status 色板可扩 failure_class 色 + 看板顶部可加筛选条。
- **不依赖 onboard 的独立深分析**：若 onboard surface-map 不够细，生成器自带一层代码深读。
  - Trigger：surface-map 骨架被证明粒度不足以支撑能力域归纳时。

## 9. Canonical refs
- `skills/sdlc-onboard/SKILL.md`（Phase C surface-map 测绘 — 骨架输入来源）
- `skills/sdlc-backlog/SKILL.md`（§1.2 叶 schema、§2 Seed、§3 Ingest 写叶逻辑）
- `scripts/backlog.py`（parse_frontmatter/load_leaves/lint/REQUIRED_FIELDS — 写叶+lint 扩展点）
- `workspace/20260615-vendor-research/.sdlc/PROFILE.md`（验证目标的 surface-map）+ `contracts/`（契约视图源）+ `explorer-repo-report.md`（业务意图分析参考）
- #4 看板（`render_board`/`board` op — 人审预览复用）
- 发散产出：5 框架 ~30 轴候选，8 簇（A 能力流/B 状态机/C 事件/D 参与者/E 契约/F 失败代价/G 数据周转/H 变更频率）
- `CLAUDE.md` 迭代表「加/改 backlog 派生操作」+「改/扩数据模型」（同步指引）
