# Spec: 需求树生命周期状态同步 + 看板可视化重构

> Date: 2026-06-23
> Status: draft
> Target surface(s): scripts-core（枚举/lint/set-status）+ board-render（看板）+ skill-prose（driver §1.1 + onboard 脚手架）+ tooling（post-checkout hook）
> Active roles (anticipated): skill-maintainer, qa, design
> Validate modes (anticipated): correctness（+ dogfood 看板人工看效果）
> 版本：本特性发布为 0.16.0（基线已含 0.15.0 Codex runtime adapter）

## 1. 问题 / 目标

需求树叶的 `status` 字段记录"走到 SDLC 哪一步"（captured→spec'd→planned→built→validated→shipped），但当前**只在两处被写**：① 生成器创建叶时按代码完整度猜一个 draft 初值；② Retire 退场时标 shipped。**中间态 spec'd/planned/built/validated 从来没人写**，导致看板"进度"长期失真（叶停在 captured 或 draft）。同时该 `status` 字段**无权威枚举定义、lint 不校验**（`status: banana` 能过 lint）。看板本身也存在 4 个可读性痛点。

目标：
- **(A 数据层) 让状态可信**：建权威枚举 + lint 校验 + 提供机械写 op + 让 SDLC 流程的进行时状态可靠地反映到看板，且**切分支/挂起特性时不丢**。
- **(B 展示层) 看板重构**：解决状态/进度不直观、树难导航、叶详情难读、聊天面板定位不清 4 个痛点。

## 2. 非目标（YAGNI）

- 不做状态机**合法迁移校验**（用户定：allow-any-set；set-status/lint 只校验取值∈枚举，不挡跳迁/回退）。
- 不把中间过渡态写进叶的历史流水（过渡态本质短命，只需反映"当前在飞谁"）。
- 不新增顶层 skill（铁律①）；不动 spec/plan/build/validate 4 个 stage skill 的 SKILL.md 加逐阶段回写（这正是选 C 而非 A 的目的——避开 L4 blast）。
- 看板不重写后端协议：复用现有 web-review `server.py` 的 Live mode（0.12.0），纯增强前端渲染。
- 不解决 worktree 间共享需求树的更大议题（gitignored 各自一份，超本特性范围）。

## 3. 现状摘要（Explore 产出）

- **代码**：`scripts/backlog.py`（739 行单体，逼近 800 行铁律）。`_set_frontmatter_status`(:516) 已是通用"改叶 status 首行"原语；`_mark_leaf_shipped`(:525) 是其 shipped 封装。`cmd_lint`(:475) 线性 problems 累加，已校验 failure_class/contract_refs/depends_on/orphan/dup，**未校验 status**。状态色 CSS 类散在 `render_board`(:194-199)，`SHIPPED`(:31) 是唯一 status 常量。看板聊天 JS 在 `CHAT_JS`(:255)，叶详情 `renderDetail`/`innerHTML`(:266-287)。
- **状态文件**：`.sdlc/STATE.md` **gitignored**（不随 git checkout 切换，一个工作目录一份，单特性、短命，带 branch/worktree/source-leaf/stage 字段）。`.sdlc/requirements/` 也 gitignored。
- **守卫**：`sdlc-guard`（pre-commit 硬层 + driver §1.1 软层）只**只读检测** branch/worktree 是否串台并 exit 1/0，**从不写**。装钩子在 onboard Phase D 脚手架自检。
- **测试**：`scripts/test_backlog.py`（514 行单测）+ `bash scripts/validate-skills`（skill 体检）。无覆盖率/类型门控。

## 4. 方案与决策

### 核心决策：C 混合 + 边界 flush（写回机制）

三方案（A 急切逐阶段回写 / B 纯惰性派生 / C 混合）中选 **C**：
- **稳态（captured/shipped）落盘持久**：captured 由生成器/Ingest 写（已有）；shipped 由 Retire 写（已有）。
- **过渡态（spec'd→validated）惰性派生**：看板渲染时读 `.sdlc/STATE.md`，对 `source-leaf` 匹配的叶**叠加显示**当前在飞 stage 映射的状态（live badge），**不写文件**。
- **边界 flush 兜底不丢**：离开/挂起特性那一刻，把当前过渡态固化进叶文件。

