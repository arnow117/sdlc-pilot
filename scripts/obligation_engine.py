#!/usr/bin/env python3
"""Immutable preview ObligationManifests and run-local expected-head CAS.

Phase 1 deliberately keeps this runtime outside the control ledger.  Its only
write target is ``<repo>/.sdlc/preview/<run-id>/obligations``.  A manifest is
content-addressed and immutable; ``HEAD.json`` is the sole mutable pointer and
is updated under an expected-head compare-and-swap operation.

This module validates mechanical structure only.  A typed attestation records
an accountable role's semantic conclusion, but never converts caller supplied
``approved`` / ``tests_passed`` / ``review_complete`` claims into facts.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterator, Mapping, Sequence

try:  # The preview runtime is POSIX file-backed, matching the surrounding control runtime.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on unsupported runtimes.
    fcntl = None  # type: ignore[assignment]


OBLIGATION_MANIFEST_SCHEMA = "sdlc-obligation-manifest-v1"
OBLIGATION_HEAD_SCHEMA = "sdlc-obligation-head-v1"
CONTEXT_MANIFEST_SCHEMA = "sdlc-context-manifest-v1"
POLICY_MANIFEST_SCHEMA = "sdlc-policy-manifest-v1"
ATTESTATION_SCHEMA = "sdlc-typed-attestation-v1"
OVERRIDE_SCHEMA = "sdlc-typed-override-v1"
PREVIEW_SCOPE = "preview"
VALID_STATUSES = frozenset({"selected", "completed", "explicitly_skipped"})
FRESH = "fresh"
STALE = "stale"

# These represent facts that a semantic override cannot replace.  The override
# schema only permits ``conditional_skip``; retaining the explicit set makes
# the policy boundary inspectable and gives callers a deterministic failure.
NON_OVERRIDABLE_INVARIANTS = frozenset({
    "approval_authenticity",
    "contract_identity",
    "context_freshness",
    "evidence_freshness",
    "evidence_hash",
    "policy_identity",
})
SELF_REPORTED_FACT_FIELDS = frozenset({
    "approved",
    "review_complete",
    "security_complete",
    "tests_passed",
})

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MANIFEST_KEYS = frozenset({
    "schema_version",
    "scope",
    "obligation_manifest_id",
    "lifecycle_run_id",
    "revision",
    "previous_ref",
    "context_manifest_ref",
    "context_input_sha256",
    "policy_manifest_ref",
    "phase_contract_ref",
    "lifecycle",
    "operation",
    "compatibility_adapter",
    "needs_classification",
    "freshness_binding",
    "freshness_binding_sha256",
    "obligation_templates",
    "obligations",
    "legacy_approval_observations",
})
_HEAD_KEYS = frozenset({
    "schema_version",
    "scope",
    "lifecycle_run_id",
    "head_ref",
    "context_manifest_ref",
    "revision",
    "updated_at",
})
_TEMPLATE_KEYS = frozenset({
    "obligation_id",
    "role",
    "responsibility",
    "participation",
    "selection_rule_id",
    "min_actors",
    "max_actors",
    "independence_constraints",
    "playbook_ref",
    "completion_assertion_ids",
    "requires_typed_attestation",
    "attestation_types",
    "skip_policy",
})
_ITEM_KEYS = _TEMPLATE_KEYS | frozenset({
    "required",
    "active",
    "status",
    "evidence_refs",
    "attestation_ref",
    "attestation",
    "completed_by",
    "completed_binding_sha256",
    "skip_reason",
    "selector_proof",
    "override_ref",
    "override",
    "superseded_by_context_ref",
})
_ATTESTATION_KEYS = frozenset({
    "schema_version",
    "scope",
    "subject_ref",
    "obligation_id",
    "role",
    "actor",
    "verdict",
    "attestation_type",
    "evidence_refs",
    "rationale_ref",
    "policy_manifest_ref",
    "context_manifest_ref",
    "created_at",
})
_OVERRIDE_KEYS = frozenset({
    "schema_version",
    "scope",
    "override_kind",
    "obligation_id",
    "role",
    "actor",
    "rule_id",
    "policy_manifest_ref",
    "context_manifest_ref",
    "reason_ref",
    "replacement_evidence_refs",
    "expires_at",
    "authorization_ref",
})
_LEGACY_OBSERVATION_KEYS = frozenset({"kind", "scope", "legacy_spec_sha256"})


class ObligationError(RuntimeError):
    """An ObligationManifest or preview action is not valid."""


class ObligationConflict(ObligationError):
    """The observed preview ObligationHead no longer matches expected state."""


def canonical_bytes(value: object) -> bytes:
    """Return the one deterministic JSON representation used for all IDs."""
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ObligationError("non-canonical-json-value") from exc
    return (rendered + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _clone(value: object) -> Any:
    return json.loads(canonical_bytes(value).decode("utf-8"))


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ObligationError(f"invalid-{label}")
    return value


def _require_exact_mapping(value: object, keys: frozenset[str], label: str) -> Mapping[str, object]:
    mapping = _require_mapping(value, label)
    if set(mapping) != keys:
        raise ObligationError(f"invalid-{label}-keys")
    return mapping


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value:
        raise ObligationError(f"invalid-{label}")
    return value


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or ".." in value:
        raise ObligationError(f"invalid-{label}")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ObligationError(f"invalid-{label}")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ObligationError(f"invalid-{label}")
    return value


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ObligationError(f"invalid-{label}")
    return value


def _require_ref(value: object, label: str) -> str:
    return _require_text(value, label)


def _normalize_refs(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ObligationError(f"invalid-{label}")
    refs = [_require_ref(item, f"{label}-item") for item in value]
    if len(set(refs)) != len(refs):
        raise ObligationError(f"duplicate-{label}")
    return sorted(refs)


def _normalize_ids(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ObligationError(f"invalid-{label}")
    ids = [_require_id(item, f"{label}-item") for item in value]
    if len(set(ids)) != len(ids):
        raise ObligationError(f"duplicate-{label}")
    return sorted(ids)


def _normalize_json(value: object, label: str, *, depth: int = 0) -> object:
    if depth > 32:
        raise ObligationError(f"{label}-too-deep")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ObligationError(f"invalid-{label}-number")
        return value
    if isinstance(value, list):
        return [_normalize_json(item, label, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key in sorted(value):
            if not isinstance(key, str) or not key:
                raise ObligationError(f"invalid-{label}-key")
            normalized[key] = _normalize_json(value[key], label, depth=depth + 1)
        return normalized
    raise ObligationError(f"invalid-{label}")


def _assert_no_self_report(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key in SELF_REPORTED_FACT_FIELDS:
                raise ObligationError(f"self-reported-fact:{key}")
            _assert_no_self_report(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_self_report(item)


def _parse_phase_ref(value: object, label: str) -> tuple[str, str]:
    ref = _require_text(value, label)
    if ref.count("#") != 1:
        raise ObligationError(f"invalid-{label}")
    policy_id, phase_id = ref.split("#", 1)
    return _require_sha256(policy_id, f"{label}-policy"), _require_id(phase_id, f"{label}-phase")


def _parse_timestamp(value: object, label: str) -> datetime:
    text = _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ObligationError(f"invalid-{label}") from exc
    if parsed.tzinfo is None:
        raise ObligationError(f"invalid-{label}")
    return parsed


def _validate_context(context: Mapping[str, object]) -> dict[str, object]:
    source = _require_mapping(context, "context-manifest")
    required = {
        "schema_version", "scope", "activation", "context_manifest_id", "context_input_sha256",
        "policy_manifest_id", "phase_contract_ref", "lifecycle_run_id", "lifecycle", "operation",
        "contracts", "profile", "diff", "selected_obligation_ids", "skipped_obligations",
        "classification_requests", "needs_classification",
    }
    if not required.issubset(source):
        raise ObligationError("incomplete-context-manifest")
    if source["schema_version"] != CONTEXT_MANIFEST_SCHEMA or source["scope"] != PREVIEW_SCOPE:
        raise ObligationError("preview-context-required")
    activation = _require_mapping(source["activation"], "context-activation")
    if activation.get("scope") != PREVIEW_SCOPE or activation.get("control_mutations") is not False:
        raise ObligationError("preview-context-activation-required")
    policy_id = _require_sha256(source["policy_manifest_id"], "context-policy-manifest-id")
    phase_policy_id, phase_id = _parse_phase_ref(source["phase_contract_ref"], "context-phase-contract-ref")
    if policy_id != phase_policy_id:
        raise ObligationError("context-policy-phase-mismatch")
    selected = _normalize_ids(source["selected_obligation_ids"], "context-selected-obligations", allow_empty=True)
    skipped_source = source["skipped_obligations"]
    if not isinstance(skipped_source, list):
        raise ObligationError("invalid-context-skipped-obligations")
    skipped: list[dict[str, object]] = []
    for raw in skipped_source:
        item = _require_exact_mapping(raw, frozenset({"id", "selector_proof"}), "context-skipped-obligation")
        obligation_id = _require_id(item["id"], "context-skipped-obligation-id")
        proof = _require_exact_mapping(
            item["selector_proof"], frozenset({"rule_id", "result"}), "context-selector-proof")
        skipped.append({
            "id": obligation_id,
            "selector_proof": {
                "rule_id": _require_id(proof["rule_id"], "context-selector-proof-rule"),
                "result": "false" if proof["result"] == "false" else _invalid("context-selector-proof-result"),
            },
        })
    skipped.sort(key=lambda item: str(item["id"]))
    skipped_ids = [str(item["id"]) for item in skipped]
    if len(set(skipped_ids)) != len(skipped_ids) or set(selected) & set(skipped_ids):
        raise ObligationError("ambiguous-context-obligation-selection")
    contracts = _normalize_json(_require_mapping(source["contracts"], "context-contracts"), "context-contracts")
    profile = _normalize_json(_require_mapping(source["profile"], "context-profile"), "context-profile")
    diff = _normalize_json(_require_mapping(source["diff"], "context-diff"), "context-diff")
    return {
        "context_manifest_id": _require_sha256(source["context_manifest_id"], "context-manifest-id"),
        "context_input_sha256": _require_sha256(source["context_input_sha256"], "context-input-sha256"),
        "policy_manifest_id": policy_id,
        "phase_contract_ref": f"{phase_policy_id}#{phase_id}",
        "phase_id": phase_id,
        "lifecycle_run_id": _require_id(source["lifecycle_run_id"], "context-lifecycle-run-id"),
        "lifecycle": _require_text(source["lifecycle"], "context-lifecycle"),
        "operation": _require_text(source["operation"], "context-operation"),
        "contracts": contracts,
        "profile": profile,
        "diff": diff,
        "selected_obligation_ids": selected,
        "skipped_obligations": skipped,
        "needs_classification": _require_bool(source["needs_classification"], "context-needs-classification"),
    }


def _invalid(label: str) -> object:
    raise ObligationError(f"invalid-{label}")


def _policy_phase(context: Mapping[str, object], policy_manifest: Mapping[str, object]) -> Mapping[str, object]:
    policy = _require_mapping(policy_manifest, "policy-manifest")
    if policy.get("schema_version") != POLICY_MANIFEST_SCHEMA:
        raise ObligationError("unsupported-policy-manifest")
    if _require_sha256(policy.get("policy_manifest_id"), "policy-manifest-id") != context["policy_manifest_id"]:
        raise ObligationError("context-policy-manifest-mismatch")
    activation = _require_mapping(policy.get("activation"), "policy-activation")
    if (activation.get("scope") != PREVIEW_SCOPE or activation.get("control_mutations") is not False
            or activation.get("output_scope") != PREVIEW_SCOPE):
        raise ObligationError("preview-policy-required")
    phases = policy.get("phases")
    if not isinstance(phases, list):
        raise ObligationError("invalid-policy-phases")
    phase_id = context["phase_id"]
    matches = [
        _require_mapping(phase, "policy-phase") for phase in phases
        if isinstance(phase, Mapping) and phase.get("id") == phase_id
    ]
    if len(matches) != 1:
        raise ObligationError(f"unknown-policy-phase:{phase_id}")
    phase = matches[0]
    if phase.get("phase_contract_ref") != context["phase_contract_ref"]:
        raise ObligationError("policy-phase-contract-mismatch")
    if phase.get("lifecycle") != context["lifecycle"] or phase.get("stage") != context["operation"]:
        raise ObligationError("context-phase-lifecycle-mismatch")
    return phase


def _roles_by_id(policy_manifest: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw_roles = _require_mapping(policy_manifest, "policy-manifest").get("roles")
    if not isinstance(raw_roles, list):
        raise ObligationError("invalid-policy-roles")
    roles: dict[str, Mapping[str, object]] = {}
    for raw in raw_roles:
        role = _require_mapping(raw, "policy-role")
        role_id = _require_id(role.get("id"), "policy-role-id")
        if role_id in roles:
            raise ObligationError(f"duplicate-policy-role:{role_id}")
        roles[role_id] = role
    return roles


def _template_from_policy(
    raw: Mapping[str, object],
    assertions_by_id: Mapping[str, Mapping[str, object]],
    semantic_attestation_types: Sequence[str],
    roles: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    obligation_id = _require_id(raw.get("id"), "policy-obligation-id")
    role_id = _require_id(raw.get("role_id"), f"policy-obligation-role:{obligation_id}")
    role = roles.get(role_id)
    if role is None:
        raise ObligationError(f"unknown-policy-obligation-role:{obligation_id}")
    participation = _require_text(raw.get("participation"), f"policy-obligation-participation:{obligation_id}")
    if participation not in {"required", "conditional"}:
        raise ObligationError(f"invalid-policy-obligation-participation:{obligation_id}")
    selection_rule = _require_id(raw.get("required_when_rule_id"), f"policy-obligation-rule:{obligation_id}")
    min_actors = _require_positive_int(raw.get("min_actors"), f"policy-obligation-min-actors:{obligation_id}")
    max_actors = _require_positive_int(raw.get("max_actors"), f"policy-obligation-max-actors:{obligation_id}")
    if min_actors > max_actors:
        raise ObligationError(f"invalid-policy-obligation-actor-range:{obligation_id}")
    constraint_ids = _normalize_ids(
        raw.get("independence_constraint_ids"), f"policy-obligation-independence:{obligation_id}", allow_empty=True)
    raw_constraints = role.get("independence_constraints")
    if not isinstance(raw_constraints, list):
        raise ObligationError(f"invalid-policy-role-constraints:{role_id}")
    all_constraints: dict[str, dict[str, object]] = {}
    for raw_constraint in raw_constraints:
        constraint = _require_mapping(raw_constraint, "policy-independence-constraint")
        constraint_id = _require_id(constraint.get("id"), "policy-independence-constraint-id")
        mode = _require_text(constraint.get("mode"), f"policy-independence-mode:{constraint_id}")
        against = _normalize_ids(
            constraint.get("against_role_ids"), f"policy-independence-against:{constraint_id}")
        all_constraints[constraint_id] = {
            "id": constraint_id,
            "mode": mode,
            "against_role_ids": against,
        }
    if any(constraint_id not in all_constraints for constraint_id in constraint_ids):
        raise ObligationError(f"unknown-policy-obligation-independence:{obligation_id}")
    playbook_ref = _require_mapping(raw.get("playbook_ref"), f"policy-obligation-playbook:{obligation_id}")
    playbook = {
        "module_id": _require_id(playbook_ref.get("module_id"), f"policy-obligation-module:{obligation_id}"),
        "anchor": _require_ref(playbook_ref.get("anchor"), f"policy-obligation-anchor:{obligation_id}"),
    }
    assertion_ids = _normalize_ids(raw.get("completion_assertion_ids"), f"policy-obligation-assertions:{obligation_id}")
    if any(assertion_id not in assertions_by_id for assertion_id in assertion_ids):
        raise ObligationError(f"unknown-policy-obligation-assertion:{obligation_id}")
    skip_policy = _require_mapping(raw.get("skip_policy"), f"policy-obligation-skip-policy:{obligation_id}")
    mode = _require_text(skip_policy.get("mode"), f"policy-obligation-skip-mode:{obligation_id}")
    allowed_when = skip_policy.get("allowed_when_rule_id")
    override_policy = _require_text(skip_policy.get("override_policy"), f"policy-obligation-override-policy:{obligation_id}")
    if participation == "required":
        if mode != "forbidden" or allowed_when is not None or override_policy != "none":
            raise ObligationError(f"required-obligation-cannot-skip:{obligation_id}")
        normalized_skip = {"mode": "forbidden", "allowed_when_rule_id": None, "override_policy": "none"}
    else:
        if mode != "selector_false_or_typed_override" or override_policy != "typed-override-v1":
            raise ObligationError(f"invalid-conditional-skip-policy:{obligation_id}")
        normalized_skip = {
            "mode": mode,
            "allowed_when_rule_id": _require_id(allowed_when, f"policy-obligation-skip-rule:{obligation_id}"),
            "override_policy": override_policy,
        }
    requires_attestation = any(assertions_by_id[assertion_id].get("kind") == "semantic" for assertion_id in assertion_ids)
    if requires_attestation and not semantic_attestation_types:
        raise ObligationError(f"semantic-obligation-missing-attestation-type:{obligation_id}")
    return {
        "obligation_id": obligation_id,
        "role": role_id,
        "responsibility": _require_text(raw.get("responsibility"), f"policy-obligation-responsibility:{obligation_id}"),
        "participation": participation,
        "selection_rule_id": selection_rule,
        "min_actors": min_actors,
        "max_actors": max_actors,
        "independence_constraints": [all_constraints[constraint_id] for constraint_id in constraint_ids],
        "playbook_ref": playbook,
        "completion_assertion_ids": assertion_ids,
        "requires_typed_attestation": requires_attestation,
        "attestation_types": sorted(semantic_attestation_types),
        "skip_policy": normalized_skip,
    }


def _templates_for_context(context: Mapping[str, object], policy_manifest: Mapping[str, object]) -> tuple[list[dict[str, object]], str | None]:
    phase = _policy_phase(context, policy_manifest)
    assertions = phase.get("completion_assertions")
    if not isinstance(assertions, list):
        raise ObligationError("invalid-policy-phase-assertions")
    assertions_by_id: dict[str, Mapping[str, object]] = {}
    for raw in assertions:
        assertion = _require_mapping(raw, "policy-assertion")
        assertion_id = _require_id(assertion.get("id"), "policy-assertion-id")
        if assertion_id in assertions_by_id:
            raise ObligationError(f"duplicate-policy-assertion:{assertion_id}")
        assertions_by_id[assertion_id] = assertion
    semantic_types = _normalize_ids(
        phase.get("semantic_attestation_types"), "policy-semantic-attestation-types", allow_empty=True)
    obligations = phase.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        raise ObligationError("invalid-policy-phase-obligations")
    roles = _roles_by_id(policy_manifest)
    templates = [_template_from_policy(_require_mapping(raw, "policy-obligation"), assertions_by_id, semantic_types, roles)
                 for raw in obligations]
    templates.sort(key=lambda item: str(item["obligation_id"]))
    if len({item["obligation_id"] for item in templates}) != len(templates):
        raise ObligationError("duplicate-policy-obligation")
    adapter = phase.get("compatibility_adapter")
    if adapter is not None:
        adapter = _require_text(adapter, "policy-compatibility-adapter")
    return templates, adapter


def _freshness_binding(context: Mapping[str, object]) -> dict[str, object]:
    return {
        "context_input_sha256": context["context_input_sha256"],
        "policy_manifest_ref": context["policy_manifest_id"],
        "phase_contract_ref": context["phase_contract_ref"],
        "contracts": context["contracts"],
        "profile": context["profile"],
        "diff": context["diff"],
    }


def _item_from_template(
    template: Mapping[str, object],
    *,
    selected: bool,
    selector_proof: Mapping[str, object] | None = None,
) -> dict[str, object]:
    item = _clone(template)
    assert isinstance(item, dict)
    if selected:
        item.update({
            "required": True,
            "active": True,
            "status": "selected",
            "evidence_refs": [],
            "attestation_ref": None,
            "attestation": None,
            "completed_by": None,
            "completed_binding_sha256": None,
            "skip_reason": None,
            "selector_proof": None,
            "override_ref": None,
            "override": None,
            "superseded_by_context_ref": None,
        })
    else:
        if selector_proof is None:
            raise ObligationError(f"missing-selector-proof:{item['obligation_id']}")
        item.update({
            "required": False,
            "active": False,
            "status": "explicitly_skipped",
            "evidence_refs": [],
            "attestation_ref": None,
            "attestation": None,
            "completed_by": None,
            "completed_binding_sha256": None,
            "skip_reason": "selector_false",
            "selector_proof": _clone(selector_proof),
            "override_ref": None,
            "override": None,
            "superseded_by_context_ref": None,
        })
    return item


def _manifest_preimage(manifest: Mapping[str, object]) -> dict[str, object]:
    preimage = _clone(manifest)
    assert isinstance(preimage, dict)
    preimage.pop("obligation_manifest_id", None)
    return preimage


def _seal_manifest(preimage: Mapping[str, object]) -> dict[str, object]:
    manifest = _clone(preimage)
    assert isinstance(manifest, dict)
    manifest.pop("obligation_manifest_id", None)
    manifest["obligation_manifest_id"] = sha256_bytes(canonical_bytes(manifest))
    return manifest


def create_obligation_manifest(
    context_manifest: Mapping[str, object],
    policy_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Create revision 1 from a resolver-produced preview ContextManifest.

    The policy is read only to build a compact per-phase template catalog.  That
    catalog is sealed into the manifest so later ``reconcile`` calls require no
    policy re-read and cannot silently adopt a different policy revision.
    """
    context = _validate_context(context_manifest)
    templates, adapter = _templates_for_context(context, policy_manifest)
    template_ids = {str(template["obligation_id"]) for template in templates}
    selected = set(context["selected_obligation_ids"])
    skipped_by_id = {str(item["id"]): item for item in context["skipped_obligations"]}
    if selected | set(skipped_by_id) != template_ids:
        raise ObligationError("context-does-not-cover-phase-obligations")
    items = [
        _item_from_template(
            template,
            selected=str(template["obligation_id"]) in selected,
            selector_proof=skipped_by_id.get(str(template["obligation_id"]), {}).get("selector_proof"),
        )
        for template in templates
    ]
    binding = _freshness_binding(context)
    manifest = _seal_manifest({
        "schema_version": OBLIGATION_MANIFEST_SCHEMA,
        "scope": PREVIEW_SCOPE,
        "lifecycle_run_id": context["lifecycle_run_id"],
        "revision": 1,
        "previous_ref": None,
        "context_manifest_ref": context["context_manifest_id"],
        "context_input_sha256": context["context_input_sha256"],
        "policy_manifest_ref": context["policy_manifest_id"],
        "phase_contract_ref": context["phase_contract_ref"],
        "lifecycle": context["lifecycle"],
        "operation": context["operation"],
        "compatibility_adapter": adapter,
        "needs_classification": context["needs_classification"],
        "freshness_binding": binding,
        "freshness_binding_sha256": sha256_bytes(canonical_bytes(binding)),
        "obligation_templates": templates,
        "obligations": items,
        "legacy_approval_observations": [],
    })
    return validate_manifest(manifest)


