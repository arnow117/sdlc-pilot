#!/usr/bin/env python3
"""Pure canonical reducer for the dual product/delivery lifecycle.

This module deliberately has no dependency on the legacy ``control.py`` or
``control_store.py`` formats.  It receives a complete mapping snapshot and
returns a new mapping snapshot for every command; callers can place the
compare-and-swap / durable-storage boundary around the returned value.

Snapshot schema (``SNAPSHOT_FORMAT``):

```
{
  "snapshot_format": "dual-lifecycle-ledger-v1",
  "schema_version": 1,
  "capabilities": ["dual-lifecycle-v1"],
  "requirements": {leaf_id: {"leaf_id", "status", "dependencies"?}},
  "product_definitions": {leaf_id: ProductDefinition},
  "product_contracts": {contract_sha256: ProductContract},
  "profile_snapshots": {snapshot_sha256: ProfileSnapshot},
  "engineering_specs": {spec_sha256: EngineeringSpec},
  "bundle_artifacts": {bundle_sha256: BundleArtifact},
  "delivery_plans": {plan_sha256: DeliveryPlan},
  "approval_policies": {policy_id: AuthorizationPolicy mapping},
  "approvals": {approval_sha256: Approval},
  "approval_heads": {approval.subject_key(subject): ApprovalHead},
  "claims": {leaf_id: Claim},
  "features": {feature_id: Feature},
  "tasks": {task_instance_sha256: Task},
  "evidence": {evidence_sha256: Evidence},
  "runner_receipts": {receipt_sha256: RunnerReceipt},
  "release_receipts": {receipt_sha256: ReleaseReceipt},
  "change_requests": {change_request_id: ChangeRequest},
}
```

``tasks`` uses an instance identity rather than only ``task_id`` so a later
generation can reuse a logical task ID without erasing historical work.  A
Task's logical identity remains ``task_id``; task commands resolve it against
the Feature's current DeliveryPlan tuple.

Important boundaries:

* Contracts, specs, plans, approvals, bundle artifacts, and receipts are
  immutable inputs.  Bundle registration packs and re-verifies exact component
  bytes before atomically storing both the bundle and its artifact envelope.
  Runner and release facts are likewise re-verified before their receipts are
  admitted to the snapshot.
* ``current_fence`` is the exact optimistic-concurrency tuple for delivery
  work.  Task, evidence, validation, and review commands require all fields;
  old agents cannot write into a newer generation.
* Product-facing status is a projection only.  ``project_delivery_status``
  never exposes an engineering artifact as a mutable product record.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Mapping, Sequence

import approval
import dual_artifact_store
import plan_compiler
import review_attestation
import trace_lint


SNAPSHOT_FORMAT = "dual-lifecycle-ledger-v1"
SCHEMA_VERSION = 1
CAPABILITY = "dual-lifecycle-v1"

FENCE_FIELDS = (
    "contract_generation",
    "product_contract_ref",
    "product_contract_approval_ref",
    "engineering_spec_ref",
    "engineering_spec_approval_ref",
    "delivery_plan_ref",
)
_CANONICAL_RUNNABLE_STRATEGIES = frozenset({"tdd", "static-check", "visual-regression", "contract-check"})

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_TASK_TERMINAL = frozenset({"verified", "abandoned", "superseded"})
_TASK_STATUSES = frozenset({
    "waiting", "ready", "claimed", "in_progress", "awaiting_verification",
    "verified", "blocked", "abandoned", "superseded",
})
_FEATURE_STATUSES = frozenset({"active", "validated", "shipped", "abandoned"})
_WORK_TYPES = frozenset({"feature", "remediation", "hotfix"})
_CR_STATUSES = frozenset({"open", "triaged", "accepted", "applied", "rejected", "cancelled"})
_COLLECTIONS = (
    "requirements", "product_definitions", "product_contracts", "profile_snapshots",
    "engineering_specs", "bundle_artifacts", "delivery_plans", "approval_policies", "approvals",
    "approval_heads", "claims", "features", "tasks", "evidence", "runner_receipts",
    "review_attestations", "release_receipts", "change_requests",
)
_SNAPSHOT_FIELDS = frozenset({"snapshot_format", "schema_version", "capabilities", *_COLLECTIONS})


class ReducerError(ValueError):
    """A lifecycle command cannot be applied to the supplied snapshot."""


def empty_snapshot() -> dict[str, object]:
    """Return an empty canonical dual-lifecycle ledger."""
    return {
        "snapshot_format": SNAPSHOT_FORMAT,
        "schema_version": SCHEMA_VERSION,
        "capabilities": [CAPABILITY],
        **{name: {} for name in _COLLECTIONS},
    }


def validate_snapshot(snapshot: Mapping[str, object]) -> None:
    """Validate the reducer's container schema without mutating ``snapshot``."""
    if not isinstance(snapshot, Mapping) or set(snapshot) != _SNAPSHOT_FIELDS:
        raise ReducerError("invalid-dual-lifecycle-snapshot-fields")
    if snapshot.get("snapshot_format") != SNAPSHOT_FORMAT or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ReducerError("unsupported-dual-lifecycle-snapshot")
    capabilities = snapshot.get("capabilities")
    if not isinstance(capabilities, list) or capabilities != [CAPABILITY]:
        raise ReducerError("missing-dual-lifecycle-capability")
    for name in _COLLECTIONS:
        value = snapshot.get(name)
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
            raise ReducerError(f"invalid-snapshot-collection:{name}")


def _working(snapshot: Mapping[str, object]) -> dict[str, object]:
    validate_snapshot(snapshot)
    result = deepcopy(dict(snapshot))
    # A read-only Mapping implementation is acceptable at the API boundary;
    # normalize collections before reducer code mutates the detached result.
    for name in _COLLECTIONS:
        result[name] = deepcopy(dict(_mapping(snapshot[name], f"snapshot-{name}")))
    return result


