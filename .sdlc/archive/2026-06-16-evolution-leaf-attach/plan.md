# Plan: EVOLUTION 条目挂源叶（Retire 写 `## sdlc 记录`）

> 来源 spec: .sdlc/spec.md（已批准）
> 复杂度等级: **L1** —— 理由: 增强单个 backlog op（Retire），纯标准库后端、无 UI/AI、改动集中在 backlog.py 一处 + 配套 test/doc。
> 生成: 2026-06-16
> Active roles: skill-maintainer (R10), qa ｜ Validate modes: correctness

## 阶段总览（波次依赖）

| Phase | 名称 | 覆盖需求 | depends_on | wave |
|-------|------|----------|------------|------|
| P1 | 挂叶实现（backlog.py + test，TDD） | R-attach, R-degrade, R-idem, D-section, D-sig | — | 1 |
| P2 | 文档 + 版本同步 | R-docsync | P1 | 2 |

> 全在 `backlog.py`/`test_backlog.py` + SKILL/CHANGELOG，串行波次（单 session 顺序）。

---

## Phase P1: 挂叶实现（TDD）

**目标**: Retire 标源叶 shipped 时，若有 evolution entry，把同条 entry 也写进该叶 `## sdlc 记录` 段；无叶/无 entry 不挂。
**覆盖需求(traceability)**: R-attach（挂叶）, R-degrade（降级）, R-idem（幂等/不重复建段头）, D-section（段名 `## sdlc 记录`）, D-sig（`_mark_leaf_shipped` 改返回路径）
**depends_on**: []　**wave**: 1
**为什么这样拆**: 实现与测试一体（TDD），是本特性唯一的逻辑核心；文档/版本无逻辑，单列 P2。

**must_haves（目标倒推）**:
- truths: `retire --leaf L --req-root R --evolution-entry E` 后，L 的叶 `.md` 含 `status: shipped` + `## sdlc 记录` + E；EVOLUTION.md 也含 E；无 `--leaf` 或无 `--evolution-entry` → 叶无 `## sdlc 记录`；叶已有该段再挂 → 段头不重复、旧新条目都在；JSON 含 `leaf_evolution`。
- artifacts: `scripts/backlog.py`（改 `_mark_leaf_shipped`、新 `_append_leaf_sdlc_log`、改 `cmd_retire`）、`scripts/test_backlog.py`（RetireTest +4）。
- key_links: `cmd_retire` → `_mark_leaf_shipped`(返回 path) → 若 path+entry → `_append_leaf_sdlc_log`。

**可观察成功标准**: `python3 scripts/test_backlog.py RetireTest -v` 全 PASS（含新 4 例 + 既有不回归）。

### Task P1-T1: 改 `_mark_leaf_shipped` 返回路径 + 新增 `_append_leaf_sdlc_log` + 接进 `cmd_retire`（TDD）
- **requirements**: R-attach, R-degrade, R-idem, D-section, D-sig
- **files**: `scripts/backlog.py`, `scripts/test_backlog.py`
- **read_first**: `scripts/backlog.py:139-194`（`_set_frontmatter_status`/`_mark_leaf_shipped`/`_append_evolution`/`cmd_retire`）、`scripts/test_backlog.py:120-164`（`run_retire`/`_read`/`_make_sdlc`/`write_leaf` 助手 + 既有 RetireTest）、`.sdlc/spec.md` §5
- **action**:
  - 改 `_mark_leaf_shipped(req_root, leaf_id)`：命中时 `path=os.path.join(req_root, lf["_path"])`，`_set_frontmatter_status(path, SHIPPED)`，**`return path`**；未命中 `return None`（替代原 bool）。
  - 加模块常量 `LEAF_SDLC_LOG_HEADER = "## sdlc 记录"` 与函数 `_append_leaf_sdlc_log(leaf_path, entry)`：读叶文本；`if LEAF_SDLC_LOG_HEADER not in text: text = text.rstrip("\n") + f"\n\n{LEAF_SDLC_LOG_HEADER}\n"`；再 `text = text.rstrip("\n") + "\n" + entry + "\n"`；写回。（仿 `_append_evolution` 缺则建头；entry 总追加到文件末尾——`## sdlc 记录` 恒为末段，故累积其下。）
  - 改 `cmd_retire`：`leaf_path=None`；`if args.leaf and args.req_root: leaf_path=_mark_leaf_shipped(...); if leaf_path is None: print("warn: 未找到源叶...", file=sys.stderr)`；`leaf_shipped = leaf_path is not None`；`leaf_evolution=None`；回流块改为 `if args.evolution_entry: backflow=_append_evolution(args.sdlc, args.evolution_entry); if leaf_path: _append_leaf_sdlc_log(leaf_path, args.evolution_entry); leaf_evolution=leaf_path`；JSON 输出加 `"leaf_evolution": leaf_evolution`。