def _validate_template(value: object) -> dict[str, object]:
    template = _require_exact_mapping(value, _TEMPLATE_KEYS, "obligation-template")
    obligation_id = _require_id(template["obligation_id"], "template-obligation-id")
    participation = _require_text(template["participation"], f"template-participation:{obligation_id}")
    if participation not in {"required", "conditional"}:
        raise ObligationError(f"invalid-template-participation:{obligation_id}")
    min_actors = _require_positive_int(template["min_actors"], f"template-min-actors:{obligation_id}")
    max_actors = _require_positive_int(template["max_actors"], f"template-max-actors:{obligation_id}")
    if min_actors > max_actors:
        raise ObligationError(f"invalid-template-actor-range:{obligation_id}")
    raw_constraints = template["independence_constraints"]
    if not isinstance(raw_constraints, list):
        raise ObligationError(f"invalid-template-independence:{obligation_id}")
    constraints: list[dict[str, object]] = []
    for raw in raw_constraints:
        constraint = _require_exact_mapping(
            raw, frozenset({"id", "mode", "against_role_ids"}), "template-independence-constraint")
        constraints.append({
            "id": _require_id(constraint["id"], "template-independence-id"),
            "mode": _require_text(constraint["mode"], "template-independence-mode"),
            "against_role_ids": _normalize_ids(constraint["against_role_ids"], "template-independence-against"),
        })
    if len({item["id"] for item in constraints}) != len(constraints):
        raise ObligationError(f"duplicate-template-independence:{obligation_id}")
    playbook = _require_exact_mapping(template["playbook_ref"], frozenset({"module_id", "anchor"}), "template-playbook")
    skip_policy = _require_exact_mapping(
        template["skip_policy"], frozenset({"mode", "allowed_when_rule_id", "override_policy"}), "template-skip-policy")
    mode = _require_text(skip_policy["mode"], f"template-skip-mode:{obligation_id}")
    if participation == "required":
        if mode != "forbidden" or skip_policy["allowed_when_rule_id"] is not None or skip_policy["override_policy"] != "none":
            raise ObligationError(f"required-obligation-cannot-skip:{obligation_id}")
        normalized_skip = {"mode": "forbidden", "allowed_when_rule_id": None, "override_policy": "none"}
    else:
        if mode != "selector_false_or_typed_override" or skip_policy["override_policy"] != "typed-override-v1":
            raise ObligationError(f"invalid-conditional-skip-policy:{obligation_id}")
        normalized_skip = {
            "mode": mode,
            "allowed_when_rule_id": _require_id(skip_policy["allowed_when_rule_id"], "template-skip-rule"),
            "override_policy": "typed-override-v1",
        }
    requires_attestation = _require_bool(template["requires_typed_attestation"], "template-requires-attestation")
    attestation_types = _normalize_ids(template["attestation_types"], "template-attestation-types", allow_empty=True)
    if requires_attestation and not attestation_types:
        raise ObligationError(f"semantic-obligation-missing-attestation-type:{obligation_id}")
    return {
        "obligation_id": obligation_id,
        "role": _require_id(template["role"], f"template-role:{obligation_id}"),
        "responsibility": _require_text(template["responsibility"], f"template-responsibility:{obligation_id}"),
        "participation": participation,
        "selection_rule_id": _require_id(template["selection_rule_id"], f"template-rule:{obligation_id}"),
        "min_actors": min_actors,
        "max_actors": max_actors,
        "independence_constraints": sorted(constraints, key=lambda item: str(item["id"])),
        "playbook_ref": {
            "module_id": _require_id(playbook["module_id"], f"template-module:{obligation_id}"),
            "anchor": _require_ref(playbook["anchor"], f"template-anchor:{obligation_id}"),
        },
        "completion_assertion_ids": _normalize_ids(template["completion_assertion_ids"], f"template-assertions:{obligation_id}"),
        "requires_typed_attestation": requires_attestation,
        "attestation_types": attestation_types,
        "skip_policy": normalized_skip,
    }


