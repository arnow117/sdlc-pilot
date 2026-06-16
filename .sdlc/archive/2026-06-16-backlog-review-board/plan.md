# Plan: backlog review 看板（需求树双表征 + 实时对话编辑）

> 来源 spec: .sdlc/spec.md（已批准）
> 复杂度等级: **L2** —— 理由: 产品级开发工具特性，有质量要求 + 需长期维护；核心逻辑（tree/move）走 TDD，渲染走结构断言。非 L3（无多团队/SLA/合规）。
> 生成: 2026-06-16
> Active roles: design, skill-maintainer, qa ｜ Validate modes: correctness, e2e:Web

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | `tree` 命令 + `build_tree` 共享 | R-tree, D-DRY | — | 1 |
| P2 | `move` 命令（叶迁域） | R-move | P1 | 2 |
| P3 | `board` HTML 渲染（DESIGN + annotate 注入） | R-board, R-live, R-design | P1 | 3 |
| P4 | fixture 树 + 文档/版本同步 | R-fixture, R-docsync | P2, P3 | 4 |

> 全部任务触及 `scripts/backlog.py` / `scripts/test_backlog.py` 同一对文件 → §4.3 隐式依赖强制串行波次（单 session 顺序执行，无并行冲突）。validate（correctness + e2e:Web）在 build 全绿后由 sdlc-validate 独立跑，不在本 plan 任务内，但各阶段成功标准用它能断言的行为表述。

---

## Phase P1: `tree` 命令 + `build_tree` 共享函数

**目标**: 能把整棵需求树导成嵌套 JSON（agent 可读全貌），并抽出 board 复用的嵌套逻辑。
**覆盖需求(traceability)**: R-tree（spec §5.1/§5.2 整树 JSON）, D-DRY（board 与 tree 共用 build_tree）
**depends_on**: []　**wave**: 1
**为什么这样拆**: build_tree 是 tree 与 board 的共同地基，先定它 + 最简消费者（tree CLI），契约先行。

**must_haves（目标倒推）**:
- truths: `backlog.py tree --root <r>` 输出 §5.2 形状；domain→subdomain→leaf 嵌套正确；summary 计数对；空树不崩。
- artifacts: `scripts/backlog.py`（+`build_tree`、`cmd_tree`）、`scripts/test_backlog.py`（+`TreeTest`）。
- key_links: `cmd_tree` 调 `load_leaves`（既有）→ `build_tree` → `json.dumps`；main 的 subparser 注册 `tree`（复用既有 `("readyqueue","coverage","lint")` 那段 `--root` 循环，把 `tree` 加进去）。

**可观察成功标准**: `python3 scripts/test_backlog.py TreeTest -v` 全 PASS。

### Task P1-T1: 写 `build_tree` + `tree` 命令（TDD）
- **requirements**: R-tree, D-DRY
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `scripts/backlog.py:51-102`（load_leaves/cmd_coverage 的 domain 解析口径）、`scripts/test_backlog.py:13-48`（write_leaf/run 助手）、`.sdlc/spec.md` §5.2
- **action**: 在 `backlog.py` 加 `build_tree(leaves)` —— 按 `domain_path`（`<domain>/<subdomain>`）两级分组，叶只取 9 个对外字段（id/title/status/priority/risk_level/depends_on/old_system_ref/new_domain_path/cross_link），返回 `{"domains":[{"domain","subdomains":[{"subdomain","leaves":[...]}]}],"summary":{"total","by_status","ready_count"}}`；`ready_count` 复用 readyqueue 判据（status!=shipped 且 depends_on 全 shipped）。加 `cmd_tree(root)`: `print(json.dumps(build_tree(load_leaves(root)), ensure_ascii=False, indent=2))`。main 把 `"tree"` 加进 `("readyqueue","coverage","lint")` 的 subparser 循环与 dispatch dict。**不读 _domain.md meta**（YAGNI，spec §5.2 的 meta best-effort，本期省，叶字段已够看板用）。