def _collection(snapshot: Mapping[str, object], name: str) -> dict[str, object]:
    value = snapshot[name]
    if not isinstance(value, dict):  # deepcopy() preserves the mappings accepted by validate_snapshot().
        raise ReducerError(f"invalid-working-collection:{name}")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ReducerError(f"invalid-{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ReducerError(f"invalid-{label}")
    return value


def _id(value: object, label: str) -> str:
    text = _text(value, label)
    if not _ID.fullmatch(text) or ".." in text:
        raise ReducerError(f"invalid-{label}")
    return text


def _sha(value: object, label: str, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ReducerError(f"invalid-{label}")
    return value


def _git_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        raise ReducerError(f"invalid-{label}")
    return value


def _generation(value: object, label: str = "contract-generation") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReducerError(f"invalid-{label}")
    return value


def _string_list(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ReducerError(f"invalid-{label}")
    result = [_id(item, f"{label}-item") for item in value]
    if len(result) != len(set(result)):
        raise ReducerError(f"duplicate-{label}")
    return sorted(result)


def _immutable_put(collection: dict[str, object], identity: str, record: Mapping[str, object], label: str) -> None:
    candidate = deepcopy(dict(record))
    current = collection.get(identity)
    if current is None:
        collection[identity] = candidate
    elif current != candidate:
        raise ReducerError(f"immutable-{label}-conflict")


def _prepare_bundle_artifact(
    bundle: Mapping[str, object], components: Mapping[str, object] | None, *,
    expected_identity: str, expected_kind: str, label: str,
) -> tuple[dict[str, object], dict[str, object]]:
    if components is None:
        raise ReducerError(f"{label}-components-required")
    try:
        artifact = dual_artifact_store.build_bundle_artifact(bundle, components)
        verified_identity = dual_artifact_store.verify_bundle_artifact(artifact)
        unpacked_bundle, _ = dual_artifact_store.unpack_bundle_artifact(artifact)
    except dual_artifact_store.ArtifactStoreError as exc:
        raise ReducerError(str(exc)) from exc
    if verified_identity != expected_identity or artifact.get("artifact_id") != expected_identity:
        raise ReducerError(f"{label}-bundle-artifact-identity-mismatch")
    if artifact.get("artifact_kind") != expected_kind:
        raise ReducerError(f"{label}-bundle-artifact-kind-mismatch")
    if unpacked_bundle != dict(bundle):
        raise ReducerError(f"{label}-bundle-artifact-mismatch")
    return unpacked_bundle, artifact


def _store_bundle_and_artifact(
    snapshot: dict[str, object], *, collection_name: str, identity: str,
    bundle: Mapping[str, object], artifact: Mapping[str, object], label: str,
) -> None:
    _immutable_put(_collection(snapshot, "bundle_artifacts"), identity, artifact, f"{label}-bundle-artifact")
    _immutable_put(_collection(snapshot, collection_name), identity, bundle, label)


def _require_bundle_artifact(
    snapshot: Mapping[str, object], *, identity: str, bundle: Mapping[str, object],
    expected_kind: str, label: str,
) -> None:
    artifact = _collection(snapshot, "bundle_artifacts").get(identity)
    if not isinstance(artifact, Mapping):
        raise ReducerError(f"missing-{label}-bundle-artifact")
    try:
        verified_identity = dual_artifact_store.verify_bundle_artifact(artifact)
        unpacked_bundle, _ = dual_artifact_store.unpack_bundle_artifact(artifact)
    except dual_artifact_store.ArtifactStoreError as exc:
        raise ReducerError(f"invalid-{label}-bundle-artifact:{exc}") from exc
    if (
        verified_identity != identity
        or artifact.get("artifact_id") != identity
        or artifact.get("artifact_kind") != expected_kind
        or unpacked_bundle != dict(bundle)
    ):
        raise ReducerError(f"{label}-bundle-artifact-mismatch")


def _product_subject(contract_id: str) -> dict[str, str]:
    return {
        "subject_type": "product_contract", "scope": "product", "subject_id": contract_id,
        "subject_ref": contract_id, "subject_revision": contract_id, "subject_sha256": contract_id,
    }


def _engineering_subject(spec_id: str) -> dict[str, str]:
    return {
        "subject_type": "engineering_spec", "scope": "feature", "subject_id": spec_id,
        "subject_ref": spec_id, "subject_revision": spec_id, "subject_sha256": spec_id,
    }


def approval_subject(subject_type: str, subject_id: str) -> dict[str, str]:
    """Build the only approval subject forms accepted by this lifecycle."""
    subject_id = str(_sha(subject_id, "approval-subject-id"))
    if subject_type == "product_contract":
        return _product_subject(subject_id)
    if subject_type == "engineering_spec":
        return _engineering_subject(subject_id)
    raise ReducerError("unsupported-approval-subject-type")


def _policy_mapping(policy: approval.AuthorizationPolicy | Mapping[str, object]) -> dict[str, object]:
    if isinstance(policy, approval.AuthorizationPolicy):
        return {
            "policy_id": policy.policy_id,
            "allowed_roles": list(policy.allowed_roles),
            "min_authn_assurance": policy.min_authn_assurance,
            **({"subject_type": policy.subject_type} if policy.subject_type is not None else {}),
            **({"scope": policy.scope} if policy.scope is not None else {}),
        }
    raw = _mapping(policy, "authorization-policy")
    parsed = approval.parse_authorization_policy(raw)
    return _policy_mapping(parsed)


def _approval_preimage(record: Mapping[str, object]) -> dict[str, object]:
    if set(record) != {
        "approval_format", "subject_type", "scope", "subject_id", "subject_ref", "subject_revision",
        "subject_sha256", "decision", "previous_approval_ref", "authorization_policy_ref", "principal_ref",
        "principal_role", "authn_method", "authn_assurance", "decision_intent_ref", "decided_at",
        "resolves_change_requests", "approval_id",
    }:
        raise ReducerError("invalid-approval-record-fields")
    return {key: record[key] for key in record if key != "approval_id"}


def _verify_approval_identity(record: Mapping[str, object]) -> str:
    preimage = _approval_preimage(record)
    expected = hashlib.sha256(approval.canonical_bytes(preimage)).hexdigest()
    actual = _sha(record.get("approval_id"), "approval-id")
    if actual != expected:
        raise ReducerError("approval-content-hash-mismatch")
    return str(actual)


def _effective_approval(
    snapshot: Mapping[str, object], subject: Mapping[str, object],
) -> dict[str, object] | None:
    key = approval.subject_key(subject)
    heads = _collection(snapshot, "approval_heads")
    approvals = _collection(snapshot, "approvals")
    policies = _collection(snapshot, "approval_policies")
    raw_head = heads.get(key)
    if not isinstance(raw_head, Mapping):
        return None
    head_ref = raw_head.get("head_ref")
    if not isinstance(head_ref, str):
        return None
    raw_record = approvals.get(head_ref)
    if not isinstance(raw_record, Mapping):
        return None
    policy_id = raw_record.get("authorization_policy_ref")
    raw_policy = policies.get(policy_id) if isinstance(policy_id, str) else None
    if not isinstance(raw_policy, Mapping):
        return None
    try:
        policy = approval.parse_authorization_policy(raw_policy)
        effective = approval.effective_approval(
            subject=subject, head=raw_head, approvals_by_id=approvals, authorization_policy=policy,
        )
    except approval.ApprovalError:
        return None
    if effective is None:
        return None
    return {**effective, "head_ref": raw_head.get("head_ref"), "head_decision": raw_head.get("head_decision")}


def apply_approval(
    snapshot: Mapping[str, object], *, approval_record: Mapping[str, object],
    authorization_policy: approval.AuthorizationPolicy | Mapping[str, object], at: str,
) -> dict[str, object]:
    """Append one authenticated approval decision and apply revocation fallout.

    Identity/role data must already have been obtained from the authority
    adapter via :mod:`approval`; this reducer verifies the content address and
    predecessor chain before changing a head.
    """
    result = _working(snapshot)
    _text(at, "approval-applied-at")
    record = _mapping(approval_record, "approval-record")
    approval_id = _verify_approval_identity(record)
    policy_mapping = _policy_mapping(authorization_policy)
    policy = approval.parse_authorization_policy(policy_mapping)
    if record.get("authorization_policy_ref") != policy.policy_id:
        raise ReducerError("approval-policy-reference-mismatch")
    subject = {
        key: record.get(key) for key in (
            "subject_type", "scope", "subject_id", "subject_ref", "subject_revision", "subject_sha256",
        )
    }
    try:
        subject_key = approval.subject_key(subject)
        heads = _collection(result, "approval_heads")
        next_head, idempotent = approval.advance_head(
            heads.get(subject_key) if isinstance(heads.get(subject_key), Mapping) else None,
            record,
        )
    except approval.ApprovalError as exc:
        raise ReducerError(str(exc)) from exc

    # A revoke would invalidate every live binding for the approved artifact.
    # Check terminal Features before moving an approval head or changing any
    # product-definition pointer.  The reducer is pure either way, but this
    # preflight keeps the transition itself all-or-nothing as well.
    if record.get("decision") == "revoke" and not idempotent:
        subject_type = record.get("subject_type")
        subject_id = record.get("subject_id")
        if isinstance(subject_type, str) and isinstance(subject_id, str):
            _assert_revocation_safe_for_shipped_features(result, subject_type, subject_id)

    _immutable_put(_collection(result, "approval_policies"), policy.policy_id, policy_mapping, "approval-policy")
    _immutable_put(_collection(result, "approvals"), approval_id, record, "approval")
    heads[subject_key] = {**next_head, "updated_at": at}

    if record.get("decision") == "revoke" and not idempotent:
        subject_type = record.get("subject_type")
        subject_id = record.get("subject_id")
        if subject_type == "product_contract" and isinstance(subject_id, str):
            _revoke_product_contract_inplace(result, subject_id, at=at, reason=f"approval-revoked:{approval_id}")
        elif subject_type == "engineering_spec" and isinstance(subject_id, str):
            _revoke_engineering_spec_inplace(result, subject_id, at=at, reason=f"approval-revoked:{approval_id}")
    return result


def _assert_revocation_safe_for_shipped_features(
    snapshot: Mapping[str, object], subject_type: str, subject_id: str,
) -> None:
    """Reject a revoke that would invalidate a shipped Feature.

    Shipped Features are historical release records. Their current contract
    and engineering-spec bindings may not be revoked through this lifecycle;
    a correction must be represented as a new Feature/contract instead.
    """
    if subject_type not in {"product_contract", "engineering_spec"}:
        return
    ref_field = "product_contract_ref" if subject_type == "product_contract" else "engineering_spec_ref"
    for raw_feature in _collection(snapshot, "features").values():
        if not isinstance(raw_feature, Mapping):
            continue
        if raw_feature.get(ref_field) != subject_id:
            continue
        if raw_feature.get("status") == "shipped":
            raise ReducerError("cannot-revoke-approval-referenced-by-shipped-feature")
        if raw_feature.get("status") == "abandoned":
            raise ReducerError("cannot-revoke-approval-referenced-by-terminal-feature")


def register_requirement(
    snapshot: Mapping[str, object], *, leaf_id: str, status: str = "ready", dependencies: Sequence[str] = (),
) -> dict[str, object]:
    """Register a compact product-side readiness record (optional but useful)."""
    result = _working(snapshot)
    leaf_id = _id(leaf_id, "leaf-id")
    status = _id(status, "requirement-status")
    deps = [_id(item, "requirement-dependency") for item in dependencies]
    if len(deps) != len(set(deps)) or leaf_id in deps:
        raise ReducerError("invalid-requirement-dependencies")
    requirements = _collection(result, "requirements")
    record = {"leaf_id": leaf_id, "status": status, "dependencies": sorted(deps)}
    current = requirements.get(leaf_id)
    if current is not None and current != record:
        raise ReducerError("requirement-record-conflict")
    requirements[leaf_id] = record
    return result


def create_product_definition(
    snapshot: Mapping[str, object], *, leaf_id: str, source_request: str, owner: str, at: str,
) -> dict[str, object]:
    """Create the product-side lifecycle record in ``unapproved/idle`` state."""
    result = _working(snapshot)
    leaf_id = _id(leaf_id, "leaf-id")
    source_request = _id(source_request, "source-request")
    owner = _id(owner, "product-owner")
    _text(at, "product-definition-created-at")
    definitions = _collection(result, "product_definitions")
    record = {
        "leaf_id": leaf_id,
        "source_request": source_request,
        "owner": owner,
        "definition_status": "unapproved",
        "draft_status": "idle",
        "current_contract_ref": None,
        "current_contract_revision": None,
        "current_contract_sha256": None,
        "current_approval_ref": None,
        "pending_contract_ref": None,
        "pending_contract_revision": None,
        "active_change_request_refs": [],
        "created_at": at,
        "updated_at": at,
    }
    current = definitions.get(leaf_id)
    if current is not None and current != record:
        raise ReducerError("product-definition-already-exists")
    definitions[leaf_id] = record
    return result


def start_product_definition(snapshot: Mapping[str, object], *, leaf_id: str, at: str) -> dict[str, object]:
    """Move a ProductDefinition from ``idle`` to ``shaping``."""
    result = _working(snapshot)
    definition = _definition(result, leaf_id)
    if definition["definition_status"] == "withdrawn":
        raise ReducerError("product-definition-is-withdrawn")
    if definition["draft_status"] != "idle":
        raise ReducerError("illegal-product-draft-transition")
    definition["draft_status"] = "shaping"
    definition["updated_at"] = _text(at, "product-definition-started-at")
    return result


def withdraw_product_definition(snapshot: Mapping[str, object], *, leaf_id: str, at: str) -> dict[str, object]:
    """Withdraw a product definition and invalidate every active Feature for it."""
    result = _working(snapshot)
    definition = _definition(result, leaf_id)
    if definition["definition_status"] == "withdrawn":
        return result
    definition.update({
        "definition_status": "withdrawn", "draft_status": "idle", "pending_contract_ref": None,
        "pending_contract_revision": None, "updated_at": _text(at, "product-definition-withdrawn-at"),
    })
    for feature_id in _feature_ids_for_leaf(result, str(definition["leaf_id"])):
        _invalidate_feature_inplace(result, feature_id, reason="product-definition-withdrawn", at=at)
    return result


def reopen_product_definition(snapshot: Mapping[str, object], *, leaf_id: str, at: str) -> dict[str, object]:
    """Reopen a withdrawn ProductDefinition; it still needs a new approval."""
    result = _working(snapshot)
    definition = _definition(result, leaf_id)
    if definition["definition_status"] != "withdrawn":
        raise ReducerError("only-withdrawn-product-definition-can-reopen")
    definition["definition_status"] = "unapproved"
    definition["draft_status"] = "idle"
    definition["updated_at"] = _text(at, "product-definition-reopened-at")
    return result


def _validate_product_contract(contract: Mapping[str, object]) -> str:
    if contract.get("contract_format") != "product-contract-v1":
        raise ReducerError("invalid-product-contract-format")
    contract_id = str(_sha(contract.get("product_contract_id"), "product-contract-id"))
    if contract.get("bundle_sha256") != contract_id:
        raise ReducerError("product-contract-bundle-id-mismatch")
    _id(contract.get("leaf_id"), "product-contract-leaf-id")
    _id(contract.get("source_request"), "product-contract-source-request")
    if contract.get("contract_kind") not in {"feature", "patch", "remediation"}:
        raise ReducerError("invalid-product-contract-kind")
    _string_list(contract.get("outcome_ids"), "product-outcome-ids", allow_empty=False)
    _string_list(contract.get("behavior_ids"), "product-behavior-ids", allow_empty=False)
    return contract_id


def register_product_contract(
    snapshot: Mapping[str, object], *, contract: Mapping[str, object], components: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Pack and atomically store an authored ProductContract and its bytes."""
    result = _working(snapshot)
    source = _mapping(contract, "product-contract")
    identity = _validate_product_contract(source)
    bundle, artifact = _prepare_bundle_artifact(
        source, components, expected_identity=identity,
        expected_kind="product_contract", label="product-contract",
    )
    _store_bundle_and_artifact(
        result, collection_name="product_contracts", identity=identity,
        bundle=bundle, artifact=artifact, label="product-contract",
    )
    return result


def submit_product_contract(
    snapshot: Mapping[str, object], *, leaf_id: str, contract: Mapping[str, object], at: str,
    components: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Attach an immutable candidate contract and await an authenticated approval."""
    result = _working(snapshot)
    definition = _definition(result, leaf_id)
    if definition["definition_status"] == "withdrawn" or definition["draft_status"] != "shaping":
        raise ReducerError("illegal-product-contract-submission")
    source = _mapping(contract, "product-contract")
    identity = _validate_product_contract(source)
    if source.get("leaf_id") != definition["leaf_id"] or source.get("source_request") != definition["source_request"]:
        raise ReducerError("product-contract-definition-subject-mismatch")
    bundle, artifact = _prepare_bundle_artifact(
        source, components, expected_identity=identity,
        expected_kind="product_contract", label="product-contract",
    )
    _store_bundle_and_artifact(
        result, collection_name="product_contracts", identity=identity,
        bundle=bundle, artifact=artifact, label="product-contract",
    )
    definition.update({
        "draft_status": "awaiting_approval", "pending_contract_ref": identity,
        "pending_contract_revision": identity, "updated_at": _text(at, "product-contract-submitted-at"),
    })
    return result


def _definition(snapshot: Mapping[str, object], leaf_id: str) -> dict[str, object]:
    leaf_id = _id(leaf_id, "leaf-id")
    raw = _collection(snapshot, "product_definitions").get(leaf_id)
    if not isinstance(raw, dict):
        raise ReducerError("unknown-product-definition")
    required = {
        "leaf_id", "source_request", "owner", "definition_status", "draft_status", "current_contract_ref",
        "current_contract_revision", "current_contract_sha256", "current_approval_ref", "pending_contract_ref",
        "pending_contract_revision", "active_change_request_refs", "created_at", "updated_at",
    }
    if set(raw) != required or raw.get("leaf_id") != leaf_id:
        raise ReducerError("invalid-product-definition-record")
    if raw.get("definition_status") not in {"unapproved", "approved", "withdrawn"}:
        raise ReducerError("invalid-product-definition-status")
    if raw.get("draft_status") not in {"idle", "shaping", "awaiting_approval"}:
        raise ReducerError("invalid-product-draft-status")
    return raw


def _product_ready(snapshot: Mapping[str, object], leaf_id: str, *, work_type: str) -> tuple[dict[str, object] | None, list[str]]:
    reasons: list[str] = []
    try:
        leaf_id = _id(leaf_id, "leaf-id")
    except ReducerError as exc:
        return None, [str(exc)]
    raw_definition = _collection(snapshot, "product_definitions").get(leaf_id)
    if not isinstance(raw_definition, dict):
        return None, ["missing-product-definition"]
    try:
        definition = _definition(snapshot, leaf_id)
    except ReducerError as exc:
        return None, [str(exc)]
    if definition["definition_status"] != "approved":
        reasons.append("product-definition-not-approved")
    contract_id = definition.get("current_contract_ref")
    approval_id = definition.get("current_approval_ref")
    contract = _collection(snapshot, "product_contracts").get(contract_id) if isinstance(contract_id, str) else None
    if not isinstance(contract, Mapping):
        reasons.append("missing-current-product-contract")
    else:
        try:
            _validate_product_contract(contract)
            _require_bundle_artifact(
                snapshot, identity=str(contract_id), bundle=contract,
                expected_kind="product_contract", label="product-contract",
            )
        except ReducerError as exc:
            reasons.append(str(exc))
        if work_type == "hotfix" and contract.get("contract_kind") != "patch":
            reasons.append("hotfix-requires-approved-patch-contract")
    if definition.get("current_contract_revision") != contract_id or definition.get("current_contract_sha256") != contract_id:
        reasons.append("current-product-contract-tuple-mismatch")
    effective = _effective_approval(snapshot, _product_subject(str(contract_id))) if isinstance(contract_id, str) else None
    if effective is None or effective.get("approval_id") != approval_id:
        reasons.append("missing-effective-product-approval")
    requirement = _collection(snapshot, "requirements").get(leaf_id)
    if isinstance(requirement, Mapping):
        if requirement.get("status") == "withdrawn":
            reasons.append("requirement-withdrawn")
        dependencies = requirement.get("dependencies", [])
        if not isinstance(dependencies, list):
            reasons.append("invalid-requirement-dependencies")
        else:
            for dependency in dependencies:
                other = _collection(snapshot, "requirements").get(dependency)
                if not isinstance(other, Mapping) or other.get("status") != "shipped":
                    reasons.append(f"dependency-not-shipped:{dependency}")
    claim = _collection(snapshot, "claims").get(leaf_id)
    if isinstance(claim, Mapping) and claim.get("status") == "active":
        reasons.append("leaf-already-claimed")
    for cr in _collection(snapshot, "change_requests").values():
        if isinstance(cr, Mapping) and cr.get("feature_id") is None and cr.get("subject_ref") == contract_id:
            if cr.get("blocking") is True and cr.get("status") in {"open", "triaged", "accepted"}:
                reasons.append("blocking-product-change-request")
                break
    return definition, sorted(set(reasons))


def product_readiness(
    snapshot: Mapping[str, object], *, leaf_id: str, work_type: str = "feature",
) -> dict[str, object]:
    """Read-only product-side readiness query with explicit mechanical reasons."""
    validate_snapshot(snapshot)
    if work_type not in _WORK_TYPES:
        raise ReducerError("invalid-work-type")
    definition, reasons = _product_ready(snapshot, leaf_id, work_type=work_type)
    return {
        "leaf_id": leaf_id,
        "work_type": work_type,
        "ready": not reasons,
        "reasons": reasons,
        "product_contract_ref": None if definition is None else definition.get("current_contract_ref"),
        "product_contract_approval_ref": None if definition is None else definition.get("current_approval_ref"),
    }


def _feature_ids_for_leaf(snapshot: Mapping[str, object], leaf_id: str) -> list[str]:
    return sorted(
        feature_id for feature_id, feature in _collection(snapshot, "features").items()
        if isinstance(feature, Mapping) and feature.get("leaf_id") == leaf_id
        and feature.get("status") not in {"shipped", "abandoned"}
    )


def _all_feature_ids_for_leaf(snapshot: Mapping[str, object], leaf_id: str) -> list[str]:
    """Return historical and in-flight Features for a read-only projection."""
    return sorted(
        feature_id for feature_id, feature in _collection(snapshot, "features").items()
        if isinstance(feature, Mapping) and feature.get("leaf_id") == leaf_id
    )


def claim_feature(
    snapshot: Mapping[str, object], *, leaf_id: str, feature_id: str, claimed_base_sha: str,
    work_type: str = "feature", expected_product_contract_ref: str | None = None,
    expected_product_approval_ref: str | None = None, at: str,
) -> dict[str, object]:
    """Claim one ready product leaf and pin its effective product approval tuple."""
    result = _working(snapshot)
    if work_type not in _WORK_TYPES:
        raise ReducerError("invalid-work-type")
    feature_id = _id(feature_id, "feature-id")
    leaf_id = _id(leaf_id, "leaf-id")
    claimed_base_sha = _git_sha(claimed_base_sha, "claimed-base-sha")
    _text(at, "feature-claimed-at")
    readiness = product_readiness(result, leaf_id=leaf_id, work_type=work_type)
    if not readiness["ready"]:
        reasons = readiness["reasons"]
        if "hotfix-requires-approved-patch-contract" in reasons:
            raise ReducerError("hotfix-requires-approved-patch-contract")
        raise ReducerError("leaf-not-ready:" + ",".join(str(item) for item in reasons))
    product_ref = _sha(readiness["product_contract_ref"], "current-product-contract-ref")
    product_approval = _sha(readiness["product_contract_approval_ref"], "current-product-approval-ref")
    if expected_product_contract_ref is not None and expected_product_contract_ref != product_ref:
        raise ReducerError("product-contract-claim-fence-conflict")
    if expected_product_approval_ref is not None and expected_product_approval_ref != product_approval:
        raise ReducerError("product-approval-claim-fence-conflict")
    features = _collection(result, "features")
    claims = _collection(result, "claims")
    if feature_id in features:
        raise ReducerError("feature-id-already-exists")
    feature = {
        "feature_id": feature_id,
        "leaf_id": leaf_id,
        "work_type": work_type,
        "status": "active",
        "contract_model": CAPABILITY,
        "contract_generation": 0,
        "product_contract_ref": product_ref,
        "product_contract_revision": product_ref,
        "product_contract_approval_ref": product_approval,
        "engineering_spec_ref": None,
        "engineering_spec_approval_ref": None,
        "profile_ref": None,
        "profile_revision": None,
        "profile_sha256": None,
        "engineering_base_sha": None,
        "delivery_plan_ref": None,
        "validation_status": "pending",
        "review_status": "pending",
        "review_attestation_ref": None,
        "active_change_request_refs": [],
        "resolved_change_request_refs": [],
        "invalidation_reasons": [],
        "release_evidence_ref": None,
        "shipped_at": None,
        "claimed_base_sha": claimed_base_sha,
        "created_at": at,
        "updated_at": at,
    }
    features[feature_id] = feature
    claims[leaf_id] = {
        "leaf_id": leaf_id, "feature_id": feature_id, "status": "active", "claimed_base_sha": claimed_base_sha,
        "product_contract_ref": product_ref, "product_contract_approval_ref": product_approval, "created_at": at,
    }
    return result


def _feature(snapshot: Mapping[str, object], feature_id: str) -> dict[str, object]:
    feature_id = _id(feature_id, "feature-id")
    raw = _collection(snapshot, "features").get(feature_id)
    if not isinstance(raw, dict):
        raise ReducerError("unknown-feature")
    required = {
        "feature_id", "leaf_id", "work_type", "status", "contract_model", "contract_generation",
        "product_contract_ref", "product_contract_revision", "product_contract_approval_ref",
        "engineering_spec_ref", "engineering_spec_approval_ref", "profile_ref", "profile_revision",
        "profile_sha256", "engineering_base_sha", "delivery_plan_ref", "validation_status", "review_status",
        "review_attestation_ref",
        "active_change_request_refs", "resolved_change_request_refs", "invalidation_reasons",
        "release_evidence_ref", "shipped_at", "claimed_base_sha",
        "created_at", "updated_at",
    }
    if set(raw) != required or raw.get("feature_id") != feature_id:
        raise ReducerError("invalid-feature-record")
    if raw.get("contract_model") != CAPABILITY or raw.get("status") not in _FEATURE_STATUSES:
        raise ReducerError("invalid-feature-contract-model-or-status")
    _generation(raw.get("contract_generation"))
    review_ref = raw.get("review_attestation_ref")
    if raw.get("review_status") in {"approved", "rejected"}:
        _sha(review_ref, "feature-review-attestation-ref")
    elif review_ref is not None:
        raise ReducerError("unreviewed-feature-has-review-attestation")
    if raw.get("status") == "shipped":
        _sha(raw.get("release_evidence_ref"), "feature-release-evidence-ref")
        _text(raw.get("shipped_at"), "feature-shipped-at")
    elif raw.get("release_evidence_ref") is not None or raw.get("shipped_at") is not None:
        raise ReducerError("unshipped-feature-has-release-record")
    return raw


def current_fence(snapshot: Mapping[str, object], *, feature_id: str) -> dict[str, object]:
    """Return the exact tuple delivery agents must echo on every later write."""
    validate_snapshot(snapshot)
    feature = _feature(snapshot, feature_id)
    return {field: deepcopy(feature[field]) for field in FENCE_FIELDS}


def _require_fence(
    snapshot: Mapping[str, object], *, feature_id: str, fence: Mapping[str, object], require_delivery: bool,
) -> dict[str, object]:
    feature = _feature(snapshot, feature_id)
    supplied = _mapping(fence, "contract-fence")
    if set(supplied) != set(FENCE_FIELDS):
        raise ReducerError("invalid-contract-fence-fields")
    expected = {field: feature[field] for field in FENCE_FIELDS}
    if dict(supplied) != expected:
        raise ReducerError("stale-contract-fence")
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-write-terminal-feature")
    if require_delivery and any(expected[field] is None for field in FENCE_FIELDS[1:]):
        raise ReducerError("incomplete-current-contract-fence")
    return feature


def _require_generation(feature: Mapping[str, object], expected_generation: int) -> None:
    if _generation(expected_generation, "expected-contract-generation") != feature.get("contract_generation"):
        raise ReducerError("stale-contract-generation")


def _validate_profile_snapshot(profile: Mapping[str, object]) -> str:
    if profile.get("profile_format") != "profile-snapshot-v1":
        raise ReducerError("invalid-profile-snapshot-format")
    identity = str(_sha(profile.get("profile_snapshot_id"), "profile-snapshot-id"))
    _sha(profile.get("profile_bytes_sha256"), "profile-bytes-sha")
    _git_sha(profile.get("source_repository_sha"), "profile-source-sha")
    _git_sha(profile.get("profile_revision"), "profile-revision")
    if profile.get("source_path") != ".sdlc/PROFILE.md":
        raise ReducerError("invalid-profile-snapshot-source-path")
    return identity


def register_profile_snapshot(
    snapshot: Mapping[str, object], *, profile_snapshot: Mapping[str, object],
    components: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Pack and store a profile byte snapshot separately from its mutable path."""
    result = _working(snapshot)
    profile = _mapping(profile_snapshot, "profile-snapshot")
    identity = _validate_profile_snapshot(profile)
    bundle, artifact = _prepare_bundle_artifact(
        profile, components, expected_identity=identity,
        expected_kind="profile_snapshot", label="profile-snapshot",
    )
    _store_bundle_and_artifact(
        result, collection_name="profile_snapshots", identity=identity,
        bundle=bundle, artifact=artifact, label="profile-snapshot",
    )
    return result


def _validate_engineering_spec(spec: Mapping[str, object]) -> str:
    if spec.get("spec_format") != "engineering-spec-v1":
        raise ReducerError("invalid-engineering-spec-format")
    identity = str(_sha(spec.get("engineering_spec_id"), "engineering-spec-id"))
    if spec.get("bundle_sha256") != identity:
        raise ReducerError("engineering-spec-bundle-id-mismatch")
    _id(spec.get("feature_id"), "engineering-spec-feature-id")
    product_ref = _sha(spec.get("product_contract_ref"), "engineering-product-contract-ref")
    if spec.get("product_contract_revision") != product_ref:
        raise ReducerError("engineering-product-contract-revision-mismatch")
    _sha(spec.get("product_contract_approval_ref"), "engineering-product-approval-ref")
    _sha(spec.get("profile_ref"), "engineering-profile-ref")
    _git_sha(spec.get("profile_revision"), "engineering-profile-revision")
    _sha(spec.get("profile_sha256"), "engineering-profile-sha")
    _git_sha(spec.get("specified_against_sha"), "engineering-base-sha")
    _string_list(spec.get("implements_product_ids"), "engineering-implements", allow_empty=False)
    _string_list(spec.get("engineering_criterion_ids"), "engineering-criteria", allow_empty=False)
    return identity


def register_engineering_spec(
    snapshot: Mapping[str, object], *, engineering_spec: Mapping[str, object],
    components: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Pack and store an immutable EngineeringSpec before Feature adoption."""
    result = _working(snapshot)
    spec = _mapping(engineering_spec, "engineering-spec")
    identity = _validate_engineering_spec(spec)
    bundle, artifact = _prepare_bundle_artifact(
        spec, components, expected_identity=identity,
        expected_kind="engineering_spec", label="engineering-spec",
    )
    _store_bundle_and_artifact(
        result, collection_name="engineering_specs", identity=identity,
        bundle=bundle, artifact=artifact, label="engineering-spec",
    )
    return result


def adopt_product_contract(
    snapshot: Mapping[str, object], *, leaf_id: str, product_contract_ref: str,
    product_contract_approval_ref: str, at: str,
) -> dict[str, object]:
    """Adopt one effectively approved ProductContract for future Feature claims.

    This changes only the ProductDefinition's current tuple.  An in-flight
    Feature remains pinned to the tuple it claimed until a feature-scoped,
    accepted ChangeRequest is applied through
    :func:`adopt_feature_product_contract`.
    """
    result = _working(snapshot)
    definition = _definition(result, leaf_id)
    contract_ref = str(_sha(product_contract_ref, "product-contract-ref"))
    approval_ref = str(_sha(product_contract_approval_ref, "product-contract-approval-ref"))
    contract = _collection(result, "product_contracts").get(contract_ref)
    if not isinstance(contract, Mapping):
        raise ReducerError("unknown-product-contract")
    _validate_product_contract(contract)
    _require_bundle_artifact(
        result, identity=contract_ref, bundle=contract,
        expected_kind="product_contract", label="product-contract",
    )
    if contract.get("leaf_id") != definition["leaf_id"]:
        raise ReducerError("product-contract-definition-subject-mismatch")
    effective = _effective_approval(result, _product_subject(contract_ref))
    if effective is None or effective.get("approval_id") != approval_ref:
        raise ReducerError("ineffective-product-contract-approval")
    current_tuple = (definition.get("current_contract_ref"), definition.get("current_approval_ref"))
    wanted_tuple = (contract_ref, approval_ref)
    if current_tuple == wanted_tuple and definition.get("definition_status") == "approved":
        return result
    if definition.get("pending_contract_ref") != contract_ref or definition.get("draft_status") != "awaiting_approval":
        raise ReducerError("product-contract-not-pending-adoption")
    at = _text(at, "product-contract-adopted-at")
    definition.update({
        "definition_status": "approved", "draft_status": "idle", "current_contract_ref": contract_ref,
        "current_contract_revision": contract_ref, "current_contract_sha256": contract_ref,
        "current_approval_ref": approval_ref, "pending_contract_ref": None, "pending_contract_revision": None,
        "updated_at": at,
    })
    return result


def adopt_feature_product_contract(
    snapshot: Mapping[str, object], *, feature_id: str, change_request_id: str,
    product_contract_ref: str, product_contract_approval_ref: str,
    expected_generation: int, at: str,
) -> dict[str, object]:
    """Apply one accepted product CR to exactly one in-flight Feature.

    ProductDefinition adoption intentionally affects future claims only.  This
    operation is the sole path that moves an existing Feature onto a newer
    product tuple: it verifies the ProductDefinition's already-adopted tuple,
    applies the accepted, Feature-bound CR, and invalidates all downstream
    delivery state in one returned snapshot.
    """
    result = _working(snapshot)
    feature = _feature(result, feature_id)
    _require_generation(feature, expected_generation)
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-adopt-product-contract-for-terminal-feature")
    record = _require_accepted_feature_change_request(
        result, change_request_id=change_request_id, feature=feature, scope="product",
    )
    if record["subject_ref"] != feature["product_contract_ref"]:
        raise ReducerError("change-request-product-subject-mismatch")

    contract_ref = str(_sha(product_contract_ref, "feature-product-contract-ref"))
    approval_ref = str(_sha(product_contract_approval_ref, "feature-product-contract-approval-ref"))
    contract = _collection(result, "product_contracts").get(contract_ref)
    if not isinstance(contract, Mapping):
        raise ReducerError("unknown-feature-product-contract")
    _validate_product_contract(contract)
    _require_bundle_artifact(
        result, identity=contract_ref, bundle=contract,
        expected_kind="product_contract", label="product-contract",
    )
    if contract.get("leaf_id") != feature["leaf_id"]:
        raise ReducerError("feature-product-contract-leaf-mismatch")
    effective = _effective_approval(result, _product_subject(contract_ref))
    if effective is None or effective.get("approval_id") != approval_ref:
        raise ReducerError("ineffective-feature-product-contract-approval")
    definition = _definition(result, str(feature["leaf_id"]))
    definition_tuple = (definition["current_contract_ref"], definition["current_approval_ref"])
    if definition_tuple != (contract_ref, approval_ref) or definition["definition_status"] != "approved":
        raise ReducerError("feature-product-contract-not-current-product-definition-tuple")
    if (feature["product_contract_ref"], feature["product_contract_approval_ref"]) == (contract_ref, approval_ref):
        raise ReducerError("feature-product-contract-already-current")

    at = _text(at, "feature-product-contract-adopted-at")
    _invalidate_feature_inplace(
        result,
        str(feature["feature_id"]),
        reason=f"feature-product-contract-adopted:{contract_ref}",
        at=at,
        product_tuple={
            "product_contract_ref": contract_ref,
            "product_contract_revision": contract_ref,
            "product_contract_approval_ref": approval_ref,
        },
    )
    updated = _feature(result, str(feature["feature_id"]))
    _complete_change_request_inplace(
        updated,
        record,
        resolution={
            "resolution_kind": "product-contract-adoption-v1",
            "product_contract_ref": contract_ref,
            "product_contract_approval_ref": approval_ref,
            "semantics": "adopt-feature-product-contract",
        },
        at=at,
    )
    return result


def adopt_engineering_spec(
    snapshot: Mapping[str, object], *, feature_id: str, engineering_spec_ref: str,
    engineering_spec_approval_ref: str, expected_generation: int, at: str,
) -> dict[str, object]:
    """Bind an approved EngineeringSpec to the Feature's current product tuple."""
    result = _working(snapshot)
    feature = _feature(result, feature_id)
    _require_generation(feature, expected_generation)
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-adopt-engineering-spec-for-terminal-feature")
    spec_ref = str(_sha(engineering_spec_ref, "engineering-spec-ref"))
    approval_ref = str(_sha(engineering_spec_approval_ref, "engineering-spec-approval-ref"))
    spec = _collection(result, "engineering_specs").get(spec_ref)
    if not isinstance(spec, Mapping):
        raise ReducerError("unknown-engineering-spec")
    _validate_engineering_spec(spec)
    _require_bundle_artifact(
        result, identity=spec_ref, bundle=spec,
        expected_kind="engineering_spec", label="engineering-spec",
    )
    if spec.get("feature_id") != feature["feature_id"]:
        raise ReducerError("engineering-spec-feature-mismatch")
    expected_product = {
        "product_contract_ref": feature["product_contract_ref"],
        "product_contract_revision": feature["product_contract_revision"],
        "product_contract_approval_ref": feature["product_contract_approval_ref"],
    }
    if any(spec.get(field) != value for field, value in expected_product.items()):
        raise ReducerError("engineering-spec-product-tuple-mismatch")
    profile_ref = spec.get("profile_ref")
    profile = _collection(result, "profile_snapshots").get(profile_ref) if isinstance(profile_ref, str) else None
    if not isinstance(profile, Mapping):
        raise ReducerError("engineering-spec-profile-snapshot-missing")
    _validate_profile_snapshot(profile)
    _require_bundle_artifact(
        result, identity=str(profile_ref), bundle=profile,
        expected_kind="profile_snapshot", label="profile-snapshot",
    )
    if profile.get("feature_id") != feature["feature_id"]:
        raise ReducerError("engineering-spec-profile-feature-mismatch")
    if profile.get("profile_revision") != spec.get("profile_revision") or profile.get("profile_bytes_sha256") != spec.get("profile_sha256"):
        raise ReducerError("engineering-spec-profile-tuple-mismatch")
    product_ref = str(feature["product_contract_ref"])
    product = _collection(result, "product_contracts").get(product_ref)
    if not isinstance(product, Mapping):
        raise ReducerError("current-product-contract-missing")
    _validate_product_contract(product)
    _require_bundle_artifact(
        result, identity=product_ref, bundle=product,
        expected_kind="product_contract", label="product-contract",
    )
    effective_product = _effective_approval(result, _product_subject(str(feature["product_contract_ref"])))
    if effective_product is None or effective_product.get("approval_id") != feature["product_contract_approval_ref"]:
        raise ReducerError("product-approval-no-longer-effective")
    effective_engineering = _effective_approval(result, _engineering_subject(spec_ref))
    if effective_engineering is None or effective_engineering.get("approval_id") != approval_ref:
        raise ReducerError("ineffective-engineering-spec-approval")
    if feature["engineering_spec_ref"] is not None:
        if feature["engineering_spec_ref"] == spec_ref and feature["engineering_spec_approval_ref"] == approval_ref:
            return result
        raise ReducerError("engineering-spec-already-bound-invalidate-first")
    at = _text(at, "engineering-spec-adopted-at")
    feature.update({
        "engineering_spec_ref": spec_ref,
        "engineering_spec_approval_ref": approval_ref,
        "profile_ref": spec["profile_ref"],
        "profile_revision": spec["profile_revision"],
        "profile_sha256": spec["profile_sha256"],
        "engineering_base_sha": spec["specified_against_sha"],
        "updated_at": at,
    })
    return result


def _plan_task_instance_id(feature_id: str, plan_id: str, task_id: str) -> str:
    return hashlib.sha256(f"{feature_id}\x00{plan_id}\x00{task_id}".encode("utf-8")).hexdigest()


def _current_tasks(snapshot: Mapping[str, object], feature: Mapping[str, object]) -> list[dict[str, object]]:
    plan_ref = feature.get("delivery_plan_ref")
    if not isinstance(plan_ref, str):
        return []
    result: list[dict[str, object]] = []
    for raw in _collection(snapshot, "tasks").values():
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("feature_id") == feature.get("feature_id")
            and raw.get("delivery_plan_ref") == plan_ref
            and raw.get("contract_generation") == feature.get("contract_generation")
        ):
            result.append(raw)
    return sorted(result, key=lambda item: str(item.get("task_id")))


def _current_task(snapshot: Mapping[str, object], feature: Mapping[str, object], task_id: str) -> dict[str, object]:
    task_id = _id(task_id, "task-id")
    matches = [task for task in _current_tasks(snapshot, feature) if task.get("task_id") == task_id]
    if len(matches) != 1:
        raise ReducerError("unknown-current-task")
    return matches[0]


def _require_no_active_blocking_change_request(
    snapshot: Mapping[str, object], feature: Mapping[str, object],
) -> None:
    """Stop delivery writes as soon as a blocking ChangeRequest is opened.

    An open discrepancy means the current Feature tuple is already known to be
    incomplete.  Deferring the stop until acceptance left a window where an
    old Task could be claimed, evidenced, validated, or reviewed.  Rejecting
    or cancelling a ChangeRequest deliberately re-enables its current tuple;
    applying one advances generation and makes that tuple stale.
    """
    feature_id = feature.get("feature_id")
    blocking_ids = sorted(
        str(change_request_id)
        for change_request_id, raw_change_request in _collection(snapshot, "change_requests").items()
        if isinstance(raw_change_request, Mapping)
        and raw_change_request.get("feature_id") == feature_id
        and raw_change_request.get("status") in {"open", "triaged", "accepted"}
        and raw_change_request.get("blocking") is True
    )
    if blocking_ids:
        raise ReducerError("active-blocking-change-request:" + ",".join(blocking_ids))


def _require_no_blocking_change_request(snapshot: Mapping[str, object], feature: Mapping[str, object]) -> None:
    """Release may not proceed while any blocking CR remains unresolved."""
    feature_id = feature.get("feature_id")
    blocking_ids = sorted(
        str(change_request_id)
        for change_request_id, raw_change_request in _collection(snapshot, "change_requests").items()
        if isinstance(raw_change_request, Mapping)
        and raw_change_request.get("feature_id") == feature_id
        and raw_change_request.get("blocking") is True
        and raw_change_request.get("status") in {"open", "triaged", "accepted"}
    )
    if blocking_ids:
        raise ReducerError("blocking-change-request-prevents-release:" + ",".join(blocking_ids))


def _validate_activation_tuple(feature: Mapping[str, object], plan: Mapping[str, object]) -> None:
    expected = {
        "feature_id": feature["feature_id"],
        "engineering_spec_ref": feature["engineering_spec_ref"],
        "engineering_spec_approval_ref": feature["engineering_spec_approval_ref"],
        "product_contract_ref": feature["product_contract_ref"],
        "product_contract_approval_ref": feature["product_contract_approval_ref"],
        "profile_ref": feature["profile_ref"],
        "profile_revision": feature["profile_revision"],
        "profile_sha256": feature["profile_sha256"],
        "base_sha": feature["engineering_base_sha"],
        "contract_generation": feature["contract_generation"],
    }
    for field, value in expected.items():
        if plan.get(field) != value:
            raise ReducerError(f"delivery-plan-current-tuple-mismatch:{field}")
    if plan.get("engineering_spec_revision") != feature["engineering_spec_ref"]:
        raise ReducerError("delivery-plan-engineering-revision-mismatch")


def activate_delivery_plan(
    snapshot: Mapping[str, object], *, feature_id: str, delivery_plan: Mapping[str, object],
    expected_generation: int, at: str,
) -> dict[str, object]:
    """Activate an immutable DeliveryPlan and create its whole task set at once."""
    result = _working(snapshot)
    feature = _feature(result, feature_id)
    _require_generation(feature, expected_generation)
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-activate-plan-for-terminal-feature")
    if feature["engineering_spec_ref"] is None or feature["engineering_spec_approval_ref"] is None:
        raise ReducerError("engineering-spec-not-adopted")
    plan = _mapping(delivery_plan, "delivery-plan")
    spec = _collection(result, "engineering_specs").get(feature["engineering_spec_ref"])
    if not isinstance(spec, Mapping):
        raise ReducerError("active-engineering-spec-missing")
    effective = _effective_approval(result, _engineering_subject(str(feature["engineering_spec_ref"])))
    if effective is None or effective.get("approval_id") != feature["engineering_spec_approval_ref"]:
        raise ReducerError("engineering-approval-no-longer-effective")
    bound_spec = {**spec, "contract_generation": feature["contract_generation"]}
    try:
        plan_id = plan_compiler.verify_delivery_plan(
            plan, engineering_spec=bound_spec, effective_approval=effective,
        )
    except plan_compiler.PlanError as exc:
        raise ReducerError(str(exc)) from exc
    _validate_activation_tuple(feature, plan)
    current_plan = feature["delivery_plan_ref"]
    if current_plan is not None:
        if current_plan == plan_id:
            return result
        raise ReducerError("delivery-plan-already-active-invalidate-first")
    at = _text(at, "delivery-plan-activated-at")
    _immutable_put(_collection(result, "delivery_plans"), plan_id, plan, "delivery-plan")
    pending: list[tuple[str, dict[str, object]]] = []
    for plan_task in plan["tasks"]:
        if not isinstance(plan_task, Mapping):
            raise ReducerError("invalid-delivery-plan-task")
        strategy = plan_task.get("evidence_strategy")
        if not isinstance(strategy, Mapping) or strategy.get("kind") not in _CANONICAL_RUNNABLE_STRATEGIES:
            # A canonical receipt must be bound to a command fixed in the
            # immutable DeliveryPlan. Typed attestations remain semantic input,
            # not runner evidence.
            raise ReducerError("canonical-execution-strategy-not-supported")
        task_id = _id(plan_task.get("id"), "delivery-plan-task-id")
        dependencies = _string_list(plan_task.get("depends_on"), "delivery-plan-task-dependencies")
        task_key = _plan_task_instance_id(str(feature["feature_id"]), plan_id, task_id)
        status = "ready" if not dependencies else "waiting"
        record = {
            "task_instance_id": task_key,
            "task_id": task_id,
            "feature_id": feature["feature_id"],
            "delivery_plan_ref": plan_id,
            "product_contract_ref": feature["product_contract_ref"],
            "product_contract_approval_ref": feature["product_contract_approval_ref"],
            "engineering_spec_ref": feature["engineering_spec_ref"],
            "engineering_spec_approval_ref": feature["engineering_spec_approval_ref"],
            "contract_generation": feature["contract_generation"],
            "status": status,
            "depends_on": dependencies,
            "execution_mode": deepcopy(plan_task.get("execution_mode")),
            "evidence_strategy": deepcopy(strategy),
            "trace_refs": deepcopy(plan_task.get("trace_refs")),
            "evidence_refs": [],
            "created_at": at,
            "updated_at": at,
        }
        pending.append((task_key, record))
    if len({item[1]["task_id"] for item in pending}) != len(pending):
        raise ReducerError("duplicate-delivery-plan-task-id")
    tasks = _collection(result, "tasks")
    for task_key, record in pending:
        _immutable_put(tasks, task_key, record, "task-instance")
    feature["delivery_plan_ref"] = plan_id
    feature["validation_status"] = "pending"
    feature["review_status"] = "pending"
    feature["review_attestation_ref"] = None
    feature["updated_at"] = at
    return result


def _feature_fence(feature: Mapping[str, object]) -> dict[str, object]:
    return {field: deepcopy(feature.get(field)) for field in FENCE_FIELDS}


def _execution_evidence_from_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    preimage: dict[str, object] = {
        "evidence_format": "execution-evidence-v2",
        "runner_receipt_ref": receipt.get("receipt_id"),
        "result": receipt.get("result"),
        "tested_sha": receipt.get("tested_sha"),
        "task_id": receipt.get("task_id"),
        "feature_id": receipt.get("feature_id"),
        **{field: deepcopy(receipt.get(field)) for field in FENCE_FIELDS},
        "trace_refs": deepcopy(receipt.get("trace_refs")),
    }
    evidence_id = hashlib.sha256(dual_artifact_store.canonical_json_bytes(preimage)).hexdigest()
    return {"evidence_id": evidence_id, **preimage}


def _current_passing_task_evidence(
    snapshot: Mapping[str, object], feature: Mapping[str, object], task: Mapping[str, object],
) -> list[Mapping[str, object]]:
    refs = task.get("evidence_refs")
    traces = task.get("trace_refs")
    if not isinstance(refs, list) or not isinstance(traces, list):
        return []
    evidence_by_id = _collection(snapshot, "evidence")
    receipts_by_id = _collection(snapshot, "runner_receipts")
    passing: list[Mapping[str, object]] = []
    for evidence_id in refs:
        raw = evidence_by_id.get(evidence_id)
        if not isinstance(raw, Mapping):
            continue
        receipt_ref = raw.get("runner_receipt_ref")
        receipt = receipts_by_id.get(receipt_ref) if isinstance(receipt_ref, str) else None
        if (
            raw.get("evidence_id") != evidence_id
            or raw.get("evidence_format") != "execution-evidence-v2"
            or raw.get("result") != "pass"
            or not isinstance(receipt, Mapping)
        ):
            continue
        try:
            verified_receipt = dual_artifact_store.verify_runner_receipt(
                receipt,
                expected_tested_sha=str(raw.get("tested_sha")),
                expected_feature_id=str(feature.get("feature_id")),
                expected_task_id=str(task.get("task_id")),
                expected_current_tuple=_feature_fence(feature),
                expected_trace_refs=traces,
            )
        except dual_artifact_store.ArtifactStoreError:
            continue
        if verified_receipt != receipt_ref or receipt.get("result") != "pass":
            continue
        if dict(raw) != _execution_evidence_from_receipt(receipt):
            continue
        passing.append(raw)
    return passing


def _current_feature_passing_evidence_refs(
    snapshot: Mapping[str, object], feature: Mapping[str, object], *, require_nonempty: bool = True,
) -> list[str]:
    """Return exactly the current passing Evidence records a review must cover.

    A semantic review may add its own rationale, but it must refer to the
    objective Evidence that made the current Feature eligible for validation.
    This keeps a review attestation inspectable after the caller and the
    transient runner process are gone.
    """
    refs: set[str] = set()
    for task in _current_tasks(snapshot, feature):
        for evidence in _current_passing_task_evidence(snapshot, feature, task):
            evidence_id = _sha(evidence.get("evidence_id"), "current-review-evidence-id")
            refs.add(evidence_id)
    if require_nonempty and not refs:
        raise ReducerError("review-requires-current-passing-evidence")
    return sorted(refs)


def transition_task(
    snapshot: Mapping[str, object], *, feature_id: str, task_id: str, action: str,
    fence: Mapping[str, object], at: str,
) -> dict[str, object]:
    """Apply a runtime Task transition only against the Feature's current fence."""
    result = _working(snapshot)
    feature = _require_fence(result, feature_id=feature_id, fence=fence, require_delivery=True)
    _require_no_active_blocking_change_request(result, feature)
    task = _current_task(result, feature, task_id)
    if task.get("status") not in _TASK_STATUSES:
        raise ReducerError("invalid-task-status")
    action = _id(action, "task-action")
    before = task["status"]
    if action == "claim":
        if before not in {"ready", "waiting"}:
            raise ReducerError("illegal-task-transition")
        dependency_states = {item["task_id"]: item["status"] for item in _current_tasks(result, feature)}
        if any(dependency_states.get(dep) != "verified" for dep in task["depends_on"]):
            raise ReducerError("task-dependencies-not-verified")
        after = "claimed"
    elif action == "start" and before == "claimed":
        after = "in_progress"
    elif action == "submit" and before == "in_progress":
        after = "awaiting_verification"
    elif action == "verify" and before == "awaiting_verification":
        if not _current_passing_task_evidence(result, feature, task):
            raise ReducerError("task-verification-requires-current-passing-evidence")
        after = "verified"
    elif action == "block" and before not in _TASK_TERMINAL:
        after = "blocked"
    elif action == "unblock" and before == "blocked":
        after = "ready"
    else:
        raise ReducerError("illegal-task-transition")
    task["status"] = after
    task["updated_at"] = _text(at, "task-transitioned-at")
    return result


def record_evidence(
    snapshot: Mapping[str, object], *, runner_record: Mapping[str, object], tested_sha: str,
    feature_id: str, task_id: str, fence: Mapping[str, object], at: str,
) -> dict[str, object]:
    """Derive immutable v2 Evidence from one canonical runner observation."""
    result = _working(snapshot)
    feature_id = _id(feature_id, "evidence-feature-id")
    task_id = _id(task_id, "evidence-task-id")
    feature = _require_fence(result, feature_id=feature_id, fence=fence, require_delivery=True)
    _require_no_active_blocking_change_request(result, feature)
    task = _current_task(result, feature, task_id)
    if task["status"] in _TASK_TERMINAL:
        raise ReducerError("cannot-attach-evidence-to-terminal-task")
    traces = task.get("trace_refs")
    if not isinstance(traces, list):
        raise ReducerError("invalid-task-trace-refs")
    try:
        receipt = dual_artifact_store.build_runner_receipt(
            _mapping(runner_record, "runner-record"),
            tested_sha=tested_sha,
            feature_id=feature_id,
            task_id=task_id,
            current_tuple=_feature_fence(feature),
            trace_refs=traces,
        )
        receipt_id = dual_artifact_store.verify_runner_receipt(
            receipt,
            expected_tested_sha=tested_sha,
            expected_feature_id=feature_id,
            expected_task_id=task_id,
            expected_current_tuple=_feature_fence(feature),
            expected_trace_refs=traces,
        )
    except dual_artifact_store.ArtifactStoreError as exc:
        raise ReducerError(str(exc)) from exc
    evidence = _execution_evidence_from_receipt(receipt)
    evidence_id = str(evidence["evidence_id"])
    _immutable_put(_collection(result, "runner_receipts"), receipt_id, receipt, "runner-receipt")
    _immutable_put(_collection(result, "evidence"), evidence_id, evidence, "evidence")
    if evidence_id not in task["evidence_refs"]:
        task["evidence_refs"].append(evidence_id)
        task["evidence_refs"].sort()
    if receipt.get("result") == "pass" and task["status"] in {"claimed", "in_progress"}:
        task["status"] = "awaiting_verification"
    task["updated_at"] = _text(at, "evidence-recorded-at")
    return result


def validate_feature(
    snapshot: Mapping[str, object], *, feature_id: str, fence: Mapping[str, object], at: str,
) -> dict[str, object]:
    """Mark a Feature validated only from current, verified task/evidence tuples."""
    result = _working(snapshot)
    feature = _require_fence(result, feature_id=feature_id, fence=fence, require_delivery=True)
    _require_no_active_blocking_change_request(result, feature)
    tasks = _current_tasks(result, feature)
    if not tasks or any(task.get("status") != "verified" for task in tasks):
        raise ReducerError("feature-tasks-not-verified")
    evidence: list[Mapping[str, object]] = []
    for task in tasks:
        refs = task.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ReducerError("verified-task-missing-evidence")
        passing = _current_passing_task_evidence(result, feature, task)
        if not passing:
            raise ReducerError("feature-has-no-passing-current-evidence")
        evidence.extend(passing)
    product = _collection(result, "product_contracts").get(feature["product_contract_ref"])
    engineering = _collection(result, "engineering_specs").get(feature["engineering_spec_ref"])
    delivery_plan = _collection(result, "delivery_plans").get(feature["delivery_plan_ref"])
    if not isinstance(product, Mapping) or not isinstance(engineering, Mapping) or not isinstance(delivery_plan, Mapping):
        raise ReducerError("feature-current-artifact-missing")
    report = trace_lint.lint_trace_graph(product, engineering, delivery_plan, tasks, evidence)
    if not report.ok:
        raise ReducerError("trace-validation-failed:" + ",".join(report.codes))
    feature["status"] = "validated"
    feature["validation_status"] = "passed"
    feature["review_status"] = "pending"
    feature["review_attestation_ref"] = None
    feature["updated_at"] = _text(at, "feature-validated-at")
    return result


def review_feature(
    snapshot: Mapping[str, object], *, feature_id: str, fence: Mapping[str, object],
    attestation: Mapping[str, object], at: str,
) -> dict[str, object]:
    """Record one immutable, authority-bound semantic review outcome."""
    result = _working(snapshot)
    feature = _require_fence(result, feature_id=feature_id, fence=fence, require_delivery=True)
    _require_no_active_blocking_change_request(result, feature)
    if feature["status"] != "validated" or feature["validation_status"] != "passed":
        raise ReducerError("review-requires-validated-feature")
    reviewed_at = _text(at, "feature-reviewed-at")
    try:
        review_ref = review_attestation.verify_review_attestation(
            attestation,
            expected_feature_id=str(feature["feature_id"]),
            expected_current_tuple=_feature_fence(feature),
            expected_reviewed_at=reviewed_at,
        )
    except review_attestation.ReviewAttestationError as exc:
        raise ReducerError(str(exc)) from exc
    expected_evidence_refs = _current_feature_passing_evidence_refs(result, feature)
    if attestation.get("evidence_refs") != expected_evidence_refs:
        raise ReducerError("review-evidence-does-not-match-current-feature-evidence")
    _immutable_put(
        _collection(result, "review_attestations"), review_ref, attestation,
        "review-attestation",
    )
    feature["review_status"] = "approved" if attestation.get("decision") == "approve" else "rejected"
    feature["review_attestation_ref"] = review_ref
    feature["updated_at"] = reviewed_at
    return result


def ship_feature(
    snapshot: Mapping[str, object], *, feature_id: str, fence: Mapping[str, object],
    release_receipt: Mapping[str, object], at: str,
) -> dict[str, object]:
    """Verify and store a release receipt before recording a fenced release."""
    result = _working(snapshot)
    feature = _require_fence(result, feature_id=feature_id, fence=fence, require_delivery=True)
    if feature["status"] != "validated" or feature["validation_status"] != "passed":
        raise ReducerError("ship-requires-validated-feature")
    if feature["review_status"] != "approved":
        raise ReducerError("ship-requires-approved-review")
    review_ref = _sha(feature.get("review_attestation_ref"), "feature-review-attestation-ref")
    stored_review = _collection(result, "review_attestations").get(review_ref)
    if not isinstance(stored_review, Mapping):
        raise ReducerError("ship-requires-current-review-attestation")
    try:
        review_attestation.verify_review_attestation(
            stored_review,
            expected_feature_id=str(feature["feature_id"]),
            expected_current_tuple=_feature_fence(feature),
            expected_decision="approve",
        )
    except review_attestation.ReviewAttestationError as exc:
        raise ReducerError(f"ship-requires-current-review-attestation:{exc}") from exc
    _require_no_blocking_change_request(result, feature)
    source = _mapping(release_receipt, "release-receipt")
    claims = _collection(result, "claims")
    claim = claims.get(feature["leaf_id"])
    if not isinstance(claim, dict) or claim.get("feature_id") != feature["feature_id"] or claim.get("status") != "active":
        raise ReducerError("ship-requires-active-feature-claim")
    at = _text(at, "feature-shipped-at")
    try:
        release_ref = dual_artifact_store.verify_release_receipt(
            source,
            expected_runner_record_ref=str(_sha(source.get("runner_record_ref"), "release-runner-record-ref")),
            expected_feature_id=str(feature["feature_id"]),
            expected_release_target=_mapping(source.get("release_target"), "release-target"),
            expected_actual_release_artifact=_mapping(
                source.get("actual_release_artifact"), "actual-release-artifact",
            ),
            expected_release_sha=_git_sha(source.get("release_sha"), "release-sha"),
            expected_current_tuple=_feature_fence(feature),
        )
    except dual_artifact_store.ArtifactStoreError as exc:
        raise ReducerError(str(exc)) from exc
    _immutable_put(_collection(result, "release_receipts"), release_ref, source, "release-receipt")
    feature.update({
        "status": "shipped",
        "release_evidence_ref": release_ref,
        "shipped_at": at,
        "updated_at": at,
    })
    claim.update({
        "status": "released",
        "released_at": at,
        "release_evidence_ref": release_ref,
    })
    return result


def open_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, feature_id: str, scope: str,
    subject_ref: str, blocking: bool, reported_by: str, at: str,
) -> dict[str, object]:
    """Open a typed CR.  Applying an accepted CR performs the invalidation."""
    result = _working(snapshot)
    change_request_id = _id(change_request_id, "change-request-id")
    feature = _feature(result, feature_id)
    if scope not in {"product", "engineering", "delivery"}:
        raise ReducerError("invalid-change-request-scope")
    subject_field = {
        "product": "product_contract_ref",
        "engineering": "engineering_spec_ref",
        "delivery": "delivery_plan_ref",
    }[scope]
    current_subject = feature.get(subject_field)
    if not isinstance(current_subject, str):
        raise ReducerError(f"change-request-current-subject-missing:{scope}")
    subject_ref = str(_sha(subject_ref, "change-request-subject-ref"))
    if subject_ref != current_subject:
        raise ReducerError(f"change-request-subject-mismatch:{scope}")
    if not isinstance(blocking, bool):
        raise ReducerError("invalid-change-request-blocking")
    record = {
        "change_request_id": change_request_id, "feature_id": feature["feature_id"], "scope": scope,
        "subject_ref": subject_ref, "status": "open", "blocking": blocking,
        "reported_by": _id(reported_by, "change-request-reported-by"), "reported_at": _text(at, "change-request-opened-at"),
        "triaged_at": None, "accepted_by": None, "accepted_at": None,
        "applied_at": None, "resolution": None,
    }
    changes = _collection(result, "change_requests")
    current = changes.get(change_request_id)
    if current is not None and current != record:
        raise ReducerError("change-request-id-conflict")
    changes[change_request_id] = record
    if change_request_id not in feature["active_change_request_refs"]:
        feature["active_change_request_refs"].append(change_request_id)
        feature["active_change_request_refs"].sort()
    feature["updated_at"] = at
    return result


def triage_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, at: str,
) -> dict[str, object]:
    result = _working(snapshot)
    record = _change_request(result, change_request_id)
    if record["status"] != "open":
        raise ReducerError("illegal-change-request-transition")
    record["status"] = "triaged"
    record["triaged_at"] = _text(at, "change-request-triaged-at")
    return result


def accept_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, accepted_by: str, at: str,
) -> dict[str, object]:
    result = _working(snapshot)
    record = _change_request(result, change_request_id)
    if record["status"] not in {"open", "triaged"}:
        raise ReducerError("illegal-change-request-transition")
    record["status"] = "accepted"
    record["accepted_by"] = _id(accepted_by, "change-request-accepted-by")
    record["accepted_at"] = _text(at, "change-request-accepted-at")
    return result


def _resolve_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, status: str, at: str,
) -> dict[str, object]:
    result = _working(snapshot)
    record = _change_request(result, change_request_id)
    if record["status"] not in {"open", "triaged", "accepted"}:
        raise ReducerError("illegal-change-request-transition")
    if status not in {"rejected", "cancelled"}:
        raise ReducerError("invalid-change-request-resolution-status")
    resolved_at = _text(at, "change-request-resolved-at")
    feature = _feature(result, str(record["feature_id"]))
    record.update({
        "status": status,
        "accepted_by": None,
        "accepted_at": None,
        "applied_at": None,
        "resolution": None,
    })
    change_request_id = str(record["change_request_id"])
    if change_request_id in feature["active_change_request_refs"]:
        feature["active_change_request_refs"].remove(change_request_id)
    if change_request_id not in feature["resolved_change_request_refs"]:
        feature["resolved_change_request_refs"].append(change_request_id)
        feature["resolved_change_request_refs"].sort()
    feature["updated_at"] = resolved_at
    return result


