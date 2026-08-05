#!/usr/bin/env python3
"""Tests for EngineeringSpec → immutable static DeliveryPlan compilation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import unittest

import contract_bundle
import plan_compiler


SHA_A = "a" * 64
SHA_B = "b" * 64
GIT_A = "a" * 40


def contract_fixture() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    product = contract_bundle.build_product_contract({
        "contract_kind": "feature", "leaf_id": "REQ-001", "source_request": "REQ-001",
        "components": {"product.md": "OUT", "behaviors.md": "SCN"},
        "outcome_ids": ["OUT-001"], "behavior_ids": ["SCN-001"],
        "behavior_kinds": {"SCN-001": "new_behavior"}, "domain_rule_ids": [],
        "experience_ids": [], "nfr_ids": [], "eval_ids": [], "intent_flags": {}, "supersedes": None,
        "created_by": "product-owner", "created_at": "t",
    })
    profile = contract_bundle.snapshot_profile(
        b"# profile\n", feature_id="FEAT-001", source_sha=GIT_A, created_at="t",
    )
    engineering = contract_bundle.build_engineering_spec({
        "feature_id": "FEAT-001", "product_contract_approval_ref": SHA_A,
        "specified_against_sha": GIT_A, "implements_product_ids": ["SCN-001"],
        "engineering_criterion_ids": ["API-001", "TEST-001"], "target_surfaces": ["server"],
        "components": {"technical.md": "API", "tests.md": "TEST"}, "supersedes": None,
        "created_by": "architect", "created_at": "t",
    }, product, profile)
    approval = {
        "approval_id": SHA_B, "subject_type": "engineering_spec", "scope": "feature",
        "subject_id": engineering["engineering_spec_id"], "subject_ref": engineering["engineering_spec_id"],
        "subject_revision": engineering["engineering_spec_id"], "subject_sha256": engineering["engineering_spec_id"],
        "decision": "approve", "head_ref": SHA_B, "head_decision": "approve",
    }
    return product, profile, engineering, approval


def tasks(engineering: dict[str, object], product: dict[str, object]) -> list[dict[str, object]]:
    pc, es = product["product_contract_id"], engineering["engineering_spec_id"]
    tdd = {"kind": "tdd", "argv": ["python3", "-m", "pytest"]}
    return [
        {
            "id": "TASK-001", "title": "Define API", "depends_on": [], "write_set": ["src/api.py"],
            "mutual_exclusion_with": [],
            "interface_owner": {"id": "IFACE-001", "criterion_ref": f"ES:{es}#API-001"},
            "interface_consumes": [], "execution_mode": "tdd", "evidence_strategy": tdd,
            "trace_refs": [f"PC:{pc}#SCN-001", f"ES:{es}#API-001"],
        },
        {
            "id": "TASK-002", "title": "Test API", "depends_on": ["TASK-001"], "write_set": ["tests/test_api.py"],
            "mutual_exclusion_with": [], "interface_owner": None, "interface_consumes": ["IFACE-001"],
            "execution_mode": "tdd", "evidence_strategy": deepcopy(tdd), "trace_refs": [f"ES:{es}#TEST-001"],
        },
    ]


def rehash_plan(plan: dict[str, object]) -> None:
    digest = hashlib.sha256(plan_compiler.canonical_bytes(plan_compiler._plan_preimage(plan))).hexdigest()
    plan["delivery_plan_id"] = digest
    plan["bundle_sha256"] = digest


class PlanCompilerTest(unittest.TestCase):
    def test_approved_spec_compiles_dag_and_one_way_projection(self) -> None:
        product, _, engineering, approval = contract_fixture()
        plan = plan_compiler.compile_delivery_plan(engineering, approval, tasks(engineering, product))
        self.assertEqual(len(str(plan["delivery_plan_id"])), 64)
        self.assertEqual(
            plan_compiler.verify_delivery_plan(
                plan, engineering_spec=engineering, effective_approval=approval,
            ),
            plan["delivery_plan_id"],
        )
        self.assertEqual(plan["tasks"][0]["evidence_strategy"]["argv"], ["python3", "-m", "pytest"])
        self.assertEqual(plan["interfaces"][0]["owner_task_id"], "TASK-001")
        self.assertEqual(plan["interfaces"][0]["consumer_task_ids"], ["TASK-002"])
        preview = plan_compiler.render_plan_projection(
            plan, engineering_spec=engineering, effective_approval=approval, run_id="RUN-001",
        )
        self.assertIn("plan_format: shadow-delivery-plan-v1", preview)
        self.assertEqual(plan_compiler.projection_path("preview", run_id="RUN-001"), ".sdlc/preview/RUN-001/plan.shadow.md")
        self.assertEqual(
            plan_compiler.projection_path("canonical", delivery_plan_id=str(plan["delivery_plan_id"])),
            f".sdlc/contracts/plans/{plan['delivery_plan_id']}/plan.projection.md",
        )
        with self.assertRaises(plan_compiler.PlanError):
            plan_compiler.projection_path("preview")
        with self.assertRaises(plan_compiler.PlanError):
            plan_compiler.projection_path("canonical")
        self.assertIn(
            "plan_format: delivery-plan-projection-v1",
            plan_compiler.render_plan_projection(
                plan, engineering_spec=engineering, effective_approval=approval, scope="canonical",
            ),
        )
        self.assertEqual(
            plan_compiler.verify_delivery_plan(
                plan, engineering_spec=engineering, effective_approval=approval,
            ),
            plan["delivery_plan_id"],
        )

    def test_not_a_boolean_or_self_report_can_establish_effective_approval(self) -> None:
        product, _, engineering, approval = contract_fixture()
        rejected = dict(approval, decision="reject", head_decision="reject")
        with self.assertRaisesRegex(plan_compiler.PlanError, "ineffective-engineering-approval"):
            plan_compiler.compile_delivery_plan(engineering, rejected, tasks(engineering, product))
        self_report = dict(approval, approved=True)
        with self.assertRaisesRegex(plan_compiler.PlanError, "self-reported-approval"):
            plan_compiler.compile_delivery_plan(engineering, self_report, tasks(engineering, product))

    def test_missing_or_wrong_trace_and_runtime_fields_fail(self) -> None:
        product, _, engineering, approval = contract_fixture()
        bad = tasks(engineering, product)
        bad[0]["trace_refs"] = [f"PC:{product['product_contract_id']}#SCN-404"]
        with self.assertRaisesRegex(plan_compiler.PlanError, "task-product-trace"):
            plan_compiler.compile_delivery_plan(engineering, approval, bad)
        bad = tasks(engineering, product)
        bad[0]["status"] = "done"
        with self.assertRaisesRegex(plan_compiler.PlanError, "runtime-fields"):
            plan_compiler.compile_delivery_plan(engineering, approval, bad)

    def test_cycle_overlap_and_non_ancestor_interface_fail(self) -> None:
        product, _, engineering, approval = contract_fixture()
        bad = tasks(engineering, product)
        bad[0]["depends_on"] = ["TASK-002"]
        with self.assertRaisesRegex(plan_compiler.PlanError, "cycle"):
            plan_compiler.compile_delivery_plan(engineering, approval, bad)
        bad = tasks(engineering, product)
        bad[1]["depends_on"] = []
        with self.assertRaisesRegex(plan_compiler.PlanError, "not-dag-ancestor"):
            plan_compiler.compile_delivery_plan(engineering, approval, bad)
        bad = tasks(engineering, product)
        bad[1]["write_set"] = ["src/api.py"]
        bad[1]["depends_on"] = []
        bad[1]["interface_consumes"] = []
        with self.assertRaisesRegex(plan_compiler.PlanError, "write-set-overlap"):
            plan_compiler.compile_delivery_plan(engineering, approval, bad)

    def test_single_task_fast_path_uses_the_same_contract_and_evidence_rules(self) -> None:
        product, _, engineering, approval = contract_fixture()
        pc, es = product["product_contract_id"], engineering["engineering_spec_id"]
        one_task = tasks(engineering, product)[0]
        one_task["interface_owner"] = None
        one_task["trace_refs"] = [f"PC:{pc}#SCN-001", f"ES:{es}#API-001", f"ES:{es}#TEST-001"]
        plan = plan_compiler.compile_delivery_plan(engineering, approval, [one_task])
        self.assertEqual(len(plan["tasks"]), 1)

    def test_manifest_tampering_and_unapproved_spec_fail(self) -> None:
        product, _, engineering, approval = contract_fixture()
        plan = plan_compiler.compile_delivery_plan(engineering, approval, tasks(engineering, product))
        plan["tasks"][0]["title"] = "edited projection source"
        with self.assertRaisesRegex(plan_compiler.PlanError, "hash-mismatch"):
            plan_compiler.verify_delivery_plan(
                plan, engineering_spec=engineering, effective_approval=approval,
            )
        broken_spec = dict(engineering, bundle_sha256=SHA_A)
        with self.assertRaisesRegex(plan_compiler.PlanError, "bundle-id-mismatch"):
            plan_compiler.compile_delivery_plan(broken_spec, approval, tasks(engineering, product))

    def test_strict_verification_requires_spec_and_effective_approval(self) -> None:
        product, _, engineering, approval = contract_fixture()
        plan = plan_compiler.compile_delivery_plan(engineering, approval, tasks(engineering, product))
        with self.assertRaises(TypeError):
            plan_compiler.verify_delivery_plan(plan)
        with self.assertRaises(TypeError):
            plan_compiler.verify_delivery_plan(plan, engineering_spec=engineering)
        rejected = dict(approval, decision="reject", head_decision="reject")
        with self.assertRaisesRegex(plan_compiler.PlanError, "ineffective-engineering-approval"):
            plan_compiler.verify_delivery_plan(
                plan, engineering_spec=engineering, effective_approval=rejected,
            )

    def test_hand_hashed_empty_or_schema_invalid_plan_is_rejected(self) -> None:
        product, _, engineering, approval = contract_fixture()
        plan = plan_compiler.compile_delivery_plan(engineering, approval, tasks(engineering, product))
        empty = deepcopy(plan)
        empty["tasks"] = []
        empty["interfaces"] = []
        rehash_plan(empty)
        with self.assertRaisesRegex(plan_compiler.PlanError, "invalid-task-definitions"):
            plan_compiler.verify_delivery_plan(
                empty, engineering_spec=engineering, effective_approval=approval,
            )
        runtime = deepcopy(plan)
        runtime["tasks"][0]["status"] = "done"
        rehash_plan(runtime)
        with self.assertRaisesRegex(plan_compiler.PlanError, "runtime-fields"):
            plan_compiler.verify_delivery_plan(
                runtime, engineering_spec=engineering, effective_approval=approval,
            )

    def test_rehashed_plan_reexecutes_dag_trace_coverage_write_set_and_interface_checks(self) -> None:
        product, _, engineering, approval = contract_fixture()
        plan = plan_compiler.compile_delivery_plan(engineering, approval, tasks(engineering, product))
        cases: list[tuple[str, dict[str, object], str]] = []

        cycle = deepcopy(plan)
        cycle["tasks"][0]["depends_on"] = ["TASK-002"]
        cases.append(("dag", cycle, "cycle"))

        missing_trace = deepcopy(plan)
        missing_trace["tasks"][0]["trace_refs"] = [
            f"ES:{engineering['engineering_spec_id']}#API-001",
        ]
        cases.append(("coverage", missing_trace, "does-not-cover-implemented-product"))

        overlap = deepcopy(plan)
        overlap["tasks"][1]["depends_on"] = []
        overlap["tasks"][1]["interface_consumes"] = []
        overlap["tasks"][1]["write_set"] = ["src/api.py"]
        cases.append(("write-set", overlap, "write-set-overlap"))

        forged_interface = deepcopy(plan)
        forged_interface["interfaces"][0]["consumer_task_ids"] = []
        cases.append(("interface", forged_interface, "interface-manifest-mismatch"))

        for label, candidate, message in cases:
            with self.subTest(label=label):
                rehash_plan(candidate)
                with self.assertRaisesRegex(plan_compiler.PlanError, message):
                    plan_compiler.verify_delivery_plan(
                        candidate, engineering_spec=engineering, effective_approval=approval,
                    )

    def test_rehashed_plan_cannot_change_bound_tuple_base_or_generation(self) -> None:
        product, _, engineering, approval = contract_fixture()
        plan = plan_compiler.compile_delivery_plan(engineering, approval, tasks(engineering, product))
        replacements: dict[str, object] = {
            "feature_id": "FEAT-OTHER",
            "engineering_spec_ref": SHA_A,
            "engineering_spec_revision": SHA_A,
            "engineering_spec_approval_ref": SHA_A,
            "product_contract_ref": SHA_A,
            "product_contract_approval_ref": SHA_B,
            "profile_ref": SHA_A,
            "profile_revision": "b" * 40,
            "profile_sha256": SHA_A,
            "base_sha": "b" * 40,
            "contract_generation": 9,
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                candidate = deepcopy(plan)
                candidate[field] = replacement
                rehash_plan(candidate)
                with self.assertRaisesRegex(
                    plan_compiler.PlanError, f"delivery-plan-binding-mismatch:{field}"
                ):
                    plan_compiler.verify_delivery_plan(
                        candidate, engineering_spec=engineering, effective_approval=approval,
                    )


if __name__ == "__main__":
    unittest.main()