- [ ] Step 1: 写失败测试 — 在 `test_backlog.py` 加：
  ```python
  class TreeTest(unittest.TestCase):
      def test_nests_and_counts(self):
          with tempfile.TemporaryDirectory() as root:
              write_leaf(root, "order.checkout.a", status="shipped", priority="P1")
              write_leaf(root, "order.checkout.b", depends_on="[order.checkout.a]")
              write_leaf(root, "user.auth.c", status="built")
              r = run("tree", root=root)
              self.assertEqual(r.returncode, 0, r.stderr)
              t = json.loads(r.stdout)
              doms = {d["domain"]: d for d in t["domains"]}
              self.assertEqual(set(doms), {"order", "user"})
              subs = doms["order"]["subdomains"]
              ids = [lf["id"] for s in subs for lf in s["leaves"]]
              self.assertIn("order.checkout.a", ids)
              self.assertEqual(t["summary"]["total"], 3)
              self.assertEqual(t["summary"]["by_status"]["shipped"], 1)
              self.assertEqual(t["summary"]["ready_count"], 2)  # a shipped→不入; b解锁; c无dep
      def test_empty_tree_ok(self):
          with tempfile.TemporaryDirectory() as root:
              r = run("tree", root=root)
              self.assertEqual(r.returncode, 0, r.stderr)
              self.assertEqual(json.loads(r.stdout)["summary"]["total"], 0)
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py TreeTest -v` → 期望 FAIL（`tree` 未注册 / build_tree 未定义）。
- [ ] Step 3: 写最小实现（`build_tree` + `cmd_tree` + main 注册），按 action 的具体结构。
- [ ] Step 4: 跑 `python3 scripts/test_backlog.py TreeTest -v` → 期望 PASS；并跑全量 `python3 scripts/test_backlog.py -v` 确认未回归既有用例。
- [ ] Step 5: 提交 `git add scripts/backlog.py scripts/test_backlog.py && git commit -m "feat(backlog): tree 命令 + build_tree 共享（整树嵌套 JSON）"`

---

## Phase P2: `move` 命令（叶迁域）

**目标**: 能确定性地把一片叶移到另一个域，自动改 id/domain_path 并改写全树对它的依赖引用。
**覆盖需求(traceability)**: R-move（spec §5.1 move 行；§5.4 错误处理；满足"移动到另一个域"交互）
**depends_on**: [P1]（共享 `backlog.py`/`test_backlog.py`，序后）　**wave**: 2
**为什么这样拆**: move 是 backlog.py 第 2 个写树 op（retire 之后），逻辑独立、可单独 TDD；与渲染解耦先做，给 P3 的 Live "迁域"动作备好命令。

**must_haves**:
- truths: `move --leaf X --to d/s` 后 X 文件在新目录、frontmatter id+domain_path 已改、别的叶 depends_on 里 X→新 id；目标已存在同 id → 拒绝非 0、不动文件；源叶不存在 → 非 0。
- artifacts: `scripts/backlog.py`（+`cmd_move`、`_set_frontmatter_field`）、`scripts/test_backlog.py`（+`MoveTest`）。
- key_links: `move` 是带额外 flag 的 subparser（仿 retire 的 `pr = sub.add_parser("retire")`），dispatch 到 `cmd_move`；复用 `load_leaves` 定位、`re.sub` 改 frontmatter（仿既有 `_set_frontmatter_status`）。

**可观察成功标准**: `python3 scripts/test_backlog.py MoveTest -v` 全 PASS。