def _validate_attestation(value: object, item: Mapping[str, object], manifest: Mapping[str, object]) -> dict[str, object]:
    _assert_no_self_report(value)
    attestation = _require_exact_mapping(value, _ATTESTATION_KEYS, "typed-attestation")
    obligation_id = str(item["obligation_id"])
    if (attestation["schema_version"] != ATTESTATION_SCHEMA or attestation["scope"] != PREVIEW_SCOPE
            or attestation["obligation_id"] != obligation_id or attestation["role"] != item["role"]
            or attestation["policy_manifest_ref"] != manifest["policy_manifest_ref"]
            or attestation["context_manifest_ref"] != manifest["context_manifest_ref"]):
        raise ObligationError(f"attestation-scope-mismatch:{obligation_id}")
    actor = _require_ref(attestation["actor"], f"attestation-actor:{obligation_id}")
    if attestation["verdict"] != "pass":
        raise ObligationError(f"attestation-not-pass:{obligation_id}")
    attestation_type = _require_id(attestation["attestation_type"], f"attestation-type:{obligation_id}")
    if attestation_type not in item["attestation_types"]:
        raise ObligationError(f"invalid-attestation-type:{obligation_id}")
    _require_ref(attestation["subject_ref"], f"attestation-subject:{obligation_id}")
    _require_ref(attestation["rationale_ref"], f"attestation-rationale:{obligation_id}")
    _parse_timestamp(attestation["created_at"], f"attestation-created-at:{obligation_id}")
    return {
        "schema_version": ATTESTATION_SCHEMA,
        "scope": PREVIEW_SCOPE,
        "subject_ref": _require_ref(attestation["subject_ref"], f"attestation-subject:{obligation_id}"),
        "obligation_id": obligation_id,
        "role": str(item["role"]),
        "actor": actor,
        "verdict": "pass",
        "attestation_type": attestation_type,
        "evidence_refs": _normalize_refs(attestation["evidence_refs"], f"attestation-evidence:{obligation_id}"),
        "rationale_ref": _require_ref(attestation["rationale_ref"], f"attestation-rationale:{obligation_id}"),
        "policy_manifest_ref": str(manifest["policy_manifest_ref"]),
        "context_manifest_ref": str(manifest["context_manifest_ref"]),
        "created_at": _require_text(attestation["created_at"], f"attestation-created-at:{obligation_id}"),
    }


