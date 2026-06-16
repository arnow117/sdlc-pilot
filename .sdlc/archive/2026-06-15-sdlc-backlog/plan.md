# Plan: sdlc-backlog —— 需求树 / backlog（子系统 A）

> 来源 spec: .sdlc/spec.md（已批准）
> 复杂度等级: **L3** —— 理由: 触及家族契约（stage 枚举 + driver 分叉），跨文件硬依赖（枚举须在 STATE 模板/driver 同步），且需独立 skill-maintainer 评审 + 回归既有 3 条 driver 分叉路径不被破坏。非大团队但"改错很贵"（改坏工具影响以后每次运行）。
> 生成: 2026-06-15
> 预解析（非权威）: active roles = [skill-maintainer]（R10：改 skills/**）；validate-modes = [correctness]（= `bash scripts/validate-skills`）；无架构漂移（被改仓即 sdlc-pilot 自身）。

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | skill 骨架 + 数据模型 + 交互操作(Seed/Ingest) | §5.2/§5.3/§5.5, §5.4(Seed/Ingest), R1/R2/R3 schema | — | 1 |
| P2 | 派生操作 helper script(Ready-queue/Coverage/Lint) | §5.4(Coverage/Ready-queue/Lint), §5.5 emit, R2(lint dup) | P1 | 2 |
| P3 | 家族契约同步 + driver 分叉 | §5.1, §5.6, §5.7, R4 | P1 | 2 |
| P4 | 集成 smoke + Codex 链接 + 版本/CHANGELOG | §6 done(smoke/symlink/version) | P2,P3 | 3 |

波次：wave1=P1 → wave2=P2‖P3（无文件重叠，可并行）→ wave3=P4。

> **规划期契约细化（写进 Decisions，非 MISSING）**：
> 1. `backlog` 作为**项目级 stage**加入枚举，与 `onboard` 同类（onboard 已在枚举内且是项目级、产 PROFILE；backlog 产 `.sdlc/requirements/`）。一片叶被选中后另起单特性 STATE 从 `spec` 开始 → 解 spec §R4 解耦。
> 2. spec §5.6 item1「role-routing 同步」**基本已被 R10 覆盖**（`skills/**`·`**/SKILL.md` 任意编辑 → skill-maintainer 透镜）。本 plan 只在 role-routing §5 自检清单加一条 breadcrumb，无功能性改动。

---

## Phase P1: sdlc-backlog skill 骨架 + 数据模型 + 交互操作

**目标**: 存在一个可被发现的 `sdlc-backlog` skill，定义清树结构/叶 schema/ready-queue 契约，并能以 Claude 驱动方式 Seed 出骨架、Ingest 一条散点需求成合法叶文件。
**覆盖需求(traceability)**: §5.2(树存储), §5.3(叶 schema), §5.5(契约定义), §5.4(Seed/Ingest), 对抗 R1(双视图)/R2(cross_link)/R3(risk_level) 落在 schema。
**depends_on**: []   **wave**: 1
**为什么这样拆**: 数据模型 + 树结构是一切的地基（P2 脚本、P3 契约、B 都依赖它）；先把"事实源 = 叶文件 frontmatter"立住。Seed/Ingest 是 Claude 交互式操作（非纯机械），与 P2 的机械派生分开。

**must_haves（目标倒推）**:
- truths(可观察): 跟 SKILL Seed 指令在空目录能生成 `<domain>/<subdomain>/` 骨架；跟 Ingest 指令能把一句需求落成一个带全字段 frontmatter 的叶文件；二义需求触发 text_mode 选主分类。
- artifacts: `skills/sdlc-backlog/SKILL.md`。
- key_links: SKILL frontmatter 的 description/triggers 让 skill 可被发现；数据模型节被 P2 脚本与 P3 driver 引用。

**可观察成功标准**: SKILL.md frontmatter 合法（name/description）；在 `/tmp/bk-sample/.sdlc/requirements/` 手跑 Seed+Ingest 产出合法骨架 + 1 个全字段叶。（注：`scripts/validate-skills` 全绿留到 P3 wired 后，此阶段 skill 暂为待接线状态。）

### Task P1-T1: 建 SKILL.md 骨架 + 数据模型节
- **requirements**: §5.2, §5.3, §5.5
- **files**: `skills/sdlc-backlog/SKILL.md`（新建）
- **read_first**: `.sdlc/spec.md`（§5.2/§5.3/§5.5/§5.6/§5.7 全节）；`skills/sdlc-spec/SKILL.md`（参照家族 SKILL.md 的 §0 可移植前置写法与 frontmatter 风格）；`.claude/skills/kb-manage/SKILL.md`（参照递归 domain-subdomain + 5 操作组织方式）
- **action**: 新建 `skills/sdlc-backlog/SKILL.md`。frontmatter 用家族风格（`name: sdlc-backlog`；`description:` 内嵌触发语「需求树/backlog/散点需求归档/Ingest 需求/迁移覆盖/老系统重写需求/选下一条需求做」+ 一句"本 skill 管 spec 之前的需求集合，不收敛单条需求(那是 sdlc-spec)、不调度 loop(那是子系统 B/未来)"）。正文先写：①§0 可移植前置（text_mode 默认 + Task-or-sequential 降级，照 sdlc-spec §0 范式）；②`## 数据模型` 节，原样落 spec §5.2 树布局、§5.3 叶 frontmatter schema（10 字段：id/title/domain_path/cross_link/old_system_ref/new_domain_path/status[captured|spec'd|planned|built|validated|shipped]/priority[P0-P3]/depends_on/risk_level[low|medium|high]/updated）、§5.5 ready-queue 契约结构；③`_index.md 是派生产物、事实源=叶 frontmatter` 的声明。五操作节先留标题占位由 P1-T2/P2 填（标题占位不违反 No-Placeholder：占位的是后续任务的产物，非本任务 action）。**不要**新增 `version:` frontmatter（家族版本由 plugin.json 统一管）。
- **acceptance_criteria**: 文件存在；`head -20 skills/sdlc-backlog/SKILL.md` 显示合法 YAML frontmatter（name + description）；`## 数据模型` 节含全部 10 个叶字段与 ready-queue 契约；`grep -c "TBD\|TODO\|待定" skills/sdlc-backlog/SKILL.md` = 0。

