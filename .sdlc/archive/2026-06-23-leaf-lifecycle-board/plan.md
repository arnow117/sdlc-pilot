# Plan: 需求树生命周期状态同步 + 看板可视化重构

> 来源 spec: .sdlc/spec.md（已批准）
> 复杂度等级: L3 —— 理由: 子系统级，枚举地基 + 写回编排跨 driver/git-hook + 看板重构三块，阶段间有硬依赖（枚举是后续全部的地基）。
> 生成: 2026-06-23

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | STATUS 权威枚举 + lint bad-status 校验 | D-枚举, R-A1, R-A2 | — | 1 |
| P2 | set-status op（共享机械写原语） | R-A-setstatus, D-allowany | P1 | 2 |
| P3 | post-checkout 钩子 + onboard 脚手架装钩子 | R-保证-硬层, D-三件套 | P2 | 3 |
| P4 | driver §1.1 reconcile 规程 | R-保证-软层, D-三件套 | P2 | 3 |
| P5 | 看板惰性叠加渲染（live badge） | R-B-惰性, D-C混合 | P2 | 3 |
| P6 | 看板 4 痛点重构 + 文档/版本 | R-B①②③④, 设计契约 | P5 | 4 |

> wave2 三个阶段（P3/P4/P5）都只 depends_on P2，但 **P3/P4 改 SKILL.md/hooks、P5 改 backlog.py render_board，互不碰同一文件** → 同 wave 可并行。P6 改 render_board/BOARD_CSS/CHAT_JS 与 P5 同文件 → 必须 P5 之后（wave4）。

---

## Phase P1: STATUS 权威枚举 + lint bad-status 校验

**目标**: status 有了单一事实源的合法值集合与顺序，且 lint 能拒非法 status。
**覆盖需求(traceability)**: spec §5.1（STATUS_ORDER/STATUS_SET/STAGE_TO_STATUS）+ §1 问题（无权威枚举、lint 不校验）。
**depends_on**: []   **wave**: 1
**为什么这样拆**: 枚举是后续 set-status/钩子/reconcile/看板全部的地基，必须先立且单独可测。

**must_haves（目标倒推）**:
- truths: ① `lint` 对 `status: banana` 报 `bad-status` 并 exit 1；② 合法 status 仍 clean；③ 代码里有唯一的 STATUS_ORDER 列表，CSS/SKILL 不再各自硬编码顺序。
- artifacts: `scripts/backlog.py`（顶部常量区）、`scripts/test_backlog.py`（StatusEnumTest/LintBadStatusTest）。
- key_links: cmd_lint 引用 STATUS_SET；STAGE_TO_STATUS 供 P3/P4 复用。

**可观察成功标准**: `python3 scripts/test_backlog.py` 全绿（含新增枚举/lint 用例）；手动 `lint` 一棵含非法 status 的树 → exit 1 + stderr 有 `bad-status`。

### Task P1-T1: 加 STATUS_ORDER / STATUS_SET / STAGE_TO_STATUS 常量
- **requirements**: spec §5.1
- **files**: scripts/backlog.py
- **read_first**: scripts/backlog.py:20-32（REQUIRED_FIELDS/FAILURE_CLASSES/SHIPPED 常量区）
- **action**: 在常量区（`SHIPPED = "shipped"` 附近）加：
  ```python
  # status 状态机权威枚举(单一事实源;CSS/SKILL/钩子/reconcile 都引此)
  STATUS_ORDER = ["captured", "spec'd", "planned", "built", "validated", "shipped"]
  STATUS_SET = set(STATUS_ORDER)
  # stage(SDLC 阶段) → 该阶段走过后叶应处的 status(供钩子 flush / driver reconcile 映射)
  STAGE_TO_STATUS = {
      "spec": "spec'd", "plan": "planned", "build": "built",
      "validate": "validated", "review": "validated", "ship": "shipped",
  }
  ```
  保留现有 `SHIPPED = "shipped"`（兼容 _mark_leaf_shipped）。不删不改其它常量。
