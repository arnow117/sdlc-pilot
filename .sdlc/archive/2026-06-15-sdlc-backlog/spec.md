# Spec: sdlc-backlog —— 需求树 / backlog（子系统 A）

> Date: 2026-06-15
> Status: draft
> Target surface(s): skill-system-self（sdlc-pilot 家族自身）
> Active roles (anticipated): skill-maintainer
> Validate modes (anticipated): correctness（`scripts/validate-skills`）
> work-type: feature
> Program: 需求驱动的 SDLC 自运转闭环（A 需求树 → B sdlc-loop 调度器）。本 spec 只覆盖 A；B 顺序随后单独 spec。
> 蒸馏来源: Loop Engineering 文章(Addy Osmani / Datawhale) + kb-manage(递归 domain-subdomain + Ingest) + tb-loop-driver(编排模式)

---

## 1. 问题 / 目标

**驱动用例**：用户正按一个老系统的逻辑整体重写新系统。老系统功能点 / 用户故事**已存在且可枚举**；业务侧**散点式**给需求（非依赖序、随时冒出），而非增量式有序输出。

现状缺口：sdlc-pilot 有 pipeline（spec→…→ship 7 个 process skill），但**没有跨特性的需求来源（backlog）**——work-source 靠人手动在 `/sdlc spec` 一次注入一条。散点需求堆进非结构化列表会迅速失控，且无法回答"老系统每个模块是否已被重新覆盖"。

**目标**：建一个**机制通用、数据项目本地**的需求树 / backlog 子系统，让散点需求被稳定归档、覆盖度可观测、并派生出一个可被未来 sdlc-loop（子系统 B）消费的 ready-queue。

- **机制**进 sdlc-pilot（新 skill `sdlc-backlog`，commit 回 GitHub，所有项目可用）。
- **数据**留在目标项目 `<target-repo>/.sdlc/requirements/`（老系统的实际 domain 树）。
- 类比 kb-manage：skill 通用 / 数据在 `~/Documents/nsync/ai_knowledge`。

## 2. 非目标（YAGNI）

- ❌ 不做子系统 B（sdlc-loop 调度器：dequeue→pipeline→回写→停、定时/事件触发、成本分诊门）——B 走自己的 spec→plan→build，本 spec 只产出 B 消费的 **ready-queue 契约**。
- ❌ 不做自动从老系统代码逆向生成需求的 AI 抽取器——Seed 操作给的是**人/agent 协助的骨架生成流程**，不是全自动逆向引擎。
- ❌ 不替代 sdlc-spec——A 管"需求集合"，spec 仍收敛"单条叶需求"。一片叶被 ready 后，照常进 spec→…→ship。
- ❌ 不引入运行时数据库 / 服务——纯文件 + git + Read/Edit/Bash/Grep（可移植铁律）。

## 3. 现状摘要（Explore 产出）

**代码现状**（sdlc-pilot 家族）：
- 家族 = driver `sdlc` + 7 process skill（onboard/spec/plan/build/validate/review/ship）。版本 0.8.0。
- stage 枚举：`onboard|spec|plan|build|validate|review|ship|done`（driver §4 + STATE 模板）。
- 状态 artifact：`.sdlc/PROFILE.md`（项目记忆）、`.sdlc/STATE.md`（单特性交接）。**无跨特性 backlog artifact**。
- `scripts/validate-skills` = 家族 correctness（断链/孤儿/frontmatter/交叉引用）。`scripts/sdlc-guard` = 边界守卫。

**可复用资产**：
- `kb-manage` / `ai_knowledge`：`domain→subdomain→entity.md` 递归文件树 + Ingest/Query/Browse/Relate/Lint 五操作 —— **直接复用递归结构 + 操作范式**。
- `tb-loop-driver` + forge/operator/analyzer：导演 + phase 子例程的 loop 编排 —— B 复用，A 不直接用。
- `planner-breakdown-sdlc`：一次性项目→阶段分解 —— Seed 操作可借鉴其"理解后再拆"，但 A 要的是**持久 + 递归 + 可累积**，planner 是一次性非持久。

