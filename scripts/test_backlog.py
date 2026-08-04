#!/usr/bin/env python3
"""Tests for scripts/backlog.py — stdlib unittest, no third-party deps."""
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.join(HERE, "backlog.py")
sys.path.insert(0, HERE)
import backlog  # noqa: E402  (直接引用常量/函数;CLI 行为仍走 subprocess run())
import board  # noqa: E402  (控制看板纯渲染 helper 直接做单测)

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

    def test_board_leafdata_has_cross_fields(self):
        with tempfile.TemporaryDirectory() as root:
            _write_leaf_extra(root, "order.checkout.a", "actor: 采购\nfailure_class: funds\n")
            out = os.path.join(root, "_b.html")
            r = run("board", "--out", out, root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = _read(out)
            self.assertIn('"actor"', html)     # leaf-data JSON 含交叉字段
            self.assertIn("ld-cross", html)     # 详情渲染交叉行(JS/CSS 容器)

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


@dataclass
class _SnapshotStub:
    """验证 board adapter 同时接受核心 dict 与 dataclass snapshot。"""
    schema_version: int = 1
    mode: str = "shared-control"
    control_root: str = ".sdlc-control"
    requests_by_id: dict = field(default_factory=dict)
    requirements_by_id: dict = field(default_factory=dict)
    claims_by_leaf: dict = field(default_factory=dict)
    features_by_id: dict = field(default_factory=dict)
    tasks_by_feature: dict = field(default_factory=dict)
    evidence_by_task: dict = field(default_factory=dict)
    feature_evidence_by_feature: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def _tracking_snapshot(payload=None):
    request_title = payload or "登录原始需求"
    owner = payload or "agent-a"
    branch = payload or "feature/feat-login"
    blocked = payload or "等待接口确认"
    command = payload or "python3 scripts/test_auth.py"
    return {
        "schema_version": 1,
        "mode": "shared-control",
        "control_root": ".sdlc-control",
        "requests_by_id": {
            "req-001": {"request_id": "req-001", "title": request_title,
                        "status": "captured", "_body": request_title},
        },
        "requirements_by_id": {
            "user.auth.login": {"id": "user.auth.login", "title": "登录",
                                "domain_path": "user/auth", "cross_link": [],
                                "old_system_ref": "legacy/Auth", "new_domain_path": "user/auth",
                                "status": "captured", "priority": "P1", "depends_on": [],
                                "risk_level": "medium", "source_request": "req-001",
                                "_body": "control requirement"},
        },
        "claims_by_leaf": {
            "user.auth.login": {"leaf_id": "user.auth.login", "feature_id": "feat-login",
                                "status": "active", "owner": owner},
        },
        "features_by_id": {
            "feat-login": {"feature_id": "feat-login", "leaf_id": "user.auth.login",
                           "feature_branch": branch, "owner": owner, "status": "in_progress",
                           "integration_sha": "feedface00000001"},
        },
        # 故意逆序，board 必须稳定按 task id 排序。
        "tasks_by_feature": {
            "feat-login": [
                {"task_id": "task-z", "status": "blocked", "branch_name": "task/z",
                 "owner": owner, "merge_status": "active", "blocked_reason": blocked,
                 "integration_sha": "feedface00000003", "freshness": "unknown"},
                {"task_id": "task-a", "status": "verified", "branch_name": "task/a",
                 "owner": owner, "merge_status": "integrated", "blocked_reason": "",
                 "integration_sha": "feedface00000002", "freshness": "fresh"},
            ],
        },
        "evidence_by_task": {
            "task-a": [
                {"evidence_id": "ev-z", "result": "pass", "scope": "task",
                 "tested_sha": "feedface00000002", "_body": command,
                 "created_at": "2026-08-04T10:02:00Z"},
                {"evidence_id": "ev-a", "result": "fail", "scope": "task",
                 "tested_sha": "feedface00000001", "_body": command,
                 "created_at": "2026-08-04T10:01:00Z"},
            ],
        },
        "feature_evidence_by_feature": {
            "feat-login": [{"evidence_id": "ev-feature", "result": "pass", "scope": "feature",
                            "tested_sha": "feedface00000001", "_body": command,
                            "created_at": "2026-08-04T10:03:00Z"}],
        },
        "warnings": [],
    }


class ControlBoardTest(unittest.TestCase):
    def _render(self, snapshot):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "user.auth.login", title="登录")
            leaves = backlog.load_leaves(root)
            return board.render_board(backlog.build_tree(leaves), leaves, control=snapshot)

    def test_renders_request_leaf_claim_feature_task_evidence_chain_in_stable_order(self):
        page = self._render(_tracking_snapshot())
        for expected in ("req-001", "登录原始需求", "user.auth.login", "feat-login",
                         "feature/feat-login", "agent-a", "task/a", "task/z",
                         "integrated", "等待接口确认", "feedface00000002",
                         "python3 scripts/test_auth.py", "ev-feature"):
            self.assertIn(expected, page)
        self.assertIn("tracking-chain", page)
        self.assertLess(page.index('"task_id": "task-a"'), page.index('"task_id": "task-z"'))
        self.assertLess(page.index('"evidence_id": "ev-a"'),
                        page.index('"evidence_id": "ev-z"'))

    def test_accepts_dataclass_snapshot(self):
        snapshot = _SnapshotStub(**_tracking_snapshot())
        page = self._render(snapshot)
        self.assertIn("feat-login", page)
        self.assertIn("task-a", page)

    def test_local_mode_is_tracked_control_not_legacy(self):
        snapshot = _tracking_snapshot()
        snapshot["mode"] = "local-serial"
        page = self._render(snapshot)
        self.assertIn("control local-serial", page)
        self.assertIn('class="tracking-summary"', page)

    def test_active_claim_is_not_counted_as_ready(self):
        page = self._render(_tracking_snapshot())
        self.assertIn("ready 0 条", page)

    def test_control_fields_cannot_break_json_script_or_html(self):
        payload = "</script><img src=x onerror=alert(1)>&\u2028\u2029"
        snapshot = _tracking_snapshot(payload)
        snapshot["warnings"] = [payload]
        page = self._render(snapshot)
        self.assertNotIn(payload, page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)
        self.assertIn("\\u003c/script\\u003e", page)
        self.assertIn("\\u0026", page)
        self.assertIn("\\u2028\\u2029", page)

    def test_missing_reference_warning_is_visible_without_crashing(self):
        snapshot = _tracking_snapshot()
        snapshot["features_by_id"] = {}
        snapshot["tasks_by_feature"] = {}
        snapshot["evidence_by_task"] = {}
        snapshot["feature_evidence_by_feature"] = {}
        snapshot["warnings"] = ["missing-feature: feat-login"]
        page = self._render(snapshot)
        self.assertIn("control-warning", page)
        self.assertIn("missing-feature: feat-login", page)
        self.assertIn("user.auth.login", page)

    def test_control_snapshot_suppresses_conflicting_local_state_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = os.path.join(tmp, "requirements")
            write_leaf(req, "user.auth.login", title="登录")
            with open(os.path.join(tmp, "STATE.md"), "w", encoding="utf-8") as f:
                f.write("stage: build\nsource-leaf: user.auth.login\n")
            out = os.path.join(tmp, "board.html")
            fake_control = SimpleNamespace(
                load_snapshot_from_ref=mock.Mock(return_value=_tracking_snapshot()),
                readyqueue_from_snapshot=mock.Mock(return_value=[]))
            args = SimpleNamespace(root=req, out=out, control_repo=tmp,
                                   control_ref="sdlc-control")
            with mock.patch.dict(sys.modules, {"control": fake_control}), \
                    mock.patch("builtins.print"):
                board.cmd_board(args)
            fake_control.load_snapshot_from_ref.assert_called_once_with(
                tmp, ref="sdlc-control", legacy_requirements_root=req,
                local_state_path=os.path.join(tmp, "STATE.md"))
            page = _read(out)
            self.assertIn("feat-login", page)
            self.assertNotIn('class="live-badge', page)
            self.assertNotIn("build中", page)

    def test_control_requirements_replace_stale_legacy_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = os.path.join(tmp, "requirements")
            write_leaf(req, "legacy.keep.a", title="旧树")
            out = os.path.join(tmp, "board.html")
            fake_control = SimpleNamespace(
                load_snapshot_from_ref=mock.Mock(return_value=_tracking_snapshot()),
                readyqueue_from_snapshot=mock.Mock(return_value=[]))
            args = SimpleNamespace(root=req, out=out, control_repo=tmp,
                                   control_ref="sdlc-control")
            with mock.patch.dict(sys.modules, {"control": fake_control}), \
                    mock.patch("builtins.print"):
                board.cmd_board(args)
            page = _read(out)
            self.assertIn("user.auth.login", page)
            self.assertIn("control requirement", page)
            self.assertNotIn("legacy.keep.a", page)

    def test_legacy_snapshot_keeps_state_overlay_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = os.path.join(tmp, "requirements")
            write_leaf(req, "user.auth.login", title="登录")
            with open(os.path.join(tmp, "STATE.md"), "w", encoding="utf-8") as f:
                f.write("stage: build\nsource-leaf: user.auth.login\n")
            out = os.path.join(tmp, "board.html")
            legacy = _tracking_snapshot()
            legacy.update({"mode": "legacy", "requests_by_id": {},
                           "requirements_by_id": {}, "claims_by_leaf": {},
                           "features_by_id": {}, "tasks_by_feature": {},
                           "evidence_by_task": {}, "feature_evidence_by_feature": {},
                           "warnings": ["control-ref-missing:missing-control"]})
            fake_control = SimpleNamespace(
                load_snapshot_from_ref=mock.Mock(return_value=legacy))
            args = SimpleNamespace(root=req, out=out, control_repo=tmp,
                                   control_ref="missing-control")
            before = set(os.listdir(tmp))
            with mock.patch.dict(sys.modules, {"control": fake_control}), \
                    mock.patch("builtins.print"):
                board.cmd_board(args)
            page = _read(out)
            self.assertIn('class="live-badge', page)
            self.assertIn("build中", page)
            self.assertNotIn('class="tracking-summary"', page)
            self.assertIn("control-ref-missing:missing-control", page)
            self.assertNotIn(".sdlc-control", set(os.listdir(tmp)) - before)

    def test_cli_accepts_control_repo_and_ref_without_mutating_legacy_root(self):
        with tempfile.TemporaryDirectory() as repo:
            subprocess.run(["git", "init", "-q", repo], check=True)
            root = os.path.join(repo, "requirements")
            write_leaf(root, "user.auth.login", title="登录")
            out = os.path.join(root, "board.html")
            before = set(os.listdir(repo))
            result = run("board", "--out", out, "--control-repo", repo,
                         "--control-ref", "missing-control", root=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            page = _read(out)
            self.assertIn("user.auth.login", page)
            self.assertIn("control-ref-missing:missing-control", page)
            self.assertNotIn(".sdlc-control", set(os.listdir(repo)) - before)


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


class WriteTreeTest(unittest.TestCase):
    def test_writes_leaves_with_optional_fields(self):
        with tempfile.TemporaryDirectory() as root:
            tree = {"leaves": [
                {"id": "order.checkout.place", "title": "作为采购我要下单以便采货",
                 "domain_path": "order/checkout", "cross_link": [],
                 "old_system_ref": "apps/api/modules/order", "new_domain_path": "order/checkout",
                 "status": "captured", "priority": "P1", "depends_on": [], "risk_level": "high",
                 "actor": "采购", "failure_class": "consistency",
                 "contract_refs": ["contracts/provided/bff"], "data_owner": "order-svc"}]}
            fp = os.path.join(root, "tree.json")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(tree, f, ensure_ascii=False)
            r = run("write-tree", "--from", fp, root=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            leaf = _read(os.path.join(root, "order", "checkout", "order.checkout.place.md"))
            self.assertIn("id: order.checkout.place", leaf)
            self.assertIn("failure_class: consistency", leaf)
            self.assertIn("actor: 采购", leaf)
            self.assertIn("作为采购我要下单", leaf)
            self.assertEqual(run("lint", root=root).returncode, 0, "写出的树应 lint clean")
            self.assertEqual(json.loads(r.stdout)["written"], 1)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            tree = {"leaves": [
                {"id": "x.y.a", "title": "t", "domain_path": "../../etc", "cross_link": [],
                 "old_system_ref": "r", "new_domain_path": "x/y", "status": "captured",
                 "priority": "P2", "depends_on": [], "risk_level": "low"},
                {"id": "../../evil", "title": "t", "domain_path": "x/y", "cross_link": [],
                 "old_system_ref": "r", "new_domain_path": "x/y", "status": "captured",
                 "priority": "P2", "depends_on": [], "risk_level": "low"}]}
            fp = os.path.join(root, "t.json")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(tree, f, ensure_ascii=False)
            r = run("write-tree", "--from", fp, root=root)
            self.assertEqual(json.loads(r.stdout)["written"], 0)   # 两条都被拒
            self.assertEqual(json.loads(r.stdout)["skipped"], 2)
            self.assertFalse(os.path.exists(os.path.join(root, "..", "etc")))  # 未逃出 root

    def test_skips_existing_leaf(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", title="原有")
            tree = {"leaves": [{"id": "order.checkout.a", "title": "新的",
                "domain_path": "order/checkout", "cross_link": [], "old_system_ref": "r",
                "new_domain_path": "order/checkout", "status": "captured", "priority": "P2",
                "depends_on": [], "risk_level": "low"}]}
            fp = os.path.join(root, "t.json")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(tree, f, ensure_ascii=False)
            r = run("write-tree", "--from", fp, root=root)
            self.assertEqual(json.loads(r.stdout)["skipped"], 1)
            self.assertIn("原有", _read(os.path.join(root, "order", "checkout", "order.checkout.a.md")))


class BoardRenoTest(unittest.TestCase):
    """看板 4 痛点重构(P6):①进度/图例/过滤 ②搜索/折叠记忆/面包屑 ③字段分组/dep可点/tooltip ④聊天状态提示。"""
    def _render(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", status="shipped", title="下单")
            write_leaf(root, "order.checkout.b", status="captured",
                       depends_on="[order.checkout.a]")
            out = os.path.join(root, "b.html")
            run("board", "--out", out, root=root)
            return _read(out)

    def test_pain1_legend_and_distribution(self):
        h = self._render()
        self.assertIn('class="legend"', h)      # 图例
        self.assertIn('class="dist"', h)         # 进度分布条(分段)

    def test_pain2_search_and_breadcrumb(self):
        h = self._render()
        self.assertIn('id="tree-search"', h)     # 搜索框
        self.assertIn('crumb', h)                # 面包屑容器
        self.assertIn('localStorage', h)         # 折叠记忆

    def test_pain3_field_grouping_and_dep_link(self):
        h = self._render()
        self.assertIn('dep-link', h)             # depends_on 可点
        self.assertIn('身份', h)                  # 字段分组小标题
        self.assertIn('交叉', h)

    def test_pain4_chat_live_status(self):
        h = self._render()
        self.assertIn('id="live-status"', h)     # 监听状态指示


class BoardLiveBadgeTest(unittest.TestCase):
    def _setup(self, with_state=True, stage="build"):
        self.tmp = tempfile.mkdtemp()
        req = os.path.join(self.tmp, "requirements")
        write_leaf(req, "user.auth.login", status="captured", title="登录")
        if with_state:
            with open(os.path.join(self.tmp, "STATE.md"), "w", encoding="utf-8") as f:
                f.write(f"# SDLC State: x\nstage: {stage}\nsource-leaf: user.auth.login\n")
        return req

    def test_overlay_when_state_present(self):
        req = self._setup(stage="build")
        out = os.path.join(self.tmp, "b.html")
        r = run("board", "--out", out, root=req)
        self.assertEqual(r.returncode, 0)
        html_txt = _read(out)
        self.assertIn('class="live-badge', html_txt)  # 真元素(非 CSS 规则)
        self.assertIn("build中", html_txt)            # 在飞 stage 显示

    def test_no_overlay_without_state(self):
        req = self._setup(with_state=False)
        out = os.path.join(self.tmp, "b.html")
        run("board", "--out", out, root=req)
        self.assertNotIn('class="live-badge', _read(out))  # 无在飞元素(CSS 规则不算)


def _leaf_status(root, leaf_id):
    dp = "/".join(leaf_id.split(".")[:2])
    txt = _read(os.path.join(root, *dp.split("/"), leaf_id + ".md"))
    for line in txt.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return None


class SetStatusTest(unittest.TestCase):
    def test_success(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "user.auth.login", status="captured")
            r = run("set-status", "--leaf", "user.auth.login", "--to", "built", root=root)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(_leaf_status(root, "user.auth.login"), "built")

    def test_allow_any_backward(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "user.auth.login", status="validated")
            r = run("set-status", "--leaf", "user.auth.login", "--to", "spec'd", root=root)
            self.assertEqual(r.returncode, 0)  # allow-any:回退也允许
            self.assertEqual(_leaf_status(root, "user.auth.login"), "spec'd")

    def test_bad_value(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "user.auth.login", status="captured")
            r = run("set-status", "--leaf", "user.auth.login", "--to", "banana", root=root)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(_leaf_status(root, "user.auth.login"), "captured")  # 未写

    def test_missing_leaf(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "user.auth.login", status="captured")
            r = run("set-status", "--leaf", "nope.x.y", "--to", "built", root=root)
            self.assertEqual(r.returncode, 2)


class LintBadStatusTest(unittest.TestCase):
    def test_rejects_unknown_status(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", status="banana")
            r = run("lint", root=root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("bad-status", r.stderr)

    def test_accepts_valid_status(self):
        with tempfile.TemporaryDirectory() as root:
            write_leaf(root, "order.checkout.a", status="built")
            r = run("lint", root=root)
            self.assertEqual(r.returncode, 0)


class StatusEnumTest(unittest.TestCase):
    def test_order_endpoints(self):
        self.assertEqual(backlog.STATUS_ORDER[0], "captured")
        self.assertEqual(backlog.STATUS_ORDER[-1], "shipped")

    def test_set_matches_order(self):
        self.assertEqual(backlog.STATUS_SET, set(backlog.STATUS_ORDER))

    def test_stage_map(self):
        self.assertEqual(backlog.STAGE_TO_STATUS["spec"], "spec'd")
        self.assertEqual(backlog.STAGE_TO_STATUS["build"], "built")
        self.assertEqual(backlog.STAGE_TO_STATUS["validate"], "validated")


if __name__ == "__main__":
    unittest.main()
