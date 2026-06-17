# Plan: 工程代码 → backlog 树生成器（capability 主轴 + 4 交叉视图）

> 来源 spec: .sdlc/spec.md（已批准，网页审 3 意见已处置）
> 复杂度等级: **L3** —— 理由: 子系统级（agent 分析 playbook + 确定性脚本落盘 + 叶数据模型扩展 + 看板渲染 + 多 agent 编排），多依赖、需独立 dogfood 验证。
> 生成: 2026-06-16
> Active roles: skill-maintainer (R10), qa, architect（子系统/数据模型变更） ｜ Validate modes: correctness + dogfood(vendor-research)

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | 叶 schema 4 可选交叉字段 + lint 校验 | R-fields, D-optional | — | 1 |
| P2 | `write-tree` 脚本 op（tree JSON→叶文件） | R-write, R-script | P1 | 2 |
| P3 | #4 看板叶详情显示 4 交叉字段 | R-board-show（a1） | P1 | 3 |
| P4 | 生成 playbook（Seed 升级 + 多 agent 编排） | R-gen, R-axis, R-granularity, R-input, R-multiagent, R-humangate | P1,P2,P3 | 4 |
| P5 | 文档 + 版本 0.14.0 同步 | R-docsync | P4 | 5 |

> P1/P2/P3 都改 `backlog.py`（同文件）→ 串行波次。P4=SKILL.md（playbook，markdown 不单测，靠 P-dogfood 验证）。dogfood 验证（对 vendor-research 跑生成器）属 **validate 阶段**（§6 验收），不在 build 任务内。

---

## Phase P1: 叶 schema 4 可选交叉字段 + lint 校验

**目标**: 叶 frontmatter 支持 4 个可选交叉字段，lint 校验其合法性，存量树（无这些字段）仍 clean。
**覆盖需求(traceability)**: R-fields（4 交叉字段）, D-optional（可选非必填，REQUIRED_FIELDS 不变）
**depends_on**: []　**wave**: 1
**为什么这样拆**: 字段是 write-tree(P2)写入、看板(P3)显示、playbook(P4)推断的共同契约 —— 契约先行。

**must_haves**:
- truths: 叶含/不含 actor/failure_class/contract_refs/data_owner 都 lint clean；failure_class 非法值 → lint 报错；contract_refs 非 list → 报错；REQUIRED_FIELDS 仍只 10 个（存量树不受影响）。
- artifacts: `scripts/backlog.py`（+常量+lint 扩展）、`scripts/test_backlog.py`（+用例）、`skills/sdlc-backlog/SKILL.md §1.2`（文档）。
- key_links: cmd_lint 读叶 → 若 4 字段存在则校验取值。

**可观察成功标准**: `python3 scripts/test_backlog.py LintCrossFieldTest -v` 全 PASS。

### Task P1-T1: lint 扩展校验 4 可选字段（TDD）
- **requirements**: R-fields, D-optional
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `scripts/backlog.py:21-26`(REQUIRED_FIELDS/PRIORITY_ORDER)、`cmd_lint`(全函数)、`scripts/test_backlog.py:13-48`(write_leaf/run)、`.sdlc/spec.md §4.3`
- **action**: 在 backlog.py 加常量 `FAILURE_CLASSES = {"funds", "consistency", "compliance", "experience"}`（对应 spec 资金正确性/数据一致性/合规信任/体验，用 ascii token 便于看板 CSS 类）。在 `cmd_lint` 的逐叶循环里追加可选字段校验：`fc = lf.get("failure_class"); if fc and fc not in FAILURE_CLASSES: problems.append(f"bad-failure-class: {lid} failure_class='{fc}' 不在 {sorted(FAILURE_CLASSES)}")`；`cr = lf.get("contract_refs"); if cr is not None and not isinstance(cr, list): problems.append(f"bad-contract-refs: {lid} contract_refs 须为 list")`。actor/data_owner 不限枚举（任意非空串，不校验）。**不动 REQUIRED_FIELDS**（4 字段非必填）。注意 `parse_frontmatter` 把 `key: [a, b]` 解析为 list、`key: scalar` 为 str——failure_class 是 scalar、contract_refs 是 list。
- **acceptance_criteria**: `python3 scripts/test_backlog.py LintCrossFieldTest -v` PASS；全量回归 PASS（存量 LintTest/RetireTest 不受影响）。