**文档现状**：本 program 无既有 spec/ADR。本 spec 为首份。

**测试现状**：家族无单测；correctness = `scripts/validate-skills`。新增 skill 需通过它（被引用、frontmatter 合法、无孤儿）。

## 4. 方案与决策

**已定（经用户逐项确认）**：

1. **范围**：A + B 都要，但**顺序两个 spec**（A 先，B 后），不做 mega-spec。A 是 B 的前置。
2. **落点**：混合——机制进 sdlc-pilot，数据留项目。
3. **机制形态**：新 skill `sdlc-backlog`，作为 **pre-spec 新阶段**。
   - 被否方案：扩 sdlc-spec/onboard（scope 不同：集合 vs 单条 / PROFILE vs 需求）；references 卡 + 路由（5 操作体量等同 kb-manage，非一张卡）。
   - **代价**：触及 stage 枚举契约 → 需 4 处同步（role-routing / STATE 模板 / onboard 字典 / driver 枚举），由 build 落地、review 把关。这是把本特性从 evolve 升到完整 `/sdlc` 的根因。

**对抗性自我证伪（§2.5）—— 这设计哪里会塌 + 缓解**：

| 风险 | 后果 | 缓解（已纳入设计） |
|---|---|---|
| R1 老系统 domain 树 ≠ 新系统架构（rewrite≠1:1） | 覆盖图骗人 | 叶同时记 `old_system_ref` 与 `new_domain_path`（双视图）；树骨架可标"重构归并" |
| R2 散点需求跨 subdomain 二义 | 覆盖统计失真、重复 | 叶支持 `cross_link[]`（多父）+ 主分类（domain-path 唯一）；Lint 查重复 |
| R3 自运转 loop 在 rewrite "错了很贵" | 错误顺 loop 放大 | A 只产 ready-queue + `risk_level`；强 gate / 成本门是 B 的责任（本 spec 非目标），但 A 必须提供 `risk_level` 字段供 B 用 |
| R4 新增 stage 与现有 driver 分叉/STATE 单写者冲突 | 家族不自洽 | backlog 与单特性 STATE 解耦：backlog 是项目级长寿 artifact（多叶），STATE 仍是单叶运行时；driver 分叉新增 "有 backlog 未起特性 → 可路由 backlog 选叶" |

## 5. 设计

### 5.1 架构定位（新阶段在生命周期中的位置）

```
[老系统] ──Seed──▶ .sdlc/requirements/ (递归需求树, 项目本地长寿)
散点需求 ──Ingest──▶        │
                            │ Ready-queue (派生: 解依赖叶 + 优先级 + risk_level)
                            ▼
              [子系统 B: sdlc-loop]  ← 本 spec 非目标, 仅定契约
                            │ dequeue 一片叶
                            ▼
        sdlc-spec → plan → build → validate → review → ship  (现有 pipeline, 单叶)
                            │ 回写叶 status
                            ▼
                  Coverage burndown (按 domain 观测迁移进度)
```

- `sdlc-backlog` = 新 pre-spec 阶段，管**需求集合**；现有 pipeline 不变，管**单叶**。
- backlog artifact 是**项目级、长寿、多叶**（区别于 STATE 的单特性、短寿、单叶）。

### 5.2 树存储（文件系统镜像，复用 kb-manage）

```
<target-repo>/.sdlc/requirements/
├── _index.md                 # 派生: 覆盖度 burndown + ready-queue 快照 (Coverage/Ready-queue 产出, 可重生成)
├── <domain>/
│   ├── _domain.md            # domain 级元信息 (老系统模块映射, new_domain 对应)
│   └── <subdomain>/
│       ├── _subdomain.md
│       └── <leaf-id>.md       # 一条具体需求 (叶)
```

- 递归：subdomain 下可再嵌 subdomain（`domain→subdomain→...→leaf`），与 kb-manage 同构。
- 每叶独立文件 → 单写者友好、git-diffable、并行 Ingest 不互锁。
- `_index.md` 是**派生产物**（由 Coverage/Ready-queue 操作生成），可随时从叶重建，不是事实源；事实源 = 各叶文件 frontmatter。