- **acceptance_criteria**: `python3 -c "import sys;sys.path.insert(0,'scripts');import backlog;assert backlog.STATUS_ORDER[0]=='captured' and backlog.STATUS_ORDER[-1]=='shipped';assert backlog.STAGE_TO_STATUS['build']=='built';print('ok')"` 输出 ok。
- [ ] Step 1: 写失败测试 —— 在 test_backlog.py 加：
  ```python
  class StatusEnumTest(unittest.TestCase):
      def test_order_endpoints(self):
          self.assertEqual(backlog.STATUS_ORDER[0], "captured")
          self.assertEqual(backlog.STATUS_ORDER[-1], "shipped")
      def test_set_matches_order(self):
          self.assertEqual(backlog.STATUS_SET, set(backlog.STATUS_ORDER))
      def test_stage_map(self):
          self.assertEqual(backlog.STAGE_TO_STATUS["spec"], "spec'd")
          self.assertEqual(backlog.STAGE_TO_STATUS["validate"], "validated")
  ```
- [ ] Step 2: `python3 scripts/test_backlog.py -k StatusEnumTest` → 期望 FAIL（AttributeError: STATUS_ORDER）。
- [ ] Step 3: 按 action 加常量。
- [ ] Step 4: `python3 scripts/test_backlog.py -k StatusEnumTest` → 期望 PASS。
- [ ] Step 5: `git add scripts/backlog.py scripts/test_backlog.py && git commit -m "feat(backlog): STATUS_ORDER/STATUS_SET/STAGE_TO_STATUS 权威枚举"`

### Task P1-T2: lint 加 bad-status 校验
- **requirements**: spec §1（lint 不校验 status）, §5.1
- **files**: scripts/backlog.py（cmd_lint）, scripts/test_backlog.py
- **read_first**: scripts/backlog.py:475-510（cmd_lint，特别是 failure_class 校验那几行 :498-503）；P1-T1 加的 STATUS_SET
- **action**: 在 cmd_lint 的 per-leaf 循环里（紧挨 failure_class 校验之后）加：
  ```python
  status = lf.get("status")
  if status and status not in STATUS_SET:
      problems.append(f"bad-status: {lid} status='{status}' 不在 {STATUS_ORDER}")
  ```
  （status 缺失已由 missing-field 抓，这里只校验"存在但非法"。与 failure_class 校验同形。）
- **acceptance_criteria**: 一棵含 `status: banana` 的叶 → `lint` exit 1 + stderr 含 `bad-status`；全合法树 → `lint: clean` exit 0。
- [ ] Step 1: 写失败测试 —— 在 test_backlog.py 的 lint 测试组（参照现有 LintCrossFieldTest）加：
  ```python
  class LintBadStatusTest(unittest.TestCase):
      def setUp(self):
          self.d = tempfile.mkdtemp()
          # 复用既有 helper 写一片合法叶,再改其 status
      def test_rejects_unknown_status(self):
          root = _make_tree(self.d, status="banana")   # 用既有造树 helper,status 传非法值
          rc = backlog.cmd_lint(root)
          self.assertEqual(rc, 1)
      def test_accepts_valid_status(self):
          root = _make_tree(self.d, status="built")
          self.assertEqual(backlog.cmd_lint(root), 0)
  ```
  （若现有 helper 不支持传 status，先在 helper 加 status 参数，默认 'captured'。）
- [ ] Step 2: `python3 scripts/test_backlog.py -k LintBadStatus` → 期望 FAIL（banana 当前能过 lint，test_rejects 失败）。
- [ ] Step 3: 按 action 加校验。
- [ ] Step 4: `python3 scripts/test_backlog.py -k LintBadStatus` → 期望 PASS。
- [ ] Step 5: `git commit -am "feat(backlog): lint 校验 status 取值合法(bad-status)"`

---

## Phase P2: set-status op（共享机械写原语）

**目标**: 有一个确定性子命令把指定叶的 status 改成任意合法值，供钩子/reconcile/人手调用。
**覆盖需求(traceability)**: spec §5.1（set-status op）+ §4 决策（allow-any-set）。
**depends_on**: [P1]（用 STATUS_SET 校验）   **wave**: 2
**为什么这样拆**: 这是写回三件套的共享原语，独立可测；钩子(P3)和 reconcile(P4)都调它。

**must_haves**:
- truths: ① `set-status --leaf X --to built` 改 X 叶 frontmatter status 为 built 并 exit 0；② 非法值（不在 STATUS_SET）exit 1 不写；③ 叶不存在 exit 2 不写；④ allow-any：`validated→spec'd` 也成功（不查迁移合法性）。
- artifacts: scripts/backlog.py（cmd_set_status + main 注册）、test_backlog.py（SetStatusTest）。
- key_links: 复用 _set_frontmatter_status；main() 子命令注册表 + dispatch。

**可观察成功标准**: `python3 scripts/test_backlog.py` 全绿含 SetStatusTest 四路径。