def reject_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, at: str,
) -> dict[str, object]:
    """Resolve an open, triaged, or accepted ChangeRequest as rejected."""
    return _resolve_change_request(
        snapshot, change_request_id=change_request_id, status="rejected", at=at,
    )


def cancel_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, at: str,
) -> dict[str, object]:
    """Resolve an open, triaged, or accepted ChangeRequest as cancelled."""
    return _resolve_change_request(
        snapshot, change_request_id=change_request_id, status="cancelled", at=at,
    )


def _change_request(snapshot: Mapping[str, object], change_request_id: str) -> dict[str, object]:
    change_request_id = _id(change_request_id, "change-request-id")
    raw = _collection(snapshot, "change_requests").get(change_request_id)
    if not isinstance(raw, dict) or raw.get("change_request_id") != change_request_id:
        raise ReducerError("unknown-change-request")
    required = {
        "change_request_id", "feature_id", "scope", "subject_ref", "status", "blocking",
        "reported_by", "reported_at", "triaged_at", "accepted_by", "accepted_at", "applied_at", "resolution",
    }
    if set(raw) != required:
        raise ReducerError("invalid-change-request-record-fields")
    _id(raw.get("feature_id"), "change-request-feature-id")
    if raw.get("scope") not in {"product", "engineering", "delivery"}:
        raise ReducerError("invalid-change-request-scope")
    _text(raw.get("subject_ref"), "change-request-subject-ref")
    if not isinstance(raw.get("blocking"), bool):
        raise ReducerError("invalid-change-request-blocking")
    _id(raw.get("reported_by"), "change-request-reported-by")
    _text(raw.get("reported_at"), "change-request-reported-at")
    if raw.get("status") not in _CR_STATUSES:
        raise ReducerError("invalid-change-request-status")
    if raw.get("triaged_at") is not None:
        _text(raw["triaged_at"], "change-request-triaged-at")
    elif raw.get("status") == "triaged":
        raise ReducerError("triaged-change-request-missing-triaged-at")
    if raw.get("status") in {"accepted", "applied"}:
        _id(raw.get("accepted_by"), "change-request-accepted-by")
        _text(raw.get("accepted_at"), "change-request-accepted-at")
    elif raw.get("accepted_by") is not None or raw.get("accepted_at") is not None:
        raise ReducerError("unaccepted-change-request-has-acceptance")
    if raw.get("status") == "applied":
        _text(raw.get("applied_at"), "change-request-applied-at")
        if not isinstance(raw.get("resolution"), Mapping):
            raise ReducerError("applied-change-request-missing-resolution")
        if raw["scope"] == "product":
            _product_contract_adoption_resolution(raw["resolution"])
        elif raw["scope"] == "engineering":
            _engineering_replacement_resolution(raw["resolution"])
        else:
            _delivery_invalidation_resolution(raw["resolution"])
    elif raw.get("applied_at") is not None or raw.get("resolution") is not None:
        raise ReducerError("unapplied-change-request-has-resolution")
    return raw