- [ ] Step 1: 写失败测试 — `test_backlog.py` 加（注意 write_leaf 现不支持额外字段，测试里手动追加 frontmatter 行）：
  ```python
  def _write_leaf_extra(root, id, extra_lines):
      domain_path = "/".join(id.split(".")[:2])
      d = os.path.join(root, *domain_path.split("/")); os.makedirs(d, exist_ok=True)
      fm = (f"---\nid: {id}\ntitle: t\ndomain_path: {domain_path}\ncross_link: []\n"
            f"old_system_ref: r-{id}\nnew_domain_path: {domain_path}\nstatus: captured\n"
            f"priority: P2\ndepends_on: []\nrisk_level: medium\nupdated: 2026-06-16\n"
            + extra_lines + "---\n\n## 需求描述\nx\n")
      with open(os.path.join(d, id + ".md"), "w", encoding="utf-8") as f: f.write(fm)

  class LintCrossFieldTest(unittest.TestCase):
      def test_valid_cross_fields_clean(self):
          with tempfile.TemporaryDirectory() as root:
              _write_leaf_extra(root, "order.checkout.a",
                  "actor: 运营\nfailure_class: funds\ncontract_refs: [contracts/provided/bff]\ndata_owner: order-svc\n")
              r = run("lint", root=root)
              self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
      def test_no_cross_fields_still_clean(self):  # 存量树
          with tempfile.TemporaryDirectory() as root:
              write_leaf(root, "order.checkout.a")
              self.assertEqual(run("lint", root=root).returncode, 0)
      def test_bad_failure_class_flagged(self):
          with tempfile.TemporaryDirectory() as root:
              _write_leaf_extra(root, "order.checkout.a", "failure_class: 乱写\n")
              r = run("lint", root=root)
              self.assertNotEqual(r.returncode, 0)
              self.assertIn("bad-failure-class", r.stdout + r.stderr)
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py LintCrossFieldTest -v` → 期望 FAIL（无 FAILURE_CLASSES/无校验，bad-failure-class 测试不报错）。
- [ ] Step 3: 写实现（FAILURE_CLASSES 常量 + cmd_lint 追加两条校验）。
- [ ] Step 4: 跑 `LintCrossFieldTest -v` PASS + 全量 `python3 scripts/test_backlog.py` PASS。
- [ ] Step 5: 提交 `git commit -m "feat(backlog): 叶 4 可选交叉字段 + lint 校验(failure_class 枚举/contract_refs list)"`