### Task P2-T1: cmd_set_status + 子命令注册
- **requirements**: spec §5.1
- **files**: scripts/backlog.py, scripts/test_backlog.py
- **read_first**: scripts/backlog.py:516-533（_set_frontmatter_status/_mark_leaf_shipped）；:695-735（main 子命令注册 + dispatch，特别 move/write-tree 的注册形态）；load_leaves 用法
- **action**: 加函数：
  ```python
  def cmd_set_status(args):
      """把指定叶 status 机械改为 args.to(allow-any:只校验值∈STATUS_SET,不查迁移合法性)。
      叶不存在→2;status 非法→1;成功→0。复用 _set_frontmatter_status。"""
      if args.to not in STATUS_SET:
          print(f"非法 status '{args.to}',须∈ {STATUS_ORDER}", file=sys.stderr)
          return 1
      for lf in load_leaves(args.root):
          if lf.get("id") == args.leaf:
              path = os.path.join(args.root, lf["_path"])
              _set_frontmatter_status(path, args.to)
              print(f"set-status: {args.leaf} -> {args.to}")
              return 0
      print(f"叶不存在: {args.leaf}", file=sys.stderr)
      return 2
  ```
  在 main() 注册（仿 move）：
  ```python
  ps = sub.add_parser("set-status", help="把指定叶 status 机械改为目标值(allow-any 迁移)")
  ps.add_argument("--root", required=True, help=".sdlc/requirements 目录")
  ps.add_argument("--leaf", required=True, help="叶 id")
  ps.add_argument("--to", required=True, help="目标 status(须∈STATUS_ORDER)")
  ```
  dispatch 加 `if args.cmd == "set-status": return cmd_set_status(args)`（放在 root 存在性检查之后，与 move/board/write-tree 并列）。
- **acceptance_criteria**: 见下 TDD 四路径全绿。
- [ ] Step 1: 写失败测试：
  ```python
  class SetStatusTest(unittest.TestCase):
      def setUp(self): self.d = tempfile.mkdtemp(); self.root = _make_tree(self.d, leaf_id="user.auth.login", status="captured")
      def _run(self, leaf, to): 
          import argparse; a = argparse.Namespace(cmd="set-status", root=self.root, leaf=leaf, to=to); return backlog.cmd_set_status(a)
      def test_success(self):
          self.assertEqual(self._run("user.auth.login","built"), 0)
          self.assertEqual(_read_status(self.root,"user.auth.login"), "built")
      def test_allow_any_backward(self):
          self._run("user.auth.login","validated"); self.assertEqual(self._run("user.auth.login","spec'd"),0)  # 回退也允许
      def test_bad_value(self): self.assertEqual(self._run("user.auth.login","banana"), 1)
      def test_missing_leaf(self): self.assertEqual(self._run("nope.x.y","built"), 2)
  ```
  （_read_status：读叶 frontmatter status 的小 helper，没有就加。）
- [ ] Step 2: `python3 scripts/test_backlog.py -k SetStatus` → FAIL（cmd_set_status 不存在）。
- [ ] Step 3: 按 action 实现 + 注册。
- [ ] Step 4: `python3 scripts/test_backlog.py -k SetStatus` → PASS。
- [ ] Step 5: `git commit -am "feat(backlog): set-status op(机械写叶 status,allow-any 迁移)"`

---

## Phase P3: post-checkout 钩子 + onboard 脚手架装钩子

**目标**: 切分支时 git 自动把当前 STATE.source-leaf 叶 status flush 落盘（硬保证）。
**覆盖需求(traceability)**: spec §4（三件套硬层 + 覆盖矩阵"同工作目录切分支"）+ §5.2。
**depends_on**: [P2]   **wave**: 3（与 P4/P5 并行：改 hooks 模板 + onboard SKILL，不碰 backlog.py 也不碰 driver SKILL）
**为什么这样拆**: 钩子是独立交付物（模板文件 + 安装规程），与 reconcile/看板互不碰文件。

**must_haves**:
- truths: ① 装上钩子后 `git checkout 别的分支` 触发 flush，当前 source-leaf 叶 status 被改成 STAGE_TO_STATUS[stage]；② 切文件（非分支）不动作；③ flush 失败/无 STATE/source-leaf=(none) → 静默 exit 0 不阻断 checkout。
- artifacts: `skills/sdlc/references/templates/hooks/post-checkout`、`skills/sdlc-onboard/SKILL.md`（Phase D 步 5 装钩子从 2→3）。
- key_links: 钩子调 `backlog.py set-status`（P2）；查找 backlog.py 仿 pre-commit 查找 sdlc-guard 的候选路径模式。