### Task P1-T2: 写 Seed + Ingest 操作 playbook
- **requirements**: §5.4(Seed/Ingest), R1, R2
- **files**: `skills/sdlc-backlog/SKILL.md`（追加 `## 操作: Seed` / `## 操作: Ingest` 两节）
- **read_first**: `skills/sdlc-backlog/SKILL.md`（P1-T1 写的数据模型节）；`.claude/skills/kb-manage/SKILL.md`（Ingest 归类范式）
- **action**: 在 SKILL.md 写两节可执行 playbook（约束+原则，非命令清单）：
  - **Seed**: 输入=老系统结构（用户/agent 描述）。行为=在 `<root>/<domain>/<subdomain>/` 建目录 + `_domain.md`/`_subdomain.md`（记 old-system 模块映射 + `new_domain` 对应，落 R1 双视图骨架）。**不自动造叶**——空 subdomain 即"待覆盖清单"。text_mode 把骨架草案给用户确认。
  - **Ingest**: 输入=一条散点需求原文。行为=按 `domain→subdomain` 归类；命中→在该 subdomain 建 `<leaf-id>.md`（id 与路径一致），填全 10 字段 frontmatter（status 默认 `captured`，priority/risk_level 询问或默认 P2/medium，depends_on 留空待补）；未命中→text_mode 提示"新建 subdomain / 挂 cross_link"；跨多 subdomain（R2 二义）→text_mode 让用户选**主分类**（写 domain_path）+ 其余写 `cross_link[]`。需求正文写进叶的 `## 需求描述`，老系统行为写进 `## 老系统行为参照`。
- **acceptance_criteria**: 手测——`mkdir -p /tmp/bk-sample/.sdlc/requirements`，跟 Seed 指令对一个示例域（如 `order/checkout`）建出 `order/checkout/_subdomain.md`+`order/_domain.md`；跟 Ingest 指令把"下单页要支持优惠券"落成 `/tmp/bk-sample/.sdlc/requirements/order/checkout/order.checkout.coupon.md`，`grep -E "^(id|title|domain_path|old_system_ref|new_domain_path|status|priority|depends_on|risk_level|cross_link|updated):" <该文件>` 命中全部 10 字段。

