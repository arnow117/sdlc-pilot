# Changelog

遵循语义化版本。格式参考 Keep a Changelog。

## [0.18.0] — 2026-06-26

### Added
- **`scripts/contrast_check.py` —— 静态 WCAG 对比度校验 DESIGN.md（纯 stdlib，无第三方依赖）**（完整 `/sdlc` dogfood：spec→plan→build(TDD)→validate→review→ship；改进 2，承接 0.17.1 的 design.md 哲学注入）：
  - **把 design 角色卡的颜色对比度检查从 B 腿 `[render]`（需浏览器）降为 A 腿 `[diff]`（静态解析）**。解析 DESIGN.md 的 `:root{}` CSS 变量 + markdown 表格语义色 → 启发式跨类配对（fg/either × bg，可被 `<!-- contrast: ink on bg -->` 注释覆盖收窄）→ WCAG 2.1 相对亮度算对比度 → 标 < AA 4.5:1 的组合。
  - **定位 = 确定性 advisory（info/warning），非强制必要条件**：默认 exit 0；`--strict` 才在低对比时 exit 1。不打乱 design 卡"以 DESIGN.md 为准、无则退回通用原则"的二值语义。
  - **诚实门**：oklch/lab/hsl 等 stdlib 无法精确转 sRGB 的色彩空间，跳过并标 `skipped: unsupported-color-space`，不假装算过。
  - 接入 `design` 角色卡检查清单 A + validate-mode playbook A 腿（防孤儿）；配套 `scripts/test_contrast_check.py`（28 用例：算法/配对/解析/负路径/CLI 全绿）。
  - **复审依据**：经 doubt-driven 复审否决官方 `@google/design.md` CLI（alpha 格式 + node_modules 供应链不入放行路径；官方 lint 对本族「散文 + `:root` CSS 变量」DESIGN.md 覆盖=0、对比度规则只看 `components.{bg,text}` 配对看不见我们的语义色）。自研脚本确定性、可离线、覆盖真实数据结构。

## [0.17.1] — 2026-06-26

### Changed
- **DESIGN.md 撰写纪律：注入两条设计哲学**（蒸馏自 google-labs/design.md PHILOSOPHY，调研 + doubt-driven 复审后落地；append-only 小改走 `/sdlc evolve`）：
  - `sdlc-spec §2.6b` + `design` 角色卡 spec 介入行新增 **"具体参照物 > 形容词堆砌"**（用"1970 年代研究生讲义"式具体参照物锚定风格，胜过"modern/clean/premium"——参照物描述一个点、形容词描述一个区域，负约束随参照物自带）与 **"散文为主、token 为辅"**（token 是校准 context 不是渲染指令）。与既有"禁 clean minimal 空话"+ §2 gray-area 具体化同源、互相强化。
  - **未**引入官方 `@google/design.md` CLI（复审证据：alpha 格式 + node_modules 供应链不宜绑入放行路径；官方 lint 对本族 DESIGN.md「纯散文 + `:root` CSS 变量」结构覆盖=0）。自研轻量 WCAG 对比度校验作为独立结构性改动，走完整 `/sdlc`，不在本次。

## [0.17.0] — 2026-06-26

### Added
- **`references/build-loop.md` + driver `/sdlc loop` 子命令 —— 测试驱动的自治特性循环(子系统 B)**(完整 `/sdlc` dogfood 落地;设计 `docs/specs/2026-06-26-sdlc-loop-design.md`)。兑现 `sdlc-backlog` 早标注的"ready-queue → 喂给未来的 sdlc-loop":
  - **形态**:meta 子命令(同 evolve/next,**不新增 skill、不进 STATE 枚举、零契约改动**),只**编排**既有 8 阶段,不重写任一阶段纪律。
  - **主循环**:从 ready-queue(`backlog.py readyqueue`)取就绪叶 → 逐叶跑 spec→plan→build(RGR)→validate→review→ship → Retire 退场 → 取下一片,直到队列干。**内核 TDD**:测试=ground truth(Anthropic building-effective-agents)。
  - **converge oracle(本特性新增核心)**:阶段间判"该叶**真做完没**"=测试全绿 + 满足 spec Done Criteria + review PASS;没做完把缺口 append 回 build,不误判完成。空队列=全局收敛 done。
  - **不绕硬门**(review / 安全 open=0 / 覆盖率照旧)、**串行取叶**(单写 STATE 防竞态)、**可恢复**(状态全在 STATE + 叶 status + 任务 `[X]`,崩了重进续接)、**停止条件**(队列干 / max-iter / blocker / 漂移)、**可移植**(text_mode + 纯文件,Codex 也能跑)。
  - `build-loop.md` **§E 已蒸馏 5 条权威 agent-loop 先进思路**(经 6 次 `/sdlc evolve` 式 append-only 提交逐条落地,每条 `distilled-from` 溯源):**E1** 每圈复述 Done Criteria(Manus context-engineering)· **E2** 失败先写教训下轮先读(Reflexion)· **E3** converge 自生成边界测试强化 oracle(AlphaCodium flow-engineering)· **E4** 可选外脑交叉验证(evaluator-optimizer,**写成原则非代码**,机会型调 Codex/claude 只读复核,永不卡 loop)· **E5** 停止+ground-truth 收紧(Anthropic)。
- 纯 additive + 一新 playbook;driver/CLAUDE/README 引用无孤儿;`validate-skills` PASS;经 Codex 只读外脑两轮评审(v1 修 6 项 + 终审)。

## [0.16.2] — 2026-06-24

### Added
- **`collaboration-discipline.md` §5.4 监督式多-agent build loop**（dogfood 实战蒸馏 `session:portal-auth-multiagent-loop-2026-06-24`，跨两仓统一认证集成）——把 §5 的并行协作纪律强化到"**后台/自治 agent 中途问不了人**"的形态，additive 补两条 + 一道闸：
  - **loop 形状**：串行冻决策+冻契约（人在环，对抗式审）→ 并行后台 build agent（每 track 一 worktree、各自绿）→ 主循环跑一次集成 SDLC 收敛；**不是"撒 N 个 agent 各跑完整 SDLC"**。
  - **前置再收紧（补 §5.1）**：自治 agent 无人工通道 → 冻死的不只是接口契约、而是**所有会让 agent 现场拍板的决策**；简报必含"契约/边界外受阻→停下回报，不要猜"（把"猜"改成"停"）；真栈并行 agent 各自自举隔离环境。
  - **收敛再加闸（补 §5.3）**：★**冻结的契约只保证"形状"不保证"解读"**——并行 track 对同一边界的解读漂移（路径 normalize/字段顺序/canonical 串/空 body hash）**per-track 单测看不见**（各测各的假设全绿、整链路 100% 401 flow-dead）；故必过一道**跨 track 集成闸**（独立评审者喂两端真实接线、或穿缝 e2e），且对抗式迭代到收敛。
