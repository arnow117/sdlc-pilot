# Spec: archive 纳入 git + Evolution log 独立化（Deferred #2，含 PROFILE 结构重构）

> Date: 2026-06-16
> Status: approved
> Target surface(s): skill-system-self（gitignore 策略 + 约定文档）
> Active roles (anticipated): skill-maintainer
> Validate modes (anticipated): correctness（validate-skills + 人工核对 git track 行为）

## 1. 问题 / 目标

`.gitignore:1 = .sdlc/` 整目录忽略 → 在 sdlc-pilot 自己仓里，退场闭环产出的 `archive/`、`EVOLUTION.md`、（未来）`PROFILE.md` **全是纯本地、跨机器/团队不持久**。完成特性的耐久 context（决策/教训/已完成工件）无法 clone 带走。

**目标 1（git 持久）**：让"已完成 / 已蒸馏"的 `.sdlc` 产物纳入 git 跨机器持久，同时**不让在飞工作态的 churn 污染 git 历史**。

**目标 2（Evolution log 独立化 / PROFILE 结构重构）**：把上特性做成 PROFILE 一节的 `## Evolution log` 提出来，定为**独立的 `EVOLUTION.md` 为正屋**，PROFILE 仅留一行指针。理由：PROFILE 六节是**有界快照**（每会话整篇读、漂移时重写），Evolution log 是**无界 append 流水**（只增、随特性数线性涨）——把流水塞进"每次整篇加载"的 PROFILE 会撑爆它、稀释稳定信息。两者本性不同 → 分文件；但 PROFILE 六节本身有界，**不拆**（避免碎片化）。

## 2. 非目标（YAGNI）

- ❌ 不 track **在飞工作态**（顶层 `spec.md/plan.md/STATE.md/validate/review`）——它们是临时态、改动频繁，退场后才以 `archive/<feat>/` 形态入仓。
- ❌ 不做自动 commit（retire 后入仓的提交由用户/正常 git 流程做，不在本特性自动化）。
- ❌ 不强制其它项目采用此策略——sdlc-pilot 自己采用 + 文档化为**推荐约定**，各项目自选。

## 3. 现状摘要（Explore 产出）

- **代码**：`.gitignore` 第 1 行 `.sdlc/` 忽略全部；第 8-11 行另忽略 web-review 的运行时 json。
- **文档**：上特性（0.10.0 退场闭环）spec §2 已定调"raw archive 体积大不入 git、蒸馏后才 track"——但用户本次明确升级为 **archive 也 track**（要完整历史可 clone）。
- **现实数据**：退场 dogfood 已产 `.sdlc/archive/2026-06-16-feature-retirement/`（+ 2026-06-15-sdlc-backlog/）+ `.sdlc/EVOLUTION.md`——本特性落地后它们即成首批被 track 的内容。
- **测试**：纯 gitignore + 文档；靠 `git check-ignore` 实测 + `validate-skills` + 人工核对。

## 4. 方案与决策

**采纳（用户选 option B）：track 蒸馏 + 历史归档。**

纳入 git：`.sdlc/archive/`（已退场特性的完整工件快照）+ `.sdlc/EVOLUTION.md`（蒸馏教训）+ `.sdlc/PROFILE.md`（若存在，项目记忆 + Evolution log）。
保持本地：顶层在飞工作态 `spec.md / plan.md / STATE.md / validate/ / review/`（含 web-review 运行时 json）。

**模型**：`.sdlc/` 的生命周期二分 —— **在飞工作态（本地、churn）** vs **已完成/已蒸馏（入仓、持久）**。退场（Retire op）正是把前者转成后者的那道闸：工件从顶层 move 进 `archive/` 的瞬间，从"被忽略"变成"被 track"。

**gitignore 改法**（关键机制）：
```gitignore
# 旧： .sdlc/
# 新：忽略 .sdlc 内容，但放行已完成/已蒸馏产物
.sdlc/*
!.sdlc/archive/
!.sdlc/EVOLUTION.md
!.sdlc/PROFILE.md
```
（`.sdlc/*` 忽略目录**内容**而非目录本身，才能用 `!` 反忽略子项；web-review 运行时 json 的忽略行保留。）