---

## Phase P2: 派生操作 helper script（Ready-queue / Coverage / Lint）

**目标**: 一个 stdlib-only 的 `scripts/backlog.py`，从 `.sdlc/requirements/**/*.md` 的 frontmatter 机械派生出 ready-queue（A/B 契约）、coverage burndown、lint 报告。
**覆盖需求(traceability)**: §5.4(Coverage/Ready-queue/Lint), §5.5(契约 emit), R2(lint 查重)。
**depends_on**: [P1]   **wave**: 2
**为什么这样拆**: Ready-queue（解依赖 DAG + 排序）、Coverage（按 domain 计数）、Lint（断依赖/重复/孤儿/缺字段）是**机械、确定性、易错于 ad-hoc grep** 的逻辑 → 收进一个稳定 helper 脚本（同 `scripts/sdlc-guard`/`validate-skills` 范式，skill-maintainer 铁律#4 的"稳定契约命令"豁免）。这是本特性唯一的真代码 → 走 TDD。

**must_haves**:
- truths: `python3 scripts/backlog.py readyqueue --root <r>` 输出仅含依赖已解除的叶、按 priority 降序的 JSON；`coverage` 输出按 domain 的 status 计数；`lint` 能报断依赖/重复 old_system_ref/缺字段。
- artifacts: `scripts/backlog.py`、`scripts/test_backlog.py`。
- key_links: SKILL.md 的 Coverage/Ready-queue/Lint 操作节调用本脚本；输出结构即 spec §5.5 契约，被子系统 B 消费。

**可观察成功标准**: `python3 scripts/test_backlog.py` 全 PASS；脚本仅用标准库（`grep -E "import (yaml|requests|tenacity)" scripts/backlog.py` 无命中）。

### Task P2-T1: TDD `backlog.py readyqueue`
- **requirements**: §5.4(Ready-queue), §5.5
- **files**: `scripts/backlog.py`（新建）、`scripts/test_backlog.py`（新建）
- **read_first**: `skills/sdlc-backlog/SKILL.md#数据模型`（叶 schema + ready-queue 契约）；`scripts/sdlc-guard`（参照家族脚本风格/退出码约定）
- **action**: TDD。先实现一个 ~25 行 stdlib frontmatter 解析器（只认 `key: scalar` 与内联 list `key: [a, b]`，足够本 schema；不引 pyyaml 以免破坏可移植）。`readyqueue` 规则：遍历所有叶，叶 ready ⟺ `depends_on` 为空 **或** 其中每个 id 对应叶的 `status == shipped`；输出 JSON 数组，元素 = `{leaf_id,title,priority,deps_resolved:true,old_system_ref,risk_level,status}`，按 priority 升序键（P0<P1<P2<P3）排序。CLI：`python3 scripts/backlog.py readyqueue --root <dir>`。
  - [ ] Step 1: 写失败测试 `scripts/test_backlog.py`（stdlib `unittest` + `tempfile`）：建临时树两叶——`a`（depends_on 空, priority P1）、`b`（depends_on=[a], a.status=captured 即未 shipped, priority P0）；断言 `readyqueue` 只返回 `a`（b 被依赖阻塞）。再加 `a.status=shipped` 后断言返回含 `b` 且排在前（P0）。
  - [ ] Step 2: 跑 `python3 scripts/test_backlog.py -q` → 期望 FAIL（ModuleNotFound/AttributeError，脚本未实现）。
  - [ ] Step 3: 写 `scripts/backlog.py`（frontmatter 解析器 + walk + readyqueue + argparse 子命令骨架）至测试通过。
  - [ ] Step 4: 跑 `python3 scripts/test_backlog.py -q` → 期望 PASS（OK）。
  - [ ] Step 5: `git add scripts/backlog.py scripts/test_backlog.py && git commit -m "feat(sdlc-backlog): backlog.py readyqueue + tests"`