def _validate_override(
    value: object,
    item: Mapping[str, object],
    manifest: Mapping[str, object],
    *,
    now: object | None,
) -> dict[str, object]:
    _assert_no_self_report(value)
    override = _require_exact_mapping(value, _OVERRIDE_KEYS, "typed-override")
    obligation_id = str(item["obligation_id"])
    kind = _require_text(override["override_kind"], f"override-kind:{obligation_id}")
    if kind in NON_OVERRIDABLE_INVARIANTS:
        raise ObligationError(f"non-overridable-invariant:{kind}")
    if kind != "conditional_skip":
        raise ObligationError(f"invalid-override-kind:{kind}")
    if (override["schema_version"] != OVERRIDE_SCHEMA or override["scope"] != PREVIEW_SCOPE
            or override["obligation_id"] != obligation_id or override["role"] != item["role"]
            or override["policy_manifest_ref"] != manifest["policy_manifest_ref"]
            or override["context_manifest_ref"] != manifest["context_manifest_ref"]
            or override["rule_id"] != item["selection_rule_id"]):
        raise ObligationError(f"override-scope-mismatch:{obligation_id}")
    if now is None:
        raise ObligationError(f"override-now-required:{obligation_id}")
    if _parse_timestamp(override["expires_at"], f"override-expires-at:{obligation_id}") <= _parse_timestamp(now, "override-now"):
        raise ObligationError(f"expired-override:{obligation_id}")
    return {
        "schema_version": OVERRIDE_SCHEMA,
        "scope": PREVIEW_SCOPE,
        "override_kind": "conditional_skip",
        "obligation_id": obligation_id,
        "role": str(item["role"]),
        "actor": _require_ref(override["actor"], f"override-actor:{obligation_id}"),
        "rule_id": str(item["selection_rule_id"]),
        "policy_manifest_ref": str(manifest["policy_manifest_ref"]),
        "context_manifest_ref": str(manifest["context_manifest_ref"]),
        "reason_ref": _require_ref(override["reason_ref"], f"override-reason:{obligation_id}"),
        "replacement_evidence_refs": _normalize_refs(
            override["replacement_evidence_refs"], f"override-evidence:{obligation_id}"),
        "expires_at": _require_text(override["expires_at"], f"override-expires-at:{obligation_id}"),
        "authorization_ref": _require_ref(override["authorization_ref"], f"override-authorization:{obligation_id}"),
    }