理由：一片叶的 built/validated 只是它 ship 前一瞬的过渡态，不值得持久化到 frontmatter 历史；captured/shipped 两个稳态值得落盘。C 把 blast radius 从 A 的 L4（碰 5 个 skill）压到 ~L2（driver §1.1 + backlog.py + 1 个 hook），且天然化解 draft-vs-lifecycle 冲突（在飞时 STATE 实时盖过 draft；flush 时 lifecycle 值**权威覆盖** draft——一旦真实 SDLC 流程跑过这片叶，stage 就是真相，超越生成器的猜测）。

被否：纯 A（blast 大、draft 冲突难处理）；纯 B（shipped 不落盘，与现有 Retire 冲突，且 STATE 被覆盖即丢）。

### 强制保证：flush check 一定会 run（三件套，硬+软两层）

用户要求"保证切分支/worktree 时回写一定跑"，不接受纯 driver best-effort。复用 sdlc-guard 的"软硬两层"模式：

1. **硬层 — `post-checkout` git 钩子**（git 强制，切分支必跑，模型/人绕不过，唯一逃逸 = 删钩子）。随 onboard 脚手架装第三个钩子（与 pre-commit/pre-push 并列）。
2. **软层 — driver §1.1 入口 reconcile**（每次用 sdlc 必跑）：对账 source-leaf 叶 status 与 STATE.stage 映射值，落后则补齐（最终一致）。兜住 Codex 无钩子/worktree/非 driver 覆盖。
3. **共享原语 — `backlog.py set-status` op**（确定性机械写，复用 `_set_frontmatter_status`）：两层都调它，单一事实源。

逃逸路径覆盖矩阵：

| 路径 | 覆盖 | 强度 |
|------|------|------|
| 同工作目录切分支 | post-checkout 钩子 | **git 硬保证** |
| 不经 driver 覆盖 STATE / Codex 无钩子 | driver §1.1 reconcile | 用 sdlc 必跑 |
| worktree 间 cd | 隔离不丢 + 回去 reconcile | 最终一致（无即时钩子，已知情接受） |
| 永久弃坑再不碰 sdlc | 叶停在最后 flush 值 | 可接受 |

### scope：一个 spec，plan 分波（0.16.0）

A（数据层）+ B（看板）合为一个特性，plan 拆 wave1=数据层（枚举/lint/set-status/钩子/driver reconcile）→ wave2=看板（4 痛点 + 惰性叠加渲染）。共享 STATUS_ORDER 枚举地基。

## 5. 设计

### 5.1 数据层（scripts-core）

**STATUS_ORDER 权威枚举**（backlog.py 顶部常量，单一事实源）：
```
STATUS_ORDER = ["captured", "spec'd", "planned", "built", "validated", "shipped"]
STATUS_SET = set(STATUS_ORDER)
STAGE_TO_STATUS = {"spec": "spec'd", "plan": "planned", "build": "built",
                   "validate": "validated", "review": "validated", "ship": "shipped"}
```
（`SHIPPED` 常量保留兼容；CSS 类、SKILL §2.7 散文改为引用此枚举概念。`spec'd` 的 CSS 安全片段沿用现有 `_status_class` 的 `spec'd→specd` 规整。）

**lint 加 bad-status 校验**（cmd_lint 循环内）：
```
status = lf.get("status")
if status and status not in STATUS_SET:
    problems.append(f"bad-status: {lid} status='{status}' 不在 {STATUS_ORDER}")
```
（与 failure_class 校验同形；status 是 REQUIRED_FIELD，缺失已被 missing-field 抓，这里补"取值非法"。）

**`set-status` op**（新子命令，机械写）：
```
backlog.py set-status --root <req-root> --leaf <id> --to <status>
  - 校验 <status> ∈ STATUS_SET（allow-any 迁移，不查 ORDER 合法性）
  - 找到 <id> 的叶 → _set_frontmatter_status(path, status) → 返回 path / exit 0
  - 叶不存在 → exit 2；status 非法 → exit 1（均不写）
```

### 5.2 写回编排（skill-prose + tooling）

