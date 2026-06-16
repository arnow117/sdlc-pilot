# Plan: feature 退场 / 工件生命周期（backlog Retire op）

> 来源 spec: .sdlc/spec.md（已批准，范围切线 L0）
> 复杂度等级: **L3** —— 理由: 触及 driver 分叉契约 + STATE/PROFILE 模板契约 + backlog skill + backlog.py（首个写树操作）+ 测试 + 版本元数据；全 additive，但跨多个契约面需独立 review + 回归既有分叉。
> 生成: 2026-06-16
> 预解析: target surface = skill-system-self → active roles = skill-maintainer；validate-modes = [correctness]（结构 lint + backlog.py 单测 + dogfood）。无 AI/UI 面 → eval/design 契约 N/A。

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | backlog.py `retire` 子命令 + TDD（确定性引擎） | REQ-ARCHIVE, REQ-SHIPPED, REQ-CLEAR, REQ-BACKFLOW, REQ-DEGRADE, REQ-IDEMPOTENT, D-02 | — | 1 |
| P2 | backlog SKILL Retire op 文档 + §1.118 修订 | REQ-TRIGGER(消费侧), D-01, REQ-CONTRACT(backlog) | P1 | 2 |
| P3 | driver 分叉/路由 + STATE/PROFILE 模板契约 | REQ-TRIGGER, REQ-CONTRACT(driver/模板), D-03 | P1 | 2 |
| P4 | 元数据同步 + 结构 lint + dogfood 收口 | REQ-VERSION, 全特性回归 | P1,P2,P3 | 3 |

需求 ID 映射（spec → 本 plan）：
- GOAL = spec §1 退场闭环（归档→回流→标shipped→清栈）
- REQ-ARCHIVE=§5.2①, REQ-BACKFLOW=§5.2②+§5.3, REQ-SHIPPED=§5.2③, REQ-CLEAR=§5.2④, REQ-TRIGGER=§5.1, REQ-DEGRADE=§5.2降级注, REQ-IDEMPOTENT=§6幂等, REQ-CONTRACT=§5.4, REQ-VERSION=§5.4版本
- D-01=backlog-owned（否决 A/B）, D-02=回流目标 PROFILE→else EVOLUTION.md, D-03=全 additive 不动枚举/skill/role-routing

---

## Phase P1: backlog.py `retire` 子命令 + TDD（确定性引擎）

**目标**: `backlog.py retire` 能确定性完成退场的机械部分——归档工件、标源叶 shipped、回流追加、清栈，且幂等安全。
**覆盖需求(traceability)**: REQ-ARCHIVE, REQ-SHIPPED, REQ-CLEAR, REQ-BACKFLOW, REQ-DEGRADE, REQ-IDEMPOTENT, D-02
**depends_on**: []   **wave**: 1
**为什么这样拆**: 这是特性的心脏，确定性可单测；先把引擎做绿，文档/契约（P2/P3）再去描述与路由它，避免文档先行却无实现可验。

**must_haves（目标倒推）**:
- truths(可观察):
  - 跑 `retire --sdlc <d> --slug s --date 2026-06-16` 后，`<d>/spec.md|plan.md|validate|review|STATE.md` 移入 `<d>/archive/2026-06-16-s/`，顶层不再有这些文件。
  - 给 `--leaf <id> --req-root <r>` 时，该叶 frontmatter `status` 变 `shipped`；之后 `readyqueue` 不再列它、且其下游解锁。
  - 给 `--evolution-entry "<txt>"`：有 `--profile` 且文件在 → 追加到其 `## Evolution log`（缺则建段）；否则写 `<d>/EVOLUTION.md`。
  - archive 目标目录已存在 → 非 0 退出、不覆盖、不动任何文件。
  - 无 `--leaf`/无 `--req-root`/叶不存在 → 跳过标 shipped 并 stderr 告警，其余步骤照常、退出 0。