### Task P1-T2: SKILL §1.2 schema 文档补 4 可选字段（非 TDD）
- **requirements**: R-fields
- **files**: `skills/sdlc-backlog/SKILL.md`
- **read_first**: `skills/sdlc-backlog/SKILL.md:76-99`（§1.2 叶 schema 10 字段块）
- **action**: §1.2 在 10 必填字段后加"**4 可选交叉视图字段**（生成器填，非必填，lint 不强制；存量叶不填仍 clean）"小节：`actor`(参与者/角色)、`failure_class`(失败代价类，枚举 funds/consistency/compliance/experience)、`contract_refs`(list，关联契约路径)、`data_owner`(数据真相源)。注明 generator(#6) 推断填入、看板显示、lint 校验取值。
- **acceptance_criteria**: SKILL §1.2 含 4 可选字段说明；`bash scripts/validate-skills` PASS。

---

## Phase P2: `write-tree` 脚本 op（tree JSON → 叶文件）

**目标**: 确定性地把 orchestrator 合并出的树 JSON 落成叶 `.md` 文件（机械落盘，与 agent 判断分离）。
**覆盖需求(traceability)**: R-write（落盘）, R-script（机械部分=脚本）
**depends_on**: [P1]　**wave**: 2
**为什么这样拆**: 落盘是机械确定性的（路径/frontmatter 拼装），最该脚本化 + TDD；与 P4 的 agent 分析判断解耦（agent 产 JSON，脚本写文件）。

**must_haves**:
- truths: `write-tree --root R --from tree.json` 把每片叶写到 `R/<domain_path>/<id>.md`，frontmatter 含 10 必填 + 出现的可选字段，body 用 leaf.body 或默认三段模板；已存在叶默认跳过（不覆盖人工改动）；写完报 {written, skipped}；产物 `lint` clean。
- artifacts: `scripts/backlog.py`（+`cmd_write_tree`）、`scripts/test_backlog.py`（+`WriteTreeTest`）。
- key_links: main 加 `write-tree` subparser（--root + --from）；dispatch `cmd_write_tree`。

**可观察成功标准**: `python3 scripts/test_backlog.py WriteTreeTest -v` PASS。

### Task P2-T1: 写 `write-tree` 命令（TDD）
- **requirements**: R-write, R-script
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `scripts/backlog.py`(parse_frontmatter/load_leaves/cmd_move 写文件法/main subparser 区)、`scripts/test_backlog.py`(run/_read)、`.sdlc/spec.md §5.1 ③/§5.2`
- **action**: 加 `LEAF_OPTIONAL = ["actor","failure_class","contract_refs","data_owner"]`。加 `cmd_write_tree(args)`：读 `args.from_`（JSON：`{"leaves":[{id,title,domain_path,cross_link,old_system_ref,new_domain_path,status,priority,depends_on,risk_level, actor?,failure_class?,contract_refs?,data_owner?, body?}]}`）；对每片叶——若 `os.path.exists(目标)` 则 skip+计数；否则按 `domain_path` 建目录、拼 frontmatter（10 必填按固定顺序 + 出现的 LEAF_OPTIONAL + `updated`），list 字段写 `[a, b]` 格式（与 parse_frontmatter 互逆），body 用 `leaf.get("body")` 或默认 `## 需求描述\n（待补）\n\n## 验收线索\n（待补）\n\n## 老系统行为参照\n（待补）`，写文件。末 `print(json.dumps({"written":n,"skipped":m,"root":root}))`。main 加 `pw=sub.add_parser("write-tree"); pw.add_argument("--root",required=True); pw.add_argument("--from",dest="from_",required=True)` + `if args.cmd=="write-tree": return cmd_write_tree(args)`（放 board 旁，注意 write-tree 也用 --root 走 isdir 检查）。
- **acceptance_criteria**: `python3 scripts/test_backlog.py WriteTreeTest -v` PASS；写出的树 `lint` clean。

- [ ] Step 1: 写失败测试：
  ```python
  class WriteTreeTest(unittest.TestCase):
      def test_writes_leaves_with_optional_fields(self):
          with tempfile.TemporaryDirectory() as root:
              tree = {"leaves": [
                  {"id":"order.checkout.place","title":"作为采购我要下单以便采货","domain_path":"order/checkout",
                   "cross_link":[],"old_system_ref":"apps/api/modules/order","new_domain_path":"order/checkout",
                   "status":"captured","priority":"P1","depends_on":[],"risk_level":"high",
                   "actor":"采购","failure_class":"consistency","contract_refs":["contracts/provided/bff"],"data_owner":"order-svc"}]}
              fp = os.path.join(root, "tree.json")
              with open(fp,"w",encoding="utf-8") as f: json.dump(tree,f,ensure_ascii=False)
              r = run("write-tree", "--from", fp, root=root)
              self.assertEqual(r.returncode, 0, r.stderr)
              leaf = _read(os.path.join(root,"order","checkout","order.checkout.place.md"))
              self.assertIn("id: order.checkout.place", leaf)
              self.assertIn("failure_class: consistency", leaf)
              self.assertIn("actor: 采购", leaf)
              self.assertIn("作为采购我要下单", leaf)
              self.assertEqual(run("lint", root=root).returncode, 0, "写出的树应 lint clean")
              self.assertEqual(json.loads(r.stdout)["written"], 1)
      def test_skips_existing_leaf(self):
          with tempfile.TemporaryDirectory() as root:
              write_leaf(root, "order.checkout.a", title="原有")
              tree = {"leaves":[{"id":"order.checkout.a","title":"新的","domain_path":"order/checkout",
                  "cross_link":[],"old_system_ref":"r","new_domain_path":"order/checkout","status":"captured",
                  "priority":"P2","depends_on":[],"risk_level":"low"}]}
              fp=os.path.join(root,"t.json")
              with open(fp,"w",encoding="utf-8") as f: json.dump(tree,f,ensure_ascii=False)
              r = run("write-tree","--from",fp,root=root)
              self.assertEqual(json.loads(r.stdout)["skipped"], 1)
              self.assertIn("原有", _read(os.path.join(root,"order","checkout","order.checkout.a.md")))  # 未覆盖
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py WriteTreeTest -v` → FAIL（write-tree 未注册）。
- [ ] Step 3: 写 `cmd_write_tree` + LEAF_OPTIONAL + main 注册。
- [ ] Step 4: `WriteTreeTest -v` PASS + 全量回归 PASS。
- [ ] Step 5: `git commit -m "feat(backlog): write-tree 脚本 op — tree JSON 落叶文件(含可选字段)+跳过已存在"`

---

## Phase P3: #4 看板叶详情显示 4 交叉字段（a1）

**目标**: 看板叶详情面板显示 actor/failure_class/contract_refs/data_owner（有值才显示）。
**覆盖需求(traceability)**: R-board-show（a1 调整：基本显示纳入本期）
**depends_on**: [P1]　**wave**: 3
**为什么这样拆**: 字段定义(P1)后才能显示；与 write-tree(P2)解耦（看板只读渲染）。

**must_haves**:
- truths: board 的 `leaf-data` JSON 含 4 字段；选叶后详情面板渲染它们（有值显示、无值隐藏）。
- artifacts: `scripts/backlog.py`（`DETAIL_KEYS` + `CHAT_JS` 的 `renderDetail`）、`scripts/test_backlog.py`（BoardTest +1）。
- key_links: `_leaf_detail_map` 已带任意字段；`renderDetail`(CHAT_JS) 加渲染 4 字段行。

**可观察成功标准**: `python3 scripts/test_backlog.py BoardTest -v` PASS（含新断言）。

### Task P3-T1: 看板详情渲染 4 字段（结构断言 TDD）
- **requirements**: R-board-show
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `scripts/backlog.py` 的 `DETAIL_KEYS`/`_leaf_detail_map`/`render_board`/`CHAT_JS` 的 `renderDetail` 函数、`scripts/test_backlog.py` BoardTest
- **action**: `DETAIL_KEYS` 加 `actor/failure_class/contract_refs/data_owner`（使 leaf-data JSON 带它们）。`CHAT_JS` 的 `renderDetail()` 在 `.ld-meta` 后加一段：有值才渲染 `域:...` 下方追加 `<div class="ld-cross">参与者: <actor> · 失败类: <failure_class> · 数据源: <data_owner> · 契约: <contract_refs join></div>`，各字段 `d.actor?...:''` 缺省隐藏（用 esc()）。BOARD_CSS 加 `.ld-cross{font-size:11px;color:var(--muted);margin-bottom:6px}`。
- **acceptance_criteria**: `python3 scripts/test_backlog.py BoardTest -v` PASS。

- [ ] Step 1: 写失败测试 — BoardTest 加：
  ```python
  def test_board_leafdata_has_cross_fields(self):
      with tempfile.TemporaryDirectory() as root:
          # 手写带交叉字段的叶（同 P1 _write_leaf_extra 思路）
          d=os.path.join(root,"order","checkout"); os.makedirs(d)
          with open(os.path.join(d,"order.checkout.a.md"),"w",encoding="utf-8") as f:
              f.write("---\nid: order.checkout.a\ntitle: t\ndomain_path: order/checkout\ncross_link: []\n"
                      "old_system_ref: r\nnew_domain_path: order/checkout\nstatus: captured\npriority: P2\n"
                      "depends_on: []\nrisk_level: medium\nactor: 采购\nfailure_class: funds\n---\n\n## 需求描述\nx\n")
          out=os.path.join(root,"_b.html"); r=run("board","--out",out,root=root)
          self.assertEqual(r.returncode,0,r.stderr)
          html=_read(out)
          self.assertIn('"actor"', html)        # leaf-data JSON 含字段
          self.assertIn("ld-cross", html)        # 详情渲染交叉行的容器/类在 JS 里
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py BoardTest::test_board_leafdata_has_cross_fields -v` → FAIL。
- [ ] Step 3: 写实现（DETAIL_KEYS + renderDetail + CSS）。
- [ ] Step 4: `BoardTest -v` PASS + 全量回归 PASS。
- [ ] Step 5: `git commit -m "feat(backlog): 看板叶详情显示 4 交叉字段(a1 基本显示)"`

---

## Phase P4: 生成 playbook（sdlc-backlog Seed 升级 + 多 agent 编排）

**目标**: 把"分析 codebase → gen 出 capability/user-story 树"的判断性规程写进 sdlc-backlog SKILL（agent-playbook），含多 agent 两阶段编排 + 人审闸 + 调 write-tree/lint。
**覆盖需求(traceability)**: R-gen, R-axis（功能/用户故事主轴）, R-granularity（自适应+上限+禁工程术语）, R-input（复用 surface-map+深读）, R-multiagent（§5.6 两阶段 fan-out）, R-humangate（人审复用 #4 看板）
**depends_on**: [P1, P2, P3]　**wave**: 4
**为什么这样拆**: 它是判断性 playbook（markdown，不单测），消费 P1 的字段契约 + P2 的 write-tree + P3 的看板；放最后写，引用已定型的脚本接口。

**must_haves**:
- truths: SKILL 有"Seed 升级=生成树"章节，描述 §5 全机制（4 段数据流 + §5.6 多 agent 两阶段 + 人审 + 调 write-tree/lint）；约束做什么/避坑，不写死脆弱命令（铁律#4）；顶部 op 描述更新。
- artifacts: `skills/sdlc-backlog/SKILL.md`（§2 Seed 章节扩 + 新增生成子章节）。
- key_links: playbook → 调 `backlog.py write-tree`（P2）+ `lint`（P1）+ 人审复用 `board`（P3/#4）。

**可观察成功标准**: SKILL 含完整生成规程；`bash scripts/validate-skills` PASS；规程可被一个全新 agent 照着对 vendor-research 执行（dogfood 在 validate 验）。

### Task P4-T1: 写生成 playbook 章节
- **requirements**: R-gen, R-axis, R-granularity, R-input, R-multiagent, R-humangate
- **files**: `skills/sdlc-backlog/SKILL.md`
- **read_first**: `.sdlc/spec.md`（§5 全节 + §4 轴决策）、`skills/sdlc-backlog/SKILL.md:127-145`（§2 Seed 现状）、`skills/sdlc-onboard/SKILL.md:122-151`（Phase C surface-map，复用输入）
- **action**: 在 §2 Seed 后加"### 2.x 生成（从代码逆向出树，#6）"章节，含：①输入（复用 PROFILE.surface-map，无则先 onboard；深读 contracts/模块/schema/docs）；②主轴=**功能/用户故事**（domain=功能域/epic，叶=用户故事"作为<角色>要<能力>以便<价值>"，**禁工程术语**，工程细节进老系统参照/交叉字段）；③叶粒度自适应（对齐状态跃迁使 depends_on 无环，每域 ≤12 软上限防碎）；④推断 status（空骨架→captured/半成品→built/真实→shipped）+ 4 交叉字段（actor/failure_class/contract_refs/data_owner，能推断则填）；⑤**多 agent 两阶段**（orchestrator 归纳功能域列表→fan-out 一域一 agent 产叶各写草稿 `<tmp>/gen/<domain>.json`、互相隔离→orchestrator 合并：去重/cross_link/depends_on 无环/每域上限；Task-or-sequential 降级；单写者）；⑥人审预览（复用 #4 `board` 看板或网页审让人剪枝改）；⑦落盘=`backlog.py write-tree --from <merged.json>` + `lint` clean。**写成约束+原则+避坑，不写死命令一行流**（铁律#4，但 `write-tree`/`lint` 作契约命令可留）。顶部 frontmatter op 列举加"生成(代码→树)"。
- **acceptance_criteria**: SKILL 含上述 7 点；`bash scripts/validate-skills` PASS；自检：一个全新 agent 读该章节能不问就对 vendor-research 跑（措辞具体到可执行）。

---

## Phase P5: 文档 + 版本 0.14.0 同步

**目标**: CHANGELOG/版本/CLAUDE 迭代表与新能力一致。
**覆盖需求(traceability)**: R-docsync
**depends_on**: [P4]　**wave**: 5

### Task P5-T1: CHANGELOG + 版本 + 回归提交
- **requirements**: R-docsync
- **files**: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, （可选 `CLAUDE.md` 迭代表加"扩叶数据模型"行）
- **read_first**: `CHANGELOG.md:1-6`、`.claude-plugin/plugin.json`、`CLAUDE.md`「加/改 backlog 派生操作」行
- **action**: CHANGELOG 顶部加 `## [0.14.0]`（Added: backlog 生成能力——分析代码 gen capability/user-story 树 + write-tree op + 叶 4 可选交叉字段 + 看板显示；多 agent 两阶段编排；Notes: additive、不加顶层 skill、叶 schema 扩展为可选字段(REQUIRED 不变)、distilled-from `session:sdlc-tree-generator-2026-06-16`）。版本三处 0.13.0→0.14.0。CLAUDE 迭代表可加一行"扩叶数据模型→§1.2 + lint + write-tree + 看板 + validate-skills"。跑 `python3 scripts/test_backlog.py`（全绿）+ `bash scripts/validate-skills`（PASS）。`git commit -m "feat(backlog): 生成器 playbook + 文档 + version 0.14.0"`
- **acceptance_criteria**: 版本三处 0.14.0；CHANGELOG 有条目；测试 + validate-skills 全过。

---

## Source Audit（出口门控，§6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|--------|----|-----------|----------|------|
| GOAL | — | 分析代码 gen backlog 树（capability 主轴+4 交叉视图），喂 #4 闭环 | P1-P5 | COVERED |
| REQ | R-fields | 叶 4 可选交叉字段 + lint 校验 | P1-T1,T2 | COVERED |
| REQ | R-write/R-script | write-tree 脚本落盘（机械部分） | P2-T1 | COVERED |
| REQ | R-board-show | 看板显示 4 字段（a1） | P3-T1 | COVERED |
| REQ | R-gen | 生成规程（agent-playbook） | P4-T1 | COVERED |
| REQ | R-axis | 主轴=功能/用户故事（a2，PM 可读禁工程术语） | P4-T1 | COVERED |
| REQ | R-granularity | 自适应+对齐状态跃迁+每域上限 | P4-T1 | COVERED |
| REQ | R-input | 复用 onboard surface-map + 深读 | P4-T1 | COVERED |
| REQ | R-multiagent | 多 agent 两阶段编排（a3，§5.6） | P4-T1 | COVERED |
| REQ | R-humangate | 落盘前人审（复用 #4 看板） | P4-T1 | COVERED |
| REQ | R-docsync | SKILL/CHANGELOG/version 同步 | P1-T2, P4-T1, P5-T1 | COVERED |
| DECISION | D-optional | 4 字段可选非必填（REQUIRED 不变） | P1-T1 | COVERED |
| DECISION | D-script-vs-agent | 判断=playbook / 机械=脚本 | P2(脚本)+P4(playbook) | COVERED |
| VALIDATE | — | dogfood: vendor-research 跑生成器（§6） | validate 阶段（非 build 任务） | DEFERRED-to-validate |
| Deferred | — | 轴自动判定 / 看板高级交互 / 不依赖 onboard 深分析 | （spec §8 显式延后） | DEFERRED |

正向全 COVERED；反向每任务 requirements 非空。自查三扫（占位/类型一致[FAILURE_CLASSES/LEAF_OPTIONAL/DETAIL_KEYS/write-tree 命名前后一致]/spec 覆盖）通过。

## 风险 / 关键决策点
- **dogfood 验证（vendor-research）放 validate 阶段**：build 产出脚本+playbook；真跑生成器（多 agent 分析 vendor-research → 出树）= validate 的 correctness+dogfood，那时才检验 playbook 实际能不能产出好树。若届时树质量差 → 回 P4 调 playbook（playbook 是 markdown，调措辞，不回 P1/P2 脚本）。
- **多 agent 编排是 playbook 描述非脚本**：build 阶段 P4 只写规程；真正 fan-out 在 validate dogfood 时由 sdlc-build/sdlc-validate 的执行引擎按 Task-or-sequential 跑。
- **failure_class 枚举用 ascii token**（funds/consistency/compliance/experience）：便于看板 CSS 类 + lint 校验；spec 的中文名（资金正确性…）作注释映射。
