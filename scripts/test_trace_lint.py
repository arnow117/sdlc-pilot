#!/usr/bin/env python3
"""Tests for deterministic cross-contract trace graph validation."""
from __future__ import annotations

from copy import deepcopy
import unittest

import contract_bundle
import trace_lint


SHA_A = "a" * 64
PLAN_ID = "c" * 64
GIT_A = "a" * 40


def fixtures() -> tuple[dict[str, object], dict[str, object], dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    product = contract_bundle.build_product_contract({
        "contract_kind": "feature", "leaf_id": "REQ-001", "source_request": "REQ-001",
        "components": {"product.md": "OUT", "behaviors.md": "SCN"},
        "outcome_ids": ["OUT-001"], "behavior_ids": ["SCN-001", "SCN-002"],
        "behavior_kinds": {"SCN-001": "new_behavior", "SCN-002": "new_behavior"},
        "domain_rule_ids": ["RULE-001"], "experience_ids": [], "nfr_ids": ["NFR-001"], "eval_ids": [],
        "intent_flags": {}, "supersedes": None, "created_by": "product-owner", "created_at": "t",
    })
    profile = contract_bundle.snapshot_profile(
        b"# profile\n", feature_id="FEAT-001", source_sha=GIT_A, created_at="t",
    )
    engineering = contract_bundle.build_engineering_spec({
        "feature_id": "FEAT-001", "product_contract_approval_ref": SHA_A,
        "specified_against_sha": GIT_A,
        "implements_product_ids": ["SCN-001", "SCN-002", "RULE-001", "NFR-001"],
        "engineering_criterion_ids": ["API-001", "TEST-001"], "target_surfaces": ["server"],
        "components": {"technical.md": "API", "tests.md": "TEST"}, "supersedes": None,
        "created_by": "architect", "created_at": "t",
    }, product, profile)
    plan = {
        "delivery_plan_id": PLAN_ID,
        "feature_id": "FEAT-001",
        "product_contract_ref": product["product_contract_id"],
        "engineering_spec_ref": engineering["engineering_spec_id"],
        "contract_generation": 0,
        "tasks": [{"id": "TASK-001"}, {"id": "TASK-002"}],
    }
    def task(task_id: str, refs: list[str]) -> dict[str, object]:
        return {
            "task_id": task_id, "feature_id": "FEAT-001", "delivery_plan_ref": PLAN_ID,
            "product_contract_ref": product["product_contract_id"],
            "engineering_spec_ref": engineering["engineering_spec_id"], "contract_generation": 0,
            "trace_refs": refs,
        }
    pc = product["product_contract_id"]
    es = engineering["engineering_spec_id"]
    tasks = [
        task("TASK-001", [f"PC:{pc}#SCN-001", f"PC:{pc}#RULE-001", f"ES:{es}#API-001"]),
        task("TASK-002", [f"PC:{pc}#SCN-002", f"PC:{pc}#NFR-001", f"ES:{es}#TEST-001"]),
    ]
    evidence = [
        {
            "evidence_id": "d" * 64, "task_id": "TASK-001", "feature_id": "FEAT-001",
            "delivery_plan_ref": PLAN_ID, "product_contract_ref": pc, "engineering_spec_ref": es,
            "contract_generation": 0, "trace_refs": list(tasks[0]["trace_refs"]),
        },
        {
            "evidence_id": "e" * 64, "task_id": "TASK-002", "feature_id": "FEAT-001",
            "delivery_plan_ref": PLAN_ID, "product_contract_ref": pc, "engineering_spec_ref": es,
            "contract_generation": 0, "trace_refs": list(tasks[1]["trace_refs"]),
        },
    ]
    return product, engineering, plan, tasks, evidence


class TraceLintTest(unittest.TestCase):
    def test_valid_graph_has_full_forward_and_reverse_coverage(self) -> None:
        product, engineering, plan, tasks, evidence = fixtures()
        report = trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence)
        self.assertEqual(report.errors, [])
        self.assertTrue(report.ok)

    def test_unknown_and_non_implemented_criterion_are_mechanical_errors(self) -> None:
        product, engineering, plan, tasks, evidence = fixtures()
        tasks[0]["trace_refs"] = [
            f"PC:{product['product_contract_id']}#SCN-404",
            f"ES:{engineering['engineering_spec_id']}#API-001",
        ]
        evidence[0]["trace_refs"] = list(tasks[0]["trace_refs"])
        report = trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence)
        self.assertIn("unknown-criterion", report.codes)

        product, engineering, plan, tasks, evidence = fixtures()
        engineering["implements_product_ids"] = ["SCN-001"]
        report = trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence)
        self.assertIn("unimplemented-product-criterion", report.codes)
        self.assertIn("product-criterion-not-implemented", report.codes)

    def test_missing_task_trace_and_cross_generation_evidence_fail(self) -> None:
        product, engineering, plan, tasks, evidence = fixtures()
        tasks[0]["trace_refs"] = []
        evidence[0]["trace_refs"] = []
        evidence[1]["contract_generation"] = 1
        report = trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence)
        self.assertIn("missing-trace-refs", report.codes)
        self.assertIn("contract-tuple-mismatch", report.codes)

    def test_legacy_requirements_can_only_be_a_generated_trace_projection(self) -> None:
        product, engineering, plan, tasks, evidence = fixtures()
        tasks[0]["requirements"] = list(tasks[0]["trace_refs"])
        self.assertEqual(trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence).errors, [])
        tasks[0]["requirements"] = ["REQ-001"]
        report = trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence)
        self.assertIn("legacy-requirements-not-generated-trace-refs", report.codes)

    def test_invalid_plan_runtime_field_duplicate_subject_and_evidence_coverage_fail(self) -> None:
        product, engineering, plan, tasks, evidence = fixtures()
        plan["tasks"][0]["status"] = "done"  # type: ignore[index]
        duplicate = deepcopy(tasks[0])
        tasks.append(duplicate)
        evidence.pop()
        report = trace_lint.lint_trace_graph(product, engineering, plan, tasks, evidence)
        self.assertIn("plan-contains-runtime-field", report.codes)
        self.assertIn("duplicate-task-id", report.codes)
        self.assertIn("unproven-task-criterion", report.codes)

    def test_parse_trace_ref_is_strict(self) -> None:
        self.assertEqual(trace_lint.parse_trace_ref(f"PC:{SHA_A}#SCN-001"), ("PC", SHA_A, "SCN-001"))
        with self.assertRaises(trace_lint.TraceError):
            trace_lint.parse_trace_ref("PC:short#SCN-001")


if __name__ == "__main__":
    unittest.main()
