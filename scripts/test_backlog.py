#!/usr/bin/env python3
"""Tests for scripts/backlog.py — stdlib unittest, no third-party deps."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.join(HERE, "backlog.py")

LEAF_TMPL = """---
id: {id}
title: {title}
domain_path: {domain_path}
cross_link: {cross_link}
old_system_ref: {old_system_ref}
new_domain_path: {domain_path}
status: {status}
priority: {priority}
depends_on: {depends_on}
risk_level: {risk_level}
updated: 2026-06-15
---

## 需求描述
test leaf {id}
"""


def write_leaf(root, id, *, status="captured", priority="P2", depends_on="[]",
               cross_link="[]", old_system_ref="ref", risk_level="medium",
               title="t"):
    domain_path = "/".join(id.split(".")[:2])
    d = os.path.join(root, *domain_path.split("/"))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, id + ".md"), "w", encoding="utf-8") as f:
        f.write(LEAF_TMPL.format(id=id, title=title, domain_path=domain_path,
                                 cross_link=cross_link, old_system_ref=old_system_ref,
                                 status=status, priority=priority,
                                 depends_on=depends_on, risk_level=risk_level))


def run(*args, root):
    r = subprocess.run([sys.executable, BACKLOG, *args, "--root", root],
                       capture_output=True, text=True)
    return r


class ReadyQueueTest(unittest.TestCase):
    def test_excludes_dep_blocked_then_unblocks(self):
        with tempfile.TemporaryDirectory() as root:
            # a: no deps, P1, captured (ready to work)
            write_leaf(root, "order.checkout.a", priority="P1")
            # b: depends on a, P0; a not shipped -> b blocked
            write_leaf(root, "order.checkout.b", priority="P0",
                       depends_on="[order.checkout.a]")
            r = run("readyqueue", root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            q = json.loads(r.stdout)
            ids = [e["leaf_id"] for e in q]
            self.assertEqual(ids, ["order.checkout.a"])  # only a is ready

            # now ship a -> a excluded (done), b becomes ready
            write_leaf(root, "order.checkout.a", priority="P1", status="shipped")
            r = run("readyqueue", root=root)
            q = json.loads(r.stdout)
            ids = [e["leaf_id"] for e in q]
            self.assertEqual(ids, ["order.checkout.b"])
            # contract fields present
            self.assertEqual(
                set(q[0].keys()),
                {"leaf_id", "title", "priority", "deps_resolved",
                 "old_system_ref", "risk_level", "status"},
            )

    def test_priority_sorted_p0_first(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "x.y.low", priority="P3")
            write_leaf(root, "x.y.high", priority="P0")
            r = run("readyqueue", root=root)
            q = json.loads(r.stdout)
            self.assertEqual([e["leaf_id"] for e in q], ["x.y.high", "x.y.low"])


class CoverageLintTest(unittest.TestCase):
    def test_coverage_counts_by_domain(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", status="captured")
            write_leaf(root, "order.checkout.b", status="shipped")
            write_leaf(root, "user.auth.c", status="built")
            r = run("coverage", root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            cov = json.loads(r.stdout)
            self.assertEqual(cov["order"]["total"], 2)
            self.assertEqual(cov["order"]["by_status"]["shipped"], 1)
            self.assertEqual(cov["user"]["total"], 1)

    def test_lint_flags_dangling_and_dup(self):
        with tempfile.TemporaryDirectory() as root:
            # dangling dep
            write_leaf(root, "order.checkout.a", depends_on="[order.checkout.ghost]")
            # duplicate old_system_ref
            write_leaf(root, "order.checkout.b", old_system_ref="SHARED")
            write_leaf(root, "user.auth.c", old_system_ref="SHARED")
            r = run("lint", root=root)
            self.assertNotEqual(r.returncode, 0)  # problems -> nonzero exit
            out = r.stdout + r.stderr
            self.assertIn("dangling", out.lower())
            self.assertIn("dup", out.lower())

    def test_lint_clean_passes(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a")
            r = run("lint", root=root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def run_retire(*args):
    r = subprocess.run([sys.executable, BACKLOG, "retire", *args],
                       capture_output=True, text=True)
    return r


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _make_sdlc(sdlc, names=("spec.md", "plan.md", "STATE.md"),
               dirs=("validate", "review")):
    for name in names:
        with open(os.path.join(sdlc, name), "w", encoding="utf-8") as f:
            f.write(name)
    for d in dirs:
        os.makedirs(os.path.join(sdlc, d), exist_ok=True)
        with open(os.path.join(sdlc, d, "r.md"), "w", encoding="utf-8") as f:
            f.write(d)


class RetireTest(unittest.TestCase):
    def test_archives_and_clears(self):
        with tempfile.TemporaryDirectory() as sdlc:
            _make_sdlc(sdlc)
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16")
            self.assertEqual(r.returncode, 0, r.stderr)
            arch = os.path.join(sdlc, "archive", "2026-06-16-feat")
            for name in ("spec.md", "plan.md", "STATE.md", "validate", "review"):
                self.assertTrue(os.path.exists(os.path.join(arch, name)),
                                f"archived missing {name}")
                self.assertFalse(os.path.exists(os.path.join(sdlc, name)),
                                 f"top-level not cleared: {name}")

    def test_marks_leaf_shipped_and_unblocks(self):
        with tempfile.TemporaryDirectory() as sdlc:
            req = os.path.join(sdlc, "req")
            os.makedirs(req)
            write_leaf(req, "order.checkout.a", priority="P1")
            write_leaf(req, "order.checkout.b", priority="P0",
                       depends_on="[order.checkout.a]")
            _make_sdlc(sdlc, names=("STATE.md",), dirs=())
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                           "--leaf", "order.checkout.a", "--req-root", req)
            self.assertEqual(r.returncode, 0, r.stderr)
            leaf_path = os.path.join(req, "order", "checkout", "order.checkout.a.md")
            self.assertIn("status: shipped", _read(leaf_path))
            rq = run("readyqueue", root=req)
            ids = [e["leaf_id"] for e in json.loads(rq.stdout)]
            self.assertEqual(ids, ["order.checkout.b"])  # downstream unblocked

    def test_backflow_always_evolution_md(self):
        # 即便目标有 PROFILE.md，回流也只进 EVOLUTION.md（PROFILE 仅留指针，不被追加）
        with tempfile.TemporaryDirectory() as sdlc:
            prof = os.path.join(sdlc, "PROFILE.md")
            with open(prof, "w", encoding="utf-8") as f:
                f.write("# Profile\n\n## Tech stack\npython\n")
            entry = "- 2026-06-16 · feat · lesson-X"
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                           "--evolution-entry", entry)
            self.assertEqual(r.returncode, 0, r.stderr)
            ev_text = _read(os.path.join(sdlc, "EVOLUTION.md"))
            self.assertIn("lesson-X", ev_text)
            prof_text = _read(prof)
            self.assertNotIn("## Evolution log", prof_text)  # PROFILE 不承载流水
            self.assertNotIn("lesson-X", prof_text)

    def test_retire_rejects_profile_flag(self):
        # --profile 已废除：Evolution log 唯一正屋是 EVOLUTION.md，不再写 PROFILE 节
        with tempfile.TemporaryDirectory() as sdlc:
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                           "--profile", os.path.join(sdlc, "PROFILE.md"),
                           "--evolution-entry", "- x")
            self.assertNotEqual(r.returncode, 0)  # argparse 拒绝未知参数
            self.assertIn("profile", (r.stderr + r.stdout).lower())

    def test_backflow_fallback_evolution_md(self):
        with tempfile.TemporaryDirectory() as sdlc:
            entry = "- 2026-06-16 · feat · lesson-Y"
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16",
                           "--evolution-entry", entry)
            self.assertEqual(r.returncode, 0, r.stderr)
            ev = os.path.join(sdlc, "EVOLUTION.md")
            self.assertTrue(os.path.exists(ev))
            self.assertIn("lesson-Y", _read(ev))

    def test_archive_exists_refuses(self):
        with tempfile.TemporaryDirectory() as sdlc:
            with open(os.path.join(sdlc, "spec.md"), "w", encoding="utf-8") as f:
                f.write("spec")
            os.makedirs(os.path.join(sdlc, "archive", "2026-06-16-feat"))
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16")
            self.assertNotEqual(r.returncode, 0)  # refuse to overwrite
            self.assertTrue(os.path.exists(os.path.join(sdlc, "spec.md")))  # untouched

    def test_no_leaf_graceful(self):
        with tempfile.TemporaryDirectory() as sdlc:
            with open(os.path.join(sdlc, "spec.md"), "w", encoding="utf-8") as f:
                f.write("spec")
            r = run_retire("--sdlc", sdlc, "--slug", "feat", "--date", "2026-06-16")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(
                os.path.join(sdlc, "archive", "2026-06-16-feat", "spec.md")))

    def test_marks_leaf_and_writes_sdlc_log(self):
        with tempfile.TemporaryDirectory() as sdlc:
            req = os.path.join(sdlc, "req")
            os.makedirs(req)
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
            req = os.path.join(sdlc, "req")
            os.makedirs(req)
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
            req = os.path.join(sdlc, "req")
            os.makedirs(req)
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

    def test_rejects_path_traversal_to(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a")
            for bad in ("../evil", "a/../../etc", "a/./b", ".."):
                r = run("move", "--leaf", "order.checkout.a", "--to", bad, root=root)
                self.assertNotEqual(r.returncode, 0, f"应拒绝非法 --to: {bad}")
            # 源叶未被移动
            self.assertTrue(os.path.exists(
                os.path.join(root, "order", "checkout", "order.checkout.a.md")))


class BoardTest(unittest.TestCase):
    def test_renders_tree_with_chat_panel(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", status="shipped", title="结算下单")
            write_leaf(root, "user.auth.b", status="captured")
            out = os.path.join(root, "_board.html")
            r = run("board", "--out", out, root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = _read(out)
            self.assertIn("order.checkout.a", html)
            self.assertIn("结算下单", html)
            self.assertIn("<details", html)              # 折叠树结构
            self.assertIn("status-shipped", html)         # 状态徽章类
            self.assertIn("--green:", html)               # DESIGN token
            # 叶卡可选中(点击 → 聊天)
            self.assertIn('data-leaf="order.checkout.a"', html)
            # 右侧聊天面板(替代批注层)
            self.assertIn("chat-panel", html)
            self.assertIn("chat-input", html)
            # 实时回路:发送 POST /feedback、轮询 /replies.json 与 /rev
            self.assertIn("/feedback", html)
            self.assertIn("/replies.json", html)
            self.assertIn("/rev", html)
            # 不再注入 annotate 批注层(改用自建聊天)
            self.assertNotIn("annotate.js", html)
            # 叶详情数据嵌入(选叶后面板顶部显示字段+正文)
            self.assertIn("leaf-data", html)
            self.assertIn("test leaf order.checkout.a", html)   # 正文进了详情数据

    def test_board_escapes_html_in_leaf_content(self):
        # 信任边界:叶内容里的 HTML 不得原样进页面(防注入)
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", title="<script>alert(1)</script>")
            out = os.path.join(root, "_board.html")
            r = run("board", "--out", out, root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = _read(out)
            self.assertNotIn("<script>alert(1)</script>", html)   # 未原样出现
            self.assertIn("&lt;script&gt;", html)                 # 已转义

    def test_board_embeds_leaf_body_and_fields(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", old_system_ref="legacy/CartServlet",
                       depends_on="[order.checkout.x]")
            write_leaf(root, "order.checkout.x")
            out = os.path.join(root, "_board.html")
            r = run("board", "--out", out, root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = _read(out)
            self.assertIn("legacy/CartServlet", html)            # old_system_ref 入详情
            self.assertIn("order.checkout.x", html)              # depends_on 入详情

    def test_empty_tree_placeholder(self):
        with tempfile.TemporaryDirectory() as root:
            out = os.path.join(root, "_board.html")
            r = run("board", "--out", out, root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("暂无需求", _read(out))


def _write_leaf_extra(root, id, extra_lines):
    """写一片叶,frontmatter 末尾插入 extra_lines(用于测可选交叉字段)。"""
    domain_path = "/".join(id.split(".")[:2])
    d = os.path.join(root, *domain_path.split("/"))
    os.makedirs(d, exist_ok=True)
    fm = (f"---\nid: {id}\ntitle: t\ndomain_path: {domain_path}\ncross_link: []\n"
          f"old_system_ref: r-{id}\nnew_domain_path: {domain_path}\nstatus: captured\n"
          f"priority: P2\ndepends_on: []\nrisk_level: medium\nupdated: 2026-06-16\n"
          + extra_lines + "---\n\n## 需求描述\nx\n")
    with open(os.path.join(d, id + ".md"), "w", encoding="utf-8") as f:
        f.write(fm)


class LintCrossFieldTest(unittest.TestCase):
    def test_valid_cross_fields_clean(self):
        with tempfile.TemporaryDirectory() as root:
            _write_leaf_extra(root, "order.checkout.a",
                "actor: 运营\nfailure_class: funds\n"
                "contract_refs: [contracts/provided/bff]\ndata_owner: order-svc\n")
            r = run("lint", root=root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_cross_fields_still_clean(self):  # 存量树不受影响
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a")
            self.assertEqual(run("lint", root=root).returncode, 0)

    def test_bad_failure_class_flagged(self):
        with tempfile.TemporaryDirectory() as root:
            _write_leaf_extra(root, "order.checkout.a", "failure_class: 乱写\n")
            r = run("lint", root=root)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("bad-failure-class", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