- **acceptance_criteria**: `python3 scripts/test_backlog.py -q` 报告 readyqueue 用例 PASS；`python3 scripts/backlog.py readyqueue --root /tmp/bk-sample/.sdlc/requirements` 输出合法 JSON 数组。

### Task P2-T2: TDD `backlog.py coverage` + `lint`
- **requirements**: §5.4(Coverage/Lint), R2
- **files**: `scripts/backlog.py`（追加子命令）、`scripts/test_backlog.py`（追加用例）
- **read_first**: `scripts/backlog.py`（P2-T1 的 walk/解析器复用）
- **action**: 加两个子命令。`coverage`：按顶层 domain 分组，统计各 status 计数 + 空 subdomain（无叶）列表；输出 JSON/文本表。`lint`：报 ①断依赖（depends_on 指向不存在的 id）②重复（同 `old_system_ref` 出现在 ≥2 叶）③缺字段（10 必填 frontmatter 缺任一）④孤儿（叶路径不在 `<domain>/<subdomain>/` 形态下）；非 0 退出码当有问题，文本列清单，**不自动修**。
  - [ ] Step 1: 测试加用例——树注入一个 `depends_on=[nonexist]` 叶 + 两叶共享同一 `old_system_ref`；断言 `lint` 同时报"断依赖"与"重复 old_system_ref"且退出码非 0；`coverage` 对 3 叶（status 各异）返回正确分组计数。
  - [ ] Step 2: 跑 `python3 scripts/test_backlog.py -q` → 期望新用例 FAIL。
  - [ ] Step 3: 实现 coverage + lint 至通过。
  - [ ] Step 4: 跑 `python3 scripts/test_backlog.py -q` → 期望全 PASS。
  - [ ] Step 5: `git commit -am "feat(sdlc-backlog): backlog.py coverage + lint"`
- **acceptance_criteria**: `python3 scripts/test_backlog.py -q` 全 PASS（含 coverage/lint 用例）；`python3 scripts/backlog.py lint --root <注入坏数据的临时树>` 退出码非 0 且列出两类问题。

### Task P2-T3: SKILL.md 接线三派生操作
- **requirements**: §5.4(Coverage/Ready-queue/Lint), §5.5
- **files**: `skills/sdlc-backlog/SKILL.md`（追加 `## 操作: Ready-queue` / `## 操作: Coverage` / `## 操作: Lint` 三节）
- **read_first**: `skills/sdlc-backlog/SKILL.md`（已写各节）；`scripts/backlog.py`（确认 CLI 签名）
- **action**: 三节各写：用途 + 调用 `python3 scripts/backlog.py {readyqueue|coverage|lint} --root <target-repo>/.sdlc/requirements`，说明输出去向（readyqueue/coverage 结果可重生成写入 `_index.md` 对应段；lint 结果 text_mode 上报不自动裁决）。声明"事实源=叶 frontmatter，脚本只读派生"。
- **acceptance_criteria**: 三节存在且各含正确 CLI 调用串；`grep -c "backlog.py" skills/sdlc-backlog/SKILL.md` ≥ 3。

---

## Phase P3: 家族契约同步 + driver 分叉

**目标**: `backlog` 作为项目级 stage 接入家族；driver 能在"有 backlog 无进行中特性"时引导选叶；`bash scripts/validate-skills` 全绿；既有 3 条 driver 分叉路径行为不变。
**覆盖需求(traceability)**: §5.1(新阶段定位), §5.6(契约同步), §5.7(driver 分叉), R4(解耦)。
**depends_on**: [P1]   **wave**: 2
**为什么这样拆**: 契约改动（枚举/分叉）集中一处做、一处验（validate-skills），与 P2 的脚本工作无文件重叠可并行；独立成阶段便于 review 聚焦把关枚举 4 处一致性。

