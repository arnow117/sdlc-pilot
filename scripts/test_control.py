#!/usr/bin/env python3
"""Contract tests for the SDLC control ledger.

The suite intentionally uses only the standard library so the control plane stays
portable across Claude, Codex, and a plain Python installation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import control  # noqa: E402
import control_store  # noqa: E402


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def requirement(leaf_id: str, *, request_id: str = "req-1", status: str = "captured",
                depends_on: list[str] | None = None, priority: str = "P2") -> dict:
    parts = leaf_id.split(".")
    domain_path = "/".join(parts[:2])
    return {
        "id": leaf_id,
        "title": f"Requirement {leaf_id}",
        "domain_path": domain_path,
        "cross_link": [],
        "old_system_ref": "(none)",
        "new_domain_path": domain_path,
        "status": status,
        "priority": priority,
        "depends_on": depends_on or [],
        "risk_level": "medium",
        "source_request": request_id,
        "updated": "2026-08-04",
    }


def task(task_id: str, *, depends_on: list[str] | None = None,
         write_set: list[str] | None = None, runtime_isolated: bool = True,
         interfaces_fixed: bool = True) -> dict:
    return {
        "task_id": task_id,
        "requirements": ["R-01"],
        "depends_on_tasks": depends_on or [],
        "write_set": write_set or [f"src/{task_id}.py"],
        "interface_owner": task_id,
        "interfaces_fixed": runtime_isolated and interfaces_fixed,
        "runtime_isolated": runtime_isolated,
        "read_first": ["scripts/control.py"],
        "action": f"Implement {task_id}",
        "acceptance_criteria": f"test {task_id} passes",
    }


def register_tasks(root: str, *, feature_id: str = "feat-a", plan_revision: str = SHA_B,
                   plan_text: str = "# Approved plan\n",
                   tasks: list[dict]) -> dict:
    plan_ref = f"features/{feature_id}/plans/{control.plan_content_id(plan_text)}.md"
    control.store_plan_artifact(
        root, feature_id=feature_id, plan_ref=plan_ref, plan_text=plan_text)
    return control.register_plan(
        root, feature_id=feature_id, plan_ref=plan_ref,
        plan_revision=plan_revision, plan_text=plan_text, tasks=tasks,
        at="2026-08-04T10:10:00+08:00")


def strict_plan(tasks: list[dict]) -> str:
    lines = ["# Approved plan", ""]
    for raw in tasks:
        lines.extend([
            f"### Task {raw['task_id']}: Implement {raw['task_id']}",
            f"- **id**: {raw['task_id']}",
            f"- **requirements**: [{', '.join(raw['requirements'])}]",
            f"- **depends_on_tasks**: [{', '.join(raw['depends_on_tasks'])}]",
            f"- **write_set**: [{', '.join(raw['write_set'])}]",
            f"- **interface_owner**: {raw['interface_owner']}",
            f"- **interfaces_fixed**: {'true' if raw['interfaces_fixed'] else 'false'}",
            f"- **runtime_isolated**: {'true' if raw['runtime_isolated'] else 'false'}",
            f"- **read_first**: [{', '.join(raw['read_first'])}]",
            f"- **action**: {raw['action']}",
            f"- **acceptance_criteria**: {raw['acceptance_criteria']}",
            "",
        ])
    return "\n".join(lines)


def seed_feature(root: str, *, leaf_id: str = "order.checkout.a",
                 feature_id: str = "feat-a") -> None:
    control.intake(
        root,
        request={"request_id": "req-1", "title": "Raw request", "body": "raw"},
        leaves=[requirement(leaf_id)],
        at="2026-08-04T10:00:00+08:00",
    )
    control.claim(
        root,
        leaf_id=leaf_id,
        feature_id=feature_id,
        feature_branch=f"feature/{feature_id}",
        claimed_base_sha=SHA_A,
        owner="agent-a",
        at="2026-08-04T10:01:00+08:00",
    )


class StrictCodecTest(unittest.TestCase):
    def test_round_trip_flat_record(self):
        record = {
            "schema_version": "1",
            "record_type": "claim",
            "leaf_id": "order.checkout.a",
            "feature_id": "feat-a",
            "status": "active",
            "evidence_refs": ["a/b.md", "c/d.md"],
            "runtime_isolated": True,
        }
        text = control_store.render_record(record, body="details")
        parsed = control_store.parse_record(text)
        self.assertEqual(parsed["leaf_id"], "order.checkout.a")
        self.assertEqual(parsed["evidence_refs"], ["a/b.md", "c/d.md"])
        self.assertIs(parsed["runtime_isolated"], True)
        self.assertEqual(parsed["_body"], "details")

    def test_rejects_nested_duplicate_and_unclosed_frontmatter(self):
        bad = [
            "---\nschema_version: 1\nrecord_type: task\n nested: bad\n---\n",
            "---\nschema_version: 1\nrecord_type: task\nstatus: ready\nstatus: blocked\n---\n",
            "---\nschema_version: 1\nrecord_type: task\n",
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(control_store.SchemaError):
                    control_store.parse_record(text)

    def test_safe_record_path_rejects_traversal_and_symlink_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "control"
            root.mkdir()
            with self.assertRaises(control_store.SchemaError):
                control_store.safe_record_path(root, "claims", "../escape.md")
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (root / "claims").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(control_store.SchemaError):
                control_store.safe_record_path(root, "claims", "leaf.md")

    def test_immutable_write_is_idempotent_but_refuses_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.md"
            record = {"schema_version": "1", "record_type": "evidence", "result": "pass"}
            self.assertTrue(control_store.write_record(path, record, immutable=True))
            self.assertFalse(control_store.write_record(path, record, immutable=True))
            changed = dict(record, result="fail")
            with self.assertRaises(control_store.ConflictError):
                control_store.write_record(path, changed, immutable=True)


class SnapshotAndLintTest(unittest.TestCase):
    def test_snapshot_has_stable_maps_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, ".sdlc-control")
            control.intake(
                root,
                request={"request_id": "req-1", "title": "Raw", "body": "body"},
                leaves=[requirement("order.checkout.a")],
                at="2026-08-04T10:00:00+08:00",
            )
            snap = control_store.load_control_snapshot(root)
            self.assertEqual(snap["schema_version"], 1)
            self.assertEqual(snap["mode"], "local-serial")
            self.assertIn("req-1", snap["requests_by_id"])
            self.assertIn("order.checkout.a", snap["requirements_by_id"])
            self.assertEqual(snap["tasks_by_feature"], {})
            self.assertEqual(snap["warnings"], [])

            missing = control_store.load_control_snapshot(
                os.path.join(tmp, "missing"), legacy_requirements_root=None)
            self.assertEqual(missing["mode"], "legacy")
            self.assertEqual(missing["requirements_by_id"], {})

    def test_lint_finds_missing_source_request_and_requirement_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".sdlc-control"
            root.mkdir()
            for leaf in (
                requirement("order.checkout.a", request_id="missing", depends_on=["order.checkout.b"]),
                requirement("order.checkout.b", request_id="missing", depends_on=["order.checkout.a"]),
            ):
                path = control_store.safe_record_path(
                    root, "requirements", *leaf["domain_path"].split("/"), f"{leaf['id']}.md")
                control_store.write_record(path, control.requirement_record(leaf))
            problems = control.lint(root)
            self.assertTrue(any("missing-source-request" in p for p in problems), problems)
            self.assertTrue(any("requirement-cycle" in p for p in problems), problems)

    def test_load_snapshot_from_missing_ref_is_non_mutating_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            before = sorted(os.listdir(tmp))
            snap = control_store.load_snapshot_from_ref(tmp, ref="sdlc-control")
            after = sorted(os.listdir(tmp))
            self.assertEqual(snap["mode"], "legacy")
            self.assertIn("control-ref-missing:sdlc-control", snap["warnings"])
            self.assertEqual(before, after)


class IntakeReadyClaimTest(unittest.TestCase):
    def test_intake_traces_multiple_leaves_to_one_request(self):
        with tempfile.TemporaryDirectory() as root:
            result = control.intake(
                root,
                request={"request_id": "req-1", "title": "Raw", "body": "raw input"},
                leaves=[requirement("order.checkout.a"), requirement("order.checkout.b")],
                at="2026-08-04T10:00:00+08:00",
            )
            self.assertEqual(result["leaf_ids"], ["order.checkout.a", "order.checkout.b"])
            snap = control_store.load_control_snapshot(root)
            self.assertEqual(
                {r["source_request"] for r in snap["requirements_by_id"].values()}, {"req-1"})

    def test_intake_prevalidates_all_paths_before_writing(self):
        with tempfile.TemporaryDirectory() as root:
            bad = requirement("order.checkout.bad")
            bad["domain_path"] = "../escape"
            with self.assertRaises(control_store.SchemaError):
                control.intake(
                    root, request={"request_id": "req-1", "title": "Raw"},
                    leaves=[requirement("order.checkout.good"), bad],
                    at="2026-08-04T10:00:00+08:00")
            self.assertFalse(Path(root, "requests", "req-1.md").exists())

    def test_readyqueue_excludes_blocked_shipped_and_active_claim(self):
        with tempfile.TemporaryDirectory() as root:
            a = requirement("order.checkout.a", status="shipped", priority="P1")
            b = requirement("order.checkout.b", depends_on=[a["id"]], priority="P0")
            missing = requirement("order.checkout.missing", priority="P3")
            c = requirement("order.checkout.c", depends_on=[missing["id"]], priority="P0")
            control.intake(root, request={"request_id": "req-1", "title": "Raw"},
                           leaves=[a, b, c, missing], at="2026-08-04T10:00:00+08:00")
            control.claim(root, leaf_id=missing["id"], feature_id="feat-missing",
                          feature_branch="feature/feat-missing", claimed_base_sha=SHA_A,
                          owner="agent-m", at="2026-08-04T10:00:30+08:00")
            self.assertEqual([x["leaf_id"] for x in control.readyqueue(root)], [b["id"]])
            control.claim(root, leaf_id=b["id"], feature_id="feat-b",
                          feature_branch="feature/feat-b", claimed_base_sha=SHA_A,
                          owner="agent-b", at="2026-08-04T10:01:00+08:00")
            self.assertEqual(control.readyqueue(root), [])

    def test_claim_conflict_reports_existing_owner_and_release_allows_reclaim(self):
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            with self.assertRaises(control_store.ConflictError) as cm:
                control.claim(root, leaf_id="order.checkout.a", feature_id="feat-b",
                              feature_branch="feature/feat-b", claimed_base_sha=SHA_A,
                              owner="agent-b", at="2026-08-04T10:02:00+08:00")
            self.assertIn("agent-a", str(cm.exception))
            with self.assertRaises(control_store.ConflictError):
                control.release(root, leaf_id="order.checkout.a", feature_id="feat-a",
                                owner="agent-b", at="2026-08-04T10:02:30+08:00",
                                reason="wrong owner")
            released = control.release(root, leaf_id="order.checkout.a", feature_id="feat-a",
                                       owner="agent-a",
                                       at="2026-08-04T10:03:00+08:00", reason="abandoned")
            self.assertEqual(released["status"], "released")
            claimed = control.claim(root, leaf_id="order.checkout.a", feature_id="feat-b",
                                    feature_branch="feature/feat-b", claimed_base_sha=SHA_B,
                                    owner="agent-b", at="2026-08-04T10:04:00+08:00")
            self.assertEqual(claimed["feature_id"], "feat-b")

    def test_feature_id_cannot_bind_two_leaves(self):
        with tempfile.TemporaryDirectory() as root:
            control.intake(root, request={"request_id": "req-1", "title": "Raw"},
                           leaves=[requirement("order.checkout.a"), requirement("order.checkout.b")],
                           at="2026-08-04T10:00:00+08:00")
            control.claim(root, leaf_id="order.checkout.a", feature_id="feat-a",
                          feature_branch="feature/feat-a", claimed_base_sha=SHA_A,
                          owner="a", at="2026-08-04T10:01:00+08:00")
            with self.assertRaises(control_store.ConflictError):
                control.claim(root, leaf_id="order.checkout.b", feature_id="feat-a",
                              feature_branch="feature/feat-a-2", claimed_base_sha=SHA_A,
                              owner="b", at="2026-08-04T10:02:00+08:00")


class TaskRegistrationAndEligibilityTest(unittest.TestCase):
    def register(self, root: str, tasks: list[dict]) -> dict:
        seed_feature(root)
        plan_text = "# Approved plan\n"
        return register_tasks(root, plan_text=plan_text, tasks=tasks)

    def test_registration_derives_ready_and_waiting_and_rejects_cycle(self):
        with tempfile.TemporaryDirectory() as root:
            self.register(root, [task("T1"), task("T2", depends_on=["T1"])])
            snap = control_store.load_control_snapshot(root)
            by_id = {x["task_id"]: x for x in snap["tasks_by_feature"]["feat-a"]}
            self.assertEqual(by_id["T1"]["status"], "ready")
            self.assertEqual(by_id["T2"]["status"], "waiting")
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            with self.assertRaises(control_store.SchemaError):
                register_tasks(
                    root, plan_text="# p",
                    tasks=[task("T1", depends_on=["T2"]), task("T2", depends_on=["T1"])])

    def test_plan_snapshot_uses_fixed_feature_path(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.register(root, [task("T1")])
            plan_text = "# Approved plan\n"
            expected = f"features/feat-a/plans/{control.plan_content_id(plan_text)}.md"
            self.assertEqual(result["plan_ref"], expected)
            self.assertEqual(Path(root, expected).read_text(encoding="utf-8"), plan_text)

    def test_write_set_rejects_glob_absolute_and_traversal(self):
        for invalid in ("src/*.py", "/etc/passwd", "src/../secret", "../secret"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(control_store.SchemaError):
                    control.normalize_write_set([invalid])

    def test_missing_and_self_dependency_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            with self.assertRaises(control_store.SchemaError):
                register_tasks(
                    root, plan_text="# p", tasks=[task("T1", depends_on=["missing"])])
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            with self.assertRaises(control_store.SchemaError):
                register_tasks(
                    root, plan_text="# p", tasks=[task("T1", depends_on=["T1"])])

    def test_branch_eligibility_enforces_each_condition(self):
        scenarios = [
            (task("T1", runtime_isolated=False), "runtime-not-isolated"),
            (task("T1", interfaces_fixed=False), "interfaces-not-fixed"),
        ]
        for task_input, reason in scenarios:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as root:
                self.register(root, [task_input])
                result = control.task_eligibility(root, feature_id="feat-a", task_id="T1",
                                                  feature_head_sha=SHA_A)
                self.assertFalse(result["eligible"])
                self.assertIn(reason, result["reasons"])

    def test_branch_eligibility_rejects_invalid_interface_owner(self):
        for owner in ("", "(none)", "missing-task"):
            with self.subTest(owner=owner), tempfile.TemporaryDirectory() as root:
                item = task("T1")
                item["interface_owner"] = owner
                self.register(root, [item])
                result = control.task_eligibility(
                    root, feature_id="feat-a", task_id="T1", feature_head_sha=SHA_A)
                self.assertIn("invalid-interface-owner", result["reasons"])

    def test_write_set_overlap_active_limit_and_serial_exclusion(self):
        with tempfile.TemporaryDirectory() as root:
            self.register(root, [
                task("T1", write_set=["src/shared/"]),
                task("T2", write_set=["src/shared/x.py"]),
                task("T3"), task("T4"), task("T5"),
            ])
            control.task_event(root, feature_id="feat-a", task_id="T1", event="claim",
                               at="2026-08-04T10:11:00+08:00", owner="a",
                               execution_mode="task_branch", branch_name="task/T1",
                               branch_base_sha=SHA_A, feature_head_sha=SHA_A)
            overlap = control.task_eligibility(root, feature_id="feat-a", task_id="T2",
                                               feature_head_sha=SHA_A)
            self.assertIn("write-set-overlap:T1", overlap["reasons"])
            for tid in ("T3", "T4"):
                control.task_event(root, feature_id="feat-a", task_id=tid, event="claim",
                                   at="2026-08-04T10:12:00+08:00", owner=tid,
                                   execution_mode="task_branch", branch_name=f"task/{tid}",
                                   branch_base_sha=SHA_A, feature_head_sha=SHA_A)
            limited = control.task_eligibility(root, feature_id="feat-a", task_id="T5",
                                               feature_head_sha=SHA_A)
            self.assertIn("active-branch-limit", limited["reasons"])

        with tempfile.TemporaryDirectory() as root:
            self.register(root, [task("T1"), task("T2")])
            with self.assertRaises(control_store.ConflictError):
                control.task_event(root, feature_id="feat-a", task_id="T1", event="claim",
                                   at="2026-08-04T10:10:00+08:00", owner="a",
                                   execution_mode="serial", feature_head_sha=SHA_B)
            control.task_event(root, feature_id="feat-a", task_id="T1", event="claim",
                               at="2026-08-04T10:11:00+08:00", owner="a",
                               execution_mode="serial", feature_head_sha=SHA_A)
            result = control.task_eligibility(root, feature_id="feat-a", task_id="T2",
                                              feature_head_sha=SHA_A)
            self.assertIn("serial-task-active:T1", result["reasons"])

    def test_guarded_state_machine_and_resulting_integration_sha(self):
        with tempfile.TemporaryDirectory() as root:
            self.register(root, [task("T1")])
            with self.assertRaises(control_store.ConflictError):
                control.task_event(root, feature_id="feat-a", task_id="T1", event="start",
                                   at="2026-08-04T10:11:00+08:00")
            control.task_event(root, feature_id="feat-a", task_id="T1", event="claim",
                               at="2026-08-04T10:11:00+08:00", owner="a",
                               execution_mode="task_branch", branch_name="task/T1",
                               branch_base_sha=SHA_A, feature_head_sha=SHA_A)
            control.task_event(root, feature_id="feat-a", task_id="T1", event="start",
                               at="2026-08-04T10:12:00+08:00")
            control.task_event(root, feature_id="feat-a", task_id="T1", event="submit",
                               at="2026-08-04T10:13:00+08:00", branch_head_sha=SHA_B)
            integrated = control.record_integration(
                root, feature_id="feat-a", task_id="T1", source_tip_sha=SHA_B,
                integration_sha=SHA_C, merge_method="squash", at="2026-08-04T10:14:00+08:00")
            self.assertEqual(integrated["branch_head_sha"], SHA_B)
            self.assertEqual(integrated["integration_sha"], SHA_C)
            self.assertNotEqual(integrated["integration_sha"], integrated["branch_head_sha"])

    def test_blocked_resume_and_verification_retry(self):
        with tempfile.TemporaryDirectory() as root:
            self.register(root, [task("T1"), task("T2", depends_on=["T1"])])
            blocked_ready = control.task_event(
                root, feature_id="feat-a", task_id="T1", event="block",
                at="2026-08-04T10:11:00+08:00", reason="x")
            self.assertEqual(blocked_ready["status"], "blocked")
            resumed_ready = control.task_event(
                root, feature_id="feat-a", task_id="T1", event="resume",
                at="2026-08-04T10:12:00+08:00")
            self.assertEqual(resumed_ready["status"], "ready")
            control.task_event(root, feature_id="feat-a", task_id="T2", event="block",
                               at="2026-08-04T10:13:00+08:00", reason="dependency")
            resumed_waiting = control.task_event(
                root, feature_id="feat-a", task_id="T2", event="resume",
                at="2026-08-04T10:14:00+08:00")
            self.assertEqual(resumed_waiting["status"], "waiting")
            control.task_event(root, feature_id="feat-a", task_id="T1", event="claim",
                               at="2026-08-04T10:15:00+08:00", owner="a",
                               execution_mode="serial", feature_head_sha=SHA_A)
            control.task_event(root, feature_id="feat-a", task_id="T1", event="start",
                               at="2026-08-04T10:16:00+08:00")
            control.task_event(root, feature_id="feat-a", task_id="T1", event="submit",
                               at="2026-08-04T10:17:00+08:00", branch_head_sha=SHA_B)
            retried = control.task_event(root, feature_id="feat-a", task_id="T1", event="retry",
                                         at="2026-08-04T10:18:00+08:00")
            self.assertEqual(retried["status"], "in_progress")

    def test_action_and_acceptance_live_only_in_task_body(self):
        with tempfile.TemporaryDirectory() as root:
            item = task("T1")
            item["action"] = "line one\nline two"
            item["acceptance_criteria"] = "run test\nexpect pass"
            self.register(root, [item])
            snap = control_store.load_control_snapshot(root)
            stored = snap["tasks_by_feature"]["feat-a"][0]
            self.assertNotIn("action", stored)
            self.assertNotIn("acceptance_criteria", stored)
            self.assertIn("## Action\nline one\nline two", stored["_body"])
            self.assertIn("## Acceptance criteria\nrun test\nexpect pass", stored["_body"])


class EvidenceFreshnessRetireTest(unittest.TestCase):
    def setUpFeature(self, root: str) -> None:
        seed_feature(root)
        plan_text = "# plan"
        register_tasks(root, plan_text=plan_text, tasks=[task("T1", write_set=["src/a/"])])
        control.task_event(root, feature_id="feat-a", task_id="T1", event="claim",
                           at="2026-08-04T10:11:00+08:00", owner="a",
                           execution_mode="serial", feature_head_sha=SHA_A)
        control.task_event(root, feature_id="feat-a", task_id="T1", event="start",
                           at="2026-08-04T10:12:00+08:00")
        control.task_event(root, feature_id="feat-a", task_id="T1", event="submit",
                           at="2026-08-04T10:13:00+08:00", branch_head_sha=SHA_C)
        control.record_integration(root, feature_id="feat-a", task_id="T1",
                                   source_tip_sha=SHA_C, integration_sha=SHA_C,
                                   merge_method="serial", at="2026-08-04T10:14:00+08:00")

    def test_evidence_is_immutable_allows_attempts_and_verify_binds_integration(self):
        with tempfile.TemporaryDirectory() as root:
            self.setUpFeature(root)
            failed = control.record_evidence(
                root, feature_id="feat-a", task_id="T1", scope="task", result="fail",
                tested_sha=SHA_C, command="python -m unittest", output="failed",
                producer="orchestrator", at="2026-08-04T10:15:00+08:00")
            passed = control.record_evidence(
                root, feature_id="feat-a", task_id="T1", scope="task", result="pass",
                tested_sha=SHA_C, command="python -m unittest", output="passed",
                producer="orchestrator", at="2026-08-04T10:16:00+08:00")
            self.assertNotEqual(failed["evidence_ref"], passed["evidence_ref"])
            with self.assertRaises(control_store.ConflictError):
                control.task_event(root, feature_id="feat-a", task_id="T1", event="verify",
                                   at="2026-08-04T10:17:00+08:00",
                                   evidence_ref=failed["evidence_ref"])
            verified = control.task_event(
                root, feature_id="feat-a", task_id="T1", event="verify",
                at="2026-08-04T10:18:00+08:00", evidence_ref=passed["evidence_ref"])
            self.assertEqual(verified["status"], "verified")

    def test_verify_rejects_task_tip_evidence_after_squash(self):
        with tempfile.TemporaryDirectory() as root:
            self.setUpFeature(root)
            wrong = control.record_evidence(
                root, feature_id="feat-a", task_id="T1", scope="task", result="pass",
                tested_sha=SHA_B, command="test", output="ok", producer="o",
                at="2026-08-04T10:15:00+08:00")
            with self.assertRaises(control_store.ConflictError):
                control.task_event(root, feature_id="feat-a", task_id="T1", event="verify",
                                   at="2026-08-04T10:16:00+08:00",
                                   evidence_ref=wrong["evidence_ref"])

    def test_freshness_exact_disjoint_overlap_and_unknown(self):
        base_task = {"integration_sha": SHA_A, "write_set": ["src/a/"]}
        self.assertEqual(control.compute_freshness(base_task, current_head_sha=SHA_A), "fresh")
        self.assertEqual(control.compute_freshness(
            base_task, current_head_sha=SHA_B, changed_paths=["src/b/x.py"]), "fresh")
        self.assertEqual(control.compute_freshness(
            base_task, current_head_sha=SHA_B, changed_paths=["src/a/x.py"]), "stale")
        self.assertEqual(control.compute_freshness(
            base_task, current_head_sha=SHA_B, changed_paths=None), "unknown")

    def test_freshness_non_ancestor_is_unknown(self):
        with tempfile.TemporaryDirectory() as repo:
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.com"],
                           check=True)
            Path(repo, "base.txt").write_text("base", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "base.txt"], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "base"], check=True)
            base = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True,
                                  capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "-C", repo, "checkout", "-q", "--orphan", "other"],
                           check=True)
            subprocess.run(["git", "-C", repo, "rm", "-qf", "base.txt"], check=True)
            Path(repo, "other.txt").write_text("other", encoding="utf-8")
            subprocess.run(["git", "-C", repo, "add", "other.txt"], check=True)
            subprocess.run(["git", "-C", repo, "commit", "-qm", "other"], check=True)
            other = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True,
                                   capture_output=True, text=True).stdout.strip()
            self.assertEqual(control.compute_freshness(
                {"integration_sha": base, "write_set": ["base.txt"]},
                current_head_sha=other, repo_root=repo), "unknown")

    def test_feature_validation_requires_current_head_evidence_then_retire_releases(self):
        with tempfile.TemporaryDirectory() as root:
            self.setUpFeature(root)
            task_ev = control.record_evidence(
                root, feature_id="feat-a", task_id="T1", scope="task", result="pass",
                tested_sha=SHA_C, command="unit", output="ok", producer="o",
                at="2026-08-04T10:15:00+08:00")
            control.task_event(root, feature_id="feat-a", task_id="T1", event="verify",
                               at="2026-08-04T10:16:00+08:00",
                               evidence_ref=task_ev["evidence_ref"])
            stale = control.record_evidence(
                root, feature_id="feat-a", task_id="_feature", scope="feature", result="pass",
                tested_sha=SHA_B, command="all", output="ok", producer="o",
                at="2026-08-04T10:17:00+08:00")
            with self.assertRaises(control_store.ConflictError):
                control.validate_feature(root, feature_id="feat-a", current_head_sha=SHA_C,
                                         evidence_ref=stale["evidence_ref"],
                                         at="2026-08-04T10:18:00+08:00")
            fresh = control.record_evidence(
                root, feature_id="feat-a", task_id="_feature", scope="feature", result="pass",
                tested_sha=SHA_C, command="all", output="ok", producer="o",
                at="2026-08-04T10:19:00+08:00")
            validated = control.validate_feature(
                root, feature_id="feat-a", current_head_sha=SHA_C,
                evidence_ref=fresh["evidence_ref"], at="2026-08-04T10:20:00+08:00")
            self.assertEqual(validated["status"], "validated")
            control.record_review(
                root, feature_id="feat-a", reviewed_sha=SHA_C, verdict="pass",
                report_refs=["review/summary.md"], reviewer="reviewer",
                at="2026-08-04T10:20:15+08:00")
            release_evidence = control.record_evidence(
                root, feature_id="feat-a", task_id="_feature", scope="release", result="pass",
                tested_sha=SHA_C, command="smoke", output="ok", producer="ship",
                at="2026-08-04T10:20:30+08:00")
            retired = control.retire(root, feature_id="feat-a",
                                     evidence_ref=release_evidence["evidence_ref"],
                                     at="2026-08-04T10:21:00+08:00")
            self.assertEqual(retired["feature_status"], "shipped")
            snap = control_store.load_control_snapshot(root)
            self.assertEqual(snap["claims_by_leaf"]["order.checkout.a"]["status"], "released")
            self.assertEqual(snap["requirements_by_id"]["order.checkout.a"]["status"], "shipped")

    def test_retire_rejects_missing_failed_and_stale_release_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            self.setUpFeature(root)
            task_ev = control.record_evidence(
                root, feature_id="feat-a", task_id="T1", scope="task", result="pass",
                tested_sha=SHA_C, command="unit", output="ok", producer="o",
                at="2026-08-04T10:15:00+08:00")
            control.task_event(root, feature_id="feat-a", task_id="T1", event="verify",
                               at="2026-08-04T10:16:00+08:00",
                               evidence_ref=task_ev["evidence_ref"])
            feature_ev = control.record_evidence(
                root, feature_id="feat-a", task_id="_feature", scope="feature", result="pass",
                tested_sha=SHA_C, command="all", output="ok", producer="o",
                at="2026-08-04T10:17:00+08:00")
            control.validate_feature(root, feature_id="feat-a", current_head_sha=SHA_C,
                                     evidence_ref=feature_ev["evidence_ref"],
                                     at="2026-08-04T10:18:00+08:00")
            control.record_review(
                root, feature_id="feat-a", reviewed_sha=SHA_C, verdict="pass",
                report_refs=["review/summary.md"], reviewer="reviewer",
                at="2026-08-04T10:18:30+08:00")
            with self.assertRaises((control_store.SchemaError, control_store.ConflictError)):
                control.retire(root, feature_id="feat-a", evidence_ref=None,
                               at="2026-08-04T10:19:00+08:00")
            for result, tested_sha in (("fail", SHA_C), ("pass", SHA_B)):
                evidence = control.record_evidence(
                    root, feature_id="feat-a", task_id="_feature", scope="release",
                    result=result, tested_sha=tested_sha, command="smoke", output=result,
                    producer="ship", at=f"2026-08-04T10:20:0{0 if result == 'fail' else 1}+08:00")
                with self.assertRaises(control_store.ConflictError):
                    control.retire(root, feature_id="feat-a",
                                   evidence_ref=evidence["evidence_ref"],
                                   at="2026-08-04T10:21:00+08:00")

    def test_superseded_is_excluded_but_abandoned_blocks_validation(self):
        for event, should_validate in (("supersede", True), ("abandon", False)):
            with self.subTest(event=event), tempfile.TemporaryDirectory() as root:
                seed_feature(root)
                plan_text = "# plan"
                register_tasks(root, plan_text=plan_text, tasks=[task("T1")])
                control.task_event(root, feature_id="feat-a", task_id="T1", event=event,
                                   at="2026-08-04T10:11:00+08:00", reason="plan changed")
                evidence = control.record_evidence(
                    root, feature_id="feat-a", task_id="_feature", scope="feature",
                    result="pass", tested_sha=SHA_A, command="all", output="ok",
                    producer="o", at="2026-08-04T10:12:00+08:00")
                if should_validate:
                    result = control.validate_feature(
                        root, feature_id="feat-a", current_head_sha=SHA_A,
                        evidence_ref=evidence["evidence_ref"],
                        at="2026-08-04T10:13:00+08:00")
                    self.assertEqual(result["status"], "validated")
                else:
                    with self.assertRaises(control_store.ConflictError):
                        control.validate_feature(
                            root, feature_id="feat-a", current_head_sha=SHA_A,
                            evidence_ref=evidence["evidence_ref"],
                            at="2026-08-04T10:13:00+08:00")


class ControlRegressionTest(unittest.TestCase):
    def test_same_claim_is_idempotent_and_wrong_owner_conflicts(self):
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            retry = control.claim(
                root, leaf_id="order.checkout.a", feature_id="feat-a",
                feature_branch="feature/feat-a", claimed_base_sha=SHA_A,
                owner="agent-a", at="2026-08-04T10:02:00+08:00")
            self.assertTrue(retry["idempotent"])
            with self.assertRaises(control_store.ConflictError):
                control.claim(
                    root, leaf_id="order.checkout.a", feature_id="feat-a",
                    feature_branch="feature/feat-a", claimed_base_sha=SHA_A,
                    owner="different", at="2026-08-04T10:03:00+08:00")

    def test_task_booleans_are_strict(self):
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            malformed = task("T1")
            malformed["runtime_isolated"] = "false"
            with self.assertRaises(control_store.SchemaError):
                register_tasks(root, tasks=[malformed])

    def test_same_task_id_across_features_and_evidence_is_feature_bound(self):
        with tempfile.TemporaryDirectory() as root:
            control.intake(
                root, request={"request_id": "req-1", "title": "Raw"},
                leaves=[requirement("order.checkout.a"), requirement("order.checkout.b")],
                at="2026-08-04T10:00:00+08:00")
            for feature_id, leaf_id in (("feat-a", "order.checkout.a"),
                                        ("feat-b", "order.checkout.b")):
                control.claim(
                    root, leaf_id=leaf_id, feature_id=feature_id,
                    feature_branch=f"feature/{feature_id}", claimed_base_sha=SHA_A,
                    owner=feature_id, at="2026-08-04T10:01:00+08:00")
                register_tasks(root, feature_id=feature_id, tasks=[task("T1")])
                control.task_event(
                    root, feature_id=feature_id, task_id="T1", event="claim",
                    execution_mode="serial", feature_head_sha=SHA_A,
                    owner=feature_id, at="2026-08-04T10:02:00+08:00")
                control.task_event(root, feature_id=feature_id, task_id="T1", event="start",
                                   at="2026-08-04T10:03:00+08:00")
                control.task_event(
                    root, feature_id=feature_id, task_id="T1", event="submit",
                    branch_head_sha=SHA_B, at="2026-08-04T10:04:00+08:00")
                control.record_integration(
                    root, feature_id=feature_id, task_id="T1", source_tip_sha=SHA_B,
                    integration_sha=SHA_C, merge_method="serial",
                    at="2026-08-04T10:05:00+08:00")
            snap = control.load_control_snapshot(root)
            self.assertEqual(len(snap["tasks_by_feature"]["feat-a"]), 1)
            self.assertEqual(len(snap["tasks_by_feature"]["feat-b"]), 1)
            self.assertEqual(snap["warnings"], [])
            evidence = control.record_evidence(
                root, feature_id="feat-a", task_id="T1", scope="task", result="pass",
                tested_sha=SHA_C, command="test", output="ok", producer="qa",
                at="2026-08-04T10:06:00+08:00")
            with self.assertRaises(control_store.ConflictError):
                control.task_event(
                    root, feature_id="feat-b", task_id="T1", event="verify",
                    evidence_ref=evidence["evidence_ref"], at="2026-08-04T10:07:00+08:00")

    def test_replan_scopes_reused_task_ids_by_revision(self):
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            register_tasks(root, plan_revision=SHA_B, plan_text="# plan one", tasks=[task("T1")])
            register_tasks(root, plan_revision=SHA_C, plan_text="# plan two", tasks=[task("T1")])
            snap = control.load_control_snapshot(root)
            records = snap["tasks_by_feature"]["feat-a"]
            self.assertEqual(len(records), 2)
            self.assertEqual(snap["features_by_id"]["feat-a"]["plan_revision"], SHA_C)
            old = next(item for item in records if item["plan_revision"] == SHA_B)
            self.assertEqual(old["status"], "superseded")

    def test_strict_lint_rejects_invalid_task_status(self):
        with tempfile.TemporaryDirectory() as root:
            seed_feature(root)
            register_tasks(root, tasks=[task("T1")])
            snap = control.load_control_snapshot(root)
            record = snap["tasks_by_feature"]["feat-a"][0]
            record["status"] = "banana"
            control_store.write_record(Path(root) / record["_path"], record,
                                       body=record["_body"])
            self.assertTrue(any("invalid-status:task" in item for item in control.lint(root)))


class GitFastForwardTest(unittest.TestCase):
    def _git(self, cwd: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd, check=check, text=True,
                              capture_output=True)

    def test_two_clones_from_same_tip_only_one_pushes(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = os.path.join(tmp, "remote.git")
            seed = os.path.join(tmp, "seed")
            clone_a = os.path.join(tmp, "a")
            clone_b = os.path.join(tmp, "b")
            self._git(tmp, "init", "--bare", "-q", remote)
            self._git(tmp, "init", "-q", seed)
            self._git(seed, "config", "user.name", "test")
            self._git(seed, "config", "user.email", "test@example.com")
            os.makedirs(os.path.join(seed, ".sdlc-control"))
            Path(seed, ".sdlc-control", ".keep").write_text("", encoding="utf-8")
            self._git(seed, "add", ".sdlc-control/.keep")
            self._git(seed, "commit", "-qm", "init control")
            self._git(seed, "branch", "-M", "sdlc-control")
            self._git(seed, "remote", "add", "origin", remote)
            self._git(seed, "push", "-q", "origin", "sdlc-control")
            self._git(tmp, "clone", "-q", "--branch", "sdlc-control", remote, clone_a)
            self._git(tmp, "clone", "-q", "--branch", "sdlc-control", remote, clone_b)
            for clone, marker in ((clone_a, "a"), (clone_b, "b")):
                self._git(clone, "config", "user.name", "test")
                self._git(clone, "config", "user.email", "test@example.com")
                Path(clone, ".sdlc-control", f"{marker}.md").write_text(marker, encoding="utf-8")
                self._git(clone, "add", ".sdlc-control")
                self._git(clone, "commit", "-qm", marker)
            base = self._git(clone_a, "rev-parse", "HEAD^").stdout.strip()
            pushed = control_store.push_control_head(
                clone_a, expected_remote_sha=base, remote="origin", branch="sdlc-control")
            self.assertTrue(pushed["pushed"])
            with self.assertRaises(control_store.ConflictError):
                control_store.push_control_head(
                    clone_b, expected_remote_sha=base, remote="origin", branch="sdlc-control")


class GitControlStoreTest(unittest.TestCase):
    def _git(self, cwd: str, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=cwd, check=True,
                              capture_output=True, text=True)
        return proc.stdout.strip()

    def _repo(self, tmp: str, *, with_remote: bool) -> tuple[str, str | None]:
        repo = os.path.join(tmp, "repo")
        remote = os.path.join(tmp, "remote.git") if with_remote else None
        if remote:
            self._git(tmp, "init", "--bare", "-q", remote)
        self._git(tmp, "init", "-q", repo)
        self._git(repo, "config", "user.name", "test")
        self._git(repo, "config", "user.email", "test@example.com")
        Path(repo, "README.md").write_text("main", encoding="utf-8")
        self._git(repo, "add", "README.md")
        self._git(repo, "commit", "-qm", "main")
        if remote:
            self._git(repo, "remote", "add", "origin", remote)
        return repo, remote

    def test_initialize_orphan_tracks_only_control_paths_without_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = self._repo(tmp, with_remote=True)
            before_branch = self._git(repo, "branch", "--show-current")
            store = control_store.GitControlStore(repo, mode="shared-control")
            result = store.initialize(at="2026-08-04T10:00:00+08:00")
            self.assertTrue(result["initialized"])
            paths = self._git(repo, "ls-tree", "-r", "--name-only", result["control_sha"])
            self.assertEqual(paths.splitlines(), [".sdlc-control/meta.md"])
            self.assertEqual(self._git(repo, "branch", "--show-current"), before_branch)

    def test_local_serial_uses_update_ref_compare_and_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = self._repo(tmp, with_remote=False)
            store = control_store.GitControlStore(repo, mode="local-serial")
            base = store.initialize(at="2026-08-04T10:00:00+08:00")["control_sha"]
            tx_a = store.begin(expected_control_sha=base)
            tx_b = store.begin(expected_control_sha=base)
            try:
                control.intake(
                    tx_a.control_root, request={"request_id": "req-a", "title": "A"},
                    leaves=[requirement("order.checkout.a", request_id="req-a")],
                    at="2026-08-04T10:01:00+08:00")
                control.intake(
                    tx_b.control_root, request={"request_id": "req-b", "title": "B"},
                    leaves=[requirement("order.checkout.b", request_id="req-b")],
                    at="2026-08-04T10:01:00+08:00")
                tx_a.commit_and_publish("a")
                with self.assertRaises(control_store.ConcurrentControlUpdate):
                    tx_b.commit_and_publish("b")
            finally:
                tx_a.close()
                tx_b.close()

    def test_transaction_rejects_business_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = self._repo(tmp, with_remote=False)
            store = control_store.GitControlStore(repo, mode="local-serial")
            store.initialize(at="2026-08-04T10:00:00+08:00")
            tx = store.begin()
            try:
                Path(tx.worktree, "business.txt").write_text("no", encoding="utf-8")
                with self.assertRaises(control_store.SchemaError):
                    tx.commit_and_publish("bad")
            finally:
                tx.close()

    def test_register_plan_publishes_plan_then_revision_bound_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = self._repo(tmp, with_remote=False)
            store = control_store.GitControlStore(repo, mode="local-serial")
            base = store.initialize(at="2026-08-04T10:00:00+08:00")["control_sha"]

            def seed(root):
                control.intake(
                    root, request={"request_id": "req-1", "title": "Raw"},
                    leaves=[requirement("order.checkout.a")],
                    at="2026-08-04T10:01:00+08:00")
                return control.claim(
                    root, leaf_id="order.checkout.a", feature_id="feat-a",
                    feature_branch="feature/feat-a", claimed_base_sha=SHA_A,
                    owner="agent-a", at="2026-08-04T10:02:00+08:00")

            seeded = store.mutate(seed, message="seed", expected_control_sha=base)
            before_plan = seeded["control_sha"]
            plan_text = strict_plan([task("T1")])
            result = store.register_plan(
                feature_id="feat-a", plan_text=plan_text,
                expected_control_sha=before_plan, at="2026-08-04T10:03:00+08:00")
            plan_sha = result["plan_commit_sha"]
            final_sha = result["control_sha"]
            self.assertEqual(self._git(repo, "rev-parse", f"{plan_sha}^"), before_plan)
            self.assertEqual(self._git(repo, "rev-parse", f"{final_sha}^"), plan_sha)
            plan_path = f".sdlc-control/{result['plan_ref']}"
            self.assertEqual(self._git(repo, "show", f"{plan_sha}:{plan_path}"),
                             plan_text.rstrip())
            task_path = f".sdlc-control/tasks/feat-a/{plan_sha}/T1.md"
            self.assertIn(f"plan_revision: {plan_sha}",
                          self._git(repo, "show", f"{final_sha}:{task_path}"))

    def test_mutating_cli_publishes_through_local_cas(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = self._repo(tmp, with_remote=False)
            store = control_store.GitControlStore(repo, mode="local-serial")
            base = store.initialize(at="2026-08-04T10:00:00+08:00")["control_sha"]
            request_path = Path(tmp, "request.json")
            leaves_path = Path(tmp, "leaves.json")
            request_path.write_text(
                json.dumps({"request_id": "req-1", "title": "Raw"}), encoding="utf-8")
            leaves_path.write_text(
                json.dumps([requirement("order.checkout.a")]), encoding="utf-8")
            proc = subprocess.run([
                sys.executable, str(HERE / "control.py"), "intake",
                "--repo-root", repo, "--mode", "local-serial",
                "--expected-control-sha", base,
                "--request-json", str(request_path), "--leaves-json", str(leaves_path),
                "--at", "2026-08-04T10:01:00+08:00",
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["pushed"])
            self.assertEqual(payload["control_sha"], store.current_sha(refresh=False))


class GitControlRaceTest(GitControlStoreTest):
    def test_two_transactions_same_leaf_only_one_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _ = self._repo(tmp, with_remote=True)
            store = control_store.GitControlStore(repo, mode="shared-control")
            store.initialize(at="2026-08-04T10:00:00+08:00")
            with store.begin() as seed:
                control.intake(
                    seed.control_root, request={"request_id": "req-1", "title": "Raw"},
                    leaves=[requirement("order.checkout.a")],
                    at="2026-08-04T10:01:00+08:00")
                seed.commit_and_publish("seed")
            tx_a = store.begin()
            tx_b = store.begin(expected_control_sha=tx_a.expected_control_sha)
            try:
                control.claim(
                    tx_a.control_root, leaf_id="order.checkout.a", feature_id="feat-a",
                    feature_branch="feature/a", claimed_base_sha=SHA_A, owner="agent-a",
                    at="2026-08-04T10:02:00+08:00")
                control.claim(
                    tx_b.control_root, leaf_id="order.checkout.a", feature_id="feat-b",
                    feature_branch="feature/b", claimed_base_sha=SHA_A, owner="agent-b",
                    at="2026-08-04T10:02:00+08:00")
                tx_a.commit_and_publish("claim a")
                with self.assertRaises(control_store.ClaimConflict) as cm:
                    tx_b.commit_and_publish("claim b")
                self.assertEqual(cm.exception.owner, "agent-a")
                self.assertEqual(cm.exception.feature_id, "feat-a")
            finally:
                tx_a.close()
                tx_b.close()


class CliSmokeTest(unittest.TestCase):
    def test_snapshot_and_lint_emit_json(self):
        with tempfile.TemporaryDirectory() as root:
            control.intake(root, request={"request_id": "req-1", "title": "Raw"},
                           leaves=[requirement("order.checkout.a")],
                           at="2026-08-04T10:00:00+08:00")
            for args in (["snapshot", "--control-root", root],
                         ["lint", "--control-root", root]):
                proc = subprocess.run([sys.executable, str(HERE / "control.py"), *args],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                json.loads(proc.stdout)


if __name__ == "__main__":
    unittest.main()
