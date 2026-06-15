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


if __name__ == "__main__":
    unittest.main()