def _require_accepted_feature_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, feature: Mapping[str, object], scope: str,
) -> dict[str, object]:
    record = _change_request(snapshot, change_request_id)
    if record["status"] != "accepted":
        raise ReducerError("change-request-must-be-accepted-before-apply")
    if record["feature_id"] != feature.get("feature_id"):
        raise ReducerError("change-request-feature-mismatch")
    if record["scope"] != scope:
        raise ReducerError("change-request-scope-mismatch")
    return record


def _complete_change_request_inplace(
    feature: dict[str, object], record: dict[str, object], *, resolution: Mapping[str, object], at: str,
) -> None:
    """Record an already-validated CR resolution after its Feature update."""
    if record.get("status") != "accepted":
        raise ReducerError("change-request-must-be-accepted-before-apply")
    if record.get("feature_id") != feature.get("feature_id"):
        raise ReducerError("change-request-feature-mismatch")
    source = _mapping(resolution, "change-request-resolution")
    if record.get("scope") == "product":
        _product_contract_adoption_resolution(source)
    elif record.get("scope") == "engineering":
        _engineering_replacement_resolution(source)
    elif record.get("scope") == "delivery":
        _delivery_invalidation_resolution(source)
    else:
        raise ReducerError("invalid-change-request-scope")
    record["status"] = "applied"
    record["applied_at"] = _text(at, "change-request-applied-at")
    record["resolution"] = deepcopy(dict(source))
    change_request_id = str(record["change_request_id"])
    if change_request_id in feature["active_change_request_refs"]:
        feature["active_change_request_refs"].remove(change_request_id)
    if change_request_id not in feature["resolved_change_request_refs"]:
        feature["resolved_change_request_refs"].append(change_request_id)
        feature["resolved_change_request_refs"].sort()


