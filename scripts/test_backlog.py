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


if __name__ == "__main__":
    unittest.main()
