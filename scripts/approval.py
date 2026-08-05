#!/usr/bin/env python3
"""Pure identity, authorization, and append-only approval-chain primitives."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping, Sequence


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")
_AUTHORITY_MODES = frozenset({"legacy", "local-serial", "shared-control"})
_ASSURANCE_RANK = {"configured-audit": 0, "signed": 1, "runtime-authenticated": 2}
_DECISIONS = frozenset({"approve", "reject", "revoke"})
_NEXT = {
    "none": frozenset({"approve", "reject"}),
    "approve": frozenset({"revoke"}),
    "reject": frozenset({"approve", "reject"}),
    "revoke": frozenset({"approve", "reject"}),
}
_CALLER_IDENTITY_FIELDS = frozenset({
    "principal", "principal_ref", "principal_role", "roles", "authn_method", "authn_assurance",
})


class ApprovalError(ValueError):
    """An identity, authorization rule, or approval-chain operation is invalid."""


@dataclass(frozen=True)
class Principal:
    principal_ref: str
    roles: tuple[str, ...]
    authn_method: str
    authn_assurance: str


@dataclass(frozen=True)
class AuthorizationPolicy:
    policy_id: str
    allowed_roles: tuple[str, ...]
    min_authn_assurance: str
    subject_type: str | None = None
    scope: str | None = None


def canonical_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ApprovalError("non-canonical-approval-value") from exc
    return (rendered + "\n").encode("utf-8")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not _TEXT.fullmatch(value):
        raise ApprovalError(f"invalid-{label}")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ApprovalError(f"invalid-{label}")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ApprovalError(f"invalid-{label}")
    return value


def _string_list(value: object, label: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ApprovalError(f"invalid-{label}")
    result = tuple(sorted({_text(item, f"{label}-item") for item in value}))
    if nonempty and not result:
        raise ApprovalError(f"invalid-{label}")
    if len(result) != len(value):
        raise ApprovalError(f"duplicate-{label}")
    return result


def resolve_principal(
    *, authority_mode: str, authority_config: Mapping[str, object], caller_payload: Mapping[str, object] | None = None,
) -> Principal:
    """Resolve identity only from the configured authority adapter, never caller data."""
    if authority_mode not in _AUTHORITY_MODES:
        raise ApprovalError("unsupported-authority-mode")
    if caller_payload is not None:
        payload = _mapping(caller_payload, "caller-payload")
        supplied = sorted(_CALLER_IDENTITY_FIELDS & set(payload))
        if supplied:
            raise ApprovalError("caller-cannot-supply-principal:" + ",".join(supplied))
    source = _mapping(authority_config, "authority-config")
    if set(source) != {"authority_mode", "principal_ref", "roles", "authn_method", "authn_assurance"}:
        raise ApprovalError("invalid-authority-config-fields")
    if source["authority_mode"] != authority_mode:
        raise ApprovalError("authority-mode-config-mismatch")
    assurance = source["authn_assurance"]
    if assurance not in _ASSURANCE_RANK:
        raise ApprovalError("invalid-authn-assurance")
    return Principal(
        principal_ref=_text(source["principal_ref"], "principal-ref"),
        roles=_string_list(source["roles"], "principal-roles"),
        authn_method=_text(source["authn_method"], "authn-method"),
        authn_assurance=str(assurance),
    )


def parse_authorization_policy(value: Mapping[str, object]) -> AuthorizationPolicy:
    source = _mapping(value, "authorization-policy")
    allowed = {"policy_id", "allowed_roles", "min_authn_assurance", "subject_type", "scope"}
    if not set(source).issubset(allowed) or not {"policy_id", "allowed_roles", "min_authn_assurance"}.issubset(source):
        raise ApprovalError("invalid-authorization-policy-fields")
    assurance = source["min_authn_assurance"]
    if assurance not in _ASSURANCE_RANK:
        raise ApprovalError("invalid-policy-assurance")
    subject_type = source.get("subject_type")
    scope = source.get("scope")
    return AuthorizationPolicy(
        policy_id=_text(source["policy_id"], "policy-id"),
        allowed_roles=_string_list(source["allowed_roles"], "policy-allowed-roles"),
        min_authn_assurance=str(assurance),
        subject_type=None if subject_type is None else _text(subject_type, "policy-subject-type"),
        scope=None if scope is None else _text(scope, "policy-scope"),
    )


def _subject(value: Mapping[str, object]) -> dict[str, str]:
    source = _mapping(value, "approval-subject")
    required = {"subject_type", "scope", "subject_id", "subject_ref", "subject_revision", "subject_sha256"}
    if set(source) != required:
        raise ApprovalError("invalid-approval-subject-fields")
    return {
        "subject_type": _text(source["subject_type"], "subject-type"),
        "scope": _text(source["scope"], "subject-scope"),
        "subject_id": _text(source["subject_id"], "subject-id"),
        "subject_ref": _text(source["subject_ref"], "subject-ref"),
        "subject_revision": _text(source["subject_revision"], "subject-revision"),
        "subject_sha256": _sha(source["subject_sha256"], "subject-sha256"),
    }


def authorize(subject: Mapping[str, object], principal: Principal, policy: AuthorizationPolicy) -> str:
    normalized_subject = _subject(subject)
    if policy.subject_type is not None and policy.subject_type != normalized_subject["subject_type"]:
        raise ApprovalError("authorization-policy-subject-type-mismatch")
    if policy.scope is not None and policy.scope != normalized_subject["scope"]:
        raise ApprovalError("authorization-policy-scope-mismatch")
    if _ASSURANCE_RANK[principal.authn_assurance] < _ASSURANCE_RANK[policy.min_authn_assurance]:
        raise ApprovalError("insufficient-authn-assurance")
    matching = sorted(set(principal.roles) & set(policy.allowed_roles))
    if not matching:
        raise ApprovalError("principal-not-authorized-for-approval")
    return matching[0]


def build_approval(
    *, subject: Mapping[str, object], decision: str, previous_approval_ref: str | None,
    authorization_policy: AuthorizationPolicy, principal: Principal, decision_intent_ref: str,
    decided_at: str, resolves_change_requests: Sequence[str] = (),
) -> dict[str, object]:
    """Build a content-addressed typed decision without mutating a head pointer."""
    normalized_subject = _subject(subject)
    if decision not in _DECISIONS:
        raise ApprovalError("invalid-approval-decision")
    if previous_approval_ref is not None:
        previous_approval_ref = _sha(previous_approval_ref, "previous-approval-ref")
    role = authorize(normalized_subject, principal, authorization_policy)
    resolved = _string_list(list(resolves_change_requests), "resolved-change-request-refs", nonempty=False)
    preimage: dict[str, object] = {
        "approval_format": "approval-v1",
        **normalized_subject,
        "decision": decision,
        "previous_approval_ref": previous_approval_ref,
        "authorization_policy_ref": authorization_policy.policy_id,
        "principal_ref": principal.principal_ref,
        "principal_role": role,
        "authn_method": principal.authn_method,
        "authn_assurance": principal.authn_assurance,
        "decision_intent_ref": _text(decision_intent_ref, "decision-intent-ref"),
        "decided_at": _text(decided_at, "decided-at"),
        "resolves_change_requests": list(resolved),
    }
    approval_id = hashlib.sha256(canonical_bytes(preimage)).hexdigest()
    return {**preimage, "approval_id": approval_id}


def subject_key(subject: Mapping[str, object]) -> str:
    normalized = _subject(subject)
    return "|".join(normalized[field] for field in ("subject_type", "scope", "subject_id"))


def advance_head(current_head: Mapping[str, object] | None, approval: Mapping[str, object]) -> tuple[dict[str, object], bool]:
    """Apply one decision-chain link with predecessor equality and idempotence."""
    record = _mapping(approval, "approval")
    if record.get("approval_format") != "approval-v1":
        raise ApprovalError("invalid-approval-format")
    approval_id = _sha(record.get("approval_id"), "approval-id")
    subject = _subject({key: record.get(key) for key in (
        "subject_type", "scope", "subject_id", "subject_ref", "subject_revision", "subject_sha256",
    )})
    decision = record.get("decision")
    if decision not in _DECISIONS:
        raise ApprovalError("invalid-approval-decision")
    current_ref: str | None = None
    current_decision = "none"
    if current_head is not None:
        head = _mapping(current_head, "approval-head")
        expected = {"subject_type": subject["subject_type"], "scope": subject["scope"], "subject_id": subject["subject_id"]}
        if any(head.get(field) != expected_value for field, expected_value in expected.items()):
            raise ApprovalError("approval-head-subject-mismatch")
        raw_ref = head.get("head_ref")
        current_ref = None if raw_ref is None else _sha(raw_ref, "approval-head-ref")
        raw_decision = head.get("head_decision", "none")
        if raw_decision not in {"none", *(_DECISIONS)}:
            raise ApprovalError("invalid-approval-head-decision")
        current_decision = str(raw_decision)
        if current_ref == approval_id:
            if current_decision != decision:
                raise ApprovalError("approval-id-head-decision-conflict")
            return dict(head), True
    if record.get("previous_approval_ref") != current_ref:
        raise ApprovalError("approval-predecessor-conflict")
    if decision not in _NEXT[current_decision]:
        raise ApprovalError(f"illegal-approval-transition:{current_decision}->{decision}")
    return {
        "record_type": "approval_head",
        "schema_version": 2,
        "subject_type": subject["subject_type"],
        "scope": subject["scope"],
        "subject_id": subject["subject_id"],
        "head_ref": approval_id,
        "head_decision": decision,
    }, False


def effective_approval(
    *, subject: Mapping[str, object], head: Mapping[str, object] | None,
    approvals_by_id: Mapping[str, Mapping[str, object]], authorization_policy: AuthorizationPolicy,
) -> dict[str, object] | None:
    """Return an approved record only when the current head and its authority still match."""
    expected = _subject(subject)
    if head is None:
        return None
    normalized_head = _mapping(head, "approval-head")
    if normalized_head.get("head_decision") != "approve":
        return None
    if any(normalized_head.get(field) != expected[field] for field in ("subject_type", "scope", "subject_id")):
        return None
    try:
        approval_id = _sha(normalized_head.get("head_ref"), "approval-head-ref")
    except ApprovalError:
        return None
    record = approvals_by_id.get(approval_id)
    if not isinstance(record, Mapping):
        return None
    try:
        record_subject = _subject({key: record.get(key) for key in expected})
        if record_subject != expected or record.get("approval_id") != approval_id or record.get("decision") != "approve":
            return None
        if record.get("authorization_policy_ref") != authorization_policy.policy_id:
            return None
        role = record.get("principal_role")
        assurance = record.get("authn_assurance")
        if role not in authorization_policy.allowed_roles or assurance not in _ASSURANCE_RANK:
            return None
        if _ASSURANCE_RANK[str(assurance)] < _ASSURANCE_RANK[authorization_policy.min_authn_assurance]:
            return None
    except ApprovalError:
        return None
    return dict(record)
