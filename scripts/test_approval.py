#!/usr/bin/env python3
"""Tests for identity-backed, append-only approval decisions."""
from __future__ import annotations

import unittest

import approval


SHA_A = "a" * 64


def subject() -> dict[str, object]:
    return {
        "subject_type": "engineering_spec", "scope": "feature", "subject_id": SHA_A,
        "subject_ref": SHA_A, "subject_revision": SHA_A, "subject_sha256": SHA_A,
    }


def config(assurance: str = "configured-audit") -> dict[str, object]:
    return {
        "authority_mode": "local-serial", "principal_ref": "principal:alice",
        "roles": ["architect", "qa"], "authn_method": "configured-file", "authn_assurance": assurance,
    }


def policy(assurance: str = "configured-audit") -> approval.AuthorizationPolicy:
    return approval.parse_authorization_policy({
        "policy_id": "approval-policy-v1", "allowed_roles": ["architect"],
        "min_authn_assurance": assurance, "subject_type": "engineering_spec", "scope": "feature",
    })


def decision(principal: approval.Principal, value: str, previous: str | None) -> dict[str, object]:
    return approval.build_approval(
        subject=subject(), decision=value, previous_approval_ref=previous,
        authorization_policy=policy(), principal=principal, decision_intent_ref="intent:001",
        decided_at="2026-08-05T10:00:00+08:00",
    )


class ApprovalTest(unittest.TestCase):
    def test_principal_comes_from_authority_adapter_not_caller_payload(self) -> None:
        principal = approval.resolve_principal(authority_mode="local-serial", authority_config=config())
        self.assertEqual(principal.principal_ref, "principal:alice")
        with self.assertRaisesRegex(approval.ApprovalError, "caller-cannot-supply-principal"):
            approval.resolve_principal(
                authority_mode="local-serial", authority_config=config(),
                caller_payload={"principal_ref": "model:pretend"},
            )
        with self.assertRaisesRegex(approval.ApprovalError, "insufficient-authn"):
            approval.authorize(subject(), principal, policy("signed"))

    def test_chain_has_one_head_predecessor_cas_and_legal_transitions(self) -> None:
        principal = approval.resolve_principal(authority_mode="local-serial", authority_config=config())
        first = decision(principal, "approve", None)
        head, idempotent = approval.advance_head(None, first)
        self.assertFalse(idempotent)
        self.assertEqual(head["head_ref"], first["approval_id"])
        same, idempotent = approval.advance_head(head, first)
        self.assertTrue(idempotent)
        self.assertEqual(same, head)
        with self.assertRaisesRegex(approval.ApprovalError, "illegal-approval-transition"):
            approval.advance_head(head, decision(principal, "approve", first["approval_id"]))
        with self.assertRaisesRegex(approval.ApprovalError, "predecessor-conflict"):
            approval.advance_head(head, decision(principal, "revoke", None))
        revoked = decision(principal, "revoke", first["approval_id"])
        revoked_head, _ = approval.advance_head(head, revoked)
        resumed = decision(principal, "approve", revoked["approval_id"])
        resumed_head, _ = approval.advance_head(revoked_head, resumed)
        self.assertEqual(resumed_head["head_decision"], "approve")

    def test_effective_approval_requires_current_approved_head_subject_and_policy(self) -> None:
        principal = approval.resolve_principal(authority_mode="local-serial", authority_config=config())
        approved = decision(principal, "approve", None)
        head, _ = approval.advance_head(None, approved)
        effective = approval.effective_approval(
            subject=subject(), head=head, approvals_by_id={str(approved["approval_id"]): approved},
            authorization_policy=policy(),
        )
        self.assertEqual(effective and effective["approval_id"], approved["approval_id"])
        no_effective = approval.effective_approval(
            subject=subject(), head=dict(head, head_decision="revoke"),
            approvals_by_id={str(approved["approval_id"]): approved}, authorization_policy=policy(),
        )
        self.assertIsNone(no_effective)
        tampered = dict(approved, principal_role="product-owner")
        self.assertIsNone(approval.effective_approval(
            subject=subject(), head=head, approvals_by_id={str(approved["approval_id"]): tampered},
            authorization_policy=policy(),
        ))

    def test_decision_identity_is_content_addressed_and_policy_bound(self) -> None:
        principal = approval.resolve_principal(authority_mode="local-serial", authority_config=config())
        first = decision(principal, "reject", None)
        duplicate = decision(principal, "reject", None)
        self.assertEqual(first["approval_id"], duplicate["approval_id"])
        different_policy = approval.parse_authorization_policy({
            "policy_id": "approval-policy-v2", "allowed_roles": ["architect"],
            "min_authn_assurance": "configured-audit",
        })
        changed = approval.build_approval(
            subject=subject(), decision="reject", previous_approval_ref=None,
            authorization_policy=different_policy, principal=principal, decision_intent_ref="intent:001",
            decided_at="2026-08-05T10:00:00+08:00",
        )
        self.assertNotEqual(first["approval_id"], changed["approval_id"])


if __name__ == "__main__":
    unittest.main()