- 纯 additive 内容补充（只动既有卡 + 溯源 frontmatter）；`validate-skills` PASS。

## [0.16.1] — 2026-06-23

### Fixed
- **pre-push hook 误拦合法的退场+合并收尾**（0.16.0 dogfood 实测发现）：`references/templates/hooks/pre-push` 两处把正常 SDLC 收尾误判为"没走流程/评审后改代码"——
  - **无 STATE.md**（retire 清栈后的合法状态）原直接拦截 → 现先看 `.sdlc/archive/` 是否非空（有退场记录=走过 SDLC）→ 放行；archive 也空才判"从没走 SDLC"拦。
  - **HEAD 移过 `reviewed-head`**（retire 归档提交 + merge 必然推进 HEAD）原判"评审后又改代码" → 现看 `reviewed-head..HEAD` 间**非 `.sdlc/` 的代码**是否真有改动（`git diff -- . ':(exclude).sdlc'`），仅 .sdlc bookkeeping 变动 → 放行；真改了代码才拦（并列出改了哪些）。
- dogfood 6 场景验证（退场态/从没跑/仅.sdlc变/评审后改码/正常/gate BLOCK）放行与拦截两路径均正确。纯 sh，硬门性质不变。

## [0.16.0] — 2026-06-23

### Added
- **需求树叶生命周期状态同步（C 混合写回 + 三件套强制保证）**：
  - `backlog.py` 加 **STATUS_ORDER / STATUS_SET / STAGE_TO_STATUS** 权威枚举（单一事实源；CSS/SKILL/钩子/reconcile 都引此）。
  - `backlog.py lint` 加 **bad-status** 校验（`status` 取值须 ∈ 枚举；`status: banana` 这类现在会被拒）。
  - `backlog.py set-status` 新 op：机械改叶 status（**allow-any 迁移**，只校验值合法不查迁移；叶不存在/非法值正确拒绝）——写回三件套的共享原语。
  - **post-checkout git 钩子**（`references/templates/hooks/post-checkout`）：切分支时把在飞特性源叶 status flush 落盘（C 混合·硬层，git 强制；无需求树则 no-op，永不阻断 checkout）。onboard Phase D 脚手架装钩子 2→3。
  - **driver §1.1b 源叶状态对账（reconcile）**：driver 每次入口对账 source-leaf 叶 status 与 STATE.stage 映射值，落后则补齐（软层，只前进不回退；兜住 Codex 无钩子/worktree/非 checkout 覆盖）。
- **看板可视化重构（4 痛点，DESIGN.md §8 为契约）**：①状态图例（6 色+含义+点击过滤）+ 按 STATUS_ORDER 分段的进度分布条；②搜索框（即时按 id/title）+ 折叠记忆（localStorage）+ 面包屑；③叶详情 4 组分组（身份/定位/关系/交叉）+ depends_on 可点跳转 + 字段 tooltip；④聊天面板 live 监听状态指示 + 引导文案。**在飞特性源叶叠加 live badge**（惰性派生读 STATE，不写文件；无 STATE 向后兼容）。

### Changed
- **看板渲染抽到 `scripts/board.py`**（从 `backlog.py` 抽出，守 800 行铁律；`board` 子命令惰性 import）。`backlog.py` 739→470 行，`board.py` 489 行。
- plugin / marketplace 版本升至 `0.16.0`。

### Notes
- 写回机制选 **C 混合**（稳态 captured/shipped 落盘 + 过渡态惰性派生 + 边界 flush）而非纯急切回写：blast radius 从 L4（碰 5 个 stage skill）压到 L2（driver + backlog.py + 1 钩子），不动 spec/plan/build/validate 4 个 stage skill。状态机 allow-any-set（不挡跳/退）。distilled-from: `session:sdlc-leaf-lifecycle-board-2026-06-23`。

## [0.15.0] — 2026-06-17 ~ 06-23

> 注：本版本号在两条并行开发线上各发生过一次（Codex adapter 线 06-17 未推 + 协作纪律线 06-23 已推 origin），合并时归并到同一 0.15.0 section；后续避免并行线撞版本号。

### Added
- **Codex runtime adapter**：新增 `skills/sdlc/references/runtime-adapters/codex.md`，把 SDLC 抽象接口映射到 Codex 运行时：用户选择(`text_mode`/结构化输入可选)、multi-agent fan-out、只读并行、`apply_patch` 文件编辑、headless 安全默认、web-review Live mode 单渠道纪律、Codex 内不自调 `codex`、repo-local `.agents/skills/sdlc*` discovery。
- **HANDOFF block 契约**：driver §5、STATE 模板、spec/plan/build/validate/review/ship 交接段统一为「阶段 skill 先输出 `## HANDOFF`，driver 作为 canonical writer 写 `.sdlc/STATE.md`」。独立直调阶段 skill 时也必须先产同一 HANDOFF，再作为单写者应用。
- **新增 `references/collaboration-discipline.md`(源码协作纪律)** —— 补上工具此前唯一缺的「源码协作」通用能力,**由 sdlc driver `§1.1` 跨阶段加载**(贯穿 entry→plan→build→review),`sdlc-build §0.2` 用于提交/波内执行:
  - 分支模型按意图分两类(**收敛型短命→主干** / **分叉型长命是设计**:客户定制·私有部署·LTS·上游 fork,优先配置+扩展点而非 fork);
  - 分支命名 `<type>/<summary>` + Conventional Commits;
  - **worktree 按需(不是默认)** + 开/合命令骨架;
  - **并行协作:前置合约(接口先冻/面切分/独立性/自包含简报)+ 收敛安全网(串行收敛 + 先基到最新+重测才合,防 merge skew 与语义冲突)**。

