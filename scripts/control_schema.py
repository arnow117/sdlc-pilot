#!/usr/bin/env python3
"""The single v1/v2 control-record registry used by dual-lifecycle code."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Mapping, Sequence


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SchemaError(ValueError):
    """A record, capability, or schema transition is invalid."""


@dataclass(frozen=True)
class RecordSpec:
    record_type: str
    schema_version: int
    required_fields: frozenset[str]
    immutable: bool
    required_capability: str | None
    identity_field: str
    status_fields: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class MutationPermission:
    allowed: bool
    reason: str | None = None


def _spec(
    record_type: str,
    version: int,
    fields: Sequence[str],
    *,
    immutable: bool,
    identity: str,
    capability: str | None = None,
    status_fields: Mapping[str, frozenset[str]] | None = None,
) -> RecordSpec:
    return RecordSpec(
        record_type=record_type,
        schema_version=version,
        required_fields=frozenset({"record_type", "schema_version", *fields}),
        immutable=immutable,
        required_capability=capability,
        identity_field=identity,
        status_fields=status_fields or {},
    )


_V1 = 1
_V2 = 2
_DUAL = "dual-lifecycle-v1"

_REGISTRY: dict[tuple[str, int], RecordSpec] = {
    ("request", _V1): _spec("request", _V1, ["request_id", "title", "status", "created_at", "updated_at"], immutable=False, identity="request_id", status_fields={"status": frozenset({"active", "withdrawn"})}),
    ("requirement", _V1): _spec("requirement", _V1, ["id", "title", "status", "source_request", "updated"], immutable=False, identity="id", status_fields={"status": frozenset({"captured", "spec'd", "planned", "built", "validated", "shipped"})}),
    ("claim", _V1): _spec("claim", _V1, ["leaf_id", "feature_id", "status", "claimed_base_sha"], immutable=False, identity="leaf_id", status_fields={"status": frozenset({"active", "released"})}),
    ("feature", _V1): _spec("feature", _V1, ["feature_id", "leaf_id", "status", "claimed_base_sha"], immutable=False, identity="feature_id", status_fields={"status": frozenset({"active", "validated", "shipped", "abandoned"})}),
    ("task", _V1): _spec("task", _V1, ["task_id", "feature_id", "status", "plan_revision"], immutable=False, identity="task_id", status_fields={"status": frozenset({"waiting", "ready", "claimed", "in_progress", "awaiting_verification", "verified", "blocked", "abandoned", "superseded"})}),
    ("evidence", _V1): _spec("evidence", _V1, ["evidence_id", "feature_id", "task_id", "scope", "result", "tested_sha"], immutable=True, identity="evidence_id", status_fields={"result": frozenset({"pass", "fail"})}),
    ("product_definition", _V2): _spec("product_definition", _V2, [
        "leaf_id", "source_request", "definition_status", "draft_status", "owner", "lifecycle_run_id",
        "policy_manifest_ref", "obligation_head_ref", "current_contract_ref", "current_contract_revision",
        "current_contract_sha256", "current_approval_ref", "pending_contract_ref", "pending_contract_revision",
        "active_change_request_refs", "created_at", "updated_at",
    ], immutable=False, identity="leaf_id", capability=_DUAL, status_fields={
        "definition_status": frozenset({"unapproved", "approved", "withdrawn"}),
        "draft_status": frozenset({"idle", "shaping", "awaiting_approval"}),
    }),
    ("product_contract", _V2): _spec("product_contract", _V2, [
        "product_contract_id", "leaf_id", "source_request", "contract_format", "contract_kind", "bundle_sha256",
        "components", "outcome_ids", "behavior_ids", "domain_rule_ids", "experience_ids", "nfr_ids", "eval_ids",
        "intent_flags", "supersedes_ref", "created_by", "created_at",
    ], immutable=True, identity="product_contract_id", capability=_DUAL),
    ("profile_snapshot", _V2): _spec("profile_snapshot", _V2, [
        "profile_snapshot_id", "feature_id", "profile_format", "profile_bytes_sha256", "source_repository_sha",
        "source_path", "profile_revision", "created_at",
    ], immutable=True, identity="profile_snapshot_id", capability=_DUAL),
    ("engineering_spec", _V2): _spec("engineering_spec", _V2, [
        "engineering_spec_id", "feature_id", "spec_format", "product_contract_ref", "product_contract_revision",
        "product_contract_approval_ref", "profile_ref", "profile_revision", "profile_sha256", "specified_against_sha",
        "bundle_sha256", "components", "implements_product_ids", "engineering_criterion_ids", "target_surfaces",
        "supersedes_ref", "created_by", "created_at",
    ], immutable=True, identity="engineering_spec_id", capability=_DUAL),
    ("delivery_plan", _V2): _spec("delivery_plan", _V2, [
        "delivery_plan_id", "feature_id", "plan_format", "engineering_spec_ref", "engineering_spec_approval_ref",
        "product_contract_ref", "product_contract_approval_ref", "profile_ref", "base_sha", "components", "tasks",
        "created_at",
    ], immutable=True, identity="delivery_plan_id", capability=_DUAL),
    ("approval_head", _V2): _spec("approval_head", _V2, [
        "subject_type", "scope", "subject_id", "head_ref", "head_decision", "updated_at",
    ], immutable=False, identity="subject_id", capability=_DUAL, status_fields={"head_decision": frozenset({"approve", "reject", "revoke", "none"})}),
    ("approval", _V2): _spec("approval", _V2, [
        "approval_id", "subject_type", "scope", "subject_id", "subject_sha256", "subject_revision", "decision",
        "previous_approval_ref", "principal_ref", "authorization_policy_ref", "authn_assurance", "decision_intent_ref",
        "resolved_change_request_refs", "created_at",
    ], immutable=True, identity="approval_id", capability=_DUAL, status_fields={"decision": frozenset({"approve", "reject", "revoke"})}),
    ("change_request", _V2): _spec("change_request", _V2, [
        "change_request_id", "scope", "subject_ref", "status", "blocking", "reported_by", "reported_at",
        "impact_refs", "resolution_ref", "accepted_by", "applied_at",
    ], immutable=False, identity="change_request_id", capability=_DUAL, status_fields={"status": frozenset({"open", "triaged", "accepted", "applied", "rejected", "cancelled"})}),
}


def record_spec(record_type: str, schema_version: int) -> RecordSpec:
    if not isinstance(record_type, str) or not isinstance(schema_version, int):
        raise SchemaError("invalid-record-spec-key")
    try:
        return _REGISTRY[(record_type, schema_version)]
    except KeyError as exc:
        raise SchemaError(f"unknown-record-schema:{record_type}@{schema_version}") from exc


def _normalize_schema_version(value: object) -> int:
    """Accept the legacy frontmatter representation without weakening v2 checks."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value in {"1", "2"}:
        return int(value)
    raise SchemaError("invalid-schema-version")