### 5.3 叶 schema（`<leaf-id>.md` frontmatter）

```markdown
---
id: <domain>.<subdomain>.<slug>      # 全局唯一, 与路径一致
title: <一句话需求>
domain_path: <domain>/<subdomain>    # 主分类 (唯一)
cross_link: []                       # 次分类: 跨 subdomain 时挂多父 (解 R2)
old_system_ref: <老系统模块/页面/接口/故事编号>   # 双视图之一 (解 R1)
new_domain_path: <新系统归属, 可与 domain_path 不同>  # 双视图之二
status: captured | spec'd | planned | built | validated | shipped
priority: P0 | P1 | P2 | P3
depends_on: []                       # 其它 leaf id, 构成依赖 DAG
risk_level: low | medium | high      # 供 B 的成本/gate 分诊
updated: <date>
---

## 需求描述
（散点需求原文 + 澄清后的意图）

## 验收线索
（怎么算这片叶 done 的初步线索, 正式验收在 sdlc-spec 阶段细化）

## 老系统行为参照
（old_system_ref 指向的实际行为, 供 rewrite 对齐）
```

### 5.4 五操作（蒸馏 kb-manage 5 op，可移植）

| 操作 | 输入 | 行为 | 输出 |
|---|---|---|---|
| **Seed** | 老系统结构（人/agent 协助描述或扫描） | 生成 `domain/subdomain` 骨架 + `_domain.md`/`_subdomain.md`；**不自动造叶**，建空骨架待 Ingest 填 | 树骨架 + 空 subdomain = 待覆盖清单 |
| **Ingest** | 一条散点需求（用户原话 / session 线索） | 归类到 `domain→subdomain`（命中则挂叶，未命中提示新建 subdomain 或 cross_link）；写叶文件 + frontmatter | 新增/更新叶；二义时 text_mode 让用户选主分类 |
| **Coverage** | 整树 + 可选老系统清单 | 按 domain 统计各 status 计数 → 迁移 burndown；空 subdomain / 未起叶高亮 | 重生成 `_index.md` 的覆盖段 |
| **Ready-queue** | 整树 | 解依赖 DAG（`depends_on` 全 shipped 的叶为 ready）→ 按 priority 排序 → 带 `risk_level` | `ready-queue`（叶列表，A/B 契约）写入 `_index.md` ready 段 |
| **Lint** | 整树 | 孤儿（无人引用叶）/ 断依赖（depends_on 指向不存在 id）/ 误分类 / 重复（同 old_system_ref 多叶）/ 过期（status 与下游 STATE 不一致） | 问题清单（text_mode），不自动裁决 |

### 5.5 接口契约（A 产出 / B 消费）—— 本 spec 的对外稳定面

```
Ready-queue（B 通过读 _index.md ready 段 或 重跑 Ready-queue 操作获得）:
[
  { leaf_id, title, priority, deps_resolved: true, old_system_ref, risk_level, status: "captured" },
  ...
]  # 已按 priority 降序; 仅含依赖已解除的叶
```

- B 只依赖这个结构，不依赖树的内部存储细节 → A/B 解耦，可独立演进。
- B 跑完一叶后**回写该叶 status**（captured→…→shipped）；回写是 B 的职责，A 提供叶文件作为回写目标。

### 5.6 与家族契约的 4 处同步（build 落地、review 把关）

新增 stage `backlog` 需同步：
1. `references/role-routing.md`（§2 触发 + §3/§4 字典 + §5 自检）：backlog 阶段加载 skill-maintainer 透镜（编辑技能体系自身时），数据操作本身不路由目标项目角色。
2. `STATE.md` 模板：stage 枚举加 `backlog`；说明 backlog 是项目级 artifact，与单特性 STATE 解耦。
3. `sdlc-onboard` Phase C 字典：onboard 可顺带探测是否已有 `.sdlc/requirements/`。
4. driver `SKILL.md`：stage 枚举（§4 路由表）+ 分叉逻辑（§2：有 backlog 且无进行中特性 → 可路由 sdlc-backlog 选叶起特性）。

