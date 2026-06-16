# SDLC State: sdlc-backlog（需求树 / backlog，子系统 A）

stage: done
status: done
updated: 2026-06-15
work-type: feature
branch: feat/sdlc-backlog
worktree: (none)
validate-modes: [correctness]
plugin-version-base: 0.8.1   # 已升 → 0.9.0
sdlc-gate: PASS reviewed-head=ae809a8eb670d74ca746752d69bd99deba2e98e9

## Gates passed
- [x] spec：spec.md 已获批（含对抗性证伪 R1-R4；Eval/Design 契约 N/A）
- [x] plan：plan.md 已拆分（L3；4 phase / 3 wave；含三必填字段；Source Audit 全 COVERED）
- [x] build：P1-P4 全完成（4 commit）；TDD red→green（test_backlog.py 5 用例）；validate-skills PASS；smoke 全链通过
- [x] validate：correctness PASS（validate-skills + test_backlog.py 5/5 + smoke + 无偷改实现）；e2e/eval-bench 不 active。报告 .sdlc/validate/correctness-report.md
- [ ] review：skill-maintainer 透镜（防臃肿/additive/可移植/溯源/枚举 4 处同步）
- [ ] ship：升 minor 0.9.0 + CHANGELOG + commit/push

## Active roles (from last diff scan)
- skill-maintainer（改动落在技能体系自身：新 skill + 契约同步）

## Changed-files snapshot
- (none yet — target surface: skill-system-self；预期新增 skills/sdlc-backlog/ + 改 role-routing / STATE 模板 / onboard / driver 枚举 / plugin.json / marketplace.json / CHANGELOG)

## Decisions log
- 2026-06-15 从 /sdlc evolve 升到完整 /sdlc：本特性是结构性改动（新建 skill + 改 stage 枚举），超出 evolve append-only 轻量路。
- 2026-06-15 范围 = A + B 都要，但顺序两个 spec（A 先，B 后）；A 是 B 前置，不做 mega-spec。
- 2026-06-15 落点 = 混合：机制进 sdlc-pilot（commit GitHub），数据留目标项目 .sdlc/requirements/（类比 kb-manage）。
- 2026-06-15 机制形态 = 新 skill sdlc-backlog 作 pre-spec 新阶段；否决"扩 spec/onboard"与"references 卡"（scope/体量不符）。
- 2026-06-15 树存储 = 文件系统递归镜像（复用 kb-manage）；ready-queue 为 A/B 唯一契约。
- 2026-06-15 pull origin/main ff 到 0.8.1（deploy-aliyun 蒸馏 + PR#1）；未碰契约文件，spec 不受影响。
- 2026-06-15 复杂度定 L3：触及 stage 枚举 + driver 分叉契约，需独立 review + 回归既有分叉。
- 2026-06-15 规划期细化：backlog 作项目级 stage（同 onboard）；spec §5.6 role-routing 同步基本已被 R10 覆盖，仅加 §5 breadcrumb；契约同步实际比 spec 设想更小。
- 2026-06-15 build 在 feat/sdlc-backlog 分支：4 commit（cbee73a/de845c8/a1708c3/d3522b3）。
- 2026-06-15 build 时细化 ready-queue 规则：ready ⟺ 自身未 shipped 且 deps 全 shipped（spec/SKILL §1.3 原仅说 deps 全 shipped，TDD 补全自身未 shipped 条件）。已同步 SKILL §1.3。
- 2026-06-15 plan 缺口于 build 补：新增流程 skill 的"计数 7→8"同步（plugin/marketplace/CLAUDE/README/skill-maintainer）未列为 plan 任务，build P4 补齐并守 CLAUDE 铁律#1 carve-out。
- 2026-06-15 P4-T2 .agents symlink = N/A（本仓无 .agents/skills 约定，Codex 经 skills/ 直接发现）。
- 2026-06-15 版本 0.8.1→0.9.0（minor：加 backlog 能力）；CHANGELOG 0.9.0 已写。commit/push 留 ship。

## Changed-files snapshot
- 新增：skills/sdlc-backlog/SKILL.md、scripts/backlog.py、scripts/test_backlog.py
- 改契约：skills/sdlc/SKILL.md、skills/sdlc/references/templates/STATE.md、skills/sdlc/references/role-routing.md、skills/sdlc-onboard/SKILL.md、skills/sdlc/references/roles/skill-maintainer.md、skills/sdlc-ship/SKILL.md
- 改元数据：.claude-plugin/{plugin,marketplace}.json、CLAUDE.md、README.md、CHANGELOG.md

## Next action
-> invoke sdlc-review（skill-maintainer 透镜：防臃肿/additive/防孤儿/溯源/枚举一致/可移植/semver + 对抗 pass）