### Changed
- **build wave fan-out 前置 write-set preflight**：从 `plan.md` 读取同 wave 各 phase/task 的 `files` 集合，若有交集则不 fan-out，降级串行或回 `sdlc-plan` 修 wave；避免 plan invariant 错标时多 agent 并发写同一文件。
- `scripts/validate-skills` 将 `references/runtime-adapters/codex.md` 纳入关键共享文件检查。
- `.gitignore` 忽略 `.playwright-mcp/`(浏览器 MCP 会话产物,非源码)。
- plugin / marketplace 版本升至 `0.15.0`。

### Notes
- 结构性兼容性改动（Codex adapter + handoff interface + 协作纪律卡），按完整 SDLC/evolve 维护者透镜处理；不新增顶层 skill，不改 stage 枚举，不改 role-routing 字典。distilled-from: `session:sdlc-codex-compat-2026-06-17` · `session:collaboration-discipline-2026-06-23`。

## [0.14.0] — 2026-06-16

### Added
- **★`sdlc-backlog` `Generate` op：分析工程 codebase → 自动 gen 出带叶的需求树**（Seed 升级；已有项目→树→#4 看板→选叶起特性闭环）。判断性 agent-playbook（写进 SKILL §2.7，像 onboard 读码）+ 确定性脚本落盘。
  - **轴决策**：主轴 `domain_path` = **功能/用户故事**（PM↔业务对齐场景驱动；domain=功能域/epic，叶=用户故事「作为<角色>要<能力>以便<价值>」，禁工程术语）；叶粒度自适应（对齐状态跃迁→depends_on 无环）+ 每域上限防碎。
  - **4 可选交叉视图字段**（叶 schema 扩展，非必填，REQUIRED_FIELDS 不变，存量树仍 lint clean）：`actor`/`failure_class`(枚举 funds·consistency·compliance·experience)/`contract_refs`(list)/`data_owner`；lint 校验取值合法性。
  - **`write-tree` 脚本 op**：merged tree JSON → 叶 `.md` 文件（机械落盘，已存在跳过不覆盖人工改）。
  - **多 agent 两阶段编排**（§5.6）：orchestrator 归纳功能域 → fan-out 一域一 agent 各写草稿（隔离）→ 合并(去重/cross_link/depends_on 无环/每域上限)→ 人审预览(复用 #4 看板)→ write-tree+lint。复用 Task-or-sequential + 单写者，不引新基建。
  - **#4 看板叶详情显示 4 交叉字段**（有值即见；高级筛选/着色 Deferred）。
- 输入复用 `sdlc-onboard` 的 surface-map（无 PROFILE 先 onboard）+ 深读 contracts/模块/schema/docs。

### Notes
- 全 **additive**：未加顶层 skill（Generate 是 backlog op）、未动 stage 枚举/routing/STATE 模板；叶 schema 扩展为**可选**字段（REQUIRED 不变）。守三铁律。
- 本期 build 产脚本+playbook；**dogfood 真跑生成器于 workspace/20260615-vendor-research** 在 validate 阶段验。Deferred：轴自动判定 / 看板高级交互(筛选着色) / 不依赖 onboard 的独立深分析。
- distilled-from: `session:sdlc-tree-generator-2026-06-16`（5 框架发散~30 轴候选 + a1/a2/a3 网页审）。

## [0.13.0] — 2026-06-16

### Added
- **★Retire 标源叶 shipped 时，把 evolution entry 也写进该源叶 `## sdlc 记录` 段**：当退场特性源自需求树（有 `--leaf`）且有 `--evolution-entry` 时，同一条蒸馏教训除 append `.sdlc/EVOLUTION.md`（全局流水，不变）外，**也 append 进该源叶 `.md` 的 `## sdlc 记录` 段**（段缺则建）——使 `.sdlc/requirements/` 需求树成为**带 sdlc 记录的活档案**，每片叶随身携带它 ship 时的耐久结论。新增 `_append_leaf_sdlc_log(leaf_path, entry)`；`cmd_retire` JSON 输出加 `leaf_evolution` 字段。`scripts/test_backlog.py` `RetireTest` +4 用例（挂叶正路径 / 无 entry 不挂 / 段已存在追加不重复建头 / 无叶仅 EVOLUTION）。

### Changed
- `_mark_leaf_shipped(req_root, leaf_id)` **返回命中叶的绝对路径或 None**（替代原 bool）——供 cmd_retire 拿路径做叶挂载；`leaf_shipped = path is not None` 语义不变。内部重构，无外部调用方。

### Notes
- 全 **additive**：未加顶层 skill、未动 stage 枚举/routing/STATE 模板/契约。**降级**：无 `--leaf` / 叶未命中 / 无 entry → 不挂（= 旧行为）；sdlc-pilot 自身无需求树 → 永不触发。**幂等**沿用 retire 的 archive-exists 守卫。EVOLUTION.md 行为完全不变。
- 文档：`sdlc-backlog/SKILL.md §6` Retire 四步表 ③ + 回流目标段 + 顶部 op 描述已同步。driver §2/§4 的 Retire **高层**描述不赘述此 op 子细节（细节归 backlog SKILL，避免 driver 膨胀；其既存 PROFILE/EVOLUTION 措辞本特性不动）。
- dogfood：用 sdlc-pilot 自己 `/sdlc` 流程开发（worktree-free，feat/evolution-leaf-attach，spec+plan 走网页审）。distilled-from: `session:sdlc-evolution-leaf-attach-2026-06-16`。

## [0.12.0] — 2026-06-16

### Added
- **★`sdlc-backlog` 需求树看板（双表征 + 实时对话编辑）**：给 `scripts/backlog.py` 加三命令——
  - **`tree`**：把整棵需求树导成 `domain→subdomain→leaf` 嵌套 JSON + `summary`（total/by_status/ready_count），给 agent 一次拿全貌（与 readyqueue/coverage 的切片互补）。内部 `build_tree(leaves)` 与 board 共用（DRY）。
  - **`board`**：渲染**自包含 HTML 看板**（纯标准库拼装、内联 CSS+JS、无模板引擎/网络字体、离线可开）——**左侧**三级折叠树（原生 `<details>`，叶卡含 status 徽章/priority/risk/依赖 + 每 domain coverage 进度条，点叶=选中）；**右侧常驻聊天面板（chatbot）**：点叶选中后，面板顶部显示该叶**完整详情**（标题/状态/优先级/风险徽章 + 域/old_system_ref/依赖 + 需求描述/验收线索/老系统参照正文，数据经 `leaf-data` JSON 嵌入），下方按 `你/agent` 气泡对话，底部输入框，per-leaf 会话。复用 web-review **Live mode** + `server.py`（不改后端、不依赖 annotate.*）把页面当 agent 的眼睛和手——发送 `POST /feedback`→agent `curl /wait` 收到→答疑/`Edit` 改叶/`move` 迁域→写 `replies.json`+bump `/rev`→页面追加 agent 气泡 / 树变即 reload；线程靠 `feedback-history.jsonl`+`replies.json` 重建（刷新不丢）= **给 backlog 补一道人看 + 对话可编辑的 review gate**。渲染只读（改树由 agent 单写者经 Edit/move）。
  - **`move`**：叶迁域（mv 文件 + 改 `id`/`domain_path` + **改写全树 `depends_on` 引用**），幂等拒覆盖。`backlog.py` 第 2 个**写树** op（retire 之后）。
- **★仓根 `DESIGN.md`（首次建立设计契约）**：sdlc-pilot 网页类产物的视觉/交互宪法——风格方向（暖色编辑感 + 硬投影）、色板 token（奶油/鼠尾草绿 + status/priority 语义色）、字体/8px 间距、组件、交互态（hover/focus-visible/选中叶）、a11y（对比 AA / 原生 details 键盘 / reduced-motion）、响应式。`design` 角色卡评审以它为基准。
- **`examples/requirements-fixture/`**：3 domain / 6 叶的示例需求树（含依赖链 + 多 status），供 board e2e 与演示；`lint` clean。

### Changed
- `sdlc-backlog/SKILL.md`：顶部 op 枚举加 Tree/Board/Move；新增 §4.4 Tree、§4.5 Board、§5 Move 章节；Retire 顺延为 §6（出口→§7、边界→§8）。

### Notes
- 全 **additive**：未加顶层 skill（tree/board/move 是 backlog 的 op）、未动 stage 枚举、未动 role-routing。守三铁律（可移植纯标准库 / 纯文件单写者 / 不加顶层 skill）。
- chatbot = agent 经 web-review Live mode 驱动（**不引独立 AI 后端**），右侧聊天面板自建（不复用 annotate 批注层 UI）。**Deferred**：工程→需求树自动生成器（backlog Seed 升级）、独立 AI 看板应用。
- dogfood：本特性用 sdlc-pilot 自己的 `/sdlc` 流程开发（独立 worktree `feat/backlog-review-board`）。distilled-from: `session:sdlc-backlog-board-2026-06-16`。

## [0.11.1] — 2026-06-16

### Changed
- **spec/plan 复核 gate 把「网页审(web-review)」从可选修辞收紧为硬性一次性告知**:此前 `sdlc-spec` §2.9 的「主动提醒」自带"简单 spec 可省那行"逃生舱口、`sdlc-plan` **根本没有**用户确认 gate 提示块(web-review 只埋在末尾可选附录),导致执行模型偏简洁时总是省略、用户从不被问到要不要划词批注。
  - `sdlc-spec` §2.9:`主动提醒` 改为「硬性告知 · 一次性」——括号「网页审」那行**必须出现在复核提示里**,不得以"默认更快/spec 简单"为由省略;选不选仍归用户。
  - `sdlc-plan`:**新增 §6.4 用户确认 gate**(呈现定稿 plan 的提示模板,含必含的「网页审」一行 + "只有用户确认后才前进"纪律),与 spec §2.9 对齐;原 §6.3 尾部可选附录降级为纯「机制说明」,把硬性告知职责让给 §6.4。
- **driver §0.3 新鲜度自检从"best-effort 顺手探"收紧为"入口必做"**:此前措辞("每次入口顺手探一下"+ 标题 best-effort)被执行模型当可选,导致 `/sdlc` 入口几乎从不真去探工具源是否落后 upstream。改为**执行硬性**(每趟 driver 入口必跑,不得以"上次探过/多半最新"跳过)同时**保留输出静默·非阻塞**纪律(只有落后才一行,失败/最新静默);并补一句点明 driver 是唯一新鲜度闸口(子技能直调不带自检,靠 driver 兜底)。
- 三处均为纯措辞精修(additive/收紧),不改 gate 判定权、不改"批准前不前进"与"自检非阻塞"纪律,不动 stage 枚举/routing/STATE/契约。distilled-from: `session:sdlc-evolve-webreview-prompt-2026-06-16`。

## [0.11.0] — 2026-06-16

### Added
- **`.sdlc/` git-track 策略（跨机器/团队持久）**：`.gitignore` 改为 `.sdlc/*` + `!archive/` + `!EVOLUTION.md` + `!PROFILE.md`——**在飞工作态**（顶层 spec/plan/STATE/validate/review）仍本地忽略（churn 不入历史），**已完成/已蒸馏产物**（退场归档 + 演进史 + 项目记忆）纳入 git。退场（Retire op）是把工作态转入 `archive/` 的那道闸。附**隐私提醒**（CLAUDE.md + README）：track 前确认 archive/EVOLUTION 无密钥。

### Changed
- **★Evolution log 独立化（PROFILE 结构重构）**：把 0.10.0 做成 PROFILE 一节的 `## Evolution log` 提为**独立 `EVOLUTION.md`（唯一正屋）**，PROFILE 仅留一行指针。理由：PROFILE 六节是**有界快照**（每会话整篇读），Evolution log 是**无界 append 流水**，本性不同 → 分文件，避免流水撑爆 PROFILE。
- **retire 回流单路径**：`backlog.py` 的 `_append_evolution` 简化为 `(sdlc_dir, entry)` 永远写 `EVOLUTION.md`；**移除 `--profile` 参数**（0.10.0 刚引入、无外部依赖，安全简化）。`test_backflow_to_profile_section`→`test_backflow_always_evolution_md` + 新增 `test_retire_rejects_profile_flag`（12/12 绿）。

### Notes
- 全 **additive**：未动 stage 枚举、未加顶层 skill、未动 role-routing。dogfood：现有 `.sdlc/archive/{sdlc-backlog,feature-retirement}` + `EVOLUTION.md` 首次入仓。distilled-from: `session:sdlc-feature-retirement-2026-06-16`。

## [0.10.0] — 2026-06-16

### Added
- **★`sdlc-backlog` 新增 `Retire`（特性退场 / close-out）操作**：当一个特性走到 `stage=done`，统一收尾其 `.sdlc/` 工件生命周期——① 归档 `spec/plan/validate/review/STATE` → `.sdlc/archive/<date>-<feature>/`；② 把 `STATE.Decisions log` 里**耐久**的决策/教训/新风险蒸馏回流 `PROFILE.md ## Evolution log`（无 PROFILE 兜底 `.sdlc/EVOLUTION.md`）；③（若源自需求树）标源叶 `status=shipped` → ready-queue 自动解锁下游叶；④ 清空 STATE 交还下个特性。backlog 因此成为特性生命周期的**两端书挡**（选叶起特性 / 退场收尾）。
- **`scripts/backlog.py retire` 子命令**（纯标准库）：承载退场的确定性机械部分（归档移动 / 标 shipped / 回流追加 / 幂等守卫）；`scripts/test_backlog.py` 新增 `RetireTest` 6 用例（归档清栈/标叶解锁下游/回流 PROFILE/回流兜底/幂等拒覆盖/无叶降级）。**retire 是 backlog.py 首个写树操作**（派生 op 仍只读）。
- **填补 backlog 已知缺口**：叶状态机的终态 `shipped` 回写此前被委托给"尚不存在的子系统 B"（ready-queue 因此永远解锁不了下游）；Retire 填上这个回写点。中间态逐阶段回写与调度循环仍属未来 B。
- **回流载体**：`PROFILE.md` 新增 `## Evolution log` 段（append-only，区别于 onboard 的静态 `Known risks`），使完成特性的耐久决策作为长寿 context 持续指导后续演进。

### Changed
- **driver**：§2 新增"退场前置"——入口检测到 `STATE.stage==done` 时**先于**三主分叉路由到 backlog Retire；§4 路由表加 `done` 行；§5 交接说明 done 退场由 backlog 执行（driver 只路由不亲自归档）。
- **STATE 模板**：把悬空的"归档或清空"改为明确退场指引；新增 `source-leaf` 字段（记特性源叶，供 Retire 回写 shipped）。

### Notes
- 全 **additive**：未动 stage 枚举（`done` 已在内）、未加顶层 skill（Retire 是 backlog 的 op）、未动 role-routing 取值字典（skill-maintainer 已覆盖）。
- 范围切线 **L0**（仅终态退场闭环）；逐阶段叶回写 / archive 入 git / 子系统 B / backlog review 看板均显式 Deferred，各自独立特性按 SDLC 逐个做。distilled-from: `session:sdlc-feature-retirement-2026-06-16`。
## [0.9.1] — 2026-06-15

### Added
- **container.md §1 + deployment-patterns §8 preflight：registry 与集群同地域告警**：跨地域 registry 会让用户卡在无端 `ImagePullBackOff`（只见 hang、不知为何），推镜像前先比对地域，不同则**先告知用户并选**（同域仓库 / 公网 endpoint / 跨域复制）；同域优先走 VPC 内网 endpoint（私网、免费、快）。
- **container.md §2.5 + deployment-patterns §8：部署必产出可直达地址**："部署成功"重定义为"用户能直接访问"而非"Pod Running"。收尾自动建 `LoadBalancer` Service（**默认内网/intranet IP**，除非明确要公网），轮询拿到 `EXTERNAL-IP` 后把 `<IP>:<port>` + 一条 `curl` verify 交给用户，**绝不停在 ClusterIP**；内网 LB 注解 provider-specific（ACK/EKS/GKE 示例在卡内）。

> 继续把 **deploy-aliyun 实战坑**沉淀进 sdlc-ship 通用层（ACR 跨地域卡住 + 部署完无法访问）。distilled-from: `deploy-aliyun(skill)` · `session:secret-no-transmit-ingest-2026-06-15`。

## [0.9.0] — 2026-06-15

### Added
- **★新增 `sdlc-backlog` 流程 skill（pre-spec 项目级 stage，子系统 A）**：把"散点式涌现的需求 / 待重写老系统的功能点"测绘成一棵**递归需求树**（`<target-repo>/.sdlc/requirements/` 的 `domain→subdomain→leaf`，复用 kb-manage 结构）。五操作：**Seed**(老系统→骨架) / **Ingest**(散点需求归类成叶) / **Coverage**(按 domain 迁移 burndown) / **Ready-queue**(派生解依赖的就绪叶 → A/B 契约) / **Lint**(断依赖/重复 old_system_ref/缺字段/孤儿)。叶 schema 10 字段含双视图(`old_system_ref`/`new_domain_path`,解 rewrite≠1:1)、`cross_link`(跨域多父)、`risk_level`(供调度器分诊)。
- **`scripts/backlog.py`**（纯标准库，无第三方依赖）：承载 readyqueue/coverage/lint 的机械派生，附 `scripts/test_backlog.py`（stdlib unittest，5 用例全过）。
- **家族契约同步**（加流程阶段的完整 4 处 + 计数）：STATE 模板 stage 枚举加 `backlog`（项目级，与 onboard 同类，解耦于单特性 STATE）；driver §2 新增正交 backlog 分叉（不改原三主分叉）+ §4 路由表加行 + §5 内嵌 schema 枚举同步；role-routing §5 R10 breadcrumb（编辑 backlog skill 由 R10 覆盖，需求树**数据**是运行时产物不进路由）；onboard Phase A 顺带探测已有 backlog；plugin/marketplace/CLAUDE/README/skill-maintainer 的"流程 skill 计数" 7→8。
- **README 技能枚举补全**：§概念表 / 文件树 / 「流程 skill」蒸馏来源表 / 使用场景表 均补上 `sdlc-backlog`，并**回填**此前遗漏的 `sdlc-ship` 行（README 自 ship 加入后未同步）。

### Notes
- backlog 是继 ship 之后第二个"真·生命周期阶段"例外（新增顶层 skill），守 CLAUDE.md 铁律 #1 的 carve-out；机制进 sdlc-pilot、需求树**数据**留目标项目（类比 kb-manage）。
- 子系统 B（`sdlc-loop` 调度器：dequeue ready-queue→pipeline→回写→停 + 定时/事件触发 + 成本分诊门）为本次**非目标**，将单独走完整 `/sdlc`。distilled-from: `session:loop-engineering-article(Addy Osmani)` · `kb-manage` · `tb-loop-driver`。

## [0.8.1] — 2026-06-15

### Added
- **deployment-patterns §7 密钥纪律加厚**：§7.1 **绝不存储且绝不传输**（不回显/不进日志/不拼 URL/不外发/不截图，真值除注入运行时外不在任何留痕处出现）；§7.2 **摄入侧坐标与密钥分离**（从台账/控制台/文档读配置只取坐标，密钥就地跳过不外带；"缺授权 ≠ 拒绝用户"——换有授权通道拿坐标）；§7.3 **创建/校验 secret 安全手法**（`--from-file` 本人输入 + 用完 shred；校验只看 key 名/条数，禁 `-o yaml`/`-o jsonpath`；kubeconfig 私钥不 cat）；§7.4 **泄露即轮换**。
- **deployment-patterns §7.5 可切换多环境坐标清单**：一份坐标清单（context/namespace/host/registry/域名），坐标与密钥分离（清单只存 Secret 名），切环境 = 改一个字段、命令骨架不变、可审计。
- **deployment-patterns §8 新增 preflight 就绪门**：环境晋级前先过"工具齐 + 登录态齐 + 目标 env 坐标无缺"，缺则停、不带半套上线。
- **deploy-targets/container.md 命名空间幂等前置**：apply 前 `get || create` 确保 namespace 存在，**绝不自动删 namespace**（级联删资源）。

> 以上为 **deploy-aliyun skill 的可移植子集**蒸馏进 sdlc-ship 通用层（厂商专属 `aliyun`/ACR 命令与扫码读文档、新手手把手交付按 R10 可移植/契约边界不蒸）。distilled-from: `deploy-aliyun(skill)` · `session:secret-no-transmit-ingest-2026-06-15`。

## [0.8.0] — 2026-06-12

### Added
- **driver §2.1 PROFILE 缺失提醒**:greenfield 一路 spec→build 不产生 PROFILE,项目会长出大量代码却无工程持久记忆。driver 每次入口探"有源码但无 `.sdlc/PROFILE.md`" → text_mode **软提醒**补 onboard(不阻断);建议 greenfield 首个 feature build 后补。补 #3。
- **sdlc-onboard AI-readiness 低分软推荐**:体检健康分 **< 阈值(默认 7/10)** → 写完 PROFILE 后软推荐起一个 remediation feature 补缺口(CLAUDE.md 级联 / scoped 命令 / 类型·测试 baseline / AGENTS.md 软链),整改走 L1+Skip-TDD。**只推荐不强制**,onboard 不因低分阻断。补 #4("保证 AI 友好"的软入口)。
- 两条均为 SKILL.md 行为追加,守三铁律(不新增顶层 skill、不动 stage 枚举、可移植 text_mode)。distilled-from: `session:traffic-domain-2026-06-12`。

## [0.7.1] — 2026-06-12

### Added
- **ai-readiness 卡:CLAUDE.md 级联判断 + AGENTS.md 软链约定**(append-only)。维度 1 补「用 PROFILE.surface-map 当输入决定该在哪几层建 CLAUDE.md——每个有『局部+代码看不出+代价高』规则的面 = 一层 `src/<surface>/CLAUDE.md` 候选,面小且规则全局则单根足够」;「好的样子」补 `AGENTS.md` 软链到 `CLAUDE.md`(`ln -s`,git mode 120000)= Codex/Claude 单一事实源免漂移,胜过指针文件。distilled-from: `session:traffic-domain-onboard-2026-06-12`。
- 仍待办(结构性,需对 sdlc-pilot 跑完整 /sdlc):driver greenfield 无 PROFILE 时强推 onboard;AI-friendly 保证门(体检阈值 gate)。

## [0.7.0] — 2026-06-11

### Added
- **driver 新鲜度自检（§0.3，best-effort 非阻塞）**：`/sdlc` 每次入口顺手探测 sdlc-pilot **工具源**是否落后 upstream（探源同 evolve §5 → `git fetch` + `rev-list --count HEAD..@{u}`）；落后则 text_mode **一行提示**「源落后 N 提交，`git -C <源> pull` 可更新（本次仍用当前版本）」，**绝不**自动 pull、绝不打断本次流程；探测失败（离线 / 无 upstream / 只读缓存 / 非软链安装）一律静默跳过。与 §1.1 边界守卫正交：守卫管「特性串台」，本节管「工具版本新鲜度」。

### Changed
- **spec/plan 复核 gate 主动提醒网页审**：web-review 此前只埋在 gate 描述之后的「可选」段，用户复核那一刻看不到这条路、得自己知道。现 `sdlc-spec`§2.9 复核提示框内嵌一行「spec 长/多节多表逐条批太累？说『网页审』，我渲染成可划词批注的本地网页」并加「主动提醒」指令；`sdlc-plan`§6.3 呈现定稿 plan 请确认时同样主动提一句。简单文档可省、默认聊天批更快。

### Fixed
- **web-review playbook 过时文案**：`playbook.md`§3「告诉用户怎么标」结尾的「提交后回对话说一声」是 auto-collect + 逐条回复 UI 闭环（0.5.0/0.6.0）之前的旧指引；改为「提交即自动回收（Live mode 下 agent 前台 `/wait` 当场拿到，文件式下读 `feedback.json`），改完会在每条批注下回复，用户不必回对话手动转述或贴回」。

distilled-from: `session:sdlc-evolve-web-review-freshness-2026-06-11`。

## [0.6.0] — 2026-06-11

### Added
- **web-review 逐条回复(agent → 用户 UI 闭环)**：agent 处理完批注后写 `replies.json`（`{批注id: 回复文本}`）到审阅 outdir，`annotate.js` 每 3s 轮询 `/replies.json`，在每条批注下渲染「↩ agent」回复块——用户在浏览器即可看到每条意见被怎么处理，形成「批注 → 修改 → 回复」的可视闭环。`playbook.md` §3.6 写入机制（与重跑 build 同一轮做）；`.gitignore` 忽略运行时 `replies.json`。

### Changed
- **web-review 提交成功文案**：从「已提交！回到对话里说一声，我来读取并统一修改。」（Live mode 下已过时）改为「已提交！agent 正在读取并统一修改，改完会在每条批注下回复。」，与 Live mode 自动回流 + 逐条回复一致。

distilled-from: `session:web-review-dogfood-2026-06-11`。

## [0.5.1] — 2026-06-11

### Fixed
- **web-review 自动刷新失效**：0.5.0 的 Live mode 注入了轮询 `/rev` 的 poller，但 `build.py` 从不写 `rev` 文件 → `/rev` 恒 404 → poller 永不触发 reload，用户只能手动刷新。修复：`build.py` 每次 build 写一个单调递增的 `rev` 文件，rebuild 后页面真正自动刷新。

### Added
- **web-review 批注历史保留**：批注此前只在 JS 内存里，一旦 reload（恰好自动刷新会触发）即全部丢失。现 `annotate.js` 把批注持久化到 `localStorage`（按页面路径+标题分键），reload/自动刷新后自动恢复列表并尽力重标高亮（跨节点长引用找不到则保留列表项）；`server.py` 每次 `/feedback` 追加一行到 `feedback-history.jsonl`，多轮提交可回溯（`feedback.json` 仍存最新一次）。
- **web-review 可见折叠按钮**：批注面板折叠此前只藏在「双击标题」里、不可发现。`annotate.js`/`annotate.css` 在面板标题加一个可见折叠按钮（‹），点击收起到侧边把手，双击标题仍可收起。

distilled-from: `session:web-review-dogfood-2026-06-11`（腾讯 MMP spec 划词复核实测）。

## [0.5.0] — 2026-06-11

### Added
- **web-review Live Mode（实时双向复核，可选升级）**：把"用户提交后回对话手动 signal"升级为 agent 前台阻塞 `curl /wait` 的 HTTP 长轮询——提交瞬间自动回流批注，改完页面自动刷新，形成 `present→await→revise` 的 human-on-the-loop gate 循环。机制只用"前台阻塞 shell"通用原语，**跨引擎（CC/Codex）都实时，不依赖任何 harness 特性**。落地：`server.py` 换 `ThreadingHTTPServer` + 加 `/wait` 长轮询端点（`threading.Event`/slot，`/feedback` 语义不变 + 仍写 `feedback.json` 兜底）；`build.py` 模板注入 `/rev` 自动刷新 poller；`playbook.md` 新增 §6 Live mode（写原则）；`test_live.py` 长轮询回归测试（释放/不死锁/超时204/submit-before-wait）；`sdlc-spec`§2.9 与 `sdlc-plan`§6.3 各加一句指向 §6。**硬约束**：必须 `ThreadingHTTPServer`，否则挂起的 `/wait` 堵死 `POST` → 死锁。distilled-from: `session:web-review-live-2026-06-11`。

## [0.4.0] — 2026-06-10

### Added
- **web-review 可选复核 gate 机制**(`skills/sdlc/references/web-review/`):把 spec/plan 渲染成「划词加批注」的本地网页让用户标注,零依赖 localhost 服务器回收 `feedback.json`,agent 再统一改回源文档。含 `playbook.md`(原则) + `build.py`(md→可批注页) + `annotate.js`/`annotate.css`(通用批注层) + `server.py`(回收服务器)。`sdlc-spec` §2.9 与 `sdlc-plan` §6.3 的用户复核 gate 各挂一句**可选**引用——文档长/逐条批太累时用,默认仍走 text_mode 聊天批,不改"批准前不前进"纪律。distilled-from: `session:spec-web-review-2026-06-10`。

## [0.3.2] — 2026-06-06

### Changed
- **skill-maintainer 卡补一条安装教训**(经 `/sdlc evolve` dogfood 蒸入):软链装完要验 `readlink ~/.{claude,codex}/skills/sdlc` 落点是可写 git 仓 + 有 plugin.json,否则 evolve 探源静默失败;技能在新会话才注册,当前会话 dogfood 需把 playbook 当数据手动跑。distilled-from: `session:evolve-dogfood-2026-06-06`。
- 首次实跑验证 `/sdlc evolve` 全闭环(探源→临时分支→lint→additive 守卫→人工检查点→owner 直推 main)。

## [0.3.1] — 2026-06-06

### Fixed
- **evolve 探源支持 Codex**:`evolve-loop.md` §5 探源同时认 `~/.claude/skills/sdlc` 与 `~/.codex/skills/sdlc`(原只查前者,纯 Codex 用户探不到可写源)。
- **README**:安装节补 Codex 全局技能目录 `~/.codex/skills/` 的软链装法(等价 `~/.claude/skills/`),两引擎共用一份可写源。

## [0.3.0] — 2026-06-06

时用时新自更新能力 `/sdlc evolve`(两轴表达,不新增顶层 skill)。

### Added
- **`skill-maintainer` 角色卡**(`roles/skill-maintainer.md`):唯一作用于工具自身的维护者视角——防臃肿 / additive 合并 / 防孤儿 / 溯源 / 可移植 / semver / **自我修改安全**。由 role-routing **R10**(改 `skills/**`·`*SKILL.md`·`references/**`·`.claude-plugin/**`)加载。角色 7→8。
- **`evolve-loop.md` playbook**(`references/`,与 distillation-loop 并列的数据):6 步管道(捕获→探源→落位→发布闸→回流→回报)+ **自我修改四层安全闭环**(临时分支 + lint + additive-only 守卫 + 人工检查点 + 原子可逆)+ GitHub 回流(owner 直推 main / 第三方 fork+PR;无 gh 降级手动 PR)。复用 distillation-loop 做落位,不重写方法论。
- **driver `/sdlc evolve` 子命令**(meta,非 stage、不进 STATE 枚举):加载 evolve-loop + skill-maintainer 透镜;触发语"蒸馏进 sdlc / 沉淀到 sdlc / evolve the skills / 自更新"。
- **小改/大改机器可判 guard**:evolve 物理上只做 append-to-existing;碰契约/新建文件即 escalate 走完整 `/sdlc`。

### 蒸馏新增源
kb-manage · sop-extractor · skill-creator(writing guide)· session:sdlc-evolve-design。

### 说明
- 设计依据 `docs/specs/2026-06-06-sdlc-evolve-design.md`。
- 铁律 #1 **不动**:meta 能力用"角色卡 + playbook + 驱动入口"表达,family 仍 driver + 7 流程 skill。CLAUDE.md "怎么迭代" 表加 meta 行。

## [0.2.2] — 2026-06-06

打包自包含修复:强门禁脚本归位到技能目录,三种安装方式路径一致。

### Changed
- **`sdlc-guard` 迁入 `skills/sdlc/scripts/`**(原在仓库根 `scripts/`)。运行时依赖随 sdlc 技能自包含 → 插件 / 软链 / Codex 三种装法路径都一致;之前软链装法直连路径会落空、只靠 onboard 拷贝兜底。`validate-skills`(开发期 lint)留在仓库根。
- 同步更新引用:driver §1.1、onboard Phase D、pre-commit hook(plugin-cache 查找路径)、README、设计 spec。
- **lint 加 §7**:校验 `sdlc-guard` 存在/可执行 + hook 查找路径未漂移,防此类位置不一致再次发生。

## [0.2.1] — 2026-06-05

流程 skill 去"命令手册化":skill 是**约束 + 原则**,不是 bash cookbook。

### Changed
- **onboard Phase A 重写**:~70 行脆弱 bash(`find`/`grep`/`awk` 一行流,带 zsh-glob/wc-total/嵌套清单/噪声等坑)→ ~20 行「采什么(4 视角表)+ 避坑原则」。之前 dogfood 找出的"缺陷"多是规定命令自身的 bug,原则化后消失。
- **去 cookbook**:onboard/driver 空仓判定、plan spec-获批检查、review base 分支探测链、各入口 `ls -la`/`ls` 检查 → 全改为原则/要确认的事。
- **保留**:`git diff --name-only` 三连(稳定且是路由契约输入)、`scripts/sdlc-guard` 调用(确定性强门禁)、`references/languages/*`·`deploy-targets/*`(参考卡,具体命令即交付物)。
- **CLAUDE.md 加铁律 #4**:skill 约束"做什么/为什么/避哪些坑",不规定"怎么执行命令";附"流程 vs 环境工具调用"判据,防蒸馏退回命令手册。

### Fixed
- **README 安装章节**:方式二软链循环漏了 `sdlc-ship`(枚举技能名易漏)→ 改为遍历 `skills/*/`,永不漏新增技能;路径去硬编码,适配"全新克隆"场景 + 加自检。

## [0.2.0] — 2026-06-05

build 后的能力扩张(角色 7、流程 skill 7、+ 语言包 / 部署)。

### Added
- **architect 角色**(全链路数据结构/契约对齐,routing R8 跨 ≥2 面触发)。
- **ai-readiness 角色**(面向 AI 友好度/可维护性,蒸 arch-doctor 10 维+23 模式;onboard 只读体检 → PROFILE;routing R9)。整改走 feature loop,不另起 skill。
- **doubt-driven 对抗性自我证伪**(spec §2.5,架构/数据/契约决策前)+ **ADR 模板正式化**(spec §2.7)。
- **设计契约前置**(spec §2.6b → DESIGN.md)。
- **7 语言包**(`references/languages/`:Python/TS/Go/Rust/Kotlin/Swift/Java-Spring,陷阱+测试+lint+LSP+框架,命令实测;routing §7;角色卡/validate/ai-readiness 接入)。
- **work-type 流程画像**(STATE:feature/remediation/hotfix,偏置 granularity 不取消硬门)+ `/sdlc next`。
- **并发/边界硬门**(`scripts/sdlc-guard` + `pre-commit` hook,git 执行模型绕不过;STATE branch/worktree 戳;多特性并行引导 worktree)。
- **retro→distillation**(从走过完整 loop 的 session 提炼,门控)。
- **★sdlc-ship 部署阶段**(第 7 流程 skill,`review→verify→ship`):环境晋级流水线 dev→staging→canary→full,每段 deploy→smoke→门→晋级/回滚;**适配多目标**(`references/deploy-targets/{static-site,container,vps}.md`)+ 通用方法论(`deployment-patterns.md`);项目特定配置从目标工程 PROFILE.Deploy/CLAUDE.md 抽,不预置;密钥不入仓。onboard 加只读部署探测。

### 蒸馏新增源
arch-aifriendly-doctor · adhd · doubt-driven-development · plan-ceo-review · session-miner/retro/orchestrator-flow-reflect · ECC 全语言包(python/go/rust/kotlin/swift/java-spring testing+security)· rust-*/swift-* 用户技能 · deployment-patterns/land-and-deploy/setup-deploy/gsd-ship/publish-research-site。

## [0.1.0] — 2026-06-05

首个可安装版本(Claude Code 插件)。

### Added — 核心
- **主线**:`sdlc` driver + 6 流程 skill(onboard / spec / plan / build / validate / review)。
- **角色卡(6)**:qa · client-dev · server-dev · design · big-data(stub)· architect(全链路接缝)。
- **validate 模式(3)**:correctness · e2e(Web/OpenAPI/App)· eval-bench。
- **路由**:`role-routing.md` R1–R8(改动代码 → 角色 + 验证模式;含 R7 配置型工程、R8 跨链路)。
- **状态契约**:`PROFILE.md`(项目级)+ `STATE.md`(feature 级)+ `sdlc-gate` 行。

### Added — 工程/纪律
- **改动驱动路由** + **跨会话状态持久化**;**Task-or-sequential 降级**(Codex 可跑)。
- **build wave 并行执行**(同 wave 多阶段 fan-out)。
- **eval 标准前置**(spec §5)+ **设计契约前置**(spec §2.6b → `DESIGN.md`)。
- **可选发散 ideation**(`divergence-frames.md`,蒸馏 adhd)+ **范围塑造**(spec §2.4b)。
- **受评接收纪律**(`receiving-feedback.md`,防过度修复)。
- **push 前 SDLC 检查**:本地 `pre-push` hook(纯 shell,读 `sdlc-gate`)。
- **并发/边界硬门禁**:`scripts/sdlc-guard`(确定性检测 STATE 与 branch/worktree 串台)+ `pre-commit` hook(git 执行、模型绕不过);STATE 加 `branch`/`worktree` 戳;driver 入口软层 + onboard 询问安装;引导用 worktree 做多特性隔离。
- 打包为插件(`.claude-plugin/`)+ `CLAUDE.md`/`AGENTS.md` 维护契约 + `scripts/validate-skills` 结构 lint。

### 蒸馏自
superpowers · gstack(+ review/specialists)· GSD(+ ai-evals.md)· agency-agents(MIT)· adhd(MIT)· 用户自有 skill(hp-* / explorer-* / startup-* / tb-* / web-api-reverse-engineering)· Playwright MCP。详见 `README.md` 溯源表 + `docs/distillation-source-map.md`。

### 已知 / 待办
- 仅 dogfood 过 onboard(测 agentic-config-demo);完整 feature 主线端到端试跑待做。
- App E2E 工具(Maestro)选型待实测;big-data 角色为 stub。
- 见设计 spec §13。