### 5.7 driver 分叉新增（不破坏现有）

现有分叉（无 PROFILE+非空→onboard / 无 PROFILE+空→spec / 有 PROFILE→续 STATE）保持。新增正交分支：
- 有 `.sdlc/requirements/`（backlog 存在）且无进行中 STATE → text_mode 提示："backlog 有 N 片 ready 叶，1) 从 ready-queue 选下一片起特性 2) 直接 /sdlc spec 注入新需求 3) Ingest 一条散点需求"。
- backlog 的存在与否不影响既有 onboard/spec 路径——纯增量。

## 6. 怎么算 done（前置验收）

- [ ] 新建 `skills/sdlc-backlog/SKILL.md`，含 Seed/Ingest/Coverage/Ready-queue/Lint 五操作的可执行 playbook（约束+原则，非命令手册；可移植：text_mode + Task-or-sequential 降级）。
- [ ] 叶 schema（§5.3）+ 树结构（§5.2）+ ready-queue 契约（§5.5）在 SKILL 内有明确定义。
- [ ] 4 处契约同步（§5.6）全部落地；`bash scripts/validate-skills` 通过（无断链/孤儿/frontmatter 错误/交叉引用缺失）。
- [ ] driver 分叉新增（§5.7）不破坏现有三条路径（回归：onboard/spec/续 STATE 行为不变）。
- [ ] `.agents/skills/sdlc-backlog` 符号链接补齐（Codex 发现入口，soul.md §0.2.1）。
- [ ] 版本升 minor（加能力）+ 一条 CHANGELOG（plugin.json + marketplace.json）。
- [ ] 端到端 smoke：在一个示例项目 `.sdlc/requirements/` 上跑 Seed→Ingest→Ready-queue→Coverage→Lint 全过，产出合法 ready-queue。

**验证命令**：`bash scripts/validate-skills`（correctness）；smoke 用临时 `/tmp` 示例树手验五操作。

## 7. Eval 契约

N/A —— 本特性不触及 AI/模型/策略面。

## 7b. 设计契约

N/A —— 本特性不触及 UI/前端面。

## 8. Deferred Ideas（结构化延后）

- **子系统 B：sdlc-loop 调度器**。Why：是"自运转闭环"的另一半（文章点 #1 调度/唤醒），用户明确"都要"。Trigger：A 落地 + 验证 backlog 可用后，单独走 spec→plan→build。Breadcrumbs：本 spec §5.5 ready-queue 契约、§2 非目标、对抗 R3、`tb-loop-driver` 编排模式。
- **成本分诊门**（原 evolve 初衷）。Why：哪些 ready 叶值得整条 loop vs inline（文章 cost/boundary）。Trigger：随 B 一起落（B2 的 gate 组件）。Breadcrumbs：叶 `risk_level` 字段已为它预留。
- **Seed 全自动逆向**（从老系统代码 AI 抽取需求）。Why：减少人工 Seed 成本。Trigger：A 手动 Seed 跑顺、有稳定老系统代码源后。Breadcrumbs：§2 非目标、Seed 操作 §5.4。

## 9. Canonical refs（强制累积）

- 文章：《提示词工程已死，Loop Engineering 来了！》Addy Osmani / Datawhale（已抓取 /tmp/wx-article/20260615_113455/article.json）
- `~/.claude/skills/sdlc/references/evolve-loop.md`、`roles/skill-maintainer.md`（本特性透镜）
- `.claude/skills/kb-manage/`（递归 domain-subdomain + 5 操作复用源）
- `.claude/skills/tb-loop-driver/`（B 的编排模式参照）
- sdlc-pilot：`skills/sdlc/SKILL.md`（driver 分叉/stage 枚举）、`references/role-routing.md`、`references/templates/STATE.md`、`scripts/validate-skills`、`scripts/sdlc-guard`、`.claude-plugin/plugin.json`
