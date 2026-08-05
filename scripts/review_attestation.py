#!/usr/bin/env python3
"""Immutable, authority-bound semantic review attestations.

Review quality is a human/AI semantic conclusion, not a runner fact.  This
module therefore does not try to derive a verdict from code; it makes the
conclusion attributable, content-addressed, bound to one Feature tuple, and
verifiable against the authority policy that permitted the reviewer role.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Mapping, Sequence

import approval


FORMAT = "feature-review-attestation-v1"
FENCE_FIELDS = (
    "contract_generation",
    "product_contract_ref",
    "product_contract_approval_ref",
    "engineering_spec_ref",
    "engineering_spec_approval_ref",
    "delivery_plan_ref",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")
_POLICY_FIELDS = frozenset({
    "policy_id", "allowed_roles", "min_authn_assurance", "subject_type", "scope",
})
_FIELDS = frozenset({
    "attestation_format", "feature_id", "decision", "reviewer_ref", "reviewer_role",
    "authn_method", "authn_assurance", "authorization_policy", "evidence_refs", "rationale_ref",
    "policy_manifest_ref", "context_manifest_ref", "reviewed_at", "review_attestation_id",
    *FENCE_FIELDS,
})


class ReviewAttestationError(ValueError):
    """A review attestation is not a valid immutable semantic record."""


def canonical_bytes(value: object) -> bytes:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReviewAttestationError("non-canonical-review-attestation-value") from exc
    return (payload + "\n").encode("utf-8")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ReviewAttestationError(f"invalid-{label}")
    return value


def _exact(value: object, expected: frozenset[str], label: str) -> Mapping[str, object]:
    source = _mapping(value, label)
    if set(source) != expected:
        raise ReviewAttestationError(f"invalid-{label}-fields")
    return source


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ReviewAttestationError(f"invalid-{label}")
    return value


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or ".." in value:
        raise ReviewAttestationError(f"invalid-{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not _TEXT.fullmatch(value):
        raise ReviewAttestationError(f"invalid-{label}")
    return value


def _timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReviewAttestationError(f"invalid-{label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewAttestationError(f"invalid-{label}") from exc
    if parsed.tzinfo is None:
        raise ReviewAttestationError(f"invalid-{label}")
    return value


def _fence(value: object) -> dict[str, object]:
    source = _exact(value, frozenset(FENCE_FIELDS), "review-fence")
    generation = source["contract_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise ReviewAttestationError("invalid-review-contract-generation")
    return {
        "contract_generation": generation,
        **{field: _sha(source[field], field.replace("_", "-")) for field in FENCE_FIELDS[1:]},
    }


def _refs(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ReviewAttestationError(f"invalid-{label}")
    refs = [_sha(item, f"{label}-item") for item in value]
    if refs != sorted(refs) or len(refs) != len(set(refs)):
        raise ReviewAttestationError(f"invalid-{label}")
    return refs


def _policy(value: object) -> tuple[dict[str, object], approval.AuthorizationPolicy]:
    source = _exact(value, _POLICY_FIELDS, "review-authorization-policy")
    try:
        parsed = approval.parse_authorization_policy(source)
    except approval.ApprovalError as exc:
        raise ReviewAttestationError(f"invalid-review-authorization-policy:{exc}") from exc
    if parsed.subject_type != "feature_review" or parsed.scope != "feature":
        raise ReviewAttestationError("review-authorization-policy-scope-mismatch")
    return {
        "policy_id": parsed.policy_id,
        "allowed_roles": list(parsed.allowed_roles),
        "min_authn_assurance": parsed.min_authn_assurance,
        "subject_type": "feature_review",
        "scope": "feature",
    }, parsed


def review_subject(feature_id: str) -> dict[str, str]:
    """Return the authorization subject used for a Feature review."""
    feature_id = _id(feature_id, "feature-id")
    digest = hashlib.sha256(f"feature-review:{feature_id}".encode("utf-8")).hexdigest()
    return {
        "subject_type": "feature_review",
        "scope": "feature",
        "subject_id": feature_id,
        "subject_ref": feature_id,
        "subject_revision": feature_id,
        "subject_sha256": digest,
    }


def _principal_from_record(source: Mapping[str, object]) -> approval.Principal:
    try:
        return approval.Principal(
            principal_ref=_text(source["reviewer_ref"], "reviewer-ref"),
            roles=(_text(source["reviewer_role"], "reviewer-role"),),
            authn_method=_text(source["authn_method"], "review-authn-method"),
            authn_assurance=_text(source["authn_assurance"], "review-authn-assurance"),
        )
    except KeyError as exc:
        raise ReviewAttestationError("missing-reviewer-identity") from exc


def build_review_attestation(
    *, feature_id: str, decision: str, current_tuple: Mapping[str, object],
    reviewer: approval.Principal, authorization_policy: approval.AuthorizationPolicy,
    evidence_refs: Sequence[str], rationale_ref: str, policy_manifest_ref: str,
    context_manifest_ref: str, reviewed_at: str,
) -> dict[str, object]:
    """Create a semantic review conclusion only from a configured reviewer/policy."""
    feature_id = _id(feature_id, "feature-id")
    if decision not in {"approve", "reject"}:
        raise ReviewAttestationError("invalid-review-decision")
    fence = _fence(current_tuple)
    policy_mapping, parsed_policy = _policy({
        "policy_id": authorization_policy.policy_id,
        "allowed_roles": list(authorization_policy.allowed_roles),
        "min_authn_assurance": authorization_policy.min_authn_assurance,
        "subject_type": authorization_policy.subject_type,
        "scope": authorization_policy.scope,
    })
    try:
        reviewer_role = approval.authorize(review_subject(feature_id), reviewer, parsed_policy)
    except approval.ApprovalError as exc:
        raise ReviewAttestationError(f"reviewer-not-authorized:{exc}") from exc
    refs = sorted({_sha(item, "review-evidence-ref") for item in evidence_refs})
    if not refs or len(refs) != len(evidence_refs):
        raise ReviewAttestationError("invalid-review-evidence-refs")
    preimage: dict[str, object] = {
        "attestation_format": FORMAT,
        "feature_id": feature_id,
        "decision": decision,
        "reviewer_ref": _text(reviewer.principal_ref, "reviewer-ref"),
        "reviewer_role": reviewer_role,
        "authn_method": _text(reviewer.authn_method, "review-authn-method"),
        "authn_assurance": _text(reviewer.authn_assurance, "review-authn-assurance"),
        "authorization_policy": policy_mapping,
        "evidence_refs": refs,
        "rationale_ref": _sha(rationale_ref, "review-rationale-ref"),
        "policy_manifest_ref": _sha(policy_manifest_ref, "review-policy-manifest-ref"),
        "context_manifest_ref": _sha(context_manifest_ref, "review-context-manifest-ref"),
        "reviewed_at": _timestamp(reviewed_at, "reviewed-at"),
        **fence,
    }
    return {**preimage, "review_attestation_id": hashlib.sha256(canonical_bytes(preimage)).hexdigest()}


def verify_review_attestation(
    value: Mapping[str, object], *, expected_feature_id: str,
    expected_current_tuple: Mapping[str, object], expected_decision: str | None = None,
    expected_reviewed_at: str | None = None,
) -> str:
    """Verify identity, tuple binding, and configured-policy authorization."""
    source = _exact(value, _FIELDS, "review-attestation")
    if source["attestation_format"] != FORMAT:
        raise ReviewAttestationError("unsupported-review-attestation-format")
    feature_id = _id(source["feature_id"], "feature-id")
    if feature_id != _id(expected_feature_id, "expected-feature-id"):
        raise ReviewAttestationError("review-feature-id-mismatch")
    decision = source["decision"]
    if decision not in {"approve", "reject"}:
        raise ReviewAttestationError("invalid-review-decision")
    if expected_decision is not None and decision != expected_decision:
        raise ReviewAttestationError("review-decision-mismatch")
    fence = _fence({field: source[field] for field in FENCE_FIELDS})
    if fence != _fence(expected_current_tuple):
        raise ReviewAttestationError("review-current-tuple-mismatch")
    policy_mapping, parsed_policy = _policy(source["authorization_policy"])
    reviewer = _principal_from_record(source)
    try:
        derived_role = approval.authorize(review_subject(feature_id), reviewer, parsed_policy)
    except approval.ApprovalError as exc:
        raise ReviewAttestationError(f"reviewer-not-authorized:{exc}") from exc
    if derived_role != source["reviewer_role"]:
        raise ReviewAttestationError("reviewer-role-mismatch")
    refs = _refs(source["evidence_refs"], "review-evidence-refs")
    rationale_ref = _sha(source["rationale_ref"], "review-rationale-ref")
    policy_ref = _sha(source["policy_manifest_ref"], "review-policy-manifest-ref")
    context_ref = _sha(source["context_manifest_ref"], "review-context-manifest-ref")
    reviewed_at = _timestamp(source["reviewed_at"], "reviewed-at")
    if expected_reviewed_at is not None and reviewed_at != _timestamp(expected_reviewed_at, "expected-reviewed-at"):
        raise ReviewAttestationError("reviewed-at-mismatch")
    preimage: dict[str, object] = {
        "attestation_format": FORMAT,
        "feature_id": feature_id,
        "decision": decision,
        "reviewer_ref": reviewer.principal_ref,
        "reviewer_role": derived_role,
        "authn_method": reviewer.authn_method,
        "authn_assurance": reviewer.authn_assurance,
        "authorization_policy": policy_mapping,
        "evidence_refs": refs,
        "rationale_ref": rationale_ref,
        "policy_manifest_ref": policy_ref,
        "context_manifest_ref": context_ref,
        "reviewed_at": reviewed_at,
        **fence,
    }
    identity = _sha(source["review_attestation_id"], "review-attestation-id")
    if hashlib.sha256(canonical_bytes(preimage)).hexdigest() != identity:
        raise ReviewAttestationError("review-attestation-content-hash-mismatch")
    return identity


__all__ = [
    "FORMAT", "FENCE_FIELDS", "ReviewAttestationError", "build_review_attestation",
    "review_subject", "verify_review_attestation",
]