def _delivery_invalidation_resolution(value: object) -> dict[str, object]:
    source = _mapping(value, "delivery-change-request-resolution")
    required = {"resolution_kind", "resolution_ref", "semantics"}
    if set(source) != required:
        raise ReducerError("invalid-delivery-change-request-resolution-fields")
    if source.get("resolution_kind") != "delivery-invalidation-v1":
        raise ReducerError("invalid-delivery-change-request-resolution-kind")
    if source.get("semantics") != "invalidate-delivery-plan":
        raise ReducerError("invalid-delivery-change-request-resolution-semantics")
    return {
        "resolution_kind": "delivery-invalidation-v1",
        "resolution_ref": str(_sha(source.get("resolution_ref"), "delivery-change-request-resolution-ref")),
        "semantics": "invalidate-delivery-plan",
    }


def _product_contract_adoption_resolution(value: object) -> dict[str, object]:
    source = _mapping(value, "product-change-request-resolution")
    required = {"resolution_kind", "product_contract_ref", "product_contract_approval_ref", "semantics"}
    if set(source) != required:
        raise ReducerError("invalid-product-change-request-resolution-fields")
    if source.get("resolution_kind") != "product-contract-adoption-v1":
        raise ReducerError("invalid-product-change-request-resolution-kind")
    if source.get("semantics") != "adopt-feature-product-contract":
        raise ReducerError("invalid-product-change-request-resolution-semantics")
    return {
        "resolution_kind": "product-contract-adoption-v1",
        "product_contract_ref": str(_sha(source.get("product_contract_ref"), "product-change-request-contract-ref")),
        "product_contract_approval_ref": str(_sha(
            source.get("product_contract_approval_ref"), "product-change-request-contract-approval-ref",
        )),
        "semantics": "adopt-feature-product-contract",
    }


