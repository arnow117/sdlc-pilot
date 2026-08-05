#!/usr/bin/env python3
"""Regression tests for immutable product/profile/engineering bundle identities."""
from __future__ import annotations

from copy import deepcopy
import unittest

import contract_bundle


SHA_A = "a" * 64
SHA_B = "b" * 64
GIT_A = "a" * 40
GIT_B = "b" * 40


def product_components() -> dict[str, object]:
    return {
        "product.json": {"outcome": "let a user finish", "limits": {"retry": 3, "timeout": 10}},
        "behaviors.md": "# SCN-001\nGiven a valid user\nWhen they submit\nThen it succeeds\n",
    }


def product_input(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "contract_kind": "feature",
        "leaf_id": "REQ-001",
        "source_request": "REQ-001",
        "components": product_components(),
        "outcome_ids": ["OUT-001"],
        "behavior_ids": ["SCN-001", "SCN-002"],
        "behavior_kinds": {"SCN-001": "new_behavior", "SCN-002": "new_behavior"},
        "domain_rule_ids": ["RULE-001"],
        "experience_ids": [],
        "nfr_ids": ["NFR-001"],
        "eval_ids": [],
        "intent_flags": {"availability_critical": False, "experience_changed": True},
        "supersedes": None,
        "created_by": "product-owner",
        "created_at": "2026-08-05T00:00:00Z",
    }
    value.update(overrides)
    return value


def profile_snapshot(profile_bytes: bytes = b"# Profile\nstack: python\n") -> dict[str, object]:
    return contract_bundle.snapshot_profile(
        profile_bytes, feature_id="FEAT-001", source_sha=GIT_A, created_at="2026-08-05T00:00:00Z",
    )


def engineering_input(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "feature_id": "FEAT-001",
        "product_contract_approval_ref": SHA_A,
        "specified_against_sha": GIT_A,
        "implements_product_ids": ["SCN-001", "RULE-001"],
        "engineering_criterion_ids": ["API-001", "TEST-001"],
        "target_surfaces": ["server", "tests"],
        "components": {
            "technical.json": {"endpoint": "/v1/submit", "retry": 3},
            "test-strategy.md": "# TEST-001\nred-green-refactor\n",
        },
        "supersedes": None,
        "created_by": "architect",
        "created_at": "2026-08-05T00:00:00Z",
    }
    value.update(overrides)
    return value