**可观察成功标准**: dogfood —— 起一个特性(source-leaf=X, stage=build)→ `git checkout main` → X 叶文件 status 变 built；`git checkout` 一个文件不触发。

### Task P3-T1: 写 post-checkout 钩子模板
- **requirements**: spec §5.2
- **files**: skills/sdlc/references/templates/hooks/post-checkout
- **read_first**: skills/sdlc/references/templates/hooks/pre-commit（查找 guard 的候选路径模式 + repo_root 取法）；spec §5.2 钩子伪码
- **action**: 新建纯 sh 钩子（git post-checkout 传 $1=prev_HEAD $2=new_HEAD $3=branch_flag）：
  ```sh
  #!/bin/sh
  # sdlc-pilot post-checkout —— 切分支时把当前在飞特性的源叶 status flush 落盘。
  # git 在每次 checkout 后自动跑;branch_flag=1 才是真切分支(0=切文件,不动作)。
  # 永不阻断 checkout(失败只警告 exit 0)。装:onboard 脚手架 / 手动 cp 到 .git/hooks/post-checkout && chmod +x。
  [ "$3" = "1" ] || exit 0
  repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
  STATE="$repo_root/.sdlc/STATE.md"; [ -f "$STATE" ] || exit 0
  val(){ grep -iE "^$1:" "$STATE" 2>/dev/null | head -1 | sed "s/^[^:]*: *//" | tr -d '\r' | sed 's/^ *//;s/ *$//'; }
  leaf=$(val source-leaf); stage=$(val stage)
  [ -n "$leaf" ] && [ "$leaf" != "(none)" ] || exit 0
  # stage→status 映射(与 backlog.STAGE_TO_STATUS 一致)
  case "$stage" in
    spec) to="spec'd";; plan) to="planned";; build) to="built";;
    validate|review) to="validated";; ship) to="shipped";; *) exit 0;;
  esac
  # 找 backlog.py(仿 pre-commit 找 guard)
  bk=""
  for c in "$repo_root/scripts/backlog.py" "$HOME/.claude/skills/sdlc-backlog/scripts/backlog.py"; do
    [ -f "$c" ] && { bk="$c"; break; }
  done
  [ -n "$bk" ] || exit 0
  req="$repo_root/.sdlc/requirements"; [ -d "$req" ] || exit 0
  python3 "$bk" set-status --root "$req" --leaf "$leaf" --to "$to" >/dev/null 2>&1 \
    || echo "ℹ post-checkout: flush 叶 '$leaf' status 失败(非阻断)" >&2
  exit 0
  ```
  注意：sdlc-pilot 自身无 requirements 树（用 Deferred 队列），故对本仓钩子是 no-op（`[ -d "$req" ]` 守住）——这正确，本特性给的是**目标项目**用的能力。
- **acceptance_criteria**: `sh -n skills/sdlc/references/templates/hooks/post-checkout`（语法检查）exit 0；模拟：造一个临时 repo + .sdlc/STATE.md(source-leaf=X,stage=build) + .sdlc/requirements 含 X 叶，跑 `sh post-checkout x x 1` 后 X 叶 status=built；跑 `sh post-checkout x x 0` 不变。
- **acceptance_criteria（dogfood 补充）**: 留 validate 阶段在带树的 fixture 上验。
- （非 TDD 五步：sh 钩子，acceptance 用语法检查 + 上面的模拟脚本验证；不要求贴 pytest。）

### Task P3-T2: onboard Phase D 脚手架装钩子 2→3
- **requirements**: spec §5.2
- **files**: skills/sdlc-onboard/SKILL.md
- **read_first**: skills/sdlc-onboard/SKILL.md Phase D 步 5（装 pre-commit/pre-push 询问那段）
- **action**: 把装 hook 的询问从两个扩到三个，加 post-checkout 选项与说明：在询问文案加一行
  `· post-checkout:切分支时自动把在飞特性的源叶 status flush 落盘(防中间态丢失)`；
  选装逻辑加：拷 `references/templates/hooks/post-checkout` 到 `<repo>/.git/hooks/post-checkout` 并 chmod +x；选项编号相应调整（如 `1) 都装 2) 仅 pre-commit 3) 仅 pre-push 4) 仅 post-checkout 5) 跳过`，或保持"都装(推荐)"含三者）。装完一句话说明 post-checkout 管什么。