**post-checkout 钩子**（`references/templates/hooks/post-checkout`，onboard 脚手架装）：
```sh
# git 传入 $1=prev_HEAD $2=new_HEAD $3=branch_flag
[ "$3" = "1" ] || exit 0          # 只在真切分支时动作(非切文件)
STATE=.sdlc/STATE.md; [ -f "$STATE" ] || exit 0
读 STATE: source-leaf / stage / branch
[ source-leaf != "(none)" ] || exit 0
映射 status = STAGE_TO_STATUS[stage]（非过渡 stage 跳过）
backlog.py set-status --root .sdlc/requirements --leaf <source-leaf> --to <status>  # flush 落盘
exit 0   # 永不阻断 checkout（flush 失败只警告）
```
> flush 用 STATE 当前内容（gitignored，切分支后原地不动），把"离开前的 stage"固化进叶。非阻断（与 pre-commit/pre-push 不同——checkout 不该被拦）。

**driver §1.1 reconcile**（SKILL 加规程）：边界自检里加一步——读 STATE.source-leaf 那片叶当前 status，若其 ORDER 序 < STAGE_TO_STATUS[STATE.stage] 的序 → 调 set-status 补齐（只前进不回退；lifecycle 权威）。可移植：纯调 backlog.py，无并行依赖。

**onboard Phase D 脚手架**（SKILL 加一条）：装 hook 询问从 2 个扩到 3 个（+post-checkout，说明它管"切分支自动 flush 叶状态"）。

### 5.3 看板重构（board-render，惰性叠加 + 4 痛点）

**惰性叠加渲染**（cmd_board / render_board）：board 命令额外读 `<root>/../STATE.md`（若存在），解析 source-leaf+stage；render 时对该叶以 STAGE_TO_STATUS 映射值**叠加 live badge**（如"⏳ build 中"高亮），文件 status 作底。STATE 不存在/无 source-leaf → 纯渲染文件 status（向后兼容）。

**4 痛点**：
- **①状态/进度**：顶部**图例**（6 状态色块+中文含义）；每域 + 全树**进度分布条**（按 STATUS_ORDER 分段，已有 `shipped/total` 升级为全状态分布）；**状态过滤**（点图例筛选/高亮某状态的叶）。
- **②树导航**：顶部**搜索框**（按 id/title 即时过滤树）；**折叠记忆**（localStorage 存折叠态，刷新不丢）；选中叶显示**面包屑**（domain › subdomain › leaf）。
- **③叶详情**：10+ 字段**分组**（身份组 id/title/status/priority｜定位组 domain_path/old_system_ref/new_domain_path｜关系组 depends_on/cross_link｜交叉组 actor/failure_class/contract_refs/data_owner/risk_level）；`depends_on` 渲染成**可点链接**（点击选中并滚动到目标叶）；字段名带 **tooltip 说明**（actor/failure_class 等含义）。
- **④聊天面板**：顶部**状态提示**（"🟢 Live 监听中 / ⚪ 未监听——需 agent 切 live"）；空态**引导文案**（何时能用、怎么让 agent 切 live）。

### 5.4 错误处理

- set-status：叶不存在/status 非法 → 非 0 退出 + stderr 明确信息，不写文件。
- post-checkout flush 失败（叶不存在/树缺失）→ 警告到 stderr，**exit 0 不阻断 checkout**。
- 看板读 STATE 失败/STATE 缺失 → 静默降级为纯文件 status 渲染（向后兼容）。
- 看板 JS innerHTML：叶字段来自受控树文件，新增 live badge/search 不引入用户可控内容；depends_on 链接用 id 白名单（只在已知叶 id 集合内跳转）。

### 5.5 测试策略

- **数据层走 TDD**（确定性）：STATUS_SET/STAGE_TO_STATUS 常量、lint bad-status（正/负路径）、set-status（成功/叶不存在/status 非法/allow-any 迁移如 validated→spec'd 不报错）。
- **写回编排**：set-status 单测覆盖；post-checkout 钩子逻辑 + driver reconcile 是 playbook/脚本，靠 dogfood 验（切分支后看叶 status 落盘 + 看板叠加）。
- **看板渲染**：correctness（render_board 产物含图例/进度条/分组/惰性 badge 的 HTML 断言）+ 人工看效果（起服浏览 examples/requirements-fixture 或 dogfood 树）。