- artifacts(必存文件): `scripts/backlog.py`（新增 `cmd_retire` + 3 个 helper + main 派发分支）、`scripts/test_backlog.py`（新增 `RetireTest`）。
- key_links: main 的 subparser 派发要为 `retire` 走独立 arg 集（不复用 readyqueue/coverage/lint 的 `--root` 循环）；`cmd_retire` 复用既有 `load_leaves` 定位叶。
**可观察成功标准**: `python3 -m pytest scripts/test_backlog.py -q`（或 `python3 scripts/test_backlog.py`）全绿，新增 RetireTest 覆盖上述 6 条行为。

### Task P1-T1: 写 retire 的失败测试（RetireTest）
- **requirements**: REQ-ARCHIVE, REQ-SHIPPED, REQ-CLEAR, REQ-BACKFLOW, REQ-DEGRADE, REQ-IDEMPOTENT
- **files**: `scripts/test_backlog.py`
- **read_first**: `scripts/test_backlog.py:1-122`（`LEAF_TMPL` / `write_leaf` / `run` helper 复用）；`.sdlc/spec.md` §5.2、§6
- **action**: 在 `test_backlog.py` 末尾（`if __name__` 之前）新增 `class RetireTest(unittest.TestCase)`，复用现成 `write_leaf`。新增 helper `run_retire(*args)` 直接 `subprocess.run([sys.executable, BACKLOG, "retire", *args])`（注意 retire 不吃 `--root`，故不能用现成 `run()`）。用 `tempfile.TemporaryDirectory()` 造 `.sdlc` 目录：写 `spec.md`/`plan.md`/`STATE.md` + `validate/`、`review/` 子目录文件。用例：
  - `test_archives_and_clears`: 跑 retire → 断言 `archive/2026-06-16-feat/` 下含 spec.md/plan.md/STATE.md/validate/review，且原顶层路径 `os.path.exists` 全 False。
  - `test_marks_leaf_shipped_and_unblocks`: 建 req-root 两叶（a 无依赖、b 依赖 a），retire `--leaf <a.id> --req-root <r>` → 读 a 叶文件断言 `status: shipped`；再 `readyqueue --root <r>` 断言 b 进队（复用现成 `run`）。
  - `test_backflow_to_profile_section`: 给 `--profile <p>`（p 内含 `## Tech stack` 无 Evolution log）+ `--evolution-entry "- 2026-06-16 · feat · lesson"` → 断言 p 文本含 `## Evolution log` 且含该行。
  - `test_backflow_fallback_evolution_md`: 不给 `--profile` → 断言 `<sdlc>/EVOLUTION.md` 存在且含该行。
  - `test_archive_exists_refuses`: 预建 `archive/2026-06-16-feat/` → 跑 retire 断言 `returncode != 0` 且 spec.md 仍在顶层（未动）。
  - `test_no_leaf_graceful`: 不给 `--leaf` → 断言 returncode 0、归档照常。
- **acceptance_criteria**: 代码写入；此步不要求通过（下一步确认 FAIL）。

- [ ] Step 1: 写失败测试（按上面 6 个用例贴真实代码进 `RetireTest`，含 `run_retire` helper）
- [ ] Step 2: 跑 `python3 -m pytest scripts/test_backlog.py::RetireTest -q` → 期望 FAIL（`retire` 子命令不存在 → argparse 报错 / 非 0）
- [ ] Step 3: （在 P1-T2 实现）
- [ ] Step 4: 跑 `python3 -m pytest scripts/test_backlog.py -q` → 期望全 PASS
- [ ] Step 5: `git add scripts/test_backlog.py scripts/backlog.py && git commit -m "feat(retire): backlog.py retire 子命令 + TDD"`

