# Plan: archive 纳入 git + Evolution log 独立化（Deferred #2）

> 来源 spec: .sdlc/spec.md（已批准，网页审 approve）
> 复杂度等级: **L2** —— 理由: gitignore 策略 + 一处代码简化(含 TDD) + 模板/文档/元数据，全 additive/小重构；无跨系统依赖。
> 生成: 2026-06-16
> 预解析: target surface = skill-system-self → roles = skill-maintainer + qa；validate-modes = [correctness]（git check-ignore 实测 + backlog.py 单测 + validate-skills）。无 AI/UI → eval/design N/A。

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | Evolution log 独立化（代码 + 测试 + 模板/SKILL）| REQ-EVOLUTION-CANON, REQ-PROFILE-POINTER, REQ-SKILL-DOC, D-EVOL | — | 1 |
| P2 | gitignore track 策略 | REQ-GITIGNORE, D-B | — | 1 |
| P3 | 文档约定 + 元数据 + dogfood 入仓收口 | REQ-CONVENTION-DOC, REQ-VERSION, REQ-DOGFOOD | P1,P2 | 2 |

需求 ID（spec → plan）：GOAL1=git 持久、GOAL2=Evolution 独立化；REQ-EVOLUTION-CANON=§4.1/§5.2b（EVOLUTION.md 唯一正屋 + `_append_evolution` 单路径 + 去 --profile）；REQ-PROFILE-POINTER=§5.2b（PROFILE 模板节→指针）；REQ-SKILL-DOC=§5.2b（backlog SKILL §5 回流描述）；REQ-GITIGNORE=§5.1；REQ-CONVENTION-DOC=§5.2/§5.3（CLAUDE/README + 隐私）；REQ-VERSION=§6；REQ-DOGFOOD=§5.4；D-B=track option B；D-EVOL=EVOLUTION 独立 vs PROFILE 节。

P1、P2 改不同文件（backlog.py/templates/SKILL vs .gitignore）→ 同 wave 无冲突；单 session 串行即可。

---

## Phase P1: Evolution log 独立化（代码 + 测试 + 模板/SKILL）

**目标**: 退场回流永远写独立的 `EVOLUTION.md`；PROFILE 不再承载流水、仅留指针；`backlog.py` 回流逻辑单路径化。
**覆盖需求(traceability)**: REQ-EVOLUTION-CANON, REQ-PROFILE-POINTER, REQ-SKILL-DOC, D-EVOL
**depends_on**: []   **wave**: 1
**为什么这样拆**: 这是本特性的唯一代码改动（确定性可单测），先 TDD 做绿；gitignore（P2）与文档（P3）围绕它。

**must_haves（目标倒推）**:
- truths: `backlog.py retire`（无 `--profile`）跑完，演进条目只进 `<sdlc>/EVOLUTION.md`；即便目标目录有 PROFILE.md，其内容也**不**被追加。
- artifacts: 改后的 `scripts/backlog.py`、`scripts/test_backlog.py`、`templates/PROFILE.md`、`skills/sdlc-backlog/SKILL.md`。
- key_links: `cmd_retire` → `_append_evolution(sdlc_dir, entry)` 单参；main retire 子parser 无 `--profile`。
**可观察成功标准**: `python3 scripts/test_backlog.py` 全绿（改后用例 + 既有不回归）；`grep -c "profile" scripts/backlog.py` 在 retire 相关处归零（除文档串）。