def _require_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or ".." in value:
        raise SchemaError(f"invalid-{field}")
    return value


def _require_sha(value: object, field: str, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SchemaError(f"invalid-{field}")
    return value


def _validate_v2_shape(record: Mapping[str, object], spec: RecordSpec) -> None:
    identity = _require_id(record[spec.identity_field], spec.identity_field)
    if spec.record_type in {"product_contract", "engineering_spec", "delivery_plan", "profile_snapshot", "approval"}:
        if not _SHA256_RE.fullmatch(identity):
            raise SchemaError(f"v2-identity-must-be-full-sha256:{spec.record_type}")
    for field in ("bundle_sha256", "profile_bytes_sha256", "profile_sha256", "specified_against_sha", "subject_sha256", "base_sha"):
        if field in record:
            _require_sha(record[field], field)
    for field in ("components", "outcome_ids", "behavior_ids", "domain_rule_ids", "experience_ids", "nfr_ids", "eval_ids", "implements_product_ids", "engineering_criterion_ids", "target_surfaces", "tasks", "active_change_request_refs", "impact_refs", "resolved_change_request_refs"):
        if field in record and not isinstance(record[field], list):
            raise SchemaError(f"invalid-{field}")
    if spec.record_type == "product_contract":
        if record["contract_format"] != "product-contract-v1":
            raise SchemaError("invalid-product-contract-format")
        if record["contract_kind"] not in {"feature", "patch", "remediation"}:
            raise SchemaError("invalid-product-contract-kind")
        if not record["outcome_ids"] or not record["behavior_ids"]:
            raise SchemaError("product-contract-requires-outcome-and-behavior")
    elif spec.record_type == "engineering_spec":
        if record["spec_format"] != "engineering-spec-v1" or not record["engineering_criterion_ids"]:
            raise SchemaError("invalid-engineering-spec")
    elif spec.record_type == "delivery_plan" and record["plan_format"] != "delivery-plan-v1":
        raise SchemaError("invalid-delivery-plan-format")
    elif spec.record_type == "profile_snapshot" and record["profile_format"] != "profile-snapshot-v1":
        raise SchemaError("invalid-profile-snapshot-format")


def expected_path(record: Mapping[str, object]) -> PurePosixPath:
    spec = record_spec(str(record.get("record_type")), _normalize_schema_version(record.get("schema_version")))
    identity = _require_id(record.get(spec.identity_field), spec.identity_field)
    if spec.schema_version == _V1:
        return PurePosixPath(f"{spec.record_type}s", f"{identity}.md")
    if spec.record_type == "product_definition":
        return PurePosixPath("product-definitions", f"{identity}.md")
    if spec.record_type == "product_contract":
        return PurePosixPath("product-contracts", _require_id(record.get("leaf_id"), "leaf_id"), identity, "manifest.md")
    if spec.record_type == "profile_snapshot":
        return PurePosixPath("profile-snapshots", _require_id(record.get("feature_id"), "feature_id"), f"{identity}.md")
    if spec.record_type == "engineering_spec":
        return PurePosixPath("engineering-specs", _require_id(record.get("feature_id"), "feature_id"), identity, "manifest.md")
    if spec.record_type == "delivery_plan":
        return PurePosixPath("delivery-plans", _require_id(record.get("feature_id"), "feature_id"), identity, "manifest.md")
    if spec.record_type == "approval_head":
        return PurePosixPath("approval-heads", str(record["subject_type"]), str(record["scope"]), f"{identity}.md")
    if spec.record_type == "approval":
        return PurePosixPath("approvals", str(record["subject_type"]), str(record["scope"]), str(record["subject_id"]), f"{identity}.md")
    if spec.record_type == "change_request":
        return PurePosixPath("change-requests", str(record["scope"]), f"{identity}.md")
    raise SchemaError(f"missing-path-rule:{spec.record_type}")


def validate_record(
    record: Mapping[str, object],
    *,
    previous_record: Mapping[str, object] | None = None,
) -> RecordSpec:
    if not isinstance(record, Mapping):
        raise SchemaError("record-must-be-a-mapping")
    schema_version = _normalize_schema_version(record.get("schema_version"))
    spec = record_spec(str(record.get("record_type")), schema_version)
    missing = spec.required_fields - set(record)
    if missing:
        raise SchemaError(f"missing-fields:{spec.record_type}:{','.join(sorted(missing))}")
    if record["record_type"] != spec.record_type or schema_version != spec.schema_version:
        raise SchemaError("record-type-or-version-mismatch")
    _require_id(record[spec.identity_field], spec.identity_field)
    for field, allowed in spec.status_fields.items():
        if record[field] not in allowed:
            raise SchemaError(f"invalid-{spec.record_type}-{field}")
    if spec.schema_version == _V2:
        _validate_v2_shape(record, spec)
    if previous_record is not None:
        try:
            old_version = _normalize_schema_version(previous_record.get("schema_version"))
        except SchemaError:
            old_version = None
        if old_version is not None and spec.schema_version < old_version:
            raise SchemaError("schema-downgrade-forbidden")
        if spec.immutable and dict(previous_record) != dict(record):
            raise SchemaError("immutable-record-cannot-change")
    path = record.get("_path")
    if path is not None and PurePosixPath(str(path)) != expected_path(record):
        raise SchemaError("record-path-does-not-match-identity")
    return spec


def _walk_mappings(value: object) -> list[Mapping[str, object]]:
    found: list[Mapping[str, object]] = []
    if isinstance(value, Mapping):
        found.append(value)
        for child in value.values():
            found.extend(_walk_mappings(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_mappings(child))
    return found


def client_can_mutate(client: str, snapshot: object, *, required_capability: str | None = None) -> MutationPermission:
    if client not in {"strict-v1", "dual-lifecycle-v1"}:
        return MutationPermission(False, "unknown-client-capability")
    records = _walk_mappings(snapshot)
    dual_seen = False
    capabilities: set[str] = set()
    for record in records:
        try:
            version = _normalize_schema_version(record.get("schema_version"))
        except SchemaError:
            version = None
        if version is not None and version >= _V2:
            dual_seen = True
        mode = record.get("lifecycle_mode")
        if mode == _DUAL:
            dual_seen = True
        values = record.get("capabilities")
        if isinstance(values, list):
            capabilities.update(value for value in values if isinstance(value, str))
    if client == "strict-v1" and dual_seen:
        return MutationPermission(False, "strict-v1-client-cannot-mutate-dual-records")
    if required_capability is not None and required_capability not in capabilities:
        return MutationPermission(False, f"missing-capability:{required_capability}")
    if client == "dual-lifecycle-v1" and dual_seen and _DUAL not in capabilities:
        return MutationPermission(False, "missing-capability:dual-lifecycle-v1")
    return MutationPermission(True)


def registry_dump() -> list[dict[str, object]]:
    """Stable, machine-readable registry introspection for tests and diagnostics."""
    return [
        {
            "record_type": spec.record_type,
            "schema_version": spec.schema_version,
            "required_fields": sorted(spec.required_fields),
            "immutable": spec.immutable,
            "required_capability": spec.required_capability,
            "identity_field": spec.identity_field,
            "status_fields": {field: sorted(values) for field, values in sorted(spec.status_fields.items())},
        }
        for (_, _), spec in sorted(_REGISTRY.items())
    ]