**must_haves**:
- truths: STATE 模板枚举含 `backlog`；driver §4 路由表有 `backlog→sdlc-backlog` 行；driver §2 分叉新增"有 .sdlc/requirements/ 且无进行中 STATE"分支（3 选项 text_mode）；onboard 能探测并报告已有 backlog；`validate-skills` 绿。
- artifacts: 改动 `skills/sdlc/references/templates/STATE.md`、`skills/sdlc/SKILL.md`、`skills/sdlc-onboard/SKILL.md`、`skills/sdlc/references/role-routing.md`。
- key_links: driver 路由表 → 指向 `sdlc-backlog` skill（消除 P1 的"待接线/孤儿"态）。

**可观察成功标准**: `bash scripts/validate-skills` 退出码 0；新 skill 不再是孤儿（被 driver §4 引用）；既有 onboard/spec/续-STATE 三分叉描述未被删改（纯增量）。

### Task P3-T1: STATE 模板枚举 + 项目级说明
- **requirements**: §5.6(item2), R4
- **files**: `skills/sdlc/references/templates/STATE.md`
- **read_first**: `skills/sdlc/references/templates/STATE.md:24`（stage 枚举行）+ 24-50（work-type 说明区）
- **action**: 第 24 行枚举改为 `stage: onboard | backlog | spec | plan | build | validate | review | ship | done`（`backlog` 紧随 `onboard`）。在说明区追加一条："`backlog` 与 `onboard` 同为**项目级 stage**（产 `.sdlc/requirements/` 需求树，不属单特性生命周期）；从 backlog 选中一片叶后另起单特性 STATE，stage 从 `spec` 起 → backlog 与单特性 STATE 解耦（互不覆盖）。"
- **acceptance_criteria**: `grep -n "backlog" skills/sdlc/references/templates/STATE.md` 命中枚举行 + 说明行；枚举仍是合法单行。

### Task P3-T2: driver §4 路由表 + §2 分叉新增（回归既有路径）
- **requirements**: §5.7, §5.1, §5.6(item4)
- **files**: `skills/sdlc/SKILL.md`
- **read_first**: `skills/sdlc/SKILL.md` §2（分叉决策）+ §4（stage 路由表）——通读确认既有 3 分叉（无PROFILE+非空→onboard / 无PROFILE+空→spec / 有PROFILE→续STATE）原文，确保只新增不改写
- **action**: ①§4 路由表加一行 `| backlog | sdlc-backlog | 传 target-repo；产/更新 .sdlc/requirements/ 需求树 |`。②§2 在现有分叉之后加**正交分支**（不动现有三条）："若 `<target-repo>/.sdlc/requirements/` 存在（backlog 已建）且无进行中 STATE → text_mode：1) 从 ready-queue 选下一片 ready 叶起特性（→ sdlc-backlog 取叶 → sdlc-spec） 2) 直接 /sdlc spec 注入新需求 3) Ingest 一条散点需求（→ sdlc-backlog）"。明确：backlog 存在与否**不影响**既有 onboard/spec/续-STATE 路径。
- **acceptance_criteria**: `grep -n "sdlc-backlog\|requirements/" skills/sdlc/SKILL.md` 命中路由表行 + 分叉分支；`git diff skills/sdlc/SKILL.md` 显示既有三分叉文本无删改（纯 addition——diff 只见 `+` 行，相关上下文 `-` 行为 0）。

### Task P3-T3: onboard 探测 + role-routing breadcrumb
- **requirements**: §5.6(item1, item3)
- **files**: `skills/sdlc-onboard/SKILL.md`、`skills/sdlc/references/role-routing.md`
- **read_first**: `skills/sdlc-onboard/SKILL.md:120-160`（Phase C/D）；`skills/sdlc/references/role-routing.md:121-135`（§5 自检清单）
- **action**: ①onboard：在 Phase A 采证或 Phase D 聚合处加一句"探测 `<target-repo>/.sdlc/requirements/`，存在则在 PROFILE 记 backlog 叶数（`python3 <sdlc-pilot>/scripts/backlog.py coverage` 摘要），作为已有需求树线索"。②role-routing §5 清单加一条 breadcrumb：`- [x] 改 sdlc-backlog skill 自身 → + skill-maintainer — 已由 R10(skills/**) 覆盖，无需单列规则`。**不**改 R10 本身（它已含 `skills/**`·`**/SKILL.md`）。
- **acceptance_criteria**: `grep -n "requirements/\|backlog" skills/sdlc-onboard/SKILL.md` 命中；role-routing §5 含 backlog breadcrumb 行；R10 规则文本未改（`git diff` R10 行无变更）。