### Task P2-T1: 写 `move` 命令（TDD）
- **requirements**: R-move
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `scripts/backlog.py:139-154`（`_set_frontmatter_status`/`_mark_leaf_shipped` 改写法）、`:196-217`（main/subparser 注册 + retire dispatch 模式）、`scripts/test_backlog.py:32-48`（write_leaf/run；run 把 `--root` 追加在末尾，额外 flag 放 args 前段）
- **action**: 加 `cmd_move(args)`：`load_leaves(args.root)` 建 `by_id`；源 = `by_id[args.leaf]`，缺则 `print(..., file=sys.stderr); return 2`。`slug = args.leaf.split(".")[-1]`；`new_dp = args.to`（`<domain>/<subdomain>`）；`new_id = new_dp.replace("/", ".") + "." + slug`；`new_path = <root>/<new_dp>/<new_id>.md`。若 `os.path.exists(new_path)` → 拒绝 `return 1`（幂等守卫，仿 retire archive 已存在）。`os.makedirs(new_dir, exist_ok=True)`；读旧文件文本，`re.sub(r"(?m)^id:.*$", f"id: {new_id}", text, count=1)` + 同法改 `domain_path: {new_dp}`，写 `new_path`、`os.remove(old_path)`。再遍历其余叶：`if args.leaf in (lf.get("depends_on") or [])` → 对该叶文件 `re.sub(r"(?m)^(depends_on:.*)$", lambda m: m.group(1).replace(args.leaf, new_id), t, count=1)` 写回。末 `print(json.dumps({"moved":args.leaf,"to":new_id,"deps_rewritten":n}, ensure_ascii=False))`。main 加 `pm = sub.add_parser("move")` 带 `--root/--leaf/--to`（均 required），`if args.cmd=="move": return cmd_move(args)`（放在 retire 分支旁，注意 move 也需要 `args.root` 存在性检查——把它纳入 `os.path.isdir(args.root)` 那条或自查）。
- **acceptance_criteria**: `python3 scripts/test_backlog.py MoveTest -v` PASS；全量回归 PASS。

- [ ] Step 1: 写失败测试：
  ```python
  class MoveTest(unittest.TestCase):
      def test_relocates_and_rewrites_deps(self):
          with tempfile.TemporaryDirectory() as root:
              write_leaf(root, "order.checkout.a")
              write_leaf(root, "user.auth.b", depends_on="[order.checkout.a]")
              r = run("move", "--leaf", "order.checkout.a", "--to", "billing/pay", root=root)
              self.assertEqual(r.returncode, 0, r.stderr)
              new = os.path.join(root, "billing", "pay", "billing.pay.a.md")
              self.assertTrue(os.path.exists(new))
              self.assertFalse(os.path.exists(
                  os.path.join(root, "order", "checkout", "order.checkout.a.md")))
              txt = _read(new)
              self.assertIn("id: billing.pay.a", txt)
              self.assertIn("domain_path: billing/pay", txt)
              dep = _read(os.path.join(root, "user", "auth", "user.auth.b.md"))
              self.assertIn("billing.pay.a", dep)          # dep 改写
              self.assertNotIn("order.checkout.a", dep)
      def test_refuses_existing_target(self):
          with tempfile.TemporaryDirectory() as root:
              write_leaf(root, "order.checkout.a")
              write_leaf(root, "billing.pay.a")            # 目标已占用
              r = run("move", "--leaf", "order.checkout.a", "--to", "billing/pay", root=root)
              self.assertNotEqual(r.returncode, 0)
              self.assertTrue(os.path.exists(
                  os.path.join(root, "order", "checkout", "order.checkout.a.md")))  # 未动
      def test_missing_source_nonzero(self):
          with tempfile.TemporaryDirectory() as root:
              r = run("move", "--leaf", "ghost.x.y", "--to", "a/b", root=root)
              self.assertNotEqual(r.returncode, 0)
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py MoveTest -v` → 期望 FAIL（move 未注册）。
- [ ] Step 3: 写 `cmd_move` + main 注册（按 action）。
- [ ] Step 4: 跑 `MoveTest -v` PASS + 全量回归 PASS。
- [ ] Step 5: `git commit -m "feat(backlog): move 命令 — 叶迁域 + 全树依赖改写（确定性写 op）"`

---

## Phase P3: `board` HTML 渲染（DESIGN + annotate 注入）

**目标**: 把整树渲染成遵 DESIGN.md 的自包含 HTML 看板，左折叠树 + 注入 web-review annotate 层 + rev 自刷新。
**覆盖需求(traceability)**: R-board（spec §5.3）, R-live（Live 接线复用）, R-design（DESIGN.md 落地）
**depends_on**: [P1]（用 build_tree）　**wave**: 3
**为什么这样拆**: 渲染依赖 P1 的 build_tree 出数据；与 move 解耦。board 命令本身只产 HTML（只读），Live 服务/浏览器验证留给 validate（e2e:Web）。

