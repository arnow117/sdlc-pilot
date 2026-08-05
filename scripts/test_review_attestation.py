#!/usr/bin/env python3
"""Contract tests for immutable, authority-bound Feature review attestations."""
from __future__ import annotations

from copy import deepcopy
import unittest

import approval
import review_attestation


TIME = "2026-08-05T10:00:00+08:00"
FEATURE_ID = "FEAT-001"
FENCE = {
    "contract_generation": 2,
    "product_contract_ref": "1" * 64,
    "product_contract_approval_ref": "2" * 64,
    "engineering_spec_ref": "3" * 64,
    "engineering_spec_approval_ref": "4" * 64,
    "delivery_plan_ref": "5" * 64,
}
POLICY = {
    "policy_id": "feature-review-v1",
    "allowed_roles": ["architect"],
    "min_authn_assurance": "configured-audit",
    "subject_type": "feature_review",
    "scope": "feature",
}


def principal(role: str) -> approval.Principal:
    return approval.resolve_principal(
        authority_mode="local-serial",
        authority_config={
            "authority_mode": "local-serial",
            "principal_ref": f"principal:{role}",
            "roles": [role],
            "authn_method": "configured-file",
            "authn_assurance": "configured-audit",
        },
    )


def attestation(*, reviewer: str = "architect", evidence_refs: list[str] | None = None) -> dict[str, object]:
    return review_attestation.build_review_attestation(
        feature_id=FEATURE_ID,
        decision="approve",
        current_tuple=FENCE,
        reviewer=principal(reviewer),
        authorization_policy=approval.parse_authorization_policy(POLICY),
        evidence_refs=evidence_refs or ["a" * 64, "b" * 64],
        rationale_ref="c" * 64,
        policy_manifest_ref="d" * 64,
        context_manifest_ref="e" * 64,
        reviewed_at=TIME,
    )


class ReviewAttestationTest(unittest.TestCase):
    def test_build_and_verify_are_deterministic_and_bind_the_full_feature_tuple(self) -> None:
        first = attestation()
        second = attestation()

        self.assertEqual(first, second)
        self.assertEqual(
            review_attestation.verify_review_attestation(
                first,
                expected_feature_id=FEATURE_ID,
                expected_current_tuple=FENCE,
                expected_decision="approve",
                expected_reviewed_at=TIME,
            ),
            first["review_attestation_id"],
        )

    def test_tampering_or_a_stale_tuple_is_rejected_without_trusting_the_record(self) -> None:
        original = attestation()
        forged = deepcopy(original)
        forged["reviewer_ref"] = "principal:forged"
        with self.assertRaisesRegex(
            review_attestation.ReviewAttestationError, "review-attestation-content-hash-mismatch",
        ):
            review_attestation.verify_review_attestation(
                forged, expected_feature_id=FEATURE_ID, expected_current_tuple=FENCE,
            )

        stale = dict(FENCE)
        stale["contract_generation"] = 1
        with self.assertRaisesRegex(
            review_attestation.ReviewAttestationError, "review-current-tuple-mismatch",
        ):
            review_attestation.verify_review_attestation(
                original, expected_feature_id=FEATURE_ID, expected_current_tuple=stale,
            )

    def test_unconfigured_reviewer_role_and_duplicate_evidence_are_rejected(self) -> None:
        with self.assertRaisesRegex(review_attestation.ReviewAttestationError, "reviewer-not-authorized"):
            attestation(reviewer="qa")
        with self.assertRaisesRegex(review_attestation.ReviewAttestationError, "invalid-review-evidence-refs"):
            attestation(evidence_refs=["a" * 64, "a" * 64])


if __name__ == "__main__":
    unittest.main()