class ContractBundleTest(unittest.TestCase):
    def test_product_bundle_normalizes_component_order_and_json_object_order(self) -> None:
        first = product_input()
        reordered = product_input(components={
            "behaviors.md": product_components()["behaviors.md"],
            "product.json": {"limits": {"timeout": 10, "retry": 3}, "outcome": "let a user finish"},
        })
        product_a = contract_bundle.build_product_contract(first)
        product_b = contract_bundle.build_product_contract(reordered)
        self.assertEqual(product_a["product_contract_id"], product_b["product_contract_id"])
        self.assertEqual(len(str(product_a["product_contract_id"])), 64)
        self.assertEqual(
            contract_bundle.verify_bundle(product_a, product_components()), product_a["product_contract_id"],
        )

    def test_profile_and_engineering_bundle_pin_all_upstream_tuples(self) -> None:
        product = contract_bundle.build_product_contract(product_input())
        profile = profile_snapshot()
        engineering = contract_bundle.build_engineering_spec(engineering_input(), product, profile)
        self.assertEqual(len(str(engineering["engineering_spec_id"])), 64)
        self.assertEqual(engineering["product_contract_ref"], product["product_contract_id"])
        self.assertEqual(engineering["profile_ref"], profile["profile_snapshot_id"])
        self.assertEqual(
            contract_bundle.verify_bundle(engineering, engineering_input()["components"]),
            engineering["engineering_spec_id"],
        )
        self.assertEqual(
            contract_bundle.verify_bundle(profile, {"PROFILE.md": b"# Profile\nstack: python\n"}),
            profile["profile_snapshot_id"],
        )

        changed_approval = contract_bundle.build_engineering_spec(
            engineering_input(product_contract_approval_ref=SHA_B), product, profile,
        )
        changed_profile = profile_snapshot(b"# Profile\nstack: go\n")
        changed_base = contract_bundle.build_engineering_spec(
            engineering_input(specified_against_sha=GIT_B), product, profile,
        )
        changed_criterion = contract_bundle.build_engineering_spec(
            engineering_input(implements_product_ids=["SCN-002", "RULE-001"]), product, profile,
        )
        self.assertNotEqual(engineering["engineering_spec_id"], changed_approval["engineering_spec_id"])
        self.assertNotEqual(profile["profile_snapshot_id"], changed_profile["profile_snapshot_id"])
        self.assertNotEqual(engineering["engineering_spec_id"], changed_base["engineering_spec_id"])
        self.assertNotEqual(engineering["engineering_spec_id"], changed_criterion["engineering_spec_id"])

    def test_patch_and_remediation_require_reproduction_or_preservation_scenario(self) -> None:
        with self.assertRaisesRegex(contract_bundle.BundleError, "behavior-kind"):
            contract_bundle.build_product_contract(product_input(contract_kind="patch", behavior_kinds=None))
        patch = contract_bundle.build_product_contract(product_input(
            contract_kind="patch",
            behavior_kinds={"SCN-001": "reproduction", "SCN-002": "preservation"},
        ))
        self.assertEqual(patch["contract_kind"], "patch")

    def test_invalid_cross_subject_supersedes_unknown_criterion_and_mutable_profile_path_fail(self) -> None:
        with self.assertRaisesRegex(contract_bundle.BundleError, "cross-leaf"):
            contract_bundle.build_product_contract(product_input(
                supersedes={"ref": SHA_A, "leaf_id": "REQ-OTHER"},
            ))
        with self.assertRaisesRegex(contract_bundle.BundleError, "profile-source-path"):
            contract_bundle.snapshot_profile(
                b"profile", feature_id="FEAT-001", source_sha=GIT_A,
                source_path="PROFILE.md", created_at="2026-08-05T00:00:00Z",
            )
        product = contract_bundle.build_product_contract(product_input())
        profile = profile_snapshot()
        with self.assertRaisesRegex(contract_bundle.BundleError, "unknown-product-criterion"):
            contract_bundle.build_engineering_spec(
                engineering_input(implements_product_ids=["SCN-404"]), product, profile,
            )
        with self.assertRaisesRegex(contract_bundle.BundleError, "cross-feature"):
            contract_bundle.build_engineering_spec(
                engineering_input(supersedes={"ref": SHA_A, "feature_id": "FEAT-OTHER"}), product, profile,
            )

    def test_duplicate_criterion_partial_hash_and_component_tampering_fail(self) -> None:
        with self.assertRaisesRegex(contract_bundle.BundleError, "duplicate-behavior"):
            contract_bundle.build_product_contract(product_input(behavior_ids=["SCN-001", "SCN-001"]))
        product = contract_bundle.build_product_contract(product_input())
        profile = profile_snapshot()
        with self.assertRaisesRegex(contract_bundle.BundleError, "approval-ref"):
            contract_bundle.build_engineering_spec(
                engineering_input(product_contract_approval_ref="a" * 16), product, profile,
            )
        tampered = deepcopy(product)
        with self.assertRaisesRegex(contract_bundle.BundleError, "component-closure-mismatch"):
            contract_bundle.verify_bundle(tampered, {
                "product.json": {"outcome": "changed", "limits": {"retry": 3, "timeout": 10}},
                "behaviors.md": product_components()["behaviors.md"],
            })

    def test_explicit_product_tuple_must_match_the_product_being_implemented(self) -> None:
        product = contract_bundle.build_product_contract(product_input())
        profile = profile_snapshot()
        with self.assertRaisesRegex(contract_bundle.BundleError, "product-contract-ref-mismatch"):
            contract_bundle.build_engineering_spec(
                engineering_input(product_contract_ref=SHA_B), product, profile,
            )


if __name__ == "__main__":
    unittest.main()
