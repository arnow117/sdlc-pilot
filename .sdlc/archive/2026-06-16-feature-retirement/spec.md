# Spec: feature 退场 / 工件生命周期（backlog Retire op）

> Date: 2026-06-15
> Status: approved
> Target surface(s): skill-system-self（sdlc-pilot 工具自身）
> Active roles (anticipated): skill-maintainer
> Validate modes (anticipated): correctness（结构 lint + backlog.py 单测 + dogfood）

## 1. 问题 / 目标

一个特性走到 `stage=done` 后，`.sdlc/` 内部 markdown（spec/plan/validate/review/STATE）目前**无人管理**：
- STATE 模板第 6 行只悬空写"归档**或**清空"，没有任何 skill/driver 执行它。
- 下个特性开始 → 新 spec/STATE 直接覆盖旧的；而 `.sdlc/` 在多数项目里被 gitignore（本仓即是）→ **覆盖即永久丢失**。
- 决策理由（STATE.Decisions log）随短命 STATE 一起死，**不回流**到长命项目记忆。
- PROFILE 六节（Tech stack/Surface map/Conventions/Entry points/Known risks/Deploy）**没有承接"已完成特性教训"的载体** → "作为 context 持续指导后续演进"这个闭环根本没接上。

**附带填一个已知缺口**：backlog 叶状态机 `captured→…→shipped`，ready-queue 规则 `ready ⟺ 自身!=shipped 且 deps 全 shipped`；但 backlog SKILL §1.118 把"回写叶 status→shipped"的职责**委托给尚不存在的子系统 B**。结果：**当前没有任何东西标叶子 shipped，ready-queue 永远解锁不了下游叶**。done 正是叶子→shipped 的时刻。

**目标**：定义并实现一个"特性退场仪式"，在 done 时：归档工件 → 回流耐久决策/教训到项目记忆 → 标源叶 shipped 并重算 ready-queue → 清空 STATE，使完成的工作被保留、被蒸馏、并持续指导后续演进。

## 2. 非目标（YAGNI）

- ❌ 不实现子系统 B（sdlc-loop 调度器）——只填它依赖的"叶 shipped 回写"这一个点。
- ❌ 不做逐阶段叶状态回写（spec'd/planned/built/validated 的中间态）——本次只回写**终态 shipped**。中间态回写记入 Deferred。
- ❌ 不把 `.sdlc/archive/` 纳入 git（沿用项目对 `.sdlc/` 的 gitignore 决策；跨团队的耐久 context 靠 PROFILE 回流承载，那是 tracked 文件）。
- ❌ 不新增 stage（done 已在枚举内）、不新增顶层 skill（守 CLAUDE 铁律#1）。

## 3. 现状摘要（Explore 产出）

- **谁写 done**：`sdlc-ship`（全量发布后，SKILL §124）或 `sdlc-review`→verify（不发布的特性）。done 之后无任何动作。
- **backlog 数据模型**：叶 frontmatter 是事实源（`status` 字段，10 必填）；`_index.md` 是派生产物；`scripts/backlog.py` 已有 readyqueue/coverage/lint 子命令（确定性文件操作）。
- **STATE↔叶 的链接**：当前 STATE **不记录**特性源自哪片叶 → Retire 无法回溯标 shipped。需补 `source-leaf:` 字段。
- **测试现状**：无单测的 markdown 靠 `scripts/validate-skills` 结构 lint + dogfood；`test_backlog.py` 已有 5 用例。天然 dogfood 素材 = 手工建立的 `.sdlc/archive/2026-06-15-sdlc-backlog/`。

## 4. 方案与决策

**采纳：退场 = backlog 新增 `Retire`（close-out）操作；driver 加 `done→backlog` 分叉。**（用户确认）

### 备选与否决（对抗性证伪 §2.5）
- **备选 A：退场逻辑住在 driver §5**。否决——违反 driver"导演只路由不干活"的身份；且 done 可由 ship 或 review 两处到达，逻辑会分裂。
- **备选 B：退场逻辑住在到达 done 的 skill（ship + review 各自做）**。否决——两处重复同一套逻辑，漂移风险高，违反单一归宿。
- **选定 C：backlog Retire op**。理由：(1) 填 backlog 自己声明却悬空的"叶 shipped 回写"缺口；(2) backlog = 工作账本，开（选叶→spec）与关（退场→shipped）都归它，闭环自然；(3) driver 保持瘦，只新增一条路由分叉。