## 6. 怎么算 done（前置验收）

- `python3 scripts/test_backlog.py` 全绿（含新增 STATUS/lint-bad-status/set-status 用例）+ `bash scripts/validate-skills` PASS。
- lint 能拒非法 status（`status: banana` → bad-status，exit 1）。
- set-status 能机械改叶 status；allow-any 迁移不报错；叶不存在/非法值正确拒绝。
- post-checkout 钩子装上后，切分支真的把当前 STATE.source-leaf 叶 status flush 落盘（dogfood 验：起特性→build→切分支→叶文件 status=built）。
- driver §1.1 reconcile：入口对账把落后的叶 status 补齐。
- 看板：图例 + 进度分布条 + 状态过滤 + 搜索 + 折叠记忆 + 面包屑 + 字段分组 + depends_on 可点 + 字段 tooltip + 聊天状态提示，且对在飞特性叠加 live badge；无 STATE 时向后兼容纯渲染。
- DESIGN.md 增补状态色板 + 进度条 + 字段分组规范。

## 7. Eval 契约
N/A（非 AI/模型/策略工作；看板渲染与脚本逻辑均确定性）。

## 7b. 设计契约
触及 UI（看板）→ active roles 含 design → 更新 `<repo>/DESIGN.md`（已有暖奶油/鼠尾草绿契约）。本次增补：**6 状态语义色板**（captured 米灰 / spec'd 蓝 / planned 黄 / built 橙 / validated 浅绿 / shipped 绿底白字，对比 ≥WCAG AA）+ **进度分布条**组件规范（按 STATUS_ORDER 分段着色）+ **叶详情字段分组**规范（4 组 + tooltip）+ **live badge**（在飞态高亮，动效只动 opacity/transform）。详见 DESIGN.md 本次新增节。

## 8. Deferred Ideas

- **worktree 间共享需求树**：当前 gitignored 各 worktree 一份，跨 worktree leaf 写回不互见。Why：worktree-per-feature 并发模型下，多特性各自树会分叉。Trigger：真出现多 worktree 并发改同一棵树。Breadcrumbs：.gitignore `.sdlc/requirements/` 这行；本 spec §2 非目标。
- **状态机合法迁移校验**：本次用户选 allow-any-set。Why：防误操作回退/跳迁。Trigger：出现状态被错误回退的实际事故。Breadcrumbs：STATUS_ORDER 已就绪，加 transition 检查即可。
- **看板状态过滤 → 持久化到 URL/localStorage**：本次先做内存态过滤。Trigger：用户要分享筛选视图。
- **搜索收起空父节点 + 面包屑各级可点回跳**（review LOW-03/04）：本次搜索只隐藏叶不收空 details；面包屑显示定位但各级未做成 <a> 回跳。Why：纯 UX 增强，核心价值（隐藏不匹配叶 / 显示定位）已达成。Trigger：用户反馈树太深需要这些。Breadcrumbs：board.py CHAT_JS 的 search input 监听 + setCrumb。

## 9. Canonical refs

- `scripts/backlog.py`（:31 SHIPPED / :194-199 状态 CSS / :255 CHAT_JS / :266-287 renderDetail / :475 cmd_lint / :516 _set_frontmatter_status / :525 _mark_leaf_shipped / :695 main op 注册）
- `scripts/test_backlog.py`（单测）
- `skills/sdlc/scripts/sdlc-guard`（软硬两层模式参照）
- `skills/sdlc/references/templates/hooks/{pre-commit,pre-push}`（钩子模板参照）
- `skills/sdlc/SKILL.md` §1.1（边界自检，加 reconcile）/ §2 退场前置
- `skills/sdlc-onboard/SKILL.md` Phase D 步 5（脚手架装钩子）
- `skills/sdlc/references/templates/STATE.md`（source-leaf/stage/branch 字段）
- `.sdlc/PROFILE.md`（surface-map）/ `DESIGN.md`（设计契约）
- `examples/requirements-fixture/`（看板验证 fixture）