### Task P1-T2: 实现 cmd_retire + helper + main 派发
- **requirements**: REQ-ARCHIVE, REQ-SHIPPED, REQ-CLEAR, REQ-BACKFLOW, REQ-DEGRADE, REQ-IDEMPOTENT, D-02
- **files**: `scripts/backlog.py`
- **read_first**: `scripts/backlog.py:1-24`（顶部 docstring、`import`、常量 `SHIPPED`/`REQUIRED_FIELDS`）、`:46-62`（`load_leaves`）、`:134-145`（`main` 派发）
- **action**:
  1. 顶部加 `import shutil`、`import re`；常量加 `RETIRE_ARTIFACTS = ["spec.md", "plan.md", "validate", "review", "STATE.md"]`。把顶部 docstring 第 10 行"本脚本只读不写树"改为"派生操作只读；retire 写树（标 shipped）+ 移工件 + 回流追加"。
  2. 新增 `def _set_frontmatter_status(path, value)`：读文件，用 `re.sub(r'(?m)^status:.*$', f'status: {value}', text, count=1)` 仅替换首个 `status:` 行，写回。
  3. 新增 `def _mark_leaf_shipped(req_root, leaf_id)`：遍历 `load_leaves(req_root)`，`id` 命中则 `_set_frontmatter_status(lf["_path"], SHIPPED)` 返回 True；未命中返回 False。
  4. 新增 `def _append_evolution(profile, sdlc_dir, entry)`：`profile` 存在 → 读文本，缺 `## Evolution log` 则 `text = text.rstrip() + "\n\n## Evolution log\n"`，再 `text = text.rstrip() + "\n" + entry + "\n"` 写回；否则 target=`os.path.join(sdlc_dir, "EVOLUTION.md")`，不存在先写 `# Evolution log\n\n`，再 append `entry + "\n"`。
  5. 新增 `def cmd_retire(args)`：`archive_dir = os.path.join(args.sdlc, "archive", f"{args.date}-{args.slug}")`；若 `os.path.exists(archive_dir)` → `print(..., file=sys.stderr); return 1`；`os.makedirs(archive_dir)`；对 `RETIRE_ARTIFACTS` 中存在者 `shutil.move(src, dst)`；若 `args.leaf and args.req_root` → `_mark_leaf_shipped`，未命中 stderr 告警（不致命）；若 `args.evolution_entry` → `_append_evolution`；`print(json.dumps({"archived": archive_dir, "moved": moved, "leaf_shipped": ...}))`；`return 0`。
  6. 改 `main`：现有循环只给 readyqueue/coverage/lint 加 `--root`；**新增** `pr = sub.add_parser("retire")` 并加 `--sdlc`(required)、`--slug`(required)、`--date`(required)、`--leaf`、`--req-root`(dest 默认 `req_root`)、`--profile`、`--evolution-entry`(dest `evolution_entry`)。派发改为：`if args.cmd == "retire": return cmd_retire(args)`，否则保留现有 `{readyqueue/coverage/lint}[cmd](args.root)`（含 `--root` 存在性校验只对这三者）。
  - **不做**：不重算/不重写 `_index.md`（ready-queue 是按需派生，标 shipped 后 `readyqueue` 自动反映；缓存快照由既有 readyqueue/coverage 重建，不在 retire 职责内）。
- **acceptance_criteria**: `python3 -m pytest scripts/test_backlog.py -q` 全 PASS（含 RetireTest 6 用例 + 既有 5 用例不回归）；`python3 scripts/backlog.py retire -h` 列出新参数。

---

## Phase P2: backlog SKILL Retire op 文档 + §1.118 修订

**目标**: backlog SKILL 把 Retire 列为一个正式 op（四步 + 判断性回流 + 优雅降级），并修正"叶 shipped 回写委托给未来 B"的旧表述。
**覆盖需求(traceability)**: D-01, REQ-CONTRACT(backlog), REQ-TRIGGER(消费侧说明)
**depends_on**: [P1]   **wave**: 2
**为什么这样拆**: 文档描述 P1 已实现的引擎 + 规定模型在回流步该如何蒸馏（判断性部分不进脚本）。与 P3 不同文件，可同 wave 并行。

**must_haves**:
- truths: backlog SKILL 出现 "Retire / close-out" op 章节，含四步表（①归档 ②回流 ③标shipped ④清栈）、确定性 vs 判断性分工（脚本做文件机械、模型做"哪些算耐久决策"的蒸馏）、无树/无叶降级；§1.118 不再把终态回写整体推给"未来 B"。
- artifacts: `skills/sdlc-backlog/SKILL.md`（新增 op 章节 + 修订 §1.118）。
- key_links: op 章节要指明命令 = `python3 scripts/backlog.py retire ...`（参考卡可留具体命令，符合铁律#4 例外②），但"哪些决策耐久得回流"写成**原则**由模型判。