- **acceptance_criteria**: `python3 scripts/test_backlog.py RetireTest -v` PASS；全量 `python3 scripts/test_backlog.py` PASS。

- [ ] Step 1: 写失败测试 — `test_backlog.py` 的 `RetireTest` 加：
  ```python
  def test_marks_leaf_and_writes_sdlc_log(self):
      with tempfile.TemporaryDirectory() as sdlc:
          req = os.path.join(sdlc, "req"); os.makedirs(req)
          write_leaf(req, "order.checkout.a", priority="P1")
          _make_sdlc(sdlc, names=("STATE.md",), dirs=())
          entry = "- 2026-06-16 · feat · 学到了X · → archive/2026-06-16-feat/"
          r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                         "--leaf", "order.checkout.a", "--req-root", req,
                         "--evolution-entry", entry)
          self.assertEqual(r.returncode, 0, r.stderr)
          leaf = _read(os.path.join(req, "order", "checkout", "order.checkout.a.md"))
          self.assertIn("status: shipped", leaf)
          self.assertIn("## sdlc 记录", leaf)
          self.assertIn("学到了X", leaf)
          self.assertIn("学到了X", _read(os.path.join(sdlc, "EVOLUTION.md")))
          self.assertTrue(json.loads(r.stdout)["leaf_evolution"])

  def test_leaf_no_entry_no_sdlc_log(self):
      with tempfile.TemporaryDirectory() as sdlc:
          req = os.path.join(sdlc, "req"); os.makedirs(req)
          write_leaf(req, "order.checkout.a")
          _make_sdlc(sdlc, names=("STATE.md",), dirs=())
          r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                         "--leaf", "order.checkout.a", "--req-root", req)
          self.assertEqual(r.returncode, 0, r.stderr)
          leaf = _read(os.path.join(req, "order", "checkout", "order.checkout.a.md"))
          self.assertIn("status: shipped", leaf)
          self.assertNotIn("## sdlc 记录", leaf)

  def test_sdlc_log_appends_to_existing_section(self):
      with tempfile.TemporaryDirectory() as sdlc:
          req = os.path.join(sdlc, "req"); os.makedirs(req)
          write_leaf(req, "order.checkout.a")
          lp = os.path.join(req, "order", "checkout", "order.checkout.a.md")
          with open(lp, "a", encoding="utf-8") as f:
              f.write("\n## sdlc 记录\n- 旧条目prior\n")
          _make_sdlc(sdlc, names=("STATE.md",), dirs=())
          r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                         "--leaf", "order.checkout.a", "--req-root", req,
                         "--evolution-entry", "- 新条目fresh")
          self.assertEqual(r.returncode, 0, r.stderr)
          leaf = _read(lp)
          self.assertEqual(leaf.count("## sdlc 记录"), 1)
          self.assertIn("旧条目prior", leaf)
          self.assertIn("新条目fresh", leaf)

  def test_no_leaf_still_only_evolution(self):
      with tempfile.TemporaryDirectory() as sdlc:
          with open(os.path.join(sdlc, "spec.md"), "w", encoding="utf-8") as f:
              f.write("spec")
          r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                         "--evolution-entry", "- 无叶entry")
          self.assertEqual(r.returncode, 0, r.stderr)
          self.assertIsNone(json.loads(r.stdout)["leaf_evolution"])
          self.assertIn("无叶entry", _read(os.path.join(sdlc, "EVOLUTION.md")))
  ```