### 被否方案
- **option A（只 track 蒸馏，archive 本地）**：git 历史最干净，但用户要完整可 clone 历史 → 否决。
- **option C（仅文档约定不改自身）**：sdlc-pilot 自身仍不持久 → 否决。

### 4.1 Evolution log 独立化（目标 2 的决策）
- **`EVOLUTION.md` 为唯一正屋**（不管项目有无 PROFILE）：append-only 演进流水。
- **PROFILE 模板的 `## Evolution log` 节 → 降级为一行指针**：`> 演进史（append-only）见同目录 EVOLUTION.md`。
- **退场回流逻辑简化**：`backlog.py` 的 `_append_evolution` 不再分"有无 PROFILE 两条路"，**永远 append `<sdlc>/EVOLUTION.md`**；retire 的 `--profile` 参数从回流职责中移除（0.10.0 刚引入、无外部依赖，可安全简化）。
- 被否："Evolution log 留在 PROFILE 一节"——会随特性无界增长撑爆每会话整篇加载的 PROFILE（次优，本特性纠正之）；"把 PROFILE 六节也拆子文档"——六节有界，拆了碎片化，违反 KISS/YAGNI。

### 范围姿态：HOLD —— 做 gitignore 策略 + Evolution log 独立化 + 约定文档 + 提交首批已 track 内容；不自动化 commit、不碰其它项目、不拆 PROFILE 其余节。

## 5. 设计

### 5.1 gitignore（机械核心）
按 §4 改 `.gitignore`：`.sdlc/` → `.sdlc/*` + 三条 `!` 反忽略（archive / EVOLUTION.md / PROFILE.md），保留 web-review json 忽略行。验证：`git check-ignore .sdlc/spec.md`（应忽略）、`git check-ignore .sdlc/archive/x`（应**不**忽略，exit 1）、`.sdlc/EVOLUTION.md`（不忽略）。

### 5.2 约定文档（让别人懂这个二分）
- **CLAUDE.md**：在"路径约定"或"怎么迭代"加一句 `.sdlc` track 策略——在飞工作态本地、archive/EVOLUTION/PROFILE 入仓；附**隐私提醒**：track 前确认 spec/plan/review 无密钥（决策日志可能含敏感配置位置）。
- **backlog Retire op 文档（SKILL §5）**：补一句"归档后 `archive/<feat>/` 即成被 track 内容，提交它把完成特性的工件 + 教训持久化"。
- **README**：在 backlog/退场相关处点一句 track 策略（一行）。

### 5.2b Evolution log 独立化（目标 2 落地）
- **`backlog.py`**：`_append_evolution` 简化为 `(_append_evolution(sdlc_dir, entry)`——只 append `<sdlc>/EVOLUTION.md`（缺则建 `# Evolution log` 头）；删 profile-section 分支。`cmd_retire` 不再传/收 `--profile`（main 子parser 去掉该参数）。
- **`scripts/test_backlog.py`**：`test_backflow_to_profile_section`（写 PROFILE 节）**改为** `test_backflow_always_evolution_md`（有无 PROFILE 都写 EVOLUTION.md）；保留 `test_backflow_fallback_evolution_md` 语义并入。
- **PROFILE 模板**：把 `## Evolution log` 整节（含注释）替换为一行指针 `> 演进史（append-only，退场回流）见同目录 EVOLUTION.md`。
- **backlog SKILL §5 Retire op**：回流步描述从"PROFILE 段 / 兜底 EVOLUTION.md"改为"统一写 EVOLUTION.md"。
- 验证：retire 跑完只在 `EVOLUTION.md` 出现条目，PROFILE（若有）不被追加。