def _engineering_replacement_resolution(value: object) -> dict[str, object]:
    source = _mapping(value, "engineering-change-request-resolution")
    required = {"resolution_kind", "engineering_spec_ref", "engineering_spec_approval_ref", "semantics"}
    if set(source) != required:
        raise ReducerError("invalid-engineering-change-request-resolution-fields")
    if source.get("resolution_kind") != "engineering-spec-replacement-v1":
        raise ReducerError("invalid-engineering-change-request-resolution-kind")
    if source.get("semantics") != "replace-engineering-spec":
        raise ReducerError("invalid-engineering-change-request-resolution-semantics")
    return {
        "resolution_kind": "engineering-spec-replacement-v1",
        "engineering_spec_ref": str(_sha(source.get("engineering_spec_ref"), "engineering-change-request-spec-ref")),
        "engineering_spec_approval_ref": str(_sha(
            source.get("engineering_spec_approval_ref"), "engineering-change-request-spec-approval-ref",
        )),
        "semantics": "replace-engineering-spec",
    }


def apply_change_request(
    snapshot: Mapping[str, object], *, change_request_id: str, resolution: Mapping[str, object],
    expected_generation: int, at: str,
) -> dict[str, object]:
    """Apply a typed accepted CR with an explicit, verifiable resolution.

    Product changes use :func:`adopt_feature_product_contract`, because they
    must move the Feature's product tuple. Engineering changes name and adopt a
    replacement EngineeringSpec. Delivery changes may invalidate only the
    DeliveryPlan, but only with an explicit resolution identity and semantics.
    """
    result = _working(snapshot)
    record = _change_request(result, change_request_id)
    feature = _feature(result, str(record["feature_id"]))
    _require_generation(feature, expected_generation)
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-apply-change-request-to-terminal-feature")
    if record["status"] != "accepted":
        raise ReducerError("change-request-must-be-accepted-before-apply")
    at = _text(at, "change-request-applied-at")
    reason = f"change-request-applied:{change_request_id}"

    if record["scope"] == "product":
        raise ReducerError("product-change-request-requires-feature-product-contract-adoption")
    if record["scope"] == "delivery":
        parsed_resolution = _delivery_invalidation_resolution(resolution)
        if feature["delivery_plan_ref"] is None or record["subject_ref"] != feature["delivery_plan_ref"]:
            raise ReducerError("delivery-change-request-subject-mismatch")
        _invalidate_delivery_inplace(result, str(feature["feature_id"]), reason=reason, at=at)
        updated = _feature(result, str(feature["feature_id"]))
        _complete_change_request_inplace(updated, record, resolution=parsed_resolution, at=at)
        return result

    if record["scope"] == "engineering":
        parsed_resolution = _engineering_replacement_resolution(resolution)
        if feature["engineering_spec_ref"] is None or record["subject_ref"] != feature["engineering_spec_ref"]:
            raise ReducerError("engineering-change-request-subject-mismatch")
        if parsed_resolution["engineering_spec_ref"] == feature["engineering_spec_ref"]:
            raise ReducerError("engineering-change-request-requires-replacement-spec")
        previous_generation = _generation(feature["contract_generation"])
        # ``adopt_engineering_spec`` validates the replacement's product,
        # profile, and effective-approval tuples. Both operations are pure, so
        # a failed candidate leaves the caller's snapshot unchanged.
        _invalidate_feature_inplace(result, str(feature["feature_id"]), reason=reason, at=at)
        result = adopt_engineering_spec(
            result,
            feature_id=str(feature["feature_id"]),
            engineering_spec_ref=str(parsed_resolution["engineering_spec_ref"]),
            engineering_spec_approval_ref=str(parsed_resolution["engineering_spec_approval_ref"]),
            expected_generation=previous_generation + 1,
            at=at,
        )
        updated = _feature(result, str(feature["feature_id"]))
        updated_record = _change_request(result, change_request_id)
        _complete_change_request_inplace(updated, updated_record, resolution=parsed_resolution, at=at)
        return result

    raise ReducerError("invalid-change-request-scope")