### Task P2-T1: 新增 Retire op 章节 + 接进 op 列表
- **requirements**: D-01, REQ-CONTRACT
- **files**: `skills/sdlc-backlog/SKILL.md`
- **read_first**: `skills/sdlc-backlog/SKILL.md`（§ 标题描述里的 op 枚举 "Seed/Ingest/Coverage/Ready-queue/Lint"、§4 派生操作章节、§1.2 叶状态机、§1.3 ready-queue）；`.sdlc/spec.md` §5.2、§5.3
- **action**: 在 §4 派生操作之后新增 `## N. 操作: Retire（特性退场 / close-out）` 章节：
  - 一句话定位：由 driver 在 `STATE.stage==done` 时路由进来，给一个完成的特性收尾。
  - **四步表**（照 spec §5.2）：①归档 `.sdlc/{spec,plan,validate,review,STATE}` → `archive/<date>-<slug>/`（脚本）②回流：模型从 `STATE.Decisions log` 蒸馏**耐久**决策/教训/新风险，经 `--evolution-entry` 写 PROFILE `## Evolution log`（无 PROFILE → `.sdlc/EVOLUTION.md`）③标源叶 `status=shipped`（`--leaf`+`--req-root`，脚本）→ ready-queue 自动解锁下游 ④清栈（STATE 随归档移走，顶层留空给下个特性）。
  - **确定性 vs 判断性**：文件移动/标 shipped/追加 = `backlog.py retire`（确定性，参考命令可留）；"哪些决策值得回流" = 模型判断（原则：跨特性仍成立的架构/契约/坑，而非一次性实现细节）。
  - **优雅降级**：无 `requirements/` 树或特性非源自叶 → 跳过③，①②④照做（spec §5.2 降级注）。
  - **单写者**：Retire 是该时刻 STATE 的唯一写者（driver 路由后 backlog 独占），归档→清栈原子完成。
  - 同步把文件顶部/§ 标题里的 op 枚举从 "Seed/Ingest/Coverage/Ready-queue/Lint" 补成含 "Retire"。
- **acceptance_criteria**: `grep -n "Retire" skills/sdlc-backlog/SKILL.md` 命中新章节 + op 枚举；章节含四步 + 降级 + 确定性/判断性分工；`bash scripts/validate-skills` 不因本文件报错。

### Task P2-T2: 修订 §1.118 的"回写委托 B"表述
- **requirements**: D-01
- **files**: `skills/sdlc-backlog/SKILL.md`
- **read_first**: `skills/sdlc-backlog/SKILL.md` §1.118（"B 跑完一叶后回写该叶 status…回写是子系统 B 职责"）；`.sdlc/spec.md` §1（缺口说明）、§2（非目标：只填终态）
- **action**: 把该句改为：终态 `shipped` 回写由 **backlog Retire op**（特性 done 时）负责，填上原先悬空的回写点；中间态（spec'd/planned/built/validated）逐阶段回写与 ready-queue 调度仍属未来子系统 B（已在本特性 spec §8 Deferred）。保留 ready-queue 契约 §1.3 不变。
- **acceptance_criteria**: §1.118 不再把"终态回写"整体归给未来 B；明确 Retire 负责终态；保留中间态/调度为 Deferred 的指向。`bash scripts/validate-skills` PASS。

---

## Phase P3: driver 分叉/路由 + STATE/PROFILE 模板契约

**目标**: driver 在 done 时路由到 backlog Retire；STATE 模板把悬空指令改实 + 加 `source-leaf`；PROFILE 模板加回流载体段。
**覆盖需求(traceability)**: REQ-TRIGGER, REQ-CONTRACT(driver/模板), D-03
**depends_on**: [P1]   **wave**: 2
**为什么这样拆**: 触发/路由/载体三处契约改动，与 backlog SKILL（P2）不同文件，可同 wave 并行；都依赖 P1 的 op 存在以便引用。