### Task P1-T1: 改测试 → 红（_append_evolution 单路径）
- **requirements**: REQ-EVOLUTION-CANON, D-EVOL
- **files**: `scripts/test_backlog.py`
- **read_first**: `scripts/test_backlog.py:120-210`（`run_retire`/`_read`/`RetireTest` 的 `test_backflow_to_profile_section`、`test_backflow_fallback_evolution_md`）；`.sdlc/spec.md` §4.1/§5.2b
- **action**: 把 `test_backflow_to_profile_section` **改名为** `test_backflow_always_evolution_md` 并改语义：仍造一个含 `## Tech stack` 的 PROFILE.md，但 retire **不传 `--profile`**，断言 ① `<sdlc>/EVOLUTION.md` 存在且含 entry；② PROFILE.md 文本**不含** `## Evolution log`、不含该 entry（`self.assertNotIn`）。`test_backflow_fallback_evolution_md` 保留（无 profile 场景）。所有 `run_retire(...)` 调用去掉 `--profile <p>` 实参。
- **acceptance_criteria**: 此步只改测试；下一步确认红。
- [ ] Step 1: 改测试（按上述贴真实代码）
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py RetireTest` → 期望 **FAIL**（现实现仍写 PROFILE 节 / 仍收 --profile，新断言 assertNotIn 不满足，或 --profile 已被去除导致旧实现报错）
- [ ] Step 3:（P1-T2 实现）
- [ ] Step 4: 跑 `python3 scripts/test_backlog.py` → 期望全 PASS
- [ ] Step 5: `git add scripts/backlog.py scripts/test_backlog.py && git commit -m "refactor(retire): Evolution log 单路径写 EVOLUTION.md（去 --profile）"`

### Task P1-T2: 简化 _append_evolution + 去 --profile（绿）
- **requirements**: REQ-EVOLUTION-CANON, D-EVOL
- **files**: `scripts/backlog.py`
- **read_first**: `scripts/backlog.py` 的 `_append_evolution`（profile/sdlc_dir 双路径）、`cmd_retire`（`if args.evolution_entry: backflow = _append_evolution(args.profile, ...)`）、`main` retire 子parser（`pr.add_argument("--profile", ...)`）
- **action**:
  1. `_append_evolution` 改签名为 `def _append_evolution(sdlc_dir, entry):`，删 profile 分支，函数体只保留"写 `os.path.join(sdlc_dir, "EVOLUTION.md")`，不存在先写 `# Evolution log\n\n` 头，再 append `entry + "\n"`"。
  2. `cmd_retire` 内改为 `backflow = _append_evolution(args.sdlc, args.evolution_entry)`。
  3. `main` retire 子parser **删** `pr.add_argument("--profile", ...)` 那行。
  4. 顶部 docstring 若提及 retire 写 PROFILE，改为"回流写 .sdlc/EVOLUTION.md"。
- **acceptance_criteria**: `python3 scripts/test_backlog.py` 全 PASS（含改后 `test_backflow_always_evolution_md` + 既有）；`python3 scripts/backlog.py retire -h` 不再列 `--profile`。

### Task P1-T3: PROFILE 模板节→指针 + backlog SKILL §5 回流描述
- **requirements**: REQ-PROFILE-POINTER, REQ-SKILL-DOC
- **files**: `skills/sdlc/references/templates/PROFILE.md`、`skills/sdlc-backlog/SKILL.md`
- **read_first**: `templates/PROFILE.md` 的 `## Evolution log` 整节（含注释块，上特性加的）；`skills/sdlc-backlog/SKILL.md` §5 Retire op 的四步表 ② 行 + "回流目标(②)" 段
- **action**:
  1. PROFILE 模板：把 `## Evolution log` 整节（标题 + 注释 + 示例条目）**替换为**：`## Evolution log` 标题 + 一行指针 `> 演进史（append-only，每特性退场由 Retire op 追加）见同目录 EVOLUTION.md。本文件只留指针，避免无界流水撑爆每会话整篇加载的 PROFILE。`
  2. backlog SKILL §5：四步表 ② 行的"写 PROFILE ## Evolution log（无 PROFILE 兜底 EVOLUTION.md）"改为"统一 append `.sdlc/EVOLUTION.md`（PROFILE 仅留指针）"；"回流目标(②)"段同步改为"唯一正屋 = `<sdlc>/EVOLUTION.md`；PROFILE 不再承载流水"。命令示例去掉 `--profile`。
- **acceptance_criteria**: `grep -A2 "## Evolution log" skills/sdlc/references/templates/PROFILE.md` 显示指针行、无原注释块；`grep -n "EVOLUTION.md" skills/sdlc-backlog/SKILL.md` 命中统一表述、§5 命令无 `--profile`；`bash scripts/validate-skills` PASS。

---

## Phase P2: gitignore track 策略

**目标**: `.sdlc/archive/` + `EVOLUTION.md` + `PROFILE.md` 纳入 git，在飞工作态仍忽略。
**覆盖需求(traceability)**: REQ-GITIGNORE, D-B
**depends_on**: []   **wave**: 1
**为什么这样拆**: 单文件机械改 + git 实测，与 P1 不同文件，独立。

**must_haves**:
- truths: `git check-ignore .sdlc/spec.md` 命中（忽略在飞态）；`.sdlc/archive/<x>`、`.sdlc/EVOLUTION.md`、`.sdlc/PROFILE.md` **不**被忽略。
- artifacts: 改后的 `.gitignore`。
- key_links: `.sdlc/*` 忽略内容 + 三条 `!` 反忽略；保留 web-review json 忽略行。