def _validate_item(value: object, manifest: Mapping[str, object]) -> dict[str, object]:
    item = _require_exact_mapping(value, _ITEM_KEYS, "obligation-item")
    template = _validate_template({key: item[key] for key in _TEMPLATE_KEYS})
    obligation_id = str(template["obligation_id"])
    status = _require_text(item["status"], f"obligation-status:{obligation_id}")
    if status not in VALID_STATUSES:
        raise ObligationError(f"invalid-obligation-status:{obligation_id}")
    active = _require_bool(item["active"], f"obligation-active:{obligation_id}")
    required = _require_bool(item["required"], f"obligation-required:{obligation_id}")
    if required and (not active or status == "explicitly_skipped"):
        raise ObligationError(f"invalid-required-obligation-state:{obligation_id}")
    evidence_refs = _normalize_refs(item["evidence_refs"], f"obligation-evidence:{obligation_id}", allow_empty=True)
    superseded = item["superseded_by_context_ref"]
    if superseded is not None:
        _require_sha256(superseded, f"obligation-superseded-context:{obligation_id}")
        if active or required:
            raise ObligationError(f"superseded-obligation-must-be-inactive:{obligation_id}")
    normalized = dict(template)
    normalized.update({
        "required": required,
        "active": active,
        "status": status,
        "evidence_refs": evidence_refs,
        "attestation_ref": None,
        "attestation": None,
        "completed_by": None,
        "completed_binding_sha256": None,
        "skip_reason": None,
        "selector_proof": None,
        "override_ref": None,
        "override": None,
        "superseded_by_context_ref": superseded,
    })
    if status == "selected":
        if evidence_refs or any(item[field] is not None for field in (
            "attestation_ref", "attestation", "completed_by", "completed_binding_sha256", "skip_reason",
            "selector_proof", "override_ref", "override",
        )):
            raise ObligationError(f"invalid-selected-obligation:{obligation_id}")
        if active and not required:
            raise ObligationError(f"invalid-selected-obligation:{obligation_id}")
        if not active and (required or superseded is None):
            raise ObligationError(f"invalid-selected-obligation:{obligation_id}")
        return normalized
    if status == "completed":
        if template["responsibility"] == "approver":
            raise ObligationError(f"preview-approval-cannot-complete:{obligation_id}")
        if not evidence_refs:
            raise ObligationError(f"completion-requires-evidence:{obligation_id}")
        completed_by = _require_ref(item["completed_by"], f"completion-actor:{obligation_id}")
        binding_sha = _require_sha256(item["completed_binding_sha256"], f"completion-binding:{obligation_id}")
        attestation_raw = item["attestation"]
        if template["requires_typed_attestation"] and attestation_raw is None:
            raise ObligationError(f"completion-requires-attestation:{obligation_id}")
        if attestation_raw is not None:
            attestation = _validate_attestation(attestation_raw, normalized, manifest)
            if attestation["actor"] != completed_by or attestation["evidence_refs"] != evidence_refs:
                raise ObligationError(f"completion-attestation-mismatch:{obligation_id}")
            ref = sha256_bytes(canonical_bytes(attestation))
            if item["attestation_ref"] != ref:
                raise ObligationError(f"attestation-ref-mismatch:{obligation_id}")
            normalized["attestation"] = attestation
            normalized["attestation_ref"] = ref
        elif item["attestation_ref"] is not None:
            raise ObligationError(f"unexpected-attestation-ref:{obligation_id}")
        if any(item[field] is not None for field in ("skip_reason", "selector_proof", "override_ref", "override")):
            raise ObligationError(f"completed-obligation-has-skip:{obligation_id}")
        normalized["completed_by"] = completed_by
        normalized["completed_binding_sha256"] = binding_sha
        return normalized
    # explicitly_skipped
    if required or item["attestation_ref"] is not None or item["attestation"] is not None or item["completed_by"] is not None:
        raise ObligationError(f"invalid-skipped-obligation:{obligation_id}")
    if item["completed_binding_sha256"] is not None:
        raise ObligationError(f"skipped-obligation-has-completion-binding:{obligation_id}")
    reason = _require_text(item["skip_reason"], f"skip-reason:{obligation_id}")
    if reason == "selector_false":
        if template["participation"] != "conditional" or item["override_ref"] is not None or item["override"] is not None:
            raise ObligationError(f"invalid-selector-skip:{obligation_id}")
        proof = _require_exact_mapping(item["selector_proof"], frozenset({"rule_id", "result"}), "selector-proof")
        if proof["rule_id"] != template["selection_rule_id"] or proof["result"] != "false" or evidence_refs:
            raise ObligationError(f"invalid-selector-proof:{obligation_id}")
        normalized["skip_reason"] = "selector_false"
        normalized["selector_proof"] = {"rule_id": str(template["selection_rule_id"]), "result": "false"}
        return normalized
    if reason == "typed_override":
        if template["participation"] != "conditional" or item["selector_proof"] is not None:
            raise ObligationError(f"invalid-override-skip:{obligation_id}")
        override = _validate_override(item["override"], normalized, manifest, now="1970-01-01T00:00:00Z")
        if evidence_refs != override["replacement_evidence_refs"]:
            raise ObligationError(f"override-evidence-mismatch:{obligation_id}")
        ref = sha256_bytes(canonical_bytes(override))
        if item["override_ref"] != ref:
            raise ObligationError(f"override-ref-mismatch:{obligation_id}")
        normalized["skip_reason"] = "typed_override"
        normalized["override"] = override
        normalized["override_ref"] = ref
        return normalized
    raise ObligationError(f"invalid-skip-reason:{obligation_id}")


def _validate_legacy_observation(value: object) -> dict[str, object]:
    _assert_no_self_report(value)
    observation = _require_exact_mapping(value, _LEGACY_OBSERVATION_KEYS, "legacy-approval-observation")
    if observation["kind"] != "legacy_approval_observation" or observation["scope"] != PREVIEW_SCOPE:
        raise ObligationError("invalid-legacy-approval-observation")
    return {
        "kind": "legacy_approval_observation",
        "scope": PREVIEW_SCOPE,
        "legacy_spec_sha256": _require_sha256(observation["legacy_spec_sha256"], "legacy-spec-sha256"),
    }