### 证伪通过的边界
- **无需求树的特性**（直接 `/sdlc spec` 起、或本工具自身）：Retire 优雅降级——跳过"标 shipped + ready-queue"，归档/回流/清栈照做。
- **不破坏既有分叉**：driver §2 新增 `STATE.stage==done → backlog Retire` 是 additive 条件，先于 onboard/spec/续-STATE 三主分叉判定。
- **范围姿态（§2.4b）**：HOLD —— 严格做"退场闭环"，逐阶段中间态回写、archive 入 git、子系统 B 全部显式 Deferred。

## 5. 设计

### 5.1 触发与路由（driver，additive）
- **driver §2 分叉**：`/sdlc` 入口读到 `STATE.stage == done` → 先路由到 **backlog Retire op** 完成退场，再继续 new-feature 分叉（即把"我们刚才手工做的"自动化）。
- **driver §4 路由表**：新增一行 `done → sdlc-backlog（Retire op）`。
- **driver §5 交接**：注明 done 的退场由 backlog 执行，driver 不自己归档（守"导演不干活"）。
- 可选 escape hatch：`/sdlc retire` 显式触发同一 op（非新 stage，仅 driver 调用姿势）。

### 5.2 backlog Retire op（新增 SKILL 章节 + backlog.py 子命令）
四步，确定性部分进 `scripts/backlog.py retire`，判断性部分（蒸馏哪些算"耐久"）由模型按 SKILL 指引做：

| 步 | 动作 | 实现 | 普适 |
|---|---|---|---|
| ① 归档 | `.sdlc/{spec.md,plan.md,validate/,review/,STATE.md}` → `.sdlc/archive/<date>-<feature>/` | 脚本（文件移动） | 全部 |
| ② 回流 | 从 STATE.Decisions log 蒸馏**耐久**决策/教训/新风险 → 写项目记忆（§5.3） | 模型蒸馏 + 脚本 append | 全部 |
| ③ 标 shipped | 源叶 `status=shipped` + 叶体补 `## 退场记录`（archive 路径 + 关键教训 breadcrumb）→ 重算 ready-queue | 脚本（复用 readyqueue） | 仅树内特性 |
| ④ 清栈 | 重置 `.sdlc/STATE.md`（清空/回模板），交还给下个特性 | 脚本 | 全部 |

- **单写者**：Retire 是该时刻 STATE 的唯一写者（driver 路由进来后 backlog 独占），归档→清栈原子完成。
- **幂等/安全**：archive 目标已存在则报错不覆盖；STATE 缺 `source-leaf` 或无 `requirements/` 树 → 跳过③并 log 说明，不阻断。

### 5.3 回流载体（步②）
- **有 `PROFILE.md`** → 新增 `## Evolution log`（append-only）：每条 `<date> · <feature> · 决策/教训/风险 · → archive/<...>`。
- **无 PROFILE**（如 sdlc-pilot 自身）→ 兜底写 `.sdlc/EVOLUTION.md`（同格式，比埋在 archive 里可见）。
- **树内特性**额外在源叶体写 breadcrumb，使需求树成为"已完成工作的活索引"。

### 5.4 契约改动清单（全 additive）
- `skills/sdlc-backlog/SKILL.md`：新增 Retire op 章节；§1.118 的"回写委托 B"改为"终态 shipped 由 Retire 回写，中间态/调度仍属未来 B"。
- `scripts/backlog.py`：新增 `retire` 子命令（archive + clear STATE + 标 shipped + readyqueue 重算）；`scripts/test_backlog.py` 补用例。
- `skills/sdlc/SKILL.md`：driver §2 分叉 + §4 路由表 + §5 交接（done→backlog）。
- `templates/STATE.md`：第 6 行悬空指令改为明确退场指引；新增 `source-leaf:` 字段（记特性源叶，供③回溯）。
- `templates/PROFILE.md`：新增 `## Evolution log` 段（回流目标）。
- 元数据：版本 minor `0.9.0 → 0.10.0`（加 Retire 能力）；`plugin.json` + `marketplace.json` + `CHANGELOG.md`；README backlog op 列表加 Retire；CLAUDE.md 迭代表必要时加行。
- **不动**：stage 枚举、skill 计数、role-routing 取值字典（skill-maintainer 已覆盖"改技能体系自身"）。