**must_haves**:
- truths: driver 读到 `STATE.stage==done` 会先路由到 backlog Retire 再分叉新特性；STATE 模板第 6 行是可执行退场指引且有 `source-leaf` 字段；PROFILE 模板有 `## Evolution log` 段。
- artifacts: `skills/sdlc/SKILL.md`、`skills/sdlc/references/templates/STATE.md`、`skills/sdlc/references/templates/PROFILE.md`。
- key_links: driver §4 路由表新增一行 `done → sdlc-backlog(Retire)`；§2 分叉新增 done 条件**先于**三主分叉；§5 交接注明 driver 不自己归档（守"导演不干活"）。
**可观察成功标准**: `bash scripts/validate-skills` PASS（引用一致、无悬空）；driver/模板三文件均含对应新增且互相指向一致（done→backlog、source-leaf、Evolution log）。

### Task P3-T1: driver SKILL —— done 分叉 + 路由表行 + 交接注
- **requirements**: REQ-TRIGGER, D-03
- **files**: `skills/sdlc/SKILL.md`
- **read_first**: `skills/sdlc/SKILL.md` §2 分叉（含"正交分支:需求树/backlog"段）、§4 路由表（onboard/backlog/spec/.../ship 行）、§5 交接、§1.2（`/sdlc next` 姿势）
- **action**:
  1. §2 分叉：在三主分叉判定**之前**新增条件——读到 `STATE.stage == done`（特性已完成未退场）→ text_mode 提示并路由到 **backlog Retire**（先收尾再起新特性），即把本 session 手工做的退场自动化。给一行可选 `/sdlc retire` 显式触发说明（非新 stage，仅 driver 调用姿势）。
  2. §4 路由表新增一行：`done | sdlc-backlog（Retire op） | 传 .sdlc 目录 + 源叶 id（若 STATE.source-leaf 有）；归档/回流/标shipped/清栈`。
  3. §5 交接：注明 done 的退场由 backlog 执行，**driver 不自己归档**（守"导演只路由不干活"）；Retire 是该时刻 STATE 单写者。
  - **不动**：stage 枚举行（done 已在内，D-03）、resolve/漂移机制。
- **acceptance_criteria**: `grep -n "Retire\|done" skills/sdlc/SKILL.md` 显示 §2 新分叉 + §4 新行 + §5 注；stage 枚举行未变；`bash scripts/validate-skills` PASS。

### Task P3-T2: STATE 模板 —— 退场指引 + source-leaf 字段
- **requirements**: REQ-CLEAR, REQ-SHIPPED, REQ-CONTRACT
- **files**: `skills/sdlc/references/templates/STATE.md`
- **read_first**: `skills/sdlc/references/templates/STATE.md:1-31`（注释块"feature 完成后归档或清空" + frontmatter 字段区 branch/worktree/validate-modes）
- **action**:
  1. 把注释块里"feature 完成（stage=done）后归档或清空"改为明确指引：done 后由 **backlog Retire op** 退场——归档到 `.sdlc/archive/<date>-<feature>/`、耐久决策回流 PROFILE `## Evolution log`、（若源自需求树）标源叶 shipped、清空本文件；由 driver 在下次 `/sdlc` 检测 `stage==done` 触发。
  2. frontmatter 字段区新增 `source-leaf: <若特性源自 requirements 树则记叶 id，否则 (none)>   # Retire 据此回写叶 shipped`。
- **acceptance_criteria**: `grep -n "source-leaf\|Retire\|archive" skills/sdlc/references/templates/STATE.md` 命中新字段 + 新指引；不再有"归档或清空"悬空措辞；`bash scripts/validate-skills` PASS。