- [ ] Step 2: 跑 `python3 scripts/test_backlog.py RetireTest -v` → 期望 FAIL（`_append_leaf_sdlc_log` 未定义 / leaf_evolution 不在 JSON / `## sdlc 记录` 未写）。
- [ ] Step 3: 写最小实现（按 action：改 `_mark_leaf_shipped` 返回 path、加 `LEAF_SDLC_LOG_HEADER`+`_append_leaf_sdlc_log`、改 `cmd_retire` 接线 + JSON）。
- [ ] Step 4: 跑 `python3 scripts/test_backlog.py RetireTest -v` PASS；全量 `python3 scripts/test_backlog.py` PASS（确认既有 `test_marks_leaf_shipped_and_unblocks` 等不回归——`_mark_leaf_shipped` 返回类型变了但 `leaf_shipped` 语义不变）。
- [ ] Step 5: 提交 `git add scripts/backlog.py scripts/test_backlog.py && git commit -m "feat(backlog): Retire 标源叶 shipped 时把 evolution entry 也写进该叶 ## sdlc 记录"`

---

## Phase P2: 文档 + 版本同步

**目标**: SKILL/CHANGELOG/version 与新行为一致；driver 高层描述顺带提一句。
**覆盖需求(traceability)**: R-docsync（spec §6 末项 + §9 + CLAUDE.md 迭代表「加/改 backlog 派生操作」）
**depends_on**: [P1]　**wave**: 2
**为什么这样拆**: 文档要等实现定型；无逻辑，与 P1 解耦。

**must_haves**:
- truths: `sdlc-backlog/SKILL.md §6` Retire 步骤②含"有 source-leaf 时同条 entry 也写进该叶 `## sdlc 记录`"；顶部 op 描述微调；CHANGELOG 有 0.13.0 条目；`plugin.json`/`marketplace.json` = 0.13.0；driver §2/§4 Retire 描述加一句挂叶（非契约）；`bash scripts/validate-skills` PASS。
- artifacts: `skills/sdlc-backlog/SKILL.md`、`CHANGELOG.md`、`.claude-plugin/{plugin,marketplace}.json`、`skills/sdlc/SKILL.md`（driver 描述句）。
- key_links: 版本 0.12.0→**0.13.0**（minor：Retire 加能力，非破坏）。

**可观察成功标准**: `bash scripts/validate-skills` = PASS；`grep "0.13.0" .claude-plugin/plugin.json`。

### Task P2-T1: 同步 SKILL §6 + 顶部 op 描述
- **requirements**: R-docsync
- **files**: `skills/sdlc-backlog/SKILL.md`
- **read_first**: `skills/sdlc-backlog/SKILL.md:1-13`（frontmatter op 列举）、§6 Retire 章节（四步表 + 回流目标段）
- **action**: §6 Retire 四步表的"② 回流"行补一句"**若有 source-leaf：同条 entry 也 append 进该源叶 `.md` 的 `## sdlc 记录` 段**（使需求树成带 sdlc 记录的活档案）"；正文回流段加一句说明叶挂载与 EVOLUTION 并行、无叶降级。顶部 frontmatter 的 Retire 描述微调（"标源叶 shipped" → "标源叶 shipped + 写叶 sdlc 记录"）。
- **acceptance_criteria**: SKILL 含 `## sdlc 记录` 挂叶说明；`bash scripts/validate-skills` PASS（frontmatter 合法）。