- **acceptance_criteria**: `bash scripts/validate-skills` PASS（SKILL.md 结构/引用一致）；grep onboard SKILL 能看到 post-checkout 出现在 Phase D 装钩子段。

---

## Phase P4: driver §1.1 reconcile 规程

**目标**: driver 每次入口对账，把落后于 STATE.stage 的源叶 status 补齐（软层兜底）。
**覆盖需求(traceability)**: spec §4（三件套软层 + 覆盖矩阵"非 driver 覆盖/Codex/worktree"）+ §5.2。
**depends_on**: [P2]   **wave**: 3（改 driver SKILL.md，与 P3 改 hooks/onboard、P5 改 backlog.py 互不碰文件）
**为什么这样拆**: 纯 driver SKILL.md 规程（markdown playbook，dogfood 验），独立。

**must_haves**:
- truths: ① driver §1.1 边界自检后多一步 reconcile：读 STATE.source-leaf 叶当前 status，若其在 STATUS_ORDER 的序 < STAGE_TO_STATUS[stage] 的序 → 调 `backlog.py set-status` 补齐（只前进不回退）；② source-leaf=(none) 或无树 → 跳过；③ 可移植（纯调脚本，无并行依赖，Codex 也能跑）。
- artifacts: skills/sdlc/SKILL.md（§1.1）。
- key_links: 调 P2 的 set-status；序比较用 STATUS_ORDER。

**可观察成功标准**: dogfood —— STATE.stage=build 但源叶 status=captured（模拟漏 flush）→ 跑一次 driver 入口 → 叶 status 被补成 built。

### Task P4-T1: driver §1.1 加 reconcile 规程
- **requirements**: spec §5.2
- **files**: skills/sdlc/SKILL.md
- **read_first**: skills/sdlc/SKILL.md §1.1（并发/边界自检，sdlc-guard 调用那段）；spec §4 三件套软层 + §5.2 driver reconcile
- **action**: 在 §1.1 边界守卫之后加一小节"§1.1b 源叶状态对账(reconcile)"：规程描述——
  「读完 STATE 且边界一致后：若 `STATE.source-leaf` 非 `(none)` 且 `<repo>/.sdlc/requirements/` 存在 → 取该叶当前 status，与 `STAGE_TO_STATUS[STATE.stage]` 比较（按 STATUS_ORDER 的序）；当前序 **更靠前**（落后）→ 调 `python3 scripts/backlog.py set-status --root .sdlc/requirements --leaf <source-leaf> --to <映射值>` 补齐（**只前进不回退**：lifecycle 权威盖过 draft，但不把已更靠后的叶降级）。失败非阻断，记一行提示。这是三件套软层：兜住 post-checkout 漏掉的（Codex 无钩子 / worktree / 非 git-checkout 覆盖 STATE）。可移植：纯调脚本。」
  附 stage→status 映射表引用（指向 backlog.STAGE_TO_STATUS，不在 SKILL 里重复硬编码顺序，只说"见 backlog.py STATUS_ORDER/STAGE_TO_STATUS"）。
- **acceptance_criteria**: `bash scripts/validate-skills` PASS；driver SKILL §1.1 出现 reconcile 规程，且明确"只前进不回退"+"可移植纯调脚本"+"失败非阻断"。dogfood 在 validate 阶段验。

---

## Phase P5: 看板惰性叠加渲染（live badge）

**目标**: 看板对在飞特性的源叶叠加显示当前 stage 的 live badge（惰性派生，不写文件）。
**覆盖需求(traceability)**: spec §5.3 惰性叠加 + §4 C 混合 + DESIGN.md §8.2。
**depends_on**: [P2]   **wave**: 3（改 backlog.py render_board/cmd_board，与 P3/P4 改 SKILL/hooks 不碰同文件；但与 P6 同碰 render_board → P6 在 P5 后）
**为什么这样拆**: 惰性叠加是看板重构的地基（先有 live 数据通道，P6 再堆 4 痛点 UI）。

**must_haves**:
- truths: ① cmd_board 读 `<root>/../STATE.md`（存在则解析 source-leaf+stage）；② render_board 对 source-leaf 命中叶在 status 徽章旁渲染 live badge（`⏳ <stage>中`）；③ 无 STATE/无 source-leaf → 不渲染 badge，HTML 与现状一致（向后兼容）。
- artifacts: scripts/backlog.py（cmd_board + render_board + 一个 _read_state_overlay helper）、test_backlog.py（BoardLiveBadgeTest）。
- key_links: render_board 新增参数 `live=None`（{leaf_id, stage}）；cmd_board 传入。