def validate_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    """Validate and canonicalize an immutable Phase 1 ObligationManifest."""
    source = _require_exact_mapping(manifest, _MANIFEST_KEYS, "obligation-manifest")
    if source["schema_version"] != OBLIGATION_MANIFEST_SCHEMA or source["scope"] != PREVIEW_SCOPE:
        raise ObligationError("preview-obligation-manifest-required")
    manifest_id = _require_sha256(source["obligation_manifest_id"], "obligation-manifest-id")
    revision = _require_positive_int(source["revision"], "obligation-revision")
    previous = source["previous_ref"]
    if revision == 1:
        if previous is not None:
            raise ObligationError("initial-obligation-manifest-has-previous-ref")
    elif _require_sha256(previous, "obligation-previous-ref") == manifest_id:
        raise ObligationError("obligation-manifest-self-reference")
    policy_ref, _ = _parse_phase_ref(source["phase_contract_ref"], "obligation-phase-contract-ref")
    if policy_ref != _require_sha256(source["policy_manifest_ref"], "obligation-policy-manifest-ref"):
        raise ObligationError("obligation-policy-phase-mismatch")
    binding = _normalize_json(_require_mapping(source["freshness_binding"], "freshness-binding"), "freshness-binding")
    if sha256_bytes(canonical_bytes(binding)) != _require_sha256(source["freshness_binding_sha256"], "freshness-binding-sha256"):
        raise ObligationError("freshness-binding-hash-mismatch")
    templates_source = source["obligation_templates"]
    if not isinstance(templates_source, list) or not templates_source:
        raise ObligationError("invalid-obligation-templates")
    templates = [_validate_template(template) for template in templates_source]
    templates.sort(key=lambda item: str(item["obligation_id"]))
    if len({item["obligation_id"] for item in templates}) != len(templates):
        raise ObligationError("duplicate-obligation-template")
    items_source = source["obligations"]
    if not isinstance(items_source, list) or not items_source:
        raise ObligationError("invalid-obligations")
    shallow = {
        "policy_manifest_ref": source["policy_manifest_ref"],
        "context_manifest_ref": source["context_manifest_ref"],
    }
    items = [_validate_item(item, shallow) for item in items_source]
    items.sort(key=lambda item: str(item["obligation_id"]))
    if len({item["obligation_id"] for item in items}) != len(items):
        raise ObligationError("duplicate-obligation-item")
    if {item["obligation_id"] for item in items} != {item["obligation_id"] for item in templates}:
        raise ObligationError("obligation-item-template-mismatch")
    observations_source = source["legacy_approval_observations"]
    if not isinstance(observations_source, list):
        raise ObligationError("invalid-legacy-approval-observations")
    observations = [_validate_legacy_observation(item) for item in observations_source]
    observations.sort(key=lambda item: str(item["legacy_spec_sha256"]))
    if len({item["legacy_spec_sha256"] for item in observations}) != len(observations):
        raise ObligationError("duplicate-legacy-approval-observation")
    normalized: dict[str, object] = {
        "schema_version": OBLIGATION_MANIFEST_SCHEMA,
        "scope": PREVIEW_SCOPE,
        "lifecycle_run_id": _require_id(source["lifecycle_run_id"], "obligation-lifecycle-run-id"),
        "revision": revision,
        "previous_ref": previous,
        "context_manifest_ref": _require_sha256(source["context_manifest_ref"], "obligation-context-manifest-ref"),
        "context_input_sha256": _require_sha256(source["context_input_sha256"], "obligation-context-input-sha256"),
        "policy_manifest_ref": _require_sha256(source["policy_manifest_ref"], "obligation-policy-manifest-ref"),
        "phase_contract_ref": _require_text(source["phase_contract_ref"], "obligation-phase-contract-ref"),
        "lifecycle": _require_text(source["lifecycle"], "obligation-lifecycle"),
        "operation": _require_text(source["operation"], "obligation-operation"),
        "compatibility_adapter": None if source["compatibility_adapter"] is None else _require_text(
            source["compatibility_adapter"], "obligation-compatibility-adapter"),
        "needs_classification": _require_bool(source["needs_classification"], "obligation-needs-classification"),
        "freshness_binding": binding,
        "freshness_binding_sha256": _require_sha256(source["freshness_binding_sha256"], "freshness-binding-sha256"),
        "obligation_templates": templates,
        "obligations": items,
        "legacy_approval_observations": observations,
    }
    expected = sha256_bytes(canonical_bytes(normalized))
    if manifest_id != expected:
        raise ObligationError("obligation-manifest-id-mismatch")
    normalized["obligation_manifest_id"] = manifest_id
    # The ID is appended after the preimage fields to preserve canonical hashing.
    return normalized


def _next_revision(manifest: Mapping[str, object], **changes: object) -> dict[str, object]:
    current = validate_manifest(manifest)
    next_value = _manifest_preimage(current)
    next_value.update(_clone(changes))
    next_value["revision"] = int(current["revision"]) + 1
    next_value["previous_ref"] = current["obligation_manifest_id"]
    return validate_manifest(_seal_manifest(next_value))


def _find_item(manifest: Mapping[str, object], obligation_id: str) -> tuple[int, dict[str, object]]:
    target = _require_id(obligation_id, "obligation-id")
    items = manifest["obligations"]
    assert isinstance(items, list)
    for index, item in enumerate(items):
        assert isinstance(item, dict)
        if item["obligation_id"] == target:
            return index, _clone(item)
    raise ObligationError(f"unknown-obligation:{target}")


def _validate_actor_role_binding(actor: str, role: str, bindings: Mapping[str, Sequence[str]]) -> None:
    if not isinstance(bindings, Mapping):
        raise ObligationError("invalid-actor-role-bindings")
    bound_roles = bindings.get(actor)
    if not isinstance(bound_roles, Sequence) or isinstance(bound_roles, (str, bytes)):
        raise ObligationError(f"actor-role-mismatch:{actor}:{role}")
    normalized = {_require_id(value, "actor-bound-role") for value in bound_roles}
    if role not in normalized:
        raise ObligationError(f"actor-role-mismatch:{actor}:{role}")


def _assert_independence(item: Mapping[str, object], actor: str, manifest: Mapping[str, object]) -> None:
    items = manifest["obligations"]
    assert isinstance(items, list)
    for constraint in item["independence_constraints"]:
        assert isinstance(constraint, Mapping)
        constraint_id = str(constraint["id"])
        if constraint["mode"] != "distinct_actor":
            raise ObligationError(f"unsupported-independence-mode:{constraint_id}")
        against = set(constraint["against_role_ids"])
        for other in items:
            assert isinstance(other, Mapping)
            if other["obligation_id"] == item["obligation_id"] or other["role"] not in against:
                continue
            if other["status"] == "completed" and other["completed_by"] == actor:
                raise ObligationError(f"independence-violation:{constraint_id}:{actor}")