### 5.3 普适建议 vs 自身采用
sdlc-pilot 自己改 `.gitignore` 即采用；文档把它写成**推荐约定**（"项目可自选是否 track archive/EVOLUTION，默认建议 track 蒸馏产物"），不替其它项目强制。

### 5.4 dogfood：提交首批已 track 内容
落地后，现有 `.sdlc/archive/{2026-06-15-sdlc-backlog, 2026-06-16-feature-retirement}/` + `.sdlc/EVOLUTION.md` 会从 ignored 变 tracked → 本特性收尾时 `git add` 并提交，作为"历史归档入仓"的首个真实实例。

## 6. 怎么算 done（前置验收）

- [ ] `.gitignore` 改后：`git check-ignore .sdlc/spec.md` 命中（忽略在飞态）；`git check-ignore .sdlc/archive/2026-06-16-feature-retirement/spec.md` exit 1（**不**忽略）；`.sdlc/EVOLUTION.md`、`.sdlc/PROFILE.md` 不忽略。
- [ ] `git status` 能看到 `.sdlc/archive/` + `.sdlc/EVOLUTION.md` 为可提交（untracked/tracked），而顶层 `spec.md/plan.md/STATE.md` 仍被忽略。
- [ ] CLAUDE.md / README / backlog SKILL §5 文档化 track 策略 + 隐私提醒。
- [ ] `bash scripts/validate-skills` PASS（文档改动未断引用）。
- [ ] dogfood：首批 archive + EVOLUTION.md 已 `git add` 进暂存（收尾提交）。
- [ ] **Evolution log 独立化**：`backlog.py retire`（不带 `--profile`）跑完，条目只进 `EVOLUTION.md`；`test_backlog.py` 改后用例全绿（`_append_evolution` 单路径）；PROFILE 模板 `## Evolution log` 节已换成一行指针；backlog SKILL §5 回流描述已更新。
- 验证命令：`git check-ignore -v <path>` / `git status --short .sdlc/` / `python3 scripts/test_backlog.py` / `bash scripts/validate-skills`。

## 7. Eval 契约
N/A（非 AI 工作）。

## 7b. 设计契约
N/A（非 UI 工作）。

## 8. Deferred Ideas
- **archive 体积管理 / 老归档清理或压缩**。Why：track archive 后仓会随特性数线性增长。Trigger：archive 占比显著或 clone 变慢时。Breadcrumbs：本 spec §4、retire op。
- **per-project track 策略可配置**（如 `.sdlc/config` 声明 track 哪些）。Why：不同项目对入仓粒度偏好不同。Trigger：出现第二种明确诉求时。Breadcrumbs：§5.3。
- **★EVOLUTION 条目对应到需求树叶子（用户指定）**：做 backlog 相关特性时，把 `EVOLUTION.md` 里每条演进记录**关联到它所属的需求树叶子节点**（`.sdlc/requirements/<...>/<leaf>.md`），使"这片需求当初为什么这么做/踩了什么坑"沉到叶子内，需求树成为带演进史的活档案。Why：EVOLUTION.md 是扁平流水，按叶子归位后可在需求维度回看演进。Trigger：下次做 backlog 相关特性（如 #4 review 看板，或叶生命周期 #1）时一并接入。Breadcrumbs：本特性 EVOLUTION.md、backlog 叶 schema（SKILL §1.2）、Retire op `source-leaf`（标 shipped 时已知叶 id，可顺带把 evolution 条目挂叶）。

## 9. Canonical refs
- `.gitignore`（第 1 行 `.sdlc/`；8-11 行 web-review json）
- `.sdlc/archive/`（退场产出，本特性的 track 对象）、`.sdlc/EVOLUTION.md`
- `skills/sdlc-backlog/SKILL.md` §5 Retire op（退场把工件转入 archive/）
- `CLAUDE.md`（路径约定 / 怎么迭代 / 铁律）、`README.md`
- 上特性 spec：`.sdlc/archive/2026-06-16-feature-retirement/spec.md` §2（原"archive 不入 git"定调，本特性升级之）