### Task P2-T1: 改 .gitignore 并 git 实测
- **requirements**: REQ-GITIGNORE, D-B
- **files**: `.gitignore`
- **read_first**: `.gitignore:1`（`.sdlc/`）、`:8-11`（web-review feedback*.json / replies.json / rev）
- **action**: 把第 1 行 `.sdlc/` 替换为：
  ```
  .sdlc/*
  !.sdlc/archive/
  !.sdlc/EVOLUTION.md
  !.sdlc/PROFILE.md
  ```
  （`.sdlc/*` 忽略**内容**而非目录本身，才能用 `!` 反忽略子项）。保留 §8-11 web-review json 忽略行不动。
- **acceptance_criteria**: 全部成立——
  `git check-ignore .sdlc/spec.md` → 命中（exit 0）；
  `git check-ignore .sdlc/STATE.md` → 命中；
  `git check-ignore .sdlc/archive/2026-06-16-feature-retirement/spec.md` → **不**命中（exit 1）；
  `git check-ignore .sdlc/EVOLUTION.md` → 不命中（exit 1）；
  `git check-ignore .sdlc/PROFILE.md` → 不命中（exit 1）。
- [ ] Step 1: 改 .gitignore
- [ ] Step 2: 跑上面 5 条 `git check-ignore -v` 逐一核对（命中/不命中符合预期）
- [ ] Step 3: `git add .gitignore && git commit -m "feat(track): .sdlc archive/EVOLUTION/PROFILE 纳入 git，在飞工作态仍忽略"`

---

## Phase P3: 文档约定 + 元数据 + dogfood 入仓收口

**目标**: track 策略文档化（含隐私提醒）；版本元数据；把现有 archive + EVOLUTION.md 首次入仓。
**覆盖需求(traceability)**: REQ-CONVENTION-DOC, REQ-VERSION, REQ-DOGFOOD
**depends_on**: [P1, P2]   **wave**: 2
**为什么这样拆**: 版本/计数反映全部改动；git add 现有 archive 依赖 P2 的 gitignore 放行；文档描述 P1 的新回流行为。

**must_haves**:
- truths: CLAUDE.md/README 有 `.sdlc` track 策略 + 隐私提醒；plugin/marketplace version 升；现有 2 个 archive + EVOLUTION.md 进暂存可提交。
- artifacts: `CLAUDE.md`、`README.md`、`.claude-plugin/{plugin,marketplace}.json`、`CHANGELOG.md`、暂存的 `.sdlc/archive/**` + `.sdlc/EVOLUTION.md`。
- key_links: 版本号 minor（加能力）；CHANGELOG 同条。

### Task P3-T1: track 策略文档 + 隐私提醒
- **requirements**: REQ-CONVENTION-DOC
- **files**: `CLAUDE.md`、`README.md`
- **read_first**: `CLAUDE.md` "路径约定" 段 + "怎么迭代" 表；`README.md` backlog/退场相关处（§使用场景 line ~151）
- **action**:
  1. CLAUDE.md "路径约定" 段加一条 `.sdlc` track 策略：在飞工作态（顶层 spec/plan/STATE/validate/review）本地忽略；`archive/` + `EVOLUTION.md` + `PROFILE.md` 纳入 git 跨机器持久（gitignore 用 `.sdlc/*` + `!` 反忽略实现）。附**隐私提醒**：track 前确认这些产物无密钥（Decisions log 可能含敏感配置位置/内网地址）。
  2. README.md 在退场/backlog 相关处加一行：完成特性的工件（archive）+ 演进史（EVOLUTION.md）默认纳入 git，可 clone 带走跨机器；推荐约定，项目可自选。
- **acceptance_criteria**: `grep -n "track\|EVOLUTION\|纳入 git\|密钥" CLAUDE.md` 命中策略 + 隐私提醒；`grep -n "EVOLUTION\|archive" README.md` 命中；`bash scripts/validate-skills` PASS。

### Task P3-T2: 版本 + CHANGELOG
- **requirements**: REQ-VERSION
- **files**: `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`、`CHANGELOG.md`
- **read_first**: `.claude-plugin/plugin.json` version（0.10.0）、`.claude-plugin/marketplace.json`（两处 version）、`CHANGELOG.md` 顶部（0.10.0 条目格式）
- **action**: version `0.10.0 → 0.11.0`（minor：加 `.sdlc` git-track 能力 + Evolution log 独立化）。三处 version 同步（plugin 1 处 + marketplace 2 处）。CHANGELOG 顶部加 `## [0.11.0] — 2026-06-16` 条目：Added=archive/EVOLUTION/PROFILE 纳入 git 的 gitignore 策略 + 隐私提醒；Changed=Evolution log 提为独立 EVOLUTION.md（PROFILE 节→指针）、retire 回流单路径去 --profile；Notes=全 additive，未动 stage 枚举/skill 计数。
- **acceptance_criteria**: `grep -c '0.11.0' .claude-plugin/plugin.json .claude-plugin/marketplace.json CHANGELOG.md` 三文件均命中；marketplace 两处 version 都 0.11.0。