### Task P2-T2: CHANGELOG + 版本 0.13.0 + driver 描述句
- **requirements**: R-docsync
- **files**: `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/sdlc/SKILL.md`
- **read_first**: `CHANGELOG.md:1-25`（顶部格式 + 0.12.0 条目）、`.claude-plugin/plugin.json`、`skills/sdlc/SKILL.md`（§2 退场前置 + §4 done 行对 Retire 的描述）
- **action**: CHANGELOG 顶部加 `## [0.13.0]`（Added: Retire 标源叶 shipped 时把 evolution entry 也写进该叶 `## sdlc 记录`，需求树成带 sdlc 记录的活档案；Changed: `_mark_leaf_shipped` 返回叶路径替代 bool；Notes: additive、无叶降级、未动 stage/skill/契约、distilled-from `session:sdlc-evolution-leaf-attach-2026-06-16`）。`plugin.json`+`marketplace.json` 的 version 0.12.0→0.13.0（三处）。`skills/sdlc/SKILL.md` §2 退场前置 + §4 done 行的 Retire 描述各加"（并把耐久决策顺带写进源叶 `## sdlc 记录`）"——高层一句，非契约变更。
- **acceptance_criteria**: `grep -c 0.13.0 .claude-plugin/plugin.json` =1；CHANGELOG 有 0.13.0 节；`bash scripts/validate-skills` PASS。

### Task P2-T3: 全量回归 + 提交
- **requirements**: R-docsync
- **files**: —
- **action**: `python3 scripts/test_backlog.py`（全绿）+ `bash scripts/validate-skills`（PASS）。`git add -A && git commit -m "docs(backlog): Retire 挂叶 ## sdlc 记录 — SKILL/driver/CHANGELOG/version 0.13.0 同步"`。
- **acceptance_criteria**: 两命令通过；提交完成。

---

## Source Audit（出口门控，§6.1）

| SOURCE | ID | 需求/决策 | 覆盖任务 | 状态 |
|--------|----|-----------|----------|------|
| GOAL | — | Retire 把 evolution entry 挂源叶，需求树成活档案 | P1-T1 | COVERED |
| REQ | R-attach | 叶命中+有 entry → 写叶 `## sdlc 记录`（§5.1/5.2） | P1-T1 | COVERED |
| REQ | R-degrade | 无叶/无 entry 不挂（§5.3） | P1-T1（test_leaf_no_entry / test_no_leaf） | COVERED |
| REQ | R-idem | 段已存在不重复建头（§5.3 幂等） | P1-T1（test_sdlc_log_appends_to_existing_section） | COVERED |
| REQ | R-docsync | SKILL/CHANGELOG/version/driver 同步（§6/§9 + CLAUDE.md 表） | P2-T1,T2,T3 | COVERED |
| DECISION | D-section | 段名 `## sdlc 记录`（非 frontmatter、非"演进史"） | P1-T1 | COVERED |
| DECISION | D-sig | `_mark_leaf_shipped` 返回路径替代 bool | P1-T1 | COVERED |
| EVAL-CRIT | — | N/A（无 AI） | — | N/A |
| Deferred | — | 历史 EVOLUTION 回填到叶（spec §8） | （显式延后，不算 gap） | DEFERRED |

正向全 COVERED；反向每任务 requirements 非空。自查三扫（占位/类型一致/spec 覆盖）通过：`_mark_leaf_shipped`/`_append_leaf_sdlc_log`/`LEAF_SDLC_LOG_HEADER`/`leaf_evolution` 命名前后一致。

## 风险 / 关键决策点
- `_append_leaf_sdlc_log` 假设 `## sdlc 记录` 恒为叶末段（总在文件尾 append）——本设计成立（只此一处写该段）；若未来叶尾追加别的段需复审。
- 版本 0.13.0（minor）：Retire 加能力非破坏；`_mark_leaf_shipped` 返回类型变更是内部、无外部调用方（仅 cmd_retire 用）。