**可观察成功标准**: `python3 scripts/test_backlog.py` 含 BoardLiveBadgeTest 全绿（有 STATE→HTML 含 live badge + 目标叶 id；无 STATE→不含）。

### Task P5-T1: cmd_board 读 STATE + render_board 渲染 live badge
- **requirements**: spec §5.3, DESIGN.md §8.2
- **files**: scripts/backlog.py, scripts/test_backlog.py
- **read_first**: scripts/backlog.py:376-450（render_board，特别 leaf badge 那行 `<span class="badge status-...">`）；:451+（cmd_board）；P1 的 STAGE_TO_STATUS
- **action**:
  1. 加 helper：
     ```python
     def _read_state_overlay(req_root):
         """读 <req_root>/../STATE.md → {leaf, status} 供看板叠加;无/不可解析→None。"""
         state = os.path.join(os.path.dirname(os.path.abspath(req_root.rstrip("/"))), "STATE.md")
         if not os.path.isfile(state): return None
         txt = open(state, encoding="utf-8").read()
         def v(k):
             m = re.search(rf"(?mi)^{k}:\s*(.+)$", txt)
             return m.group(1).strip() if m else ""
         leaf, stage = v("source-leaf"), v("stage")
         if not leaf or leaf == "(none)": return None
         to = STAGE_TO_STATUS.get(stage)
         return {"leaf": leaf, "stage": stage, "status": to} if to else None
     ```
  2. `render_board(tree, leaves, title=..., live=None)`：在生成 leaf badge 处，若 `live and live["leaf"]==lf.get("id")` → 在 status 徽章后追加
     `<span class="live-badge" title="在飞:{stage}">⏳ {esc(live["stage"])}中</span>`。
  3. cmd_board 调 `live=_read_state_overlay(args.root)` 并传给 render_board。
- **acceptance_criteria**: 见 TDD。
- [ ] Step 1: 写失败测试 BoardLiveBadgeTest：造树(叶 user.auth.login) + 写 `<root>/../STATE.md`(source-leaf: user.auth.login / stage: build)；调 cmd_board 生成 HTML → assert `live-badge` 与 `build中` 在 HTML；删 STATE 再渲染 → assert `live-badge` 不在 HTML。
- [ ] Step 2: `python3 scripts/test_backlog.py -k BoardLiveBadge` → FAIL。
- [ ] Step 3: 按 action 实现。
- [ ] Step 4: PASS。
- [ ] Step 5: `git commit -am "feat(backlog): 看板惰性叠加在飞特性 live badge(读 STATE)"`

---

## Phase P6: 看板 4 痛点重构 + 文档/版本

**目标**: 看板解决 4 痛点，按 DESIGN.md §8 契约；CHANGELOG + 版本 0.16.0。
**覆盖需求(traceability)**: spec §5.3 ①②③④ + §6 验收 + §7b 设计契约 + DESIGN.md §8。
**depends_on**: [P5]   **wave**: 4（与 P5 同碰 render_board/BOARD_CSS/CHAT_JS）
**为什么这样拆**: 纯前端渲染增强，量大，单列一阶段；放最后因与 P5 同文件、且要等 live 通道就位。

**must_haves**:
- truths（对照 DESIGN.md §8）: ① 进度分布条按 STATUS_ORDER 分段 + 顶部图例 6 色 + 点图例筛状态；② 搜索框即时过滤 + 折叠态 localStorage 记忆 + 选中叶面包屑；③ 叶详情 4 组分组 + depends_on 可点跳转 + 字段 tooltip；④ 聊天面板头部监听状态提示 + 空态引导。
- artifacts: scripts/backlog.py（render_board/BOARD_CSS/CHAT_JS/_leaf_detail_map）、test_backlog.py（断言关键 HTML 锚点）、CHANGELOG.md、.claude-plugin/{plugin,marketplace}.json、DESIGN.md（已在 spec 阶段更新，本阶段只校对一致）。
- key_links: 进度条复用 cov_items 升级；状态过滤/搜索/折叠记忆是 CHAT_JS（或新 BOARD_JS）；depends_on 可点用叶 id 白名单跳转。