### Task P3-T3: PROFILE 模板 —— 新增 Evolution log 段
- **requirements**: REQ-BACKFLOW, D-02
- **files**: `skills/sdlc/references/templates/PROFILE.md`
- **read_first**: `skills/sdlc/references/templates/PROFILE.md`（六节：Tech stack/Surface map/Conventions/Entry points/Known risks/Deploy 的标题与注释风格）
- **action**: 在 `## Known risks` 与 `## Deploy` 之间（或文件末）新增 `## Evolution log` 段，附注释说明：append-only；由 backlog Retire op 在特性 done 时回流；每条格式 `- <date> · <feature> · <耐久决策/教训/新风险> · → archive/<date>-<feature>/`；与 `Known risks`（onboard 测绘的静态风险）区分——Evolution log 是已完成特性沉淀的动态教训。
- **acceptance_criteria**: `grep -n "Evolution log" skills/sdlc/references/templates/PROFILE.md` 命中；注释说明回流来源与格式；`bash scripts/validate-skills` PASS。

---

## Phase P4: 元数据同步 + 结构 lint + dogfood 收口

**目标**: 版本/CHANGELOG/README/CLAUDE 同步到位，结构 lint + 单测 + dogfood 全绿。
**覆盖需求(traceability)**: REQ-VERSION, 全特性回归
**depends_on**: [P1, P2, P3]   **wave**: 3
**为什么这样拆**: 版本号与计数必须反映全部改动，结构 lint 校验跨文件引用一致，dogfood 验证端到端——都得等前三阶段落定。

**must_haves**:
- truths: `plugin.json`/`marketplace.json` version = `0.10.0`；CHANGELOG 有 0.10.0 条目；README backlog op 列表含 Retire；`validate-skills` clean；`test_backlog.py` 全绿；dogfood 跑通一次 retire。
- artifacts: `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、`CHANGELOG.md`、`README.md`、必要时 `CLAUDE.md`。
- key_links: 版本 bump 与 CHANGELOG 同条；README op 枚举与 backlog SKILL §（P2）一致。

### Task P4-T1: 版本 + CHANGELOG + README + CLAUDE 同步
- **requirements**: REQ-VERSION, D-03
- **files**: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `README.md`, `CLAUDE.md`
- **read_first**: `.claude-plugin/plugin.json`（`"version"` 行）、`.claude-plugin/marketplace.json`（version 行）、`CHANGELOG.md` 顶部（0.9.0 条目格式）、`README.md`（backlog op 枚举处）、`CLAUDE.md`（"怎么迭代"表 + 铁律#1 的家族 8 skill 描述）
- **action**:
  1. `plugin.json` + `marketplace.json` 的 `version` 从 `0.9.0` → `0.10.0`（minor：加 Retire 能力）。
  2. `CHANGELOG.md` 顶部加 `## 0.10.0` 条目：backlog 新增 Retire op（特性 done 退场：归档/回流 PROFILE/标叶 shipped/清栈）+ driver done→backlog 分叉 + STATE/PROFILE 模板契约（全 additive，不动 stage 枚举/skill 计数）。
  3. `README.md` backlog op 枚举补 Retire；如有"流程/能力"描述同步。
  4. `CLAUDE.md`："怎么迭代"表若有 backlog/op 相关行则补 Retire 一句；**不改**铁律#1 的"8 流程 skill"计数（未加 skill）。
  - **不动**：stage 枚举、skill 计数、role-routing 取值字典。
- **acceptance_criteria**: `grep -l '"version": "0.10.0"' .claude-plugin/plugin.json .claude-plugin/marketplace.json` 两文件都命中；`grep -n "0.10.0" CHANGELOG.md` 命中；`grep -n "Retire" README.md` 命中；skill 计数未变。