### Task P3-T3: dogfood — 现有 archive + EVOLUTION 首次入仓 + 收口验证
- **requirements**: REQ-DOGFOOD
- **files**: （git 暂存 `.sdlc/archive/**` + `.sdlc/EVOLUTION.md`；验证）
- **read_first**: `.sdlc/archive/`（2 个归档目录）、`.sdlc/EVOLUTION.md`、本特性 spec §5.4
- **action**:
  1. **隐私自查**：`grep -rniE "password|token|secret|api[_-]?key|内网|10\.|192\.168" .sdlc/archive/ .sdlc/EVOLUTION.md` → 若命中敏感值，停下报用户（本仓应无，但守隐私铁律）。
  2. `git add .sdlc/archive/ .sdlc/EVOLUTION.md` → `git status --short .sdlc/` 确认这些进暂存、而 `.sdlc/spec.md`/`plan.md`/`STATE.md` 仍被忽略（不出现在 status）。
  3. 收口：`python3 scripts/test_backlog.py`（全绿）+ `bash scripts/validate-skills`（PASS）+ P2 的 5 条 check-ignore 复核。
  4. 提交：`git add -A 已跟踪 && git commit -m "feat(track): bump 0.11.0 + 文档 track 策略 + 首批 archive/EVOLUTION 入仓（dogfood）"`（把 P3 全部改动 + 首批入仓内容一起提交）。
- **acceptance_criteria**: `git status --short .sdlc/` 显示 archive/** + EVOLUTION.md 已跟踪/暂存，顶层 spec/plan/STATE **不**出现；隐私自查无敏感命中；test + validate-skills 全过。

---

## Source Audit（出口门控，§6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|---|---|---|---|---|
| GOAL | GOAL1 | .sdlc 已完成/已蒸馏产物纳入 git 持久 | P2-T1, P3-T3 | COVERED |
| GOAL | GOAL2 | Evolution log 独立化 / PROFILE 结构重构 | P1-T1,T2,T3 | COVERED |
| REQ | REQ-GITIGNORE | gitignore `.sdlc/*` + `!` 反忽略 | P2-T1 | COVERED |
| REQ | REQ-EVOLUTION-CANON | EVOLUTION.md 唯一正屋 + _append_evolution 单路径 + 去 --profile | P1-T1,T2 | COVERED |
| REQ | REQ-PROFILE-POINTER | PROFILE 模板节→指针 | P1-T3 | COVERED |
| REQ | REQ-SKILL-DOC | backlog SKILL §5 回流描述更新 | P1-T3 | COVERED |
| REQ | REQ-CONVENTION-DOC | CLAUDE/README track 策略 + 隐私提醒 | P3-T1 | COVERED |
| REQ | REQ-VERSION | 0.11.0 + CHANGELOG | P3-T2 | COVERED |
| REQ | REQ-DOGFOOD | 现有 archive + EVOLUTION 首次入仓 | P3-T3 | COVERED |
| DECISION | D-B | track option B（archive+EVOLUTION+PROFILE，工作态本地）| P2-T1, P3-T3 | COVERED |
| DECISION | D-EVOL | EVOLUTION 独立 vs PROFILE 节 | P1-T1,T2,T3 | COVERED |
| EVAL-CRIT | — | N/A（非 AI） | — | N/A |

**Coverage Gate（反向）**：P1-T1→EVOLUTION-CANON/D-EVOL；P1-T2→EVOLUTION-CANON/D-EVOL；P1-T3→PROFILE-POINTER/SKILL-DOC；P2-T1→GITIGNORE/D-B；P3-T1→CONVENTION-DOC；P3-T2→VERSION；P3-T3→DOGFOOD/D-B/GOAL1。每任务指回需求，无孤儿。

## 风险 / 关键决策点
- **gitignore 反忽略陷阱**：必须用 `.sdlc/*`（忽略内容）而非 `.sdlc/`（忽略目录本身），否则 `!` 反忽略子项无效——P2-T1 的 5 条 check-ignore 实测专门兜这个。
- **隐私**：track archive 把 spec/plan/review/decisions 入仓——P3-T3 加隐私自查 grep；文档加提醒。本仓（工具自身）应无密钥。
- **去 --profile 是缩小 CLI**：0.10.0 刚引入、无外部依赖，安全；其它仓若已脚本化调用 retire 需知（CHANGELOG 注明）。