**可观察成功标准**: correctness —— test_backlog.py 断言 HTML 含图例容器/分段进度条/搜索框/字段分组/可点 depends_on/聊天状态提示；人工起服看 examples/requirements-fixture 效果（验收在 validate）。

### Task P6-T1: 进度分布条 + 图例 + 状态过滤（痛点①）
- **requirements**: spec §5.3①, DESIGN.md §8.1
- **files**: scripts/backlog.py（render_board cov 段 + BOARD_CSS + JS）, test_backlog.py
- **read_first**: scripts/backlog.py:382-393（cov_items 现状 shipped/total）；:194-199（status CSS）；DESIGN.md §8.1
- **action**: ① cov_items 从单 shipped/total 升级为**按 STATUS_ORDER 分段**：每域统计各 status 计数，渲染 `<div class="dist">` 内多段 `<i class="seg status-X" style="width:%">`（段 title="status·N"）；顶部加全树总分布条。② 顶部加**图例** `<div class="legend">` 6 个 `<span class="lg status-X">含义</span>`。③ 点图例项 → JS 给 body 加 `data-filter=X`，CSS 高亮/淡化非该 status 叶。BOARD_CSS 加 .dist/.seg/.legend/.lg + filter 态样式（用 §2.1 既有 status 色，对比达 AA）。
- **acceptance_criteria**: test 断言 HTML 含 `class="legend"` + 6 个 status 段 + `class="dist"`；起服点图例某状态→非该状态叶变淡（人工/validate 验）。

### Task P6-T2: 搜索 + 折叠记忆 + 面包屑（痛点②）
- **requirements**: spec §5.3②, DESIGN.md §8.4
- **files**: scripts/backlog.py（render_board 顶部加搜索框 + JS + 面包屑容器）, test_backlog.py
- **read_first**: scripts/backlog.py:255（CHAT_JS）；render_board body/details 生成段；DESIGN.md §8.4
- **action**: ① 顶部加 `<input id="tree-search" placeholder="搜索 id/title…">`，JS 监听 input 即时隐藏不匹配 `.leaf`（match id 或 title，子串不分大小写）；空查询全显。② `<details>` 的 toggle 事件把 open 态存 localStorage（key=domain/subdomain 名），渲染后 JS 读 localStorage 恢复折叠态。③ 选中叶时在聊天头或树顶渲染面包屑 `domain › subdomain › leaf`（各级 span 可点回跳/展开）。JS 注意：localStorage 不可用（隐私模式）时静默降级。
- **acceptance_criteria**: test 断言 HTML 含 `id="tree-search"` + 面包屑容器 id；起服搜索过滤即时、刷新保折叠（人工/validate 验）。

### Task P6-T3: 叶详情字段分组 + depends_on 可点 + tooltip（痛点③）
- **requirements**: spec §5.3③, DESIGN.md §8.3
- **files**: scripts/backlog.py（_leaf_detail_map + CHAT_JS renderDetail + DETAIL CSS）, test_backlog.py
- **read_first**: scripts/backlog.py:255-290（CHAT_JS，renderDetail/DETAIL_KEYS/innerHTML）；_leaf_detail_map；DESIGN.md §8.3
- **action**: renderDetail 改为按 **4 组**渲染（身份 id/title/status/priority｜定位 domain_path/old_system_ref/new_domain_path｜关系 depends_on/cross_link｜交叉 actor/failure_class/contract_refs/data_owner/risk_level），每组小标题。depends_on 每项渲染成 `<a class="dep-link" data-goto="ID">ID</a>`，JS 点击 → 选中并 scrollIntoView 目标叶（仅当 ID 在已知叶集合，否则纯文本）。字段名加 `title=` tooltip（actor/failure_class/contract_refs/data_owner 含义；failure_class 说明枚举四类）。innerHTML 仍只注入受控树字段 + 白名单 id。
- **acceptance_criteria**: test 断言 leaf-data/detail 渲染含 4 组小标题 + `dep-link` + tooltip title 属性；起服点 depends_on 跳到目标叶（人工/validate 验）。