### Task P3-T4: validate-skills 绿
- **requirements**: §6(done: 4 处同步 + validate 通过)
- **files**: —（验证任务，不改文件）
- **read_first**: `scripts/validate-skills`（确认它检查的项：断链/孤儿/frontmatter/交叉引用）
- **action**: 跑 `bash scripts/validate-skills`。若报 sdlc-backlog 相关孤儿/断链/frontmatter → 回 P1-T1 或 P3-T2 修（多半是 driver 路由表未正确引用 skill 名，或 SKILL frontmatter 字段缺失）。
- **acceptance_criteria**: `bash scripts/validate-skills; echo $?` → 末行 `0`，无 sdlc-backlog 相关告警。

---

## Phase P4: 集成 smoke + Codex 链接 + 版本/CHANGELOG

**目标**: 全链路五操作在示例树上跑通；Codex 发现入口补齐；版本升 0.9.0 + CHANGELOG（commit/push 由 sdlc-ship 阶段执行）。
**覆盖需求(traceability)**: §6(done: smoke / .agents symlink / version+CHANGELOG)。
**depends_on**: [P2, P3]   **wave**: 3
**为什么这样拆**: 集成验证需 P1(交互操作)+P2(脚本)+P3(接线)全到位；版本/链接是收尾，放最后避免中途反复改版本号。

**must_haves**:
- truths: 在示例树上 Seed→Ingest→readyqueue→coverage→lint 全链通过且产物合法；`.agents/skills/sdlc-backlog` 链接可解析（若该仓用 .agents 入口）；plugin.json/marketplace.json = 0.9.0；CHANGELOG 有一条。
- artifacts: `/tmp` 示例树（临时，不入仓）；`.agents/skills/sdlc-backlog`（条件）；改 `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、`CHANGELOG.md`。
- key_links: 版本号在 plugin.json 与 marketplace.json 一致。

**可观察成功标准**: 全链 smoke 无错；`grep '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json` 均显示 `0.9.0`；`bash scripts/validate-skills` 仍绿。

### Task P4-T1: 端到端 smoke（全链五操作）
- **requirements**: §6(done: smoke)
- **files**: —（用 `/tmp` 临时树，不入仓）
- **read_first**: `skills/sdlc-backlog/SKILL.md`（五操作全节）
- **action**: 在 `/tmp/bk-e2e/.sdlc/requirements/` 跟 SKILL 指令：Seed 2 个 domain（如 `order`,`user`）各 1 subdomain；Ingest 3 条散点需求（其一含 `depends_on` 指向另一条、其一 `cross_link` 跨 subdomain）；跑 `python3 scripts/backlog.py readyqueue/coverage/lint --root /tmp/bk-e2e/.sdlc/requirements`。
- **acceptance_criteria**: readyqueue 输出合法 JSON 且正确排除被依赖阻塞的叶；coverage 计数 = 3 叶分组正确；lint 退出码 0（无坏数据）；全程无脚本异常。

### Task P4-T2: Codex 发现入口
- **requirements**: §6(done: .agents symlink), soul.md §0.2.1
- **files**: `.agents/skills/sdlc-backlog`（条件创建）
- **read_first**: 仓根 `ls -la .agents/skills 2>/dev/null`（确认该仓是否用 .agents 入口约定）
- **action**: 若 `.agents/skills/` 存在 → `ln -s ../../skills/sdlc-backlog .agents/skills/sdlc-backlog`（相对链接，随仓维护）。若该仓不用 .agents 入口 → 跳过并在 STATE 记"N/A：该仓无 .agents/skills 约定"。
- **acceptance_criteria**: 若创建：`readlink .agents/skills/sdlc-backlog` 指向 `../../skills/sdlc-backlog` 且 `test -e .agents/skills/sdlc-backlog` 成立；若跳过：STATE 记明原因。

