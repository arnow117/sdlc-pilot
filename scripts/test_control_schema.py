#!/usr/bin/env python3
"""Tests for the central v1/v2 schema registry."""
from __future__ import annotations

from copy import deepcopy
import unittest

import control_schema


SHA_A = "a" * 64
SHA_B = "b" * 64


def product_contract() -> dict[str, object]:
    return {
        "record_type": "product_contract", "schema_version": 2,
        "product_contract_id": SHA_A, "leaf_id": "REQ-001", "source_request": "REQ-001",
        "contract_format": "product-contract-v1", "contract_kind": "feature", "bundle_sha256": SHA_A,
        "components": [], "outcome_ids": ["OUT-001"], "behavior_ids": ["SCN-001"],
        "domain_rule_ids": [], "experience_ids": [], "nfr_ids": [], "eval_ids": [], "intent_flags": [],
        "supersedes_ref": None, "created_by": "principal-1", "created_at": "2026-08-05T00:00:00Z",
    }


def engineering_spec() -> dict[str, object]:
    return {
        "record_type": "engineering_spec", "schema_version": 2,
        "engineering_spec_id": SHA_B, "feature_id": "FEAT-001", "spec_format": "engineering-spec-v1",
        "product_contract_ref": SHA_A, "product_contract_revision": SHA_A, "product_contract_approval_ref": SHA_A,
        "profile_ref": SHA_A, "profile_revision": SHA_A, "profile_sha256": SHA_A, "specified_against_sha": SHA_A,
        "bundle_sha256": SHA_B, "components": [], "implements_product_ids": ["SCN-001"],
        "engineering_criterion_ids": ["TEST-001"], "target_surfaces": ["server"], "supersedes_ref": None,
        "created_by": "principal-1", "created_at": "2026-08-05T00:00:00Z",
    }


class ControlSchemaTest(unittest.TestCase):
    def test_v2_specs_validate_and_have_identity_paths(self) -> None:
        spec = control_schema.record_spec("engineering_spec", 2)
        self.assertIn("product_contract_ref", spec.required_fields)
        record = engineering_spec()
        record["_path"] = "engineering-specs/FEAT-001/" + SHA_B + "/manifest.md"
        self.assertEqual(control_schema.validate_record(record), spec)

    def test_missing_fields_bad_status_downgrade_and_immutability_fail(self) -> None:
        with self.assertRaises(control_schema.SchemaError):
            control_schema.validate_record({"record_type": "approval", "schema_version": 2})
        definition = {
            "record_type": "product_definition", "schema_version": 2, "leaf_id": "REQ-001",
            "source_request": "REQ-001", "definition_status": "wrong", "draft_status": "idle", "owner": None,
            "lifecycle_run_id": "run-1", "policy_manifest_ref": SHA_A, "obligation_head_ref": SHA_A,
            "current_contract_ref": None, "current_contract_revision": None, "current_contract_sha256": None,
            "current_approval_ref": None, "pending_contract_ref": None, "pending_contract_revision": None,
            "active_change_request_refs": [], "created_at": "t", "updated_at": "t",
        }
        with self.assertRaises(control_schema.SchemaError):
            control_schema.validate_record(definition)
        changed = product_contract()
        changed["created_by"] = "other"
        with self.assertRaises(control_schema.SchemaError):
            control_schema.validate_record(changed, previous_record=product_contract())
        older = deepcopy(product_contract())
        older["schema_version"] = 3
        with self.assertRaises(control_schema.SchemaError):
            control_schema.validate_record(product_contract(), previous_record=older)

    def test_v1_remains_readable_and_strict_v1_is_fail_closed_for_dual_state(self) -> None:
        legacy = {"record_type": "evidence", "schema_version": 1, "evidence_id": "EV-001", "feature_id": "FEAT-001", "task_id": "TASK-001", "scope": "task", "result": "pass", "tested_sha": SHA_A}
        control_schema.validate_record(legacy)
        legacy_frontmatter = dict(legacy, schema_version="1")
        self.assertEqual(control_schema.validate_record(legacy_frontmatter).schema_version, 1)
        snapshot = {"capabilities": ["dual-lifecycle-v1"], "records": [engineering_spec()]}
        denied = control_schema.client_can_mutate("strict-v1", snapshot)
        self.assertFalse(denied.allowed)
        self.assertIn("strict-v1", denied.reason or "")
        self.assertTrue(control_schema.client_can_mutate("dual-lifecycle-v1", snapshot).allowed)

    def test_registry_dump_is_stable_and_unknown_schema_fails(self) -> None:
        self.assertEqual(control_schema.registry_dump(), control_schema.registry_dump())
        with self.assertRaises(control_schema.SchemaError):
            control_schema.record_spec("unknown", 2)


if __name__ == "__main__":
    unittest.main()