## 6. 怎么算 done（前置验收）

- [ ] `backlog.py retire <feature> [--leaf <id>]`：把当前 `.sdlc/` 工件归档到 `archive/<date>-<feature>/`，重置 STATE；给定 leaf 时该叶 `status=shipped` 且 ready-queue 重算正确；无 leaf/无树时优雅跳过③。
- [ ] 归档目标已存在 → 报错不覆盖（幂等安全）。
- [ ] 回流：有 PROFILE 写入 `## Evolution log`；无 PROFILE 写 `.sdlc/EVOLUTION.md`。
- [ ] `scripts/test_backlog.py` 新用例全绿（含：归档落位、STATE 重置、叶 shipped、ready-queue 解锁下游、无树降级、回流兜底）。
- [ ] `scripts/validate-skills` 结构 lint PASS（引用一致、frontmatter、无悬空）。
- [ ] driver 读到 `stage==done` 能路由到 Retire（dogfood：拿 `archive/2026-06-15-sdlc-backlog/` 之外的一个 fixture 跑通）。
- [ ] 版本升至 0.10.0，CHANGELOG/plugin/marketplace/README 同步。
- 验证命令：`python3 scripts/backlog.py retire ...` / `python3 -m pytest scripts/test_backlog.py` / `bash scripts/validate-skills`。

## 7. Eval 契约
N/A（非 AI/模型/策略工作）。

## 7b. 设计契约
N/A（非 UI/前端工作）。

## 8. Deferred Ideas（结构化延后）

- **逐阶段叶状态回写**（spec'd/planned/built/validated 中间态）。Why：让需求树实时反映在飞特性进度。Trigger：子系统 B（sdlc-loop）立项时。Breadcrumbs：backlog SKILL §1.2 状态机、本 spec §2。
- **archive 纳入 git / 跨机器同步**。Why：团队共享完成工件而非仅本地。Trigger：出现"需回看他人已退场特性原始工件"的真实需求。Breadcrumbs：`.sdlc/` gitignore 决策、§2。
- **子系统 B（sdlc-loop 调度器）**：消费 ready-queue 自动起特性。Why：backlog 产 ready-queue 本就为喂它。Trigger：独立特性。Breadcrumbs：backlog ready-queue 契约 §1.3。
- **backlog 需求树 review 看板（新特性，非本特性）**：把 `.sdlc/requirements/` 树渲染成双表征——(人) 单文件 HTML 看板，暖奶油/鼠尾草绿风格、**按产品功能层级 domain→subdomain→leaf 从粗到细可折叠**（非平铺卡片），带 status/priority/risk 筛选、ready-queue 高亮、shipped/archive breadcrumb；(agent) 缩进的 json/yaml。形态预估 = backlog 新派生 op（如 `backlog.py render` 出 HTML + json/yaml），触及 UI 面 → 需 §2.6b DESIGN.md + e2e:Web + design 角色。Why：需求树目前只有 `_index.md` 文本，缺人类可览的全局视图，且与 Retire 产出的 shipped/lessons 数据天然互补。Trigger：Retire 落地后（数据更全）或用户优先级提前。Breadcrumbs：风格参考 `/Users/mac/Downloads/requirement-dashboard.html`（暖色看板，但本特性要改成层级而非平铺）；backlog 树 schema §1.1-1.3；既有 `references/web-review/playbook.md`（渲染基础设施可复用）。

## 9. Canonical refs

- `skills/sdlc-backlog/SKILL.md`（§1.2 叶 schema、§1.3 ready-queue、§1.118 回写委托）
- `skills/sdlc/references/templates/STATE.md`（第 6 行悬空指令、字段）
- `skills/sdlc/references/templates/PROFILE.md`（六节，缺回流载体）
- `skills/sdlc/SKILL.md`（§2 分叉 / §4 路由 / §5 交接）
- `scripts/backlog.py` + `scripts/test_backlog.py`（既有子命令模式）
- `.sdlc/archive/2026-06-15-sdlc-backlog/`（手工建立的首个归档实例 = Retire 参考实现 + dogfood 素材）
- `CLAUDE.md`（三条铁律：不轻易加顶层 skill / 可移植 text_mode / 纯文件单写者）