**must_haves**:
- truths: `board --root <r>` 产 HTML 文件，含每片叶 id、三级 `<details>`、status 徽章、coverage 条、DESIGN token CSS 变量；`</head>` 前有 `annotate.css` 引用、`</body>` 前有 `annotate.js` + `/rev` 轮询；空树出占位页不崩。
- artifacts: `scripts/backlog.py`（+`render_board(tree)`、`cmd_board`）、`scripts/test_backlog.py`（+`BoardTest`）。
- key_links: `cmd_board` 调 `build_tree(load_leaves(root))` → `render_board` → 写 `--out`（默认 `<root>/_board.html`）；CSS 取 `DESIGN.md §2` token；annotate 两行用相对路径引用（服务时由 server.py 同目录托管，§3.3 约定）；rev poller 片段照 `web-review/build.py` 注入的那段。

**可观察成功标准**: `python3 scripts/test_backlog.py BoardTest -v` PASS；人工/e2e 阶段渲染 fixture 后浏览器可折叠、视觉合 DESIGN.md。

### Task P3-T1: 写 `render_board` + `board` 命令（结构断言 TDD）
- **requirements**: R-board, R-design
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `DESIGN.md`（全文：token §2、组件 §4、交互态 §5、响应式 §6）、`skills/sdlc/references/web-review/build.py`（拿 `/rev` poller 注入片段的确切写法 + annotate 两行注入位置）、`skills/sdlc/references/web-review/playbook.md:32`（手工页注入约定）、`scripts/backlog.py`（build_tree 输出形状，P1 已加）
- **action**: 加 `render_board(tree, *, css_vars)` 返回完整 HTML 字符串（纯 f-string 拼装，无模板引擎）：`<head>` 内联 `:root{}` 用 DESIGN.md §2 的 token（`--bg/--panel/--ink/--muted/--line/--green/--green-soft/--radius/--shadow` + status/priority 色）+ board 自身 CSS（`<details>` 三级缩进、`.leaf` 卡、`.badge.status-<st>`、`.cov-bar`、`summary:focus-visible` 2px green、`@media(max-width:768px)` 单列、`@media(prefers-reduced-motion:reduce)` 去过渡）；`<body>` 顶部按 `tree["summary"]` 渲 coverage 条，主体 `for d in tree["domains"]` → `<details><summary>domain</summary>` → 子域 `<details>` → 叶 `<article class="leaf" id="{id}">` 含 title + `<span class="badge status-{status}">` + priority pill + risk 点 + depends_on；空 `tree["domains"]` 渲 `<p class="empty">暂无需求</p>`。`</head>` 前插 `<link rel="stylesheet" href="annotate.css">`，`</body>` 前插 `<script src="annotate.js"></script>` + rev poller `<script>`（照 build.py）。加 `cmd_board(root, out)`: 写文件，默认 `out=<root>/_board.html`；main 加 `pb = sub.add_parser("board")` 带 `--root`(required) + `--out`(可选)。所有用户可见文本与叶内容做 HTML 转义（`html.escape`）防破坏结构。
- **acceptance_criteria**: `python3 scripts/test_backlog.py BoardTest -v` PASS。

- [ ] Step 1: 写失败测试：
  ```python
  class BoardTest(unittest.TestCase):
      def test_renders_tree_and_injects_annotate(self):
          with tempfile.TemporaryDirectory() as root:
              write_leaf(root, "order.checkout.a", status="shipped", title="结算下单")
              write_leaf(root, "user.auth.b", status="captured")
              out = os.path.join(root, "_board.html")
              r = run("board", "--out", out, root=root)
              self.assertEqual(r.returncode, 0, r.stderr)
              html = _read(out)
              self.assertIn("order.checkout.a", html)
              self.assertIn("结算下单", html)
              self.assertIn("<details", html)            # 折叠结构
              self.assertIn("status-shipped", html)       # 状态徽章类
              self.assertIn("--green:", html)             # DESIGN token
              self.assertIn("annotate.css", html)         # 注入
              self.assertIn("annotate.js", html)
              self.assertIn("/rev", html)                 # 自刷新轮询
      def test_empty_tree_placeholder(self):
          with tempfile.TemporaryDirectory() as root:
              out = os.path.join(root, "_board.html")
              r = run("board", "--out", out, root=root)
              self.assertEqual(r.returncode, 0, r.stderr)
              self.assertIn("暂无需求", _read(out))
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py BoardTest -v` → 期望 FAIL。
- [ ] Step 3: 写 `render_board` + `cmd_board` + main 注册（先读 build.py 取 poller 片段）。
- [ ] Step 4: 跑 `BoardTest -v` PASS + 全量回归 PASS。
- [ ] Step 5: `git commit -m "feat(backlog): board 命令 — 折叠树 HTML 看板（DESIGN token + annotate/rev 注入）"`