def invalidate_feature(
    snapshot: Mapping[str, object], *, feature_id: str, reason: str, at: str,
) -> dict[str, object]:
    """Explicitly invalidate downstream engineering/plan work for one Feature."""
    result = _working(snapshot)
    _invalidate_feature_inplace(result, feature_id, reason=reason, at=at)
    return result


def _invalidate_delivery_inplace(
    snapshot: Mapping[str, object], feature_id: str, *, reason: str, at: str,
) -> None:
    """Supersede only the current DeliveryPlan while retaining its EngineeringSpec."""
    feature = _feature(snapshot, feature_id)
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-invalidate-terminal-feature")
    if feature["delivery_plan_ref"] is None:
        raise ReducerError("cannot-invalidate-missing-delivery-plan")
    at = _text(at, "delivery-invalidated-at")
    _text(reason, "invalidation-reason")
    for task in _current_tasks(snapshot, feature):
        if task.get("status") not in _TASK_TERMINAL:
            task["status"] = "superseded"
            task["updated_at"] = at
            task["superseded_reason"] = reason
    feature.update({
        "contract_generation": _generation(feature["contract_generation"]) + 1,
        "delivery_plan_ref": None,
        "validation_status": "pending",
        "review_status": "pending",
        "review_attestation_ref": None,
        "status": "active" if feature["status"] == "validated" else feature["status"],
        "updated_at": at,
    })
    if reason not in feature["invalidation_reasons"]:
        # Evidence and superseded Task records remain historical artifacts;
        # clearing the current plan/generation removes them from current work.
        feature["invalidation_reasons"].append(reason)
        feature["invalidation_reasons"].sort()


