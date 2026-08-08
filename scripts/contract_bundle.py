#!/usr/bin/env python3
"""Canonical, content-addressed ProductContract and EngineeringSpec bundles.

This module deliberately has no control-store dependency.  It turns explicit,
already-authored component bytes into immutable manifests; it does not decide
whether a contract is semantically sufficient or approved.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import PurePosixPath
import re
from typing import Mapping


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PRODUCT_PREFIXES = {
    "outcome_ids": "OUT-",
    "behavior_ids": "SCN-",
    "domain_rule_ids": "RULE-",
    "experience_ids": "EXP-",
    "nfr_ids": "NFR-",
    "eval_ids": "EVAL-",
}
_PRODUCT_AUXILIARY_PREFIXES = {
    "decision_ids": "DEC-",
    "deferred_ids": "DEF-",
}
_ENGINEERING_PREFIXES = ("ARCH-", "API-", "DATA-", "REL-", "SEC-", "TEST-")


class BundleError(ValueError):
    """A bundle lacks an immutable, fully-verifiable identity."""


def canonical_bytes(value: object) -> bytes:
    """Encode canonical JSON without silently accepting non-finite data."""
    try:
        rendered = json.dumps(
            _normalize_json(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BundleError("non-canonical-json") from exc
    return (rendered + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize_json(value: object, *, depth: int = 0) -> object:
    if depth > 32:
        raise BundleError("metadata-too-deep")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BundleError("non-finite-metadata")
        return value
    if isinstance(value, list):
        return [_normalize_json(item, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key in sorted(value):
            if not isinstance(key, str) or not key:
                raise BundleError("invalid-metadata-key")
            normalized[key] = _normalize_json(value[key], depth=depth + 1)
        return normalized
    raise BundleError("invalid-metadata-value")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise BundleError(f"invalid-{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BundleError(f"invalid-{label}")
    return value


def _id(value: object, label: str) -> str:
    text = _text(value, label)
    if not _ID_RE.fullmatch(text) or ".." in text:
        raise BundleError(f"invalid-{label}")
    return text


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BundleError(f"invalid-{label}")
    return value


def _git_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise BundleError(f"invalid-{label}")
    return value


def _string_list(value: object, label: str, *, prefix: str | tuple[str, ...] | None = None,
                 nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise BundleError(f"invalid-{label}")
    result = [_id(item, f"{label}-item") for item in value]
    if len(result) != len(set(result)):
        raise BundleError(f"duplicate-{label}")
    if prefix is not None:
        prefixes = (prefix,) if isinstance(prefix, str) else prefix
        if any(not item.startswith(prefixes) for item in result):
            raise BundleError(f"invalid-{label}-prefix")
    return sorted(result)


def _intent_flags(value: object) -> object:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return _normalize_json(value)
    if isinstance(value, list):
        return _string_list(value, "intent-flags")
    raise BundleError("invalid-intent-flags")


def _safe_component_path(value: object) -> str:
    path = _text(value, "component-path")
    pure = PurePosixPath(path)
    if (
        pure.is_absolute()
        or path != pure.as_posix()
        or "\\" in path
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or path == "manifest.md"
    ):
        raise BundleError(f"unsafe-component-path:{path}")
    return path


def _component_bytes(value: object, path: str) -> bytes:
    if isinstance(value, bytes):
        result = value
    elif isinstance(value, str):
        result = value.encode("utf-8")
    elif isinstance(value, (Mapping, list)):
        result = canonical_bytes(value)
    else:
        raise BundleError(f"invalid-component-bytes:{path}")
    if not result:
        raise BundleError(f"empty-component:{path}")
    return result


def normalize_components(value: object) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    """Return canonical component bytes and a sorted, hash-only closure."""
    source = _mapping(value, "components")
    if not source:
        raise BundleError("empty-components")
    components: dict[str, bytes] = {}
    for raw_path, content in source.items():
        path = _safe_component_path(raw_path)
        if path in components:
            raise BundleError(f"duplicate-component-path:{path}")
        components[path] = _component_bytes(content, path)
    descriptors = [
        {"path": path, "sha256": sha256_bytes(components[path])}
        for path in sorted(components)
    ]
    return components, descriptors


def _component_ref_from_path(value: object, *, label: str, descriptors: list[dict[str, str]]) -> dict[str, str]:
    """Bind a semantic contract section to one hash-addressed component."""
    path = _safe_component_path(value)
    matches = [item for item in descriptors if item["path"] == path]
    if len(matches) != 1:
        raise BundleError(f"unknown-{label}-component")
    return dict(matches[0])


def _component_ref_from_bundle(
    value: object, *, label: str, descriptors: list[dict[str, str]],
) -> dict[str, str]:
    source = _mapping(value, f"{label}-ref")
    if set(source) != {"path", "sha256"}:
        raise BundleError(f"invalid-{label}-ref")
    candidate = {
        "path": _safe_component_path(source["path"]),
        "sha256": _sha256(source["sha256"], f"{label}-component-sha"),
    }
    if candidate not in descriptors:
        raise BundleError(f"{label}-ref-not-in-components")
    return candidate


def _required_component_ref(
    value: object, *, label: str, criterion_ids: list[str], descriptors: list[dict[str, str]],
) -> dict[str, str] | None:
    if not criterion_ids:
        if value is not None:
            raise BundleError(f"{label}-component-without-criteria")
        return None
    if value is None:
        raise BundleError(f"{label}-component-required")
    return _component_ref_from_path(value, label=label, descriptors=descriptors)


def closure_sha256(metadata: Mapping[str, object], components: Mapping[str, object]) -> str:
    """Calculate the full closure hash without relying on a mutable filesystem."""
    _, descriptors = normalize_components(components)
    return sha256_bytes(canonical_bytes({"metadata": _normalize_json(metadata), "components": descriptors}))


def _supersedes(value: object, *, subject_key: str, subject_id: str) -> str | None:
    if value is None:
        return None
    source = _mapping(value, "supersedes")
    if set(source) != {"ref", subject_key}:
        raise BundleError("invalid-supersedes-keys")
    if _id(source[subject_key], f"supersedes-{subject_key}") != subject_id:
        raise BundleError(f"cross-{subject_key}-supersedes")
    return _sha256(source["ref"], "supersedes-ref")


def _behavior_kinds(value: object, behavior_ids: list[str], contract_kind: str) -> dict[str, str]:
    if value is None:
        if contract_kind in {"patch", "remediation"}:
            raise BundleError("patch-or-remediation-requires-behavior-kind")
        return {item: "new_behavior" for item in behavior_ids}
    source = _mapping(value, "behavior-kinds")
    if set(source) != set(behavior_ids):
        raise BundleError("behavior-kinds-must-cover-behavior-ids")
    allowed = {"new_behavior", "preservation", "reproduction"}
    result: dict[str, str] = {}
    for item in behavior_ids:
        kind = source[item]
        if kind not in allowed:
            raise BundleError(f"invalid-behavior-kind:{item}")
        result[item] = str(kind)
    if contract_kind in {"patch", "remediation"} and not any(
        kind in {"preservation", "reproduction"} for kind in result.values()
    ):
        raise BundleError("patch-or-remediation-requires-preservation-or-reproduction-scn")
    return result


def _product_metadata(
    *, contract_kind: str, leaf_id: str, source_request: str, outcome_ids: list[str],
    behavior_ids: list[str], behavior_kinds: Mapping[str, str], domain_rule_ids: list[str],
    experience_ids: list[str], nfr_ids: list[str], eval_ids: list[str], decision_ids: list[str] | None,
    deferred_ids: list[str] | None, decision_log_ref: Mapping[str, str] | None,
    deferred_items_ref: Mapping[str, str] | None, experience_contract_ref: Mapping[str, str] | None,
    intent_flags: object, supersedes_ref: str | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "contract_format": "product-contract-v1",
        "contract_kind": contract_kind,
        "leaf_id": leaf_id,
        "source_request": source_request,
        "outcome_ids": outcome_ids,
        "behavior_ids": behavior_ids,
        "behavior_kinds": dict(sorted(behavior_kinds.items())),
        "domain_rule_ids": domain_rule_ids,
        "experience_ids": experience_ids,
        "nfr_ids": nfr_ids,
        "eval_ids": eval_ids,
        "intent_flags": intent_flags,
        "supersedes_ref": supersedes_ref,
    }
    if decision_ids is not None:
        metadata["decision_ids"] = decision_ids
    if deferred_ids is not None:
        metadata["deferred_ids"] = deferred_ids
    if decision_log_ref is not None:
        metadata["decision_log_ref"] = dict(decision_log_ref)
    if deferred_items_ref is not None:
        metadata["deferred_items_ref"] = dict(deferred_items_ref)
    if experience_contract_ref is not None:
        metadata["experience_contract_ref"] = dict(experience_contract_ref)
    return metadata


def build_product_contract(value: Mapping[str, object]) -> dict[str, object]:
    """Build an immutable ProductContract from explicit authored components."""
    source = _mapping(value, "product-contract-input")
    allowed = {
        "contract_kind", "leaf_id", "source_request", "components", "outcome_ids", "behavior_ids",
        "behavior_kinds", "domain_rule_ids", "experience_ids", "nfr_ids", "eval_ids", "intent_flags",
        "decision_ids", "deferred_ids", "decision_log_component", "deferred_items_component",
        "experience_contract_component",
        "supersedes", "created_by", "created_at",
    }
    if not set(source).issubset(allowed):
        raise BundleError("unknown-product-contract-input-field")
    contract_kind = source.get("contract_kind")
    if contract_kind not in {"feature", "patch", "remediation"}:
        raise BundleError("invalid-contract-kind")
    leaf_id = _id(source.get("leaf_id"), "leaf-id")
    source_request = _id(source.get("source_request"), "source-request")
    outcome_ids = _string_list(source.get("outcome_ids"), "outcome-ids", prefix="OUT-", nonempty=True)
    behavior_ids = _string_list(source.get("behavior_ids"), "behavior-ids", prefix="SCN-", nonempty=True)
    behavior_kinds = _behavior_kinds(source.get("behavior_kinds"), behavior_ids, contract_kind)
    domain_rule_ids = _string_list(source.get("domain_rule_ids", []), "domain-rule-ids", prefix="RULE-")
    experience_ids = _string_list(source.get("experience_ids", []), "experience-ids", prefix="EXP-")
    nfr_ids = _string_list(source.get("nfr_ids", []), "nfr-ids", prefix="NFR-")
    eval_ids = _string_list(source.get("eval_ids", []), "eval-ids", prefix="EVAL-")
    decision_ids = _string_list(source.get("decision_ids", []), "decision-ids", prefix="DEC-")
    deferred_ids = _string_list(source.get("deferred_ids", []), "deferred-ids", prefix="DEF-")
    intent_flags = _intent_flags(source.get("intent_flags"))
    supersedes_ref = _supersedes(source.get("supersedes"), subject_key="leaf_id", subject_id=leaf_id)
    created_by = _id(source.get("created_by"), "created-by")
    created_at = _text(source.get("created_at"), "created-at")
    components, descriptors = normalize_components(source.get("components"))
    decision_log_ref = _required_component_ref(
        source.get("decision_log_component"), label="decision-log", criterion_ids=decision_ids,
        descriptors=descriptors,
    )
    deferred_items_ref = _required_component_ref(
        source.get("deferred_items_component"), label="deferred-items", criterion_ids=deferred_ids,
        descriptors=descriptors,
    )
    experience_contract_ref = _required_component_ref(
        source.get("experience_contract_component"), label="experience-contract", criterion_ids=experience_ids,
        descriptors=descriptors,
    )
    metadata = _product_metadata(
        contract_kind=contract_kind, leaf_id=leaf_id, source_request=source_request,
        outcome_ids=outcome_ids, behavior_ids=behavior_ids, behavior_kinds=behavior_kinds,
        domain_rule_ids=domain_rule_ids, experience_ids=experience_ids, nfr_ids=nfr_ids,
        eval_ids=eval_ids, decision_ids=decision_ids, deferred_ids=deferred_ids,
        decision_log_ref=decision_log_ref, deferred_items_ref=deferred_items_ref,
        experience_contract_ref=experience_contract_ref, intent_flags=intent_flags,
        supersedes_ref=supersedes_ref,
    )
    bundle_sha256 = sha256_bytes(canonical_bytes({"metadata": metadata, "components": descriptors}))
    return {
        **metadata,
        "product_contract_id": bundle_sha256,
        "bundle_sha256": bundle_sha256,
        "components": descriptors,
        "created_by": created_by,
        "created_at": created_at,
    }


def _profile_metadata(
    *, feature_id: str, profile_bytes_sha256: str, source_repository_sha: str,
    source_path: str, profile_revision: str,
) -> dict[str, object]:
    return {
        "profile_format": "profile-snapshot-v1",
        "feature_id": feature_id,
        "profile_bytes_sha256": profile_bytes_sha256,
        "source_repository_sha": source_repository_sha,
        "source_path": source_path,
        "profile_revision": profile_revision,
    }


def snapshot_profile(
    profile_bytes: bytes | str,
    *,
    feature_id: str,
    source_sha: str,
    source_path: str = ".sdlc/PROFILE.md",
    profile_revision: str | None = None,
    created_at: str,
) -> dict[str, object]:
    """Snapshot PROFILE bytes so an EngineeringSpec never follows a mutable path."""
    feature_id = _id(feature_id, "feature-id")
    source_sha = _git_sha(source_sha, "profile-source-sha")
    source_path = _safe_profile_source_path(source_path)
    if not isinstance(profile_bytes, (bytes, str)):
        raise BundleError("invalid-profile-bytes")
    raw = profile_bytes if isinstance(profile_bytes, bytes) else profile_bytes.encode("utf-8")
    if not raw:
        raise BundleError("empty-profile-bytes")
    if profile_revision is None:
        profile_revision = source_sha
    profile_revision = _git_sha(profile_revision, "profile-revision")
    created_at = _text(created_at, "created-at")
    components = {"PROFILE.md": raw}
    _, descriptors = normalize_components(components)
    metadata = _profile_metadata(
        feature_id=feature_id, profile_bytes_sha256=sha256_bytes(raw),
        source_repository_sha=source_sha, source_path=source_path, profile_revision=profile_revision,
    )
    snapshot_id = sha256_bytes(canonical_bytes({"metadata": metadata, "components": descriptors}))
    return {
        **metadata,
        "profile_snapshot_id": snapshot_id,
        "components": descriptors,
        "created_at": created_at,
    }


def _safe_profile_source_path(value: object) -> str:
    path = _text(value, "profile-source-path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or path != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        raise BundleError("unsafe-profile-source-path")
    if path != ".sdlc/PROFILE.md":
        raise BundleError("profile-source-path-must-be-sdlc-profile")
    return path


def _product_projection(value: object) -> Mapping[str, object]:
    product = _mapping(value, "product-contract")
    if product.get("contract_format") != "product-contract-v1":
        raise BundleError("invalid-upstream-product-contract-format")
    _sha256(product.get("product_contract_id"), "upstream-product-contract-id")
    _sha256(product.get("bundle_sha256"), "upstream-product-contract-sha")
    if product["product_contract_id"] != product["bundle_sha256"]:
        raise BundleError("upstream-product-contract-id-mismatch")
    product_criteria: dict[str, list[str]] = {}
    for field, prefix in _PRODUCT_PREFIXES.items():
        product_criteria[field] = _string_list(
            product.get(field), f"upstream-{field}", prefix=prefix,
            nonempty=field in {"outcome_ids", "behavior_ids"},
        )
    descriptors = _descriptors_from_bundle(product)
    auxiliary_criteria: dict[str, list[str] | None] = {}
    for field, prefix in _PRODUCT_AUXILIARY_PREFIXES.items():
        auxiliary_criteria[field] = (
            _string_list(product.get(field), f"upstream-{field}", prefix=prefix)
            if field in product else None
        )
    component_refs: dict[str, dict[str, str] | None] = {}
    for field, label in (
        ("decision_log_ref", "decision-log"),
        ("deferred_items_ref", "deferred-items"),
        ("experience_contract_ref", "experience-contract"),
    ):
        component_refs[field] = (
            _component_ref_from_bundle(product[field], label=label, descriptors=descriptors)
            if field in product else None
        )
    for ids_field, ref_field, label in (
        ("decision_ids", "decision_log_ref", "decision-log"),
        ("deferred_ids", "deferred_items_ref", "deferred-items"),
    ):
        criterion_ids = auxiliary_criteria[ids_field]
        if criterion_ids is not None and bool(criterion_ids) != bool(component_refs[ref_field]):
            raise BundleError(f"{label}-criteria-and-component-must-match")
    if component_refs["experience_contract_ref"] is not None and not product_criteria["experience_ids"]:
        raise BundleError("experience-contract-component-without-criteria")
    return product


def _profile_projection(value: object, feature_id: str) -> Mapping[str, object]:
    profile = _mapping(value, "profile-snapshot")
    if profile.get("profile_format") != "profile-snapshot-v1":
        raise BundleError("invalid-profile-snapshot-format")
    _sha256(profile.get("profile_snapshot_id"), "profile-snapshot-id")
    _sha256(profile.get("profile_bytes_sha256"), "profile-bytes-sha")
    _git_sha(profile.get("source_repository_sha"), "profile-source-sha")
    _safe_profile_source_path(profile.get("source_path"))
    _git_sha(profile.get("profile_revision"), "profile-revision")
    if profile.get("feature_id") != feature_id:
        raise BundleError("profile-snapshot-feature-mismatch")
    return profile


def _engineering_metadata(
    *, feature_id: str, product_contract_ref: str, product_contract_revision: str,
    product_contract_approval_ref: str, profile_ref: str, profile_revision: str,
    profile_sha256: str, specified_against_sha: str, implements_product_ids: list[str],
    engineering_criterion_ids: list[str], target_surfaces: list[str], supersedes_ref: str | None,
) -> dict[str, object]:
    return {
        "spec_format": "engineering-spec-v1",
        "feature_id": feature_id,
        "product_contract_ref": product_contract_ref,
        "product_contract_revision": product_contract_revision,
        "product_contract_approval_ref": product_contract_approval_ref,
        "profile_ref": profile_ref,
        "profile_revision": profile_revision,
        "profile_sha256": profile_sha256,
        "specified_against_sha": specified_against_sha,
        "implements_product_ids": implements_product_ids,
        "engineering_criterion_ids": engineering_criterion_ids,
        "target_surfaces": target_surfaces,
        "supersedes_ref": supersedes_ref,
    }


def build_engineering_spec(
    value: Mapping[str, object], product_contract: Mapping[str, object], profile_snapshot: Mapping[str, object],
) -> dict[str, object]:
    """Build an EngineeringSpec pinned to immutable product and profile tuples."""
    source = _mapping(value, "engineering-spec-input")
    allowed = {
        "feature_id", "product_contract_ref", "product_contract_revision", "product_contract_approval_ref",
        "specified_against_sha", "implements_product_ids", "engineering_criterion_ids", "target_surfaces",
        "components", "supersedes", "created_by", "created_at",
    }
    if not set(source).issubset(allowed):
        raise BundleError("unknown-engineering-spec-input-field")
    feature_id = _id(source.get("feature_id"), "feature-id")
    product = _product_projection(product_contract)
    profile = _profile_projection(profile_snapshot, feature_id)
    product_id = _sha256(product["product_contract_id"], "upstream-product-contract-id")
    if source.get("product_contract_ref", product_id) != product_id:
        raise BundleError("product-contract-ref-mismatch")
    if source.get("product_contract_revision", product_id) != product_id:
        raise BundleError("product-contract-revision-mismatch")
    approval_ref = _sha256(source.get("product_contract_approval_ref"), "product-contract-approval-ref")
    specified_against_sha = _git_sha(source.get("specified_against_sha"), "specified-against-sha")
    known_product_ids = {
        item for field in _PRODUCT_PREFIXES for item in product.get(field, [])  # type: ignore[arg-type]
    }
    implements_product_ids = _string_list(source.get("implements_product_ids"), "implements-product-ids", nonempty=True)
    if not set(implements_product_ids).issubset(known_product_ids):
        raise BundleError("engineering-spec-implements-unknown-product-criterion")
    engineering_criterion_ids = _string_list(
        source.get("engineering_criterion_ids"), "engineering-criterion-ids",
        prefix=_ENGINEERING_PREFIXES, nonempty=True,
    )
    target_surfaces = _string_list(source.get("target_surfaces"), "target-surfaces", nonempty=True)
    supersedes_ref = _supersedes(source.get("supersedes"), subject_key="feature_id", subject_id=feature_id)
    created_by = _id(source.get("created_by"), "created-by")
    created_at = _text(source.get("created_at"), "created-at")
    _, descriptors = normalize_components(source.get("components"))
    metadata = _engineering_metadata(
        feature_id=feature_id, product_contract_ref=product_id, product_contract_revision=product_id,
        product_contract_approval_ref=approval_ref, profile_ref=_sha256(profile["profile_snapshot_id"], "profile-ref"),
        profile_revision=_git_sha(profile["profile_revision"], "profile-revision"),
        profile_sha256=_sha256(profile["profile_bytes_sha256"], "profile-sha"),
        specified_against_sha=specified_against_sha, implements_product_ids=implements_product_ids,
        engineering_criterion_ids=engineering_criterion_ids, target_surfaces=target_surfaces,
        supersedes_ref=supersedes_ref,
    )
    bundle_sha256 = sha256_bytes(canonical_bytes({"metadata": metadata, "components": descriptors}))
    return {
        **metadata,
        "engineering_spec_id": bundle_sha256,
        "bundle_sha256": bundle_sha256,
        "components": descriptors,
        "created_by": created_by,
        "created_at": created_at,
    }


def _descriptors_from_bundle(bundle: Mapping[str, object]) -> list[dict[str, str]]:
    raw = bundle.get("components")
    if not isinstance(raw, list) or not raw:
        raise BundleError("invalid-bundle-components")
    descriptors: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise BundleError("invalid-bundle-component-descriptor")
        descriptors.append({"path": _safe_component_path(item["path"]), "sha256": _sha256(item["sha256"], "component-sha")})
    if descriptors != sorted(descriptors, key=lambda item: item["path"]):
        raise BundleError("unsorted-bundle-components")
    if len({item["path"] for item in descriptors}) != len(descriptors):
        raise BundleError("duplicate-bundle-component-path")
    return descriptors


def _bundle_metadata(bundle: Mapping[str, object]) -> tuple[str, str, dict[str, object]]:
    if bundle.get("contract_format") == "product-contract-v1":
        product_id = _sha256(bundle.get("product_contract_id"), "product-contract-id")
        contract_kind = bundle.get("contract_kind")
        if contract_kind not in {"feature", "patch", "remediation"}:
            raise BundleError("invalid-contract-kind")
        leaf_id = _id(bundle.get("leaf_id"), "leaf-id")
        descriptors = _descriptors_from_bundle(bundle)
        decision_ids = (
            None if "decision_ids" not in bundle
            else _string_list(bundle.get("decision_ids"), "decision-ids", prefix="DEC-")
        )
        deferred_ids = (
            None if "deferred_ids" not in bundle
            else _string_list(bundle.get("deferred_ids"), "deferred-ids", prefix="DEF-")
        )
        decision_log_ref = (
            None if "decision_log_ref" not in bundle
            else _component_ref_from_bundle(bundle["decision_log_ref"], label="decision-log", descriptors=descriptors)
        )
        deferred_items_ref = (
            None if "deferred_items_ref" not in bundle
            else _component_ref_from_bundle(bundle["deferred_items_ref"], label="deferred-items", descriptors=descriptors)
        )
        experience_contract_ref = (
            None if "experience_contract_ref" not in bundle
            else _component_ref_from_bundle(bundle["experience_contract_ref"], label="experience-contract", descriptors=descriptors)
        )
        for criterion_ids, component_ref, label in (
            (decision_ids, decision_log_ref, "decision-log"),
            (deferred_ids, deferred_items_ref, "deferred-items"),
        ):
            if criterion_ids is not None and bool(criterion_ids) != bool(component_ref):
                raise BundleError(f"{label}-criteria-and-component-must-match")
        if experience_contract_ref is not None and not bundle.get("experience_ids"):
            raise BundleError("experience-contract-component-without-criteria")
        metadata = _product_metadata(
            contract_kind=str(contract_kind), leaf_id=leaf_id,
            source_request=_id(bundle.get("source_request"), "source-request"),
            outcome_ids=_string_list(bundle.get("outcome_ids"), "outcome-ids", prefix="OUT-", nonempty=True),
            behavior_ids=_string_list(bundle.get("behavior_ids"), "behavior-ids", prefix="SCN-", nonempty=True),
            behavior_kinds=_behavior_kinds(bundle.get("behavior_kinds"), _string_list(bundle.get("behavior_ids"), "behavior-ids", prefix="SCN-", nonempty=True), str(contract_kind)),
            domain_rule_ids=_string_list(bundle.get("domain_rule_ids"), "domain-rule-ids", prefix="RULE-"),
            experience_ids=_string_list(bundle.get("experience_ids"), "experience-ids", prefix="EXP-"),
            nfr_ids=_string_list(bundle.get("nfr_ids"), "nfr-ids", prefix="NFR-"),
            eval_ids=_string_list(bundle.get("eval_ids"), "eval-ids", prefix="EVAL-"),
            decision_ids=decision_ids,
            deferred_ids=deferred_ids,
            decision_log_ref=decision_log_ref,
            deferred_items_ref=deferred_items_ref,
            experience_contract_ref=experience_contract_ref,
            intent_flags=_intent_flags(bundle.get("intent_flags")),
            supersedes_ref=None if bundle.get("supersedes_ref") is None else _sha256(bundle.get("supersedes_ref"), "supersedes-ref"),
        )
        return "product_contract", product_id, metadata
    if bundle.get("profile_format") == "profile-snapshot-v1":
        snapshot_id = _sha256(bundle.get("profile_snapshot_id"), "profile-snapshot-id")
        metadata = _profile_metadata(
            feature_id=_id(bundle.get("feature_id"), "feature-id"),
            profile_bytes_sha256=_sha256(bundle.get("profile_bytes_sha256"), "profile-bytes-sha"),
            source_repository_sha=_git_sha(bundle.get("source_repository_sha"), "profile-source-sha"),
            source_path=_safe_profile_source_path(bundle.get("source_path")),
            profile_revision=_git_sha(bundle.get("profile_revision"), "profile-revision"),
        )
        return "profile_snapshot", snapshot_id, metadata
    if bundle.get("spec_format") == "engineering-spec-v1":
        spec_id = _sha256(bundle.get("engineering_spec_id"), "engineering-spec-id")
        metadata = _engineering_metadata(
            feature_id=_id(bundle.get("feature_id"), "feature-id"),
            product_contract_ref=_sha256(bundle.get("product_contract_ref"), "product-contract-ref"),
            product_contract_revision=_sha256(bundle.get("product_contract_revision"), "product-contract-revision"),
            product_contract_approval_ref=_sha256(bundle.get("product_contract_approval_ref"), "product-contract-approval-ref"),
            profile_ref=_sha256(bundle.get("profile_ref"), "profile-ref"),
            profile_revision=_git_sha(bundle.get("profile_revision"), "profile-revision"),
            profile_sha256=_sha256(bundle.get("profile_sha256"), "profile-sha"),
            specified_against_sha=_git_sha(bundle.get("specified_against_sha"), "specified-against-sha"),
            implements_product_ids=_string_list(bundle.get("implements_product_ids"), "implements-product-ids", nonempty=True),
            engineering_criterion_ids=_string_list(bundle.get("engineering_criterion_ids"), "engineering-criterion-ids", prefix=_ENGINEERING_PREFIXES, nonempty=True),
            target_surfaces=_string_list(bundle.get("target_surfaces"), "target-surfaces", nonempty=True),
            supersedes_ref=None if bundle.get("supersedes_ref") is None else _sha256(bundle.get("supersedes_ref"), "supersedes-ref"),
        )
        return "engineering_spec", spec_id, metadata
    raise BundleError("unsupported-bundle-format")


def verify_bundle(bundle: Mapping[str, object], components: Mapping[str, object]) -> str:
    """Recompute a bundle's closure using supplied immutable bytes.

    The caller must supply the stored component bytes.  A local source path is
    intentionally not accepted, so verification cannot accidentally follow a
    newer draft or PROFILE file.
    """
    source = _mapping(bundle, "bundle")
    _, identity, metadata = _bundle_metadata(source)
    declared_hash = _sha256(source.get("bundle_sha256", identity), "bundle-sha")
    if declared_hash != identity:
        raise BundleError("bundle-id-and-sha-mismatch")
    _, actual_descriptors = normalize_components(components)
    if _descriptors_from_bundle(source) != actual_descriptors:
        raise BundleError("component-closure-mismatch")
    actual = sha256_bytes(canonical_bytes({"metadata": metadata, "components": actual_descriptors}))
    if actual != identity:
        raise BundleError("bundle-hash-mismatch")
    if source.get("profile_format") == "profile-snapshot-v1":
        profile_bytes = components.get("PROFILE.md")
        if profile_bytes is None or sha256_bytes(_component_bytes(profile_bytes, "PROFILE.md")) != source.get("profile_bytes_sha256"):
            raise BundleError("profile-bytes-hash-mismatch")
    return identity