### Task P4-T2: 结构 lint + 单测 + dogfood 收口
- **requirements**: 全特性回归
- **files**: （无源码改动；验证 + 记录）
- **read_first**: `scripts/validate-skills`（lint 范围）、`.sdlc/archive/2026-06-15-sdlc-backlog/`（已存在的归档实例，作 dogfood 对照）
- **action**:
  1. `bash scripts/validate-skills` → 必 clean（角色名↔文件、引用一致、frontmatter、无悬空）。
  2. `python3 -m pytest scripts/test_backlog.py -q`（或 `python3 scripts/test_backlog.py`）→ 全绿。
  3. **dogfood**：造一个临时 `.sdlc` fixture（含 spec/plan/STATE + 一个 requirements 叶），跑 `python3 scripts/backlog.py retire --sdlc <tmp> --slug demo --date 2026-06-16 --leaf <id> --req-root <tmp/req> --evolution-entry "- ..."` → 人工核对：archive 落位、叶 shipped、EVOLUTION/PROFILE 追加、顶层清空、再跑一次报 archive 已存在拒绝。**在临时目录做，不污染本仓**。
- **acceptance_criteria**: validate-skills 输出 `clean`；pytest 全 PASS；dogfood 六行为人工核对通过（结果记 STATE Decisions log）。

---

## Source Audit（出口门控，§6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|---|---|---|---|---|
| GOAL | — | 退场闭环（归档→回流→标shipped→清栈） | P1-T2, P3-T1 | COVERED |
| REQ | REQ-ARCHIVE | 归档工件到 archive/<date>-<feat>/ | P1-T1,P1-T2 | COVERED |
| REQ | REQ-BACKFLOW | 耐久决策回流 PROFILE/EVOLUTION | P1-T2, P2-T1, P3-T3 | COVERED |
| REQ | REQ-SHIPPED | 标源叶 shipped + ready-queue 解锁 | P1-T1,P1-T2, P3-T2 | COVERED |
| REQ | REQ-CLEAR | 清空 STATE | P1-T2, P3-T2 | COVERED |
| REQ | REQ-TRIGGER | driver done→backlog 分叉 | P3-T1, P2-T1 | COVERED |
| REQ | REQ-DEGRADE | 无树/无叶优雅降级 | P1-T1,P1-T2, P2-T1 | COVERED |
| REQ | REQ-IDEMPOTENT | archive 已存在报错不覆盖 | P1-T1,P1-T2 | COVERED |
| REQ | REQ-CONTRACT | backlog SKILL + driver + STATE/PROFILE 模板同步 | P2-T1,P2-T2, P3-T1,T2,T3 | COVERED |
| REQ | REQ-VERSION | 0.10.0 + CHANGELOG + README | P4-T1 | COVERED |
| DECISION | D-01 | backlog-owned（否决 driver/ship-each） | P2-T1,P2-T2, P3-T1 | COVERED |
| DECISION | D-02 | 回流目标 PROFILE→else EVOLUTION.md | P1-T2, P3-T3 | COVERED |
| DECISION | D-03 | 全 additive，不动枚举/skill/role-routing | P3-T1, P4-T1 | COVERED |
| EVAL-CRIT | — | N/A（非 AI 工作） | — | N/A |

**Coverage Gate（反向）**：P1-T1→REQ-ARCHIVE/SHIPPED/CLEAR/BACKFLOW/DEGRADE/IDEMPOTENT；P1-T2→同+ D-02；P2-T1→D-01/CONTRACT/TRIGGER；P2-T2→D-01；P3-T1→TRIGGER/D-03；P3-T2→CLEAR/SHIPPED/CONTRACT；P3-T3→BACKFLOW/D-02；P4-T1→VERSION/D-03；P4-T2→全回归。每个任务均指回需求，无孤儿任务。

## 风险 / 关键决策点
- **backlog.py 首次写树**：retire 是该脚本第一个写操作（既往只读）。风险=误移/误改叶。缓解=幂等 archive 守卫 + `_set_frontmatter_status` 用 `count=1` 只改首个 status 行 + 全程在 TDD 临时目录验证，dogfood 也只在 tmp。
- **driver §2 新分叉顺序**：done 检测必须**先于**三主分叉，否则 done STATE 会被误判为"续接特性"。P3-T1 需显式置于分叉链最前。
- **回流"耐久"判断主观**：交模型按原则判（跨特性仍成立=回流，一次性细节=不回流），不进脚本。review 阶段 skill-maintainer 透镜复核回流内容是否得当。