def _invalidate_feature_inplace(
    snapshot: Mapping[str, object], feature_id: str, *, reason: str, at: str,
    product_tuple: Mapping[str, object] | None = None,
) -> None:
    feature = _feature(snapshot, feature_id)
    if feature["status"] in {"shipped", "abandoned"}:
        raise ReducerError("cannot-invalidate-terminal-feature")
    at = _text(at, "feature-invalidated-at")
    _text(reason, "invalidation-reason")
    if product_tuple is not None:
        required = {"product_contract_ref", "product_contract_revision", "product_contract_approval_ref"}
        if set(product_tuple) != required:
            raise ReducerError("invalid-product-invalidation-tuple")
        for field in required:
            _sha(product_tuple[field], field)
        feature.update({field: product_tuple[field] for field in required})
    old_generation = _generation(feature["contract_generation"])
    for task in _current_tasks(snapshot, feature):
        if task.get("status") not in _TASK_TERMINAL:
            task["status"] = "superseded"
            task["updated_at"] = at
            task["superseded_reason"] = reason
    feature.update({
        "contract_generation": old_generation + 1,
        "engineering_spec_ref": None,
        "engineering_spec_approval_ref": None,
        "profile_ref": None,
        "profile_revision": None,
        "profile_sha256": None,
        "engineering_base_sha": None,
        "delivery_plan_ref": None,
        "validation_status": "pending",
        "review_status": "pending",
        "review_attestation_ref": None,
        "status": "active" if feature["status"] == "validated" else feature["status"],
        "updated_at": at,
    })
    if reason not in feature["invalidation_reasons"]:
        # This is an audit marker, not a mutation of historical Evidence.
        feature["invalidation_reasons"].append(reason)
        feature["invalidation_reasons"].sort()


def _revoke_product_contract_inplace(snapshot: Mapping[str, object], contract_id: str, *, at: str, reason: str) -> None:
    for raw_definition in _collection(snapshot, "product_definitions").values():
        if not isinstance(raw_definition, dict) or raw_definition.get("current_contract_ref") != contract_id:
            continue
        raw_definition["definition_status"] = "unapproved"
        raw_definition["current_approval_ref"] = None
        raw_definition["updated_at"] = at
    for feature_id, feature in list(_collection(snapshot, "features").items()):
        if isinstance(feature, Mapping) and feature.get("product_contract_ref") == contract_id:
            _invalidate_feature_inplace(snapshot, feature_id, reason=reason, at=at)
            current = _feature(snapshot, feature_id)
            current["product_contract_approval_ref"] = None


def _revoke_engineering_spec_inplace(snapshot: Mapping[str, object], spec_id: str, *, at: str, reason: str) -> None:
    for feature_id, feature in list(_collection(snapshot, "features").items()):
        if isinstance(feature, Mapping) and feature.get("engineering_spec_ref") == spec_id:
            _invalidate_feature_inplace(snapshot, feature_id, reason=reason, at=at)


def project_delivery_status(snapshot: Mapping[str, object], *, leaf_id: str) -> dict[str, object]:
    """Return a detached product-facing delivery projection without engineering internals."""
    validate_snapshot(snapshot)
    definition = _definition(snapshot, leaf_id)
    features: list[dict[str, object]] = []
    for feature_id in _all_feature_ids_for_leaf(snapshot, str(definition["leaf_id"])):
        feature = _feature(snapshot, feature_id)
        tasks = _current_tasks(snapshot, feature)
        counts: dict[str, int] = {}
        for task in tasks:
            status = str(task["status"])
            counts[status] = counts.get(status, 0) + 1
        if feature["status"] == "shipped":
            delivery_state = "shipped"
        elif feature["status"] == "validated":
            delivery_state = "validated"
        elif feature["delivery_plan_ref"] is None:
            delivery_state = "not_started"
        elif tasks and all(task["status"] == "verified" for task in tasks):
            delivery_state = "ready_for_validation"
        else:
            delivery_state = "in_progress"
        features.append({
            "feature_id": feature["feature_id"],
            "status": feature["status"],
            "contract_generation": feature["contract_generation"],
            "delivery_state": delivery_state,
            "validation_status": feature["validation_status"],
            "review_status": feature["review_status"],
            "task_counts": dict(sorted(counts.items())),
            "active_change_request_refs": list(feature["active_change_request_refs"]),
        })
    return deepcopy({
        "leaf_id": definition["leaf_id"],
        "definition_status": definition["definition_status"],
        "product_contract_ref": definition["current_contract_ref"],
        "product_contract_approval_ref": definition["current_approval_ref"],
        "features": features,
    })


def project_feature_status(snapshot: Mapping[str, object], *, feature_id: str) -> dict[str, object]:
    """Return the minimal detached engineering context for one Feature."""
    validate_snapshot(snapshot)
    feature = _feature(snapshot, feature_id)
    tasks = [
        {
            "task_id": deepcopy(task.get("task_id")),
            "status": deepcopy(task.get("status")),
            "depends_on": deepcopy(task.get("depends_on")),
            "execution_mode": deepcopy(task.get("execution_mode")),
            "evidence_strategy": deepcopy(task.get("evidence_strategy")),
            "trace_refs": deepcopy(task.get("trace_refs")),
            "evidence_refs": deepcopy(task.get("evidence_refs")),
        }
        for task in _current_tasks(snapshot, feature)
    ]
    return {
        "feature_id": feature["feature_id"],
        "leaf_id": feature["leaf_id"],
        "work_type": feature["work_type"],
        "status": feature["status"],
        "validation_status": feature["validation_status"],
        "review_status": feature["review_status"],
        "review_attestation_ref": feature["review_attestation_ref"],
        "review_evidence_refs": _current_feature_passing_evidence_refs(
            snapshot, feature, require_nonempty=False,
        ),
        "current_fence": _feature_fence(feature),
        "active_change_request_refs": deepcopy(feature["active_change_request_refs"]),
        "resolved_change_request_refs": deepcopy(feature["resolved_change_request_refs"]),
        "release_evidence_ref": feature["release_evidence_ref"],
        "tasks": tasks,
    }


def reduce(snapshot: Mapping[str, object], intent: Mapping[str, object]) -> dict[str, object]:
    """Dispatch one serializable lifecycle intent to its pure reducer function.

    This is intentionally a thin transport adapter: persistence code supplies a
    snapshot, performs a compare-and-swap around the returned snapshot, and
    never needs to duplicate lifecycle transition rules.  Direct named APIs
    remain preferable inside Python code because their signatures are clearer.
    """
    source = _mapping(intent, "lifecycle-intent")
    operation = _id(source.get("operation"), "lifecycle-operation")
    handlers = {
        "register_requirement": register_requirement,
        "create_product_definition": create_product_definition,
        "start_product_definition": start_product_definition,
        "withdraw_product_definition": withdraw_product_definition,
        "reopen_product_definition": reopen_product_definition,
        "register_product_contract": register_product_contract,
        "submit_product_contract": submit_product_contract,
        "apply_approval": apply_approval,
        "adopt_product_contract": adopt_product_contract,
        "adopt_feature_product_contract": adopt_feature_product_contract,
        "claim_feature": claim_feature,
        "register_profile_snapshot": register_profile_snapshot,
        "register_engineering_spec": register_engineering_spec,
        "adopt_engineering_spec": adopt_engineering_spec,
        "activate_delivery_plan": activate_delivery_plan,
        "transition_task": transition_task,
        "record_evidence": record_evidence,
        "validate_feature": validate_feature,
        "review_feature": review_feature,
        "ship_feature": ship_feature,
        "open_change_request": open_change_request,
        "triage_change_request": triage_change_request,
        "accept_change_request": accept_change_request,
        "reject_change_request": reject_change_request,
        "cancel_change_request": cancel_change_request,
        "apply_change_request": apply_change_request,
        "invalidate_feature": invalidate_feature,
    }
    handler = handlers.get(operation)
    if handler is None:
        raise ReducerError("unknown-lifecycle-operation")
    payload = {key: value for key, value in source.items() if key != "operation"}
    try:
        return handler(snapshot, **payload)  # type: ignore[misc, no-any-return]
    except TypeError as exc:
        raise ReducerError(f"invalid-lifecycle-intent:{operation}") from exc


__all__ = [
    "CAPABILITY", "FENCE_FIELDS", "ReducerError", "SCHEMA_VERSION", "SNAPSHOT_FORMAT",
    "accept_change_request", "activate_delivery_plan", "adopt_engineering_spec", "adopt_feature_product_contract",
    "adopt_product_contract",
    "apply_approval", "apply_change_request", "approval_subject", "cancel_change_request", "claim_feature",
    "create_product_definition",
    "current_fence", "empty_snapshot", "invalidate_feature", "open_change_request", "product_readiness",
    "project_delivery_status", "project_feature_status", "record_evidence", "register_engineering_spec", "register_product_contract",
    "register_profile_snapshot", "register_requirement", "reopen_product_definition", "review_feature",
    "reduce", "reject_change_request", "ship_feature", "start_product_definition", "submit_product_contract",
    "transition_task", "triage_change_request",
    "validate_feature", "validate_snapshot", "withdraw_product_definition",
]