---

## Phase P4: fixture 树 + 文档/版本同步

**目标**: 建一棵可演示的小需求树供 e2e 与给用户看效果；按 CLAUDE.md 迭代表把新 op 同步进 SKILL/CHANGELOG/版本。
**覆盖需求(traceability)**: R-fixture（spec §5.5 e2e 需 fixture）, R-docsync（spec §7b/§9 文档矩阵 + CLAUDE.md 迭代表）
**depends_on**: [P2, P3]　**wave**: 4
**为什么这样拆**: 文档同步要等命令定型；fixture 要等 board/move 能跑才有意义演示。

**must_haves**:
- truths: `examples/requirements-fixture/` 有 ≥2 domain、含 depends_on、覆盖多 status 的合法叶（`backlog.py lint` clean）；`sdlc-backlog/SKILL.md` 顶部 op 枚举与正文含 tree/board/move 章节；`CHANGELOG.md` 有新版条目；`plugin.json`/`marketplace.json` version 升次版本；`bash scripts/validate-skills` PASS。
- artifacts: `examples/requirements-fixture/<domain>/<subdomain>/*.md`、`skills/sdlc-backlog/SKILL.md`、`CHANGELOG.md`、`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`。
- key_links: fixture lint clean → 喂 board/tree；SKILL.md op 章节链 `scripts/backlog.py`；CHANGELOG distilled-from 本 session。

**可观察成功标准**: `python3 scripts/backlog.py lint --root examples/requirements-fixture` = clean；`bash scripts/validate-skills` = PASS。