### Task P6-T4: 聊天面板状态提示 + 引导（痛点④）
- **requirements**: spec §5.3④, DESIGN.md §8.5
- **files**: scripts/backlog.py（chat_panel 头部 + CHAT_JS + CSS）, test_backlog.py
- **read_first**: scripts/backlog.py:418-430（chat_panel 生成）；CHAT_JS 的 /wait /rev 轮询逻辑；DESIGN.md §8.5
- **action**: chat_panel 头部加监听状态指示 `<span id="live-status">`，JS 据是否正在 /wait 轮询/收到 rev 切换 🟢「Live 监听中」/⚪「未监听 — 需 agent 切 live」。空消息态文案改为引导：说明 chatbot=在场 agent、要实时须让 agent 切 live 监听（占会话），附一句"agent 未监听时你的留言会被 /feedback 收集，agent 下次处理"。
- **acceptance_criteria**: test 断言 HTML 含 `id="live-status"` + 引导文案关键词；人工看状态切换（validate 验）。

### Task P6-T5: CHANGELOG + 版本 0.16.0 + DESIGN 一致校对
- **requirements**: spec §6（版本）, CLAUDE.md 提交纪律
- **files**: CHANGELOG.md, .claude-plugin/plugin.json, .claude-plugin/marketplace.json
- **read_first**: CHANGELOG.md 顶部（0.15.0 条目格式）；两个 json 的 version 字段（现 0.15.0）
- **action**: CHANGELOG 加 `## [0.16.0]` 条目（生命周期状态同步：STATUS 枚举/lint/set-status/post-checkout 钩子/driver reconcile + 看板重构 4 痛点 + live badge）；plugin.json/marketplace.json version 0.15.0→0.16.0；marketplace plugin description 补"叶生命周期状态同步 + 看板重构"。校对 DESIGN.md §8 与实现一致（如有渲染细节偏差回改 DESIGN 或实现取齐）。
- **acceptance_criteria**: `grep 0.16.0 .claude-plugin/plugin.json .claude-plugin/marketplace.json CHANGELOG.md` 三处命中；`bash scripts/validate-skills` PASS。

---

## Source Audit（出口门控，§6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|---|---|---|---|---|
| GOAL | — | 状态可信 + 看板可读 | P1-P6 | COVERED |
| REQ | A1 status 权威枚举 | P1-T1 | P1-T1 | COVERED |
| REQ | A2 lint 校验 status | P1-T2 | P1-T2 | COVERED |
| REQ | A-setstatus set-status op | P2-T1 | P2-T1 | COVERED |
| REQ | 保证-硬层 post-checkout 切分支必 flush | P3-T1/T2 | P3 | COVERED |
| REQ | 保证-软层 driver reconcile | P4-T1 | P4 | COVERED |
| REQ | B-惰性 看板叠加 live badge | P5-T1 | P5 | COVERED |
| REQ | B① 进度/图例/过滤 | P6-T1 | P6-T1 | COVERED |
| REQ | B② 搜索/折叠记忆/面包屑 | P6-T2 | P6-T2 | COVERED |
| REQ | B③ 字段分组/depends_on 可点/tooltip | P6-T3 | P6-T3 | COVERED |
| REQ | B④ 聊天状态提示/引导 | P6-T4 | P6-T4 | COVERED |
| DECISION | C 混合写回 | P5(惰性)+P3/P4(flush)+现有 Retire(shipped) | P3/P4/P5 | COVERED |
| DECISION | 三件套强制 | P2(op)+P3(钩子)+P4(reconcile) | P2/P3/P4 | COVERED |
| DECISION | allow-any-set | P2-T1(test_allow_any_backward) | P2-T1 | COVERED |
| DECISION | 设计契约 DESIGN.md §8 | spec 阶段已更新 + P6-T5 校对 | P6-T5 | COVERED |
| EVAL-CRIT | — | N/A（非 AI） | — | N/A |

Coverage Gate（反向）：每个 Task 的 requirements 字段均非空指回 spec 条款。✓

## 风险 / 关键决策点

- **backlog.py 逼近 800 行铁律**：本特性再加 STATUS 常量 + cmd_set_status + _read_state_overlay + render_board/CHAT_JS 大改。build 时若过 800 行 → 评估拆模块（但纯 stdlib 单文件可移植性要权衡；可作 Deferred 或本期最后处理）。**这是 build 阶段要盯的爆量点**。
- **P3 钩子对 sdlc-pilot 自身是 no-op**（无 requirements 树）→ 钩子/reconcile 的真实行为只能在**带树的 fixture/目标项目** dogfood 验，不能靠 sdlc-pilot 自身验。validate 阶段需造带树 fixture。
- **同 wave 文件冲突已规避**：P3(hooks/onboard SKILL)、P4(driver SKILL)、P5(backlog.py render_board) 三者 wave3 不碰同文件；P6 与 P5 同碰 render_board 故 wave4。