### Task P4-T3: 版本 0.9.0 + CHANGELOG
- **requirements**: §6(done: version+CHANGELOG)；skill-maintainer 铁律#6（加能力=minor）
- **files**: `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、`CHANGELOG.md`
- **read_first**: `.claude-plugin/plugin.json`（version 行）、`.claude-plugin/marketplace.json`（version 行）、`CHANGELOG.md`（既有条目格式）
- **action**: 两处 `version` `0.8.1`→`0.9.0`（minor：新增 sdlc-backlog 能力）。CHANGELOG 加一条 `## 0.9.0` 摘要："feat(sdlc-backlog): 需求树/backlog 子系统 A——递归 domain-subdomain 树 + 5 操作(Seed/Ingest/Coverage/Ready-queue/Lint) + ready-queue 契约(A/B 解耦) + backlog 项目级 stage 接入家族"。**注：实际 commit/push 由 sdlc-ship 阶段执行**，本任务只改文件。
- **acceptance_criteria**: 两文件 version 均 `0.9.0`（`grep '"version"' 两文件` 一致）；CHANGELOG 有 `0.9.0` 条目；`bash scripts/validate-skills` 退出码 0。

---

## Source Audit（出口门控 §6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|---|---|---|---|---|
| GOAL | — | 需求树+backlog；机制通用/数据本地 | P1-P4 | COVERED |
| REQ | §5.2 | 文件系统递归树存储 | P1-T1 | COVERED |
| REQ | §5.3 | 叶 schema 10 字段 | P1-T1 | COVERED |
| REQ | §5.4-Seed | Seed 老系统→骨架 | P1-T2 | COVERED |
| REQ | §5.4-Ingest | Ingest 散点归类 | P1-T2 | COVERED |
| REQ | §5.4-Ready | Ready-queue 派生 | P2-T1, P2-T3 | COVERED |
| REQ | §5.4-Coverage | Coverage burndown | P2-T2, P2-T3 | COVERED |
| REQ | §5.4-Lint | Lint 5 类问题 | P2-T2, P2-T3 | COVERED |
| REQ | §5.5 | ready-queue 契约(A/B) | P1-T1(定义), P2-T1(emit) | COVERED |
| REQ | §5.1 | backlog 作 pre-spec/项目级 stage | P3-T1, P3-T2 | COVERED |
| REQ | §5.6 | 4 处契约同步 | P3-T1/T2/T3, P3-T4(验) | COVERED |
| REQ | §5.7 | driver 分叉新增 | P3-T2 | COVERED |
| DECISION | D-机制形态 | 新 skill sdlc-backlog | P1-T1 | COVERED |
| DECISION | D-落点 | 混合(机制进 pilot/数据留项目) | P1/P4(机制), 数据=运行时 | COVERED |
| RISK | R1 | 双视图 old/new | P1-T1(schema), P1-T2(Seed) | COVERED |
| RISK | R2 | cross_link 多父 + 查重 | P1-T1/T2, P2-T2(lint dup) | COVERED |
| RISK | R3 | risk_level 留给 B | P1-T1(schema 字段) | COVERED |
| RISK | R4 | backlog/STATE 解耦 | P3-T1(说明) | COVERED |
| DONE | §6 | smoke/symlink/version | P4-T1/T2/T3 | COVERED |

**Coverage Gate（反向）**：所有 P1-T1..P4-T3 的 `requirements` 字段均非空，指回上表某 ID。无悬空任务。
**MISSING**：无。Deferred（子系统 B / 成本分诊门 / Seed 全自动逆向）已在 spec §8 显式延后，不计 gap。

## 风险 / 关键决策点（L3 → 进 build 前确认）

1. **frontmatter 解析器手写 vs pyyaml**：选手写 stdlib 子集（可移植，不污染依赖）。若叶 schema 将来变复杂可重审。
2. **driver SKILL.md 是契约文件**：P3-T2 改它必须纯 additive（diff 不删既有三分叉文本）——review 阶段 skill-maintainer 重点核验。
3. **P1 阶段 validate-skills 暂不绿**（skill 待接线）：可接受，全绿门移到 P3-T4；build 推进时知悉此序。