def complete_obligation(
    manifest: Mapping[str, object],
    obligation_id: str,
    *,
    actor: str,
    actor_role_bindings: Mapping[str, Sequence[str]],
    evidence_refs: Sequence[str],
    attestation: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Append a completion revision after validating Evidence and typed role input."""
    current = validate_manifest(manifest)
    index, item = _find_item(current, obligation_id)
    obligation_id = str(item["obligation_id"])
    actor = _require_ref(actor, f"completion-actor:{obligation_id}")
    if item["responsibility"] == "approver":
        # Phase 1 has no ApprovalHead.  An observation may be stored separately,
        # but it can never become a dual approval completion.
        raise ObligationError(f"preview-approval-cannot-complete:{obligation_id}")
    if item["status"] != "selected" or not item["active"]:
        raise ObligationError(f"obligation-not-selected:{obligation_id}")
    if item["min_actors"] != 1 or item["max_actors"] != 1:
        raise ObligationError(f"multiple-actor-obligation-requires-batch-api:{obligation_id}")
    _validate_actor_role_binding(actor, str(item["role"]), actor_role_bindings)
    _assert_independence(item, actor, current)
    if isinstance(evidence_refs, (str, bytes)):
        raise ObligationError(f"invalid-completion-evidence:{obligation_id}")
    refs = _normalize_refs(list(evidence_refs), f"completion-evidence:{obligation_id}")
    normalized_attestation: dict[str, object] | None = None
    if attestation is not None:
        normalized_attestation = _validate_attestation(attestation, item, current)
        if normalized_attestation["actor"] != actor or normalized_attestation["evidence_refs"] != refs:
            raise ObligationError(f"completion-attestation-mismatch:{obligation_id}")
    elif item["requires_typed_attestation"]:
        raise ObligationError(f"completion-requires-attestation:{obligation_id}")
    item.update({
        "status": "completed",
        "required": True,
        "active": True,
        "evidence_refs": refs,
        "attestation": normalized_attestation,
        "attestation_ref": None if normalized_attestation is None else sha256_bytes(canonical_bytes(normalized_attestation)),
        "completed_by": actor,
        "completed_binding_sha256": current["freshness_binding_sha256"],
        "skip_reason": None,
        "selector_proof": None,
        "override_ref": None,
        "override": None,
        "superseded_by_context_ref": None,
    })
    items = _clone(current["obligations"])
    assert isinstance(items, list)
    items[index] = item
    return _next_revision(current, obligations=items)


def apply_override(
    manifest: Mapping[str, object],
    obligation_id: str,
    *,
    override: Mapping[str, object],
    actor_role_bindings: Mapping[str, Sequence[str]],
    now: str,
) -> dict[str, object]:
    """Append a typed conditional-skip decision; required obligations cannot skip."""
    current = validate_manifest(manifest)
    index, item = _find_item(current, obligation_id)
    obligation_id = str(item["obligation_id"])
    if item["responsibility"] == "approver":
        raise ObligationError(f"preview-approval-cannot-override:{obligation_id}")
    if item["participation"] != "conditional":
        raise ObligationError(f"required-obligation-cannot-skip:{obligation_id}")
    if item["status"] != "selected" or not item["active"]:
        raise ObligationError(f"obligation-not-selected:{obligation_id}")
    normalized = _validate_override(override, item, current, now=now)
    _validate_actor_role_binding(str(normalized["actor"]), str(item["role"]), actor_role_bindings)
    _assert_independence(item, str(normalized["actor"]), current)
    item.update({
        "status": "explicitly_skipped",
        "required": False,
        "active": True,
        "evidence_refs": normalized["replacement_evidence_refs"],
        "attestation": None,
        "attestation_ref": None,
        "completed_by": None,
        "completed_binding_sha256": None,
        "skip_reason": "typed_override",
        "selector_proof": None,
        "override": normalized,
        "override_ref": sha256_bytes(canonical_bytes(normalized)),
        "superseded_by_context_ref": None,
    })
    items = _clone(current["obligations"])
    assert isinstance(items, list)
    items[index] = item
    return _next_revision(current, obligations=items)


def record_legacy_approval_observation(
    manifest: Mapping[str, object],
    observation: Mapping[str, object],
) -> dict[str, object]:
    """Record compatibility evidence without changing any approval obligation."""
    current = validate_manifest(manifest)
    normalized = _validate_legacy_observation(observation)
    observations = _clone(current["legacy_approval_observations"])
    assert isinstance(observations, list)
    if any(item["legacy_spec_sha256"] == normalized["legacy_spec_sha256"] for item in observations):
        return current
    observations.append(normalized)
    observations.sort(key=lambda item: str(item["legacy_spec_sha256"]))
    return _next_revision(current, legacy_approval_observations=observations)


def _freshness_allows_inheritance(freshness: object) -> bool:
    if freshness == FRESH:
        return True
    if freshness == STALE:
        return False
    if not isinstance(freshness, Mapping):
        raise ObligationError("invalid-freshness")
    required = {"artifact", "attestation", "diff", "evidence", "policy"}
    if set(freshness) != required or any(not isinstance(freshness[key], bool) for key in required):
        raise ObligationError("invalid-freshness")
    return all(bool(freshness[key]) for key in required)


def _context_selection(context: Mapping[str, object], template_ids: set[str]) -> tuple[set[str], dict[str, Mapping[str, object]]]:
    selected = set(context["selected_obligation_ids"])
    skipped = {str(item["id"]): item for item in context["skipped_obligations"]}
    if selected | set(skipped) != template_ids:
        raise ObligationError("context-does-not-cover-phase-obligations")
    return selected, skipped


def reconcile(
    current_manifest: Mapping[str, object],
    new_context_manifest: Mapping[str, object],
    *,
    freshness: object = FRESH,
) -> dict[str, object]:
    """Merge a re-resolved context without deleting historical obligations.

    Completed work is inherited only when the mechanical freshness binding is
    unchanged *and* the caller's runner/canonical-state freshness verdict is
    fully fresh.  Any context, artifact, diff, policy, Evidence, or attestation
    uncertainty is therefore conservative: the item returns to ``selected``.
    """
    current = validate_manifest(current_manifest)
    context = _validate_context(new_context_manifest)
    if (context["lifecycle_run_id"] != current["lifecycle_run_id"]
            or context["policy_manifest_id"] != current["policy_manifest_ref"]
            or context["phase_contract_ref"] != current["phase_contract_ref"]
            or context["lifecycle"] != current["lifecycle"]
            or context["operation"] != current["operation"]):
        raise ObligationError("reconcile-context-identity-mismatch")
    new_binding = _freshness_binding(context)
    binding_sha = sha256_bytes(canonical_bytes(new_binding))
    may_inherit_completed = (
        binding_sha == current["freshness_binding_sha256"] and _freshness_allows_inheritance(freshness)
    )
    templates = _clone(current["obligation_templates"])
    assert isinstance(templates, list)
    template_by_id = {str(item["obligation_id"]): item for item in templates}
    selected, skipped_by_id = _context_selection(context, set(template_by_id))
    current_items = _clone(current["obligations"])
    assert isinstance(current_items, list)
    old_by_id = {str(item["obligation_id"]): item for item in current_items}
    merged: list[dict[str, object]] = []
    for obligation_id in sorted(template_by_id):
        template = template_by_id[obligation_id]
        old = old_by_id.get(obligation_id)
        if obligation_id in selected:
            if (old is not None and old["status"] == "completed" and old["active"]
                    and may_inherit_completed and old["completed_binding_sha256"] == binding_sha):
                inherited = _clone(old)
                assert isinstance(inherited, dict)
                inherited["active"] = True
                inherited["required"] = True
                inherited["superseded_by_context_ref"] = None
                merged.append(inherited)
                continue
            if (old is not None and old["status"] == "explicitly_skipped" and old["skip_reason"] == "typed_override"
                    and old["active"] and binding_sha == current["freshness_binding_sha256"]):
                inherited_override = _clone(old)
                assert isinstance(inherited_override, dict)
                inherited_override["active"] = True
                inherited_override["required"] = False
                inherited_override["superseded_by_context_ref"] = None
                merged.append(inherited_override)
                continue
            merged.append(_item_from_template(template, selected=True))
            continue
        proof = skipped_by_id[obligation_id]["selector_proof"]
        if old is not None and old["status"] in {"selected", "completed"} and old["active"]:
            inactive = _clone(old)
            assert isinstance(inactive, dict)
            inactive["active"] = False
            inactive["required"] = False
            inactive["superseded_by_context_ref"] = context["context_manifest_id"]
            merged.append(inactive)
        else:
            merged.append(_item_from_template(template, selected=False, selector_proof=proof))
    return _next_revision(
        current,
        context_manifest_ref=context["context_manifest_id"],
        context_input_sha256=context["context_input_sha256"],
        needs_classification=context["needs_classification"],
        freshness_binding=new_binding,
        freshness_binding_sha256=binding_sha,
        obligations=merged,
    )


def require_transition_ready(manifest: Mapping[str, object], *, now: str | None = None) -> dict[str, object]:
    """Check preview readiness without performing a lifecycle/control transition."""
    current = validate_manifest(manifest)
    if current["needs_classification"]:
        raise ObligationError("needs-classification")
    missing = [
        str(item["obligation_id"])
        for item in current["obligations"]
        if item["active"] and item["status"] == "selected"
    ]
    if missing:
        raise ObligationError(f"incomplete-required:{','.join(sorted(missing))}")
    for item in current["obligations"]:
        if not item["active"] or item["status"] != "explicitly_skipped" or item["skip_reason"] != "typed_override":
            continue
        _validate_override(item["override"], item, current, now=now)
    return {
        "scope": PREVIEW_SCOPE,
        "readiness": "diagnostic-only",
        "obligation_manifest_ref": current["obligation_manifest_id"],
        "completed_obligation_ids": sorted(
            str(item["obligation_id"])
            for item in current["obligations"]
            if item["active"] and item["status"] == "completed"
        ),
    }


def _ensure_directory(parent: Path, name: str, root: Path) -> Path:
    target = parent / name
    try:
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise ObligationError(f"unsafe-preview-directory:{target}")
        else:
            target.mkdir()
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
    except ObligationError:
        raise
    except (OSError, ValueError) as exc:
        raise ObligationError(f"unsafe-preview-directory:{target}") from exc
    return resolved


def _preview_obligation_dir(repo_root: str | os.PathLike[str], run_id: str) -> Path:
    run_id = _require_id(run_id, "lifecycle-run-id")
    try:
        root = Path(repo_root).resolve(strict=True)
    except OSError as exc:
        raise ObligationError("preview-repository-root-not-found") from exc
    if not root.is_dir():
        raise ObligationError("preview-repository-root-not-directory")
    current = root
    for part in (".sdlc", "preview", run_id, "obligations"):
        current = _ensure_directory(current, part, root)
    return current


def preview_head_path(repo_root: str | os.PathLike[str], lifecycle_run_id: str) -> Path:
    """Return the only legal mutable pointer path for one preview run."""
    return _preview_obligation_dir(repo_root, lifecycle_run_id) / "HEAD.json"


def _checked_head_path(head_path: str | os.PathLike[str], lifecycle_run_id: str) -> Path:
    candidate = Path(head_path).absolute()
    if candidate.name != "HEAD.json" or candidate.parent.name != "obligations":
        raise ObligationError("invalid-preview-head-path")
    run_dir = candidate.parent.parent
    if run_dir.name != lifecycle_run_id or run_dir.parent.name != "preview" or run_dir.parent.parent.name != ".sdlc":
        raise ObligationError("invalid-preview-head-path")
    repo_root = run_dir.parent.parent.parent
    expected = preview_head_path(repo_root, lifecycle_run_id)
    if candidate != expected.absolute():
        raise ObligationError("invalid-preview-head-path")
    return expected


def _reject_duplicate_json_key(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ObligationError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ObligationError(f"non-finite-json-constant:{value}")


def _read_json(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink():
        raise ObligationError(f"symlink-preview-artifact:{path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_key,
            parse_constant=_reject_json_constant,
        )
    except ObligationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObligationError(f"invalid-{label}") from exc
    return dict(_require_mapping(value, label))


def _write_immutable_json(path: Path, value: Mapping[str, object]) -> bool:
    if path.exists():
        if path.is_symlink():
            raise ObligationError(f"symlink-preview-artifact:{path}")
        try:
            if path.read_bytes() == canonical_bytes(value):
                return False
        except OSError as exc:
            raise ObligationError(f"preview-artifact-read-failed:{path}") from exc
        raise ObligationConflict(f"immutable-preview-manifest-conflict:{path.name}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return _write_immutable_json(path, value)
    except OSError as exc:
        raise ObligationError(f"preview-artifact-write-failed:{path}") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ObligationError(f"preview-artifact-write-failed:{path}") from exc
    return True


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    if path.exists() and path.is_symlink():
        raise ObligationError(f"symlink-preview-artifact:{path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ObligationError(f"preview-head-write-failed:{path}") from exc
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _head_lock(head_path: Path) -> Iterator[None]:
    if fcntl is None:  # pragma: no cover - this runtime is intentionally unsupported for file CAS.
        raise ObligationError("preview-head-locking-unavailable")
    lock_path = head_path.with_name(".HEAD.lock")
    if lock_path.exists() and lock_path.is_symlink():
        raise ObligationError(f"symlink-preview-artifact:{lock_path}")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ObligationError(f"preview-head-lock-failed:{head_path}") from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ObligationConflict("preview-head-update-in-progress") from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _validate_head(value: Mapping[str, object]) -> dict[str, object]:
    head = _require_exact_mapping(value, _HEAD_KEYS, "obligation-head")
    if head["schema_version"] != OBLIGATION_HEAD_SCHEMA or head["scope"] != PREVIEW_SCOPE:
        raise ObligationError("invalid-preview-obligation-head")
    updated_at = head["updated_at"]
    if updated_at is not None:
        _parse_timestamp(updated_at, "obligation-head-updated-at")
    return {
        "schema_version": OBLIGATION_HEAD_SCHEMA,
        "scope": PREVIEW_SCOPE,
        "lifecycle_run_id": _require_id(head["lifecycle_run_id"], "head-lifecycle-run-id"),
        "head_ref": _require_sha256(head["head_ref"], "head-ref"),
        "context_manifest_ref": _require_sha256(head["context_manifest_ref"], "head-context-manifest-ref"),
        "revision": _require_positive_int(head["revision"], "head-revision"),
        "updated_at": None if updated_at is None else _require_text(updated_at, "head-updated-at"),
    }


def read_head(head_path: str | os.PathLike[str]) -> dict[str, object]:
    """Read one preview-only ObligationHead; never looks at control state."""
    candidate = Path(head_path).absolute()
    if candidate.name != "HEAD.json" or candidate.parent.name != "obligations":
        raise ObligationError("invalid-preview-head-path")
    run_id = _require_id(candidate.parent.parent.name, "head-lifecycle-run-id")
    checked = _checked_head_path(candidate, run_id)
    if not checked.exists():
        raise ObligationError("preview-head-not-found")
    head = _validate_head(_read_json(checked, "obligation-head"))
    if head["lifecycle_run_id"] != run_id:
        raise ObligationError("preview-head-run-mismatch")
    return head


def update_head(
    head_path: str | os.PathLike[str],
    *,
    expected: str | None,
    manifest: Mapping[str, object],
    updated_at: str | None = None,
) -> dict[str, object]:
    """Persist an immutable manifest and atomically replace HEAD if expected matches.

    ``expected=None`` creates revision 1.  The caller must retry from a fresh
    head after a conflict; this function never rewrites control records or
    legacy ``STATE.md``.
    """
    current_manifest = validate_manifest(manifest)
    run_id = str(current_manifest["lifecycle_run_id"])
    checked = _checked_head_path(head_path, run_id)
    if expected is not None:
        # A malformed expected value cannot equal a valid content-addressed
        # head; report it through the same CAS conflict path rather than
        # turning a stale caller retry into a schema side channel.
        expected = _require_ref(expected, "expected-head-ref")
    if updated_at is not None:
        _parse_timestamp(updated_at, "head-updated-at")
    with _head_lock(checked):
        if checked.exists():
            old_head = _validate_head(_read_json(checked, "obligation-head"))
            actual = old_head["head_ref"]
            if old_head["lifecycle_run_id"] != run_id:
                raise ObligationConflict("preview-head-run-mismatch")
        else:
            old_head = None
            actual = None
        if actual != expected:
            raise ObligationConflict(f"expected-head-mismatch:{expected}:{actual}")
        if current_manifest["previous_ref"] != expected:
            raise ObligationConflict("manifest-previous-ref-mismatch")
        expected_revision = 1 if old_head is None else int(old_head["revision"]) + 1
        if current_manifest["revision"] != expected_revision:
            raise ObligationConflict("manifest-revision-mismatch")
        manifest_path = checked.parent / f"{current_manifest['obligation_manifest_id']}.json"
        _write_immutable_json(manifest_path, current_manifest)
        new_head = {
            "schema_version": OBLIGATION_HEAD_SCHEMA,
            "scope": PREVIEW_SCOPE,
            "lifecycle_run_id": run_id,
            "head_ref": current_manifest["obligation_manifest_id"],
            "context_manifest_ref": current_manifest["context_manifest_ref"],
            "revision": current_manifest["revision"],
            "updated_at": updated_at,
        }
        _write_json_atomic(checked, new_head)
    return _validate_head(new_head)


def load_manifest(
    repo_root: str | os.PathLike[str],
    lifecycle_run_id: str,
    obligation_manifest_ref: str,
) -> dict[str, object]:
    """Load and verify one immutable preview manifest by content-addressed ref."""
    run_id = _require_id(lifecycle_run_id, "lifecycle-run-id")
    manifest_ref = _require_sha256(obligation_manifest_ref, "obligation-manifest-ref")
    path = _preview_obligation_dir(repo_root, run_id) / f"{manifest_ref}.json"
    if not path.exists():
        raise ObligationError("preview-obligation-manifest-not-found")
    manifest = validate_manifest(_read_json(path, "obligation-manifest"))
    if manifest["lifecycle_run_id"] != run_id or manifest["obligation_manifest_id"] != manifest_ref:
        raise ObligationError("preview-obligation-manifest-ref-mismatch")
    return manifest


def start_preview_run(
    repo_root: str | os.PathLike[str],
    context_manifest: Mapping[str, object],
    policy_manifest: Mapping[str, object],
    *,
    updated_at: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Create revision 1 and its local preview head, idempotently by content."""
    manifest = create_obligation_manifest(context_manifest, policy_manifest)
    head_path = preview_head_path(repo_root, str(manifest["lifecycle_run_id"]))
    try:
        head = update_head(head_path, expected=None, manifest=manifest, updated_at=updated_at)
    except ObligationConflict:
        head = read_head(head_path)
        if head["head_ref"] != manifest["obligation_manifest_id"]:
            raise
    return manifest, head