### Task P4-T1: 建 fixture 需求树
- **requirements**: R-fixture
- **files**: `examples/requirements-fixture/**`（新建）
- **read_first**: `skills/sdlc-backlog/SKILL.md:74-99`（叶 10 字段 schema）、`scripts/test_backlog.py:13-29`（LEAF_TMPL 字段样例）
- **action**: 建 ≥2 domain（如 `order/checkout`、`user/auth`、`billing/pay`）共 5-6 片叶，每片填全 10 必填字段：覆盖 status ∈ {captured, spec'd, built, shipped}、priority ∈ {P0..P3}、至少一条 `depends_on` 指向同树另一叶（构成可解锁链）、risk_level 混合。叶正文写一两句真实感需求描述。**确保 `lint` clean**（无断依赖/重复 old_system_ref/缺字段/孤儿）。
- **acceptance_criteria**: `python3 scripts/backlog.py lint --root examples/requirements-fixture` 退出 0 输出 `lint: clean`；`python3 scripts/backlog.py tree --root examples/requirements-fixture` 出合理嵌套。

### Task P4-T2: 同步 sdlc-backlog SKILL.md（op 枚举 + 章节）
- **requirements**: R-docsync
- **files**: `skills/sdlc-backlog/SKILL.md`
- **read_first**: `skills/sdlc-backlog/SKILL.md:1-13`（frontmatter op 描述）、`:168-196`（§4 派生操作章节样式）、`CLAUDE.md`「加/改 backlog 派生操作」行
- **action**: 在 §4 派生操作后加一节「§4.x 视图导出（tree / board）」与说明 move（或并入新「§ 视图与编辑」节）：tree=整树 JSON、board=折叠树 HTML 看板（注入 web-review annotate + Live mode 给 backlog 补 review gate）、move=叶迁域（确定性写，第 2 个写树 op）；命令样例用 `python3 <bk> tree/board/move --root <root> ...`。更新顶部 frontmatter 的 op 列举（加 tree/board/move）。**强调 board/tree 只读、move 写树但单写者**。
- **acceptance_criteria**: SKILL.md 含 tree/board/move 三命令说明 + 顶部枚举更新；`bash scripts/validate-skills` PASS（frontmatter 合法）。

### Task P4-T3: CHANGELOG + 版本号
- **requirements**: R-docsync
- **files**: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- **read_first**: `CHANGELOG.md:1-20`（格式 + 最新版条目）、`.claude-plugin/plugin.json`（当前 version）
- **action**: CHANGELOG 顶部加新版条目（Added: backlog tree/board/move + DESIGN.md + fixture；Notes: additive、未加顶层 skill/stage、distilled-from 本 session）。把 `plugin.json` 与 `marketplace.json` 的 `version` 升一个次版本（**注意**：另一 session 的 0.11.1 evolve 在原 worktree 未提交、未合 main，本 worktree 切自 main=0.11.0；以本 worktree 实际 `plugin.json` 当前值为基准 +0.1.0，落地前确认不与 main 冲突——合并时若 main 已进 0.11.1 则顺延）。
- **acceptance_criteria**: CHANGELOG 有新条目；两个 json version 一致且高于基准；`bash scripts/validate-skills` PASS。

### Task P4-T4: 全量回归 + 提交
- **requirements**: R-docsync
- **files**: —
- **read_first**: —
- **action**: 跑 `python3 scripts/test_backlog.py -v`（全绿）+ `bash scripts/validate-skills`（PASS）。`git add -A && git commit -m "feat(backlog): fixture 树 + DESIGN.md + SKILL/CHANGELOG/version 同步（看板特性收口）"`。
- **acceptance_criteria**: 两命令均通过；提交完成。

---

## Source Audit（出口门控，§6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|--------|----|-----------|----------|------|
| GOAL | — | 需求树双表征（人看 HTML + agent JSON）+ 补 review gate | P1,P3,P4 | COVERED |
| REQ | R-tree | 整树嵌套 JSON 导出（§5.1/§5.2） | P1-T1 | COVERED |
| REQ | R-move | 叶迁域 + 依赖改写 + 幂等（§5.1/§5.4） | P2-T1 | COVERED |
| REQ | R-board | 折叠树 HTML 看板（§5.3） | P3-T1 | COVERED |
| REQ | R-live | Live mode 实时对话编辑接线（§5.3） | P3-T1（注入 annotate/rev）+ validate(e2e) | COVERED |
| REQ | R-design | DESIGN.md 视觉/交互/a11y/响应式落地（§7b） | P3-T1 + DESIGN.md（spec 阶段已建） | COVERED |
| REQ | R-fixture | e2e 用 fixture 树（§5.5） | P4-T1 | COVERED |
| REQ | R-docsync | SKILL/CHANGELOG/version 同步（§9 + CLAUDE.md 表） | P4-T2,T3,T4 | COVERED |
| DECISION | D-DRY | board 与 tree 共用 build_tree | P1-T1 | COVERED |
| DECISION | D-A | chatbot=agent经Live mode（非独立AI后端） | P3-T1（复用 server.py，不引后端） | COVERED |
| DECISION | D-collect→edit | 不是 collect-only；agent 单写者经 Edit/move 改树 | P2-T1 + P3-T1 | COVERED |
| EVAL-CRIT | — | N/A（无 AI 工作） | — | N/A |
| Deferred | — | 工程→树生成器 / 方案B / 自由聊天流 | （显式延后，不算 gap） | DEFERRED |

正向全 COVERED；反向每任务 `requirements` 字段非空指回某 REQ/DECISION。自查三扫（占位/类型一致/spec 覆盖）通过。

## 风险 / 关键决策点

- **版本号基准**（P4-T3）：本 worktree 切自 main(0.11.0)，与另一 session 的 0.11.1 evolve 并行——落地/合并时确认版本不撞（已在任务备注处置）。
- **rev poller 片段**（P3-T1）：依赖 `web-review/build.py` 的注入写法，build 时先读取确切片段，勿臆造。
- **board 服务形态**：board 命令只产 HTML；Live 演示（copy 为 index.html + server.py 同目录起服）属 e2e/validate 操作步，不在 build 任务内。
