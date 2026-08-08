#!/usr/bin/env python3
"""Strict, stateless artifact helpers for the dual-lifecycle ledger.

The helpers in this module do not read or write a filesystem and do not make
workflow decisions.  They only normalize immutable bytes, bind execution or
release facts to the current lifecycle tuple, and re-verify every identity at
the storage boundary.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from typing import Mapping

import contract_bundle
import evidence_runner


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TRACE_REF_RE = re.compile(r"^(PC|ES):([0-9a-f]{64})#([A-Z][A-Z0-9]*-[0-9]{3,})$")

_FENCE_FIELDS = (
    "contract_generation",
    "product_contract_ref",
    "product_contract_approval_ref",
    "engineering_spec_ref",
    "engineering_spec_approval_ref",
    "delivery_plan_ref",
)

_PRODUCT_BUNDLE_FIELDS = frozenset({
    "contract_format", "contract_kind", "leaf_id", "source_request", "outcome_ids",
    "behavior_ids", "behavior_kinds", "domain_rule_ids", "experience_ids", "nfr_ids",
    "eval_ids", "intent_flags", "supersedes_ref", "product_contract_id", "bundle_sha256",
    "components", "created_by", "created_at",
})
_PRODUCT_BUNDLE_OPTIONAL_FIELDS = frozenset({
    "decision_ids", "deferred_ids", "decision_log_ref", "deferred_items_ref", "experience_contract_ref",
})
_PROFILE_BUNDLE_FIELDS = frozenset({
    "profile_format", "feature_id", "profile_bytes_sha256", "source_repository_sha",
    "source_path", "profile_revision", "profile_snapshot_id", "components", "created_at",
})
_ENGINEERING_BUNDLE_FIELDS = frozenset({
    "spec_format", "feature_id", "product_contract_ref", "product_contract_revision",
    "product_contract_approval_ref", "profile_ref", "profile_revision", "profile_sha256",
    "specified_against_sha", "implements_product_ids", "engineering_criterion_ids",
    "target_surfaces", "supersedes_ref", "engineering_spec_id", "bundle_sha256",
    "components", "created_by", "created_at",
})

_BUNDLE_ARTIFACT_FIELDS = frozenset({
    "artifact_format", "artifact_kind", "artifact_id", "bundle", "components",
    "artifact_sha256",
})
_STORED_COMPONENT_FIELDS = frozenset({"path", "encoding", "content", "sha256"})

_RUNNER_RECORD_FIELDS = frozenset({
    "schema_version", "scope", "argv", "cwd_identity", "timeout_seconds", "timed_out",
    "exit_code", "stdout", "stderr", "tool_version", "code_sha", "policy_manifest_ref",
    "context_manifest_ref", "evidence_id",
})
_RUNNER_OUTPUT_FIELDS = frozenset({"sha256", "bytes", "truncated", "encoding", "preview"})
_RUNNER_RECEIPT_FIELDS = frozenset({
    "receipt_format", "runner_record_ref", "runner_record", "command", "exit_code",
    "timed_out", "result", "tested_sha", "feature_id", "task_id", "trace_refs",
    "receipt_id", *_FENCE_FIELDS,
})

_RELEASE_TARGET_FIELDS = frozenset({"environment", "target_type", "target_ref"})
_RELEASE_ARTIFACT_FIELDS = frozenset({"artifact_type", "artifact_ref", "artifact_sha256"})
_RELEASE_RECEIPT_FIELDS = frozenset({
    "receipt_format", "runner_record_ref", "runner_record", "command", "exit_code",
    "timed_out", "result", "tested_code_sha256", "feature_id", "release_target",
    "actual_release_artifact", "release_sha", "receipt_id", *_FENCE_FIELDS,
})


class ArtifactStoreError(ValueError):
    """An artifact is non-canonical, incomplete, or fails identity verification."""


def _normalize_json(value: object, *, depth: int = 0) -> object:
    if depth > 32:
        raise ArtifactStoreError("canonical-json-too-deep")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArtifactStoreError("non-finite-canonical-json-number")
        return value
    if isinstance(value, list):
        return [_normalize_json(item, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) or not key for key in value):
            raise ArtifactStoreError("invalid-canonical-json-key")
        return {
            key: _normalize_json(value[key], depth=depth + 1)
            for key in sorted(value)
        }
    raise ArtifactStoreError("invalid-canonical-json-value")


def canonical_json_bytes(value: object) -> bytes:
    """Return the repository's deterministic UTF-8 JSON representation."""
    try:
        rendered = json.dumps(
            _normalize_json(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return (rendered + "\n").encode("utf-8")
    except ArtifactStoreError:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ArtifactStoreError("invalid-canonical-json") from exc


def _content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ArtifactStoreError(f"invalid-{label}")
    return value


def _exact_fields(
    value: object, expected: frozenset[str], label: str,
) -> Mapping[str, object]:
    source = _mapping(value, label)
    actual = set(source)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "-"
        unknown = ",".join(sorted(actual - expected)) or "-"
        raise ArtifactStoreError(f"{label}-fields:missing={missing};unknown={unknown}")
    return source


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ArtifactStoreError(f"invalid-{label}")
    return value


def _one_line_text(value: object, label: str) -> str:
    result = _text(value, label)
    if "\n" in result or "\r" in result:
        raise ArtifactStoreError(f"invalid-{label}")
    return result


def _id(value: object, label: str) -> str:
    result = _text(value, label)
    if not _ID_RE.fullmatch(result) or ".." in result:
        raise ArtifactStoreError(f"invalid-{label}")
    return result


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ArtifactStoreError(f"invalid-{label}")
    return value


def _git_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ArtifactStoreError(f"invalid-{label}")
    return value


def _normalize_bundle(bundle: object) -> tuple[dict[str, object], str, str]:
    source = _mapping(bundle, "bundle")
    if "contract_format" in source:
        # product-contract-v1 predates its decision/deferred/experience
        # section pointers. Existing records remain valid; new optional
        # sections are accepted only from this closed extension set.
        expected = _PRODUCT_BUNDLE_FIELDS | (set(source) & _PRODUCT_BUNDLE_OPTIONAL_FIELDS)
        source = _exact_fields(source, expected, "bundle")
        if source["contract_format"] != "product-contract-v1":
            raise ArtifactStoreError("unsupported-bundle-format")
        kind = "product_contract"
        identity = _sha256(source["product_contract_id"], "product-contract-id")
        _id(source["created_by"], "created-by")
        _text(source["created_at"], "created-at")
    elif "profile_format" in source:
        source = _exact_fields(source, _PROFILE_BUNDLE_FIELDS, "bundle")
        if source["profile_format"] != "profile-snapshot-v1":
            raise ArtifactStoreError("unsupported-bundle-format")
        kind = "profile_snapshot"
        identity = _sha256(source["profile_snapshot_id"], "profile-snapshot-id")
        _text(source["created_at"], "created-at")
    elif "spec_format" in source:
        source = _exact_fields(source, _ENGINEERING_BUNDLE_FIELDS, "bundle")
        if source["spec_format"] != "engineering-spec-v1":
            raise ArtifactStoreError("unsupported-bundle-format")
        kind = "engineering_spec"
        identity = _sha256(source["engineering_spec_id"], "engineering-spec-id")
        _id(source["created_by"], "created-by")
        _text(source["created_at"], "created-at")
    else:
        raise ArtifactStoreError("unsupported-bundle-format")
    normalized = _normalize_json(source)
    if not isinstance(normalized, dict):  # Kept explicit for type checkers and custom Mapping inputs.
        raise ArtifactStoreError("invalid-bundle")
    return normalized, kind, identity


def _verify_contract_bundle(bundle: Mapping[str, object], components: Mapping[str, bytes]) -> str:
    try:
        return contract_bundle.verify_bundle(bundle, components)
    except contract_bundle.BundleError as exc:
        raise ArtifactStoreError(f"bundle-verification:{exc}") from exc


def _normalized_components(value: object) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    try:
        return contract_bundle.normalize_components(value)
    except contract_bundle.BundleError as exc:
        raise ArtifactStoreError(f"component-normalization:{exc}") from exc


def _store_components(components: Mapping[str, bytes]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for path in sorted(components):
        raw = components[path]
        try:
            content = raw.decode("utf-8", errors="strict")
            encoding = "utf-8"
        except UnicodeDecodeError:
            content = base64.b64encode(raw).decode("ascii")
            encoding = "base64"
        result.append({
            "path": path,
            "encoding": encoding,
            "content": content,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return result


def _decode_components(value: object) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    if not isinstance(value, list) or not value:
        raise ArtifactStoreError("invalid-artifact-components")
    stored: list[dict[str, str]] = []
    components: dict[str, bytes] = {}
    for item in value:
        source = _exact_fields(item, _STORED_COMPONENT_FIELDS, "artifact-component")
        path = _text(source["path"], "component-path")
        if path in components:
            raise ArtifactStoreError(f"duplicate-component-path:{path}")
        encoding = source["encoding"]
        content = source["content"]
        if not isinstance(content, str):
            raise ArtifactStoreError(f"invalid-component-content:{path}")
        if encoding == "utf-8":
            try:
                raw = content.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ArtifactStoreError(f"invalid-component-utf8:{path}") from exc
        elif encoding == "base64":
            try:
                encoded = content.encode("ascii", errors="strict")
                raw = base64.b64decode(encoded, validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                raise ArtifactStoreError(f"invalid-component-base64:{path}") from exc
            if base64.b64encode(raw).decode("ascii") != content:
                raise ArtifactStoreError(f"noncanonical-component-base64:{path}")
            try:
                raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                pass
            else:
                raise ArtifactStoreError(f"noncanonical-component-encoding:{path}")
        else:
            raise ArtifactStoreError(f"invalid-component-encoding:{path}")
        declared_sha = _sha256(source["sha256"], "component-sha")
        if hashlib.sha256(raw).hexdigest() != declared_sha:
            raise ArtifactStoreError(f"component-sha-mismatch:{path}")
        components[path] = raw
        stored.append({
            "path": path,
            "encoding": str(encoding),
            "content": content,
            "sha256": declared_sha,
        })
    paths = [item["path"] for item in stored]
    if paths != sorted(paths):
        raise ArtifactStoreError("unsorted-artifact-components")
    # Reuse the contract module's path, emptiness, and descriptor checks.
    normalized, descriptors = _normalized_components(components)
    expected_descriptors = [
        {"path": item["path"], "sha256": item["sha256"]}
        for item in stored
    ]
    if descriptors != expected_descriptors:
        raise ArtifactStoreError("component-descriptor-mismatch")
    return stored, normalized


def build_bundle_artifact(
    bundle: Mapping[str, object], components: Mapping[str, object],
) -> dict[str, object]:
    """Pack one verified contract/profile/spec bundle into canonical JSON data."""
    normalized_bundle, kind, identity = _normalize_bundle(bundle)
    normalized_components, _ = _normalized_components(components)
    verified = _verify_contract_bundle(normalized_bundle, normalized_components)
    if verified != identity:
        raise ArtifactStoreError("bundle-identity-mismatch")
    preimage: dict[str, object] = {
        "artifact_format": "dual-bundle-artifact-v1",
        "artifact_kind": kind,
        "artifact_id": identity,
        "bundle": normalized_bundle,
        "components": _store_components(normalized_components),
    }
    return {**preimage, "artifact_sha256": _content_sha256(preimage)}


def _verified_bundle_artifact(
    artifact: Mapping[str, object],
) -> tuple[str, dict[str, object], dict[str, bytes]]:
    source = _exact_fields(artifact, _BUNDLE_ARTIFACT_FIELDS, "artifact")
    if source["artifact_format"] != "dual-bundle-artifact-v1":
        raise ArtifactStoreError("unsupported-artifact-format")
    artifact_kind = source["artifact_kind"]
    if artifact_kind not in {"product_contract", "profile_snapshot", "engineering_spec"}:
        raise ArtifactStoreError("invalid-artifact-kind")
    artifact_id = _sha256(source["artifact_id"], "artifact-id")
    bundle, bundle_kind, bundle_id = _normalize_bundle(source["bundle"])
    stored_components, components = _decode_components(source["components"])
    verified = _verify_contract_bundle(bundle, components)
    if (artifact_kind, artifact_id) != (bundle_kind, bundle_id) or verified != artifact_id:
        raise ArtifactStoreError("artifact-bundle-identity-mismatch")
    declared_artifact_sha = _sha256(source["artifact_sha256"], "artifact-sha256")
    preimage = {
        "artifact_format": "dual-bundle-artifact-v1",
        "artifact_kind": artifact_kind,
        "artifact_id": artifact_id,
        "bundle": bundle,
        "components": stored_components,
    }
    if _content_sha256(preimage) != declared_artifact_sha:
        raise ArtifactStoreError("artifact-content-hash-mismatch")
    return artifact_id, bundle, components


def verify_bundle_artifact(artifact: Mapping[str, object]) -> str:
    """Verify the envelope hash, every component, and the contract closure."""
    identity, _, _ = _verified_bundle_artifact(artifact)
    return identity


def unpack_bundle_artifact(
    artifact: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, bytes]]:
    """Verify and return a detached bundle plus its exact component bytes."""
    _, bundle, components = _verified_bundle_artifact(artifact)
    return bundle, components


def _argv(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ArtifactStoreError(f"invalid-{label}")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item or "\x00" in item:
            raise ArtifactStoreError(f"invalid-{label}-{index}")
        result.append(item)
    return result


def _runner_output(value: object, label: str) -> dict[str, object]:
    source = _exact_fields(value, _RUNNER_OUTPUT_FIELDS, f"runner-{label}")
    digest = _sha256(source["sha256"], f"runner-{label}-sha")
    byte_count = source["bytes"]
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        raise ArtifactStoreError(f"invalid-runner-{label}-bytes")
    truncated = source["truncated"]
    if not isinstance(truncated, bool):
        raise ArtifactStoreError(f"invalid-runner-{label}-truncated")
    encoding = source["encoding"]
    if encoding not in {"utf-8", "binary"}:
        raise ArtifactStoreError(f"invalid-runner-{label}-encoding")
    preview = source["preview"]
    if not isinstance(preview, str):
        raise ArtifactStoreError(f"invalid-runner-{label}-preview")
    if not truncated and encoding == "utf-8":
        preview_bytes = preview.encode("utf-8")
        if len(preview_bytes) != byte_count or hashlib.sha256(preview_bytes).hexdigest() != digest:
            raise ArtifactStoreError(f"runner-{label}-preview-mismatch")
    return {
        "sha256": digest,
        "bytes": byte_count,
        "truncated": truncated,
        "encoding": str(encoding),
        "preview": preview,
    }


def _normalize_runner_record(value: object) -> dict[str, object]:
    source = _exact_fields(value, _RUNNER_RECORD_FIELDS, "runner-record")
    if source["schema_version"] != "canonical-runner-evidence-v1" or source["scope"] != "canonical":
        raise ArtifactStoreError("runner-record-must-be-canonical")
    argv = _argv(source["argv"], "runner-argv")
    cwd_identity = _sha256(source["cwd_identity"], "runner-cwd-identity")
    timeout_seconds = source["timeout_seconds"]
    if not isinstance(timeout_seconds, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ArtifactStoreError("invalid-runner-timeout-seconds")
    timed_out = source["timed_out"]
    if not isinstance(timed_out, bool):
        raise ArtifactStoreError("invalid-runner-timed-out")
    exit_code = source["exit_code"]
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise ArtifactStoreError("invalid-runner-exit-code")
    stdout = _runner_output(source["stdout"], "stdout")
    stderr = _runner_output(source["stderr"], "stderr")
    tool_version = _text(source["tool_version"], "runner-tool-version")
    code_sha = _sha256(source["code_sha"], "runner-code-sha")
    policy_ref = _sha256(source["policy_manifest_ref"], "runner-policy-manifest-ref")
    context_ref = _sha256(source["context_manifest_ref"], "runner-context-manifest-ref")
    evidence_id = _sha256(source["evidence_id"], "runner-evidence-id")
    normalized: dict[str, object] = {
        "schema_version": "canonical-runner-evidence-v1",
        "scope": "canonical",
        "argv": argv,
        "cwd_identity": cwd_identity,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "tool_version": tool_version,
        "code_sha": code_sha,
        "policy_manifest_ref": policy_ref,
        "context_manifest_ref": context_ref,
        "evidence_id": evidence_id,
    }
    evidence_preimage = {
        **{key: normalized[key] for key in (
            "schema_version", "scope", "argv", "cwd_identity", "timeout_seconds", "timed_out",
            "exit_code",
        )},
        "stdout": {key: stdout[key] for key in ("sha256", "bytes", "truncated", "encoding")},
        "stderr": {key: stderr[key] for key in ("sha256", "bytes", "truncated", "encoding")},
        **{key: normalized[key] for key in (
            "tool_version", "code_sha", "policy_manifest_ref", "context_manifest_ref",
        )},
    }
    recomputed = hashlib.sha256(evidence_runner.canonical_bytes(evidence_preimage)).hexdigest()
    if recomputed != evidence_id:
        raise ArtifactStoreError("runner-evidence-hash-mismatch")
    try:
        evidence_runner.derive_mechanical_facts(normalized)
    except evidence_runner.EvidenceError as exc:
        raise ArtifactStoreError(f"invalid-runner-mechanical-facts:{exc}") from exc
    return normalized


def _current_tuple(value: object) -> dict[str, object]:
    source = _exact_fields(value, frozenset(_FENCE_FIELDS), "current-tuple")
    generation = source["contract_generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise ArtifactStoreError("invalid-contract-generation")
    return {
        "contract_generation": generation,
        **{
            field: _sha256(source[field], field.replace("_", "-"))
            for field in _FENCE_FIELDS[1:]
        },
    }


def _trace_refs(value: object, *, require_sorted: bool) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ArtifactStoreError("invalid-trace-refs")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _TRACE_REF_RE.fullmatch(item):
            raise ArtifactStoreError(f"invalid-trace-ref:{item}")
        result.append(item)
    if len(result) != len(set(result)):
        raise ArtifactStoreError("duplicate-trace-ref")
    normalized = sorted(result)
    if require_sorted and result != normalized:
        raise ArtifactStoreError("unsorted-trace-refs")
    return normalized


def build_runner_receipt(
    runner_record: Mapping[str, object],
    *,
    tested_sha: str,
    feature_id: str,
    task_id: str,
    current_tuple: Mapping[str, object],
    trace_refs: list[str],
) -> dict[str, object]:
    """Build a receipt from verified runner facts; no result input is accepted."""
    runner = _normalize_runner_record(runner_record)
    tested_sha = _sha256(tested_sha, "tested-sha")
    if tested_sha != runner["code_sha"]:
        raise ArtifactStoreError("tested-sha-runner-mismatch")
    feature_id = _id(feature_id, "feature-id")
    task_id = _id(task_id, "task-id")
    fence = _current_tuple(current_tuple)
    traces = _trace_refs(trace_refs, require_sorted=False)
    exit_code = runner["exit_code"]
    timed_out = runner["timed_out"]
    preimage: dict[str, object] = {
        "receipt_format": "runner-receipt-v1",
        "runner_record_ref": runner["evidence_id"],
        "runner_record": runner,
        "command": runner["argv"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "result": "pass" if exit_code == 0 and timed_out is False else "fail",
        "tested_sha": tested_sha,
        "feature_id": feature_id,
        "task_id": task_id,
        **fence,
        "trace_refs": traces,
    }
    return {**preimage, "receipt_id": _content_sha256(preimage)}


def verify_runner_receipt(
    receipt: Mapping[str, object],
    *,
    expected_tested_sha: str,
    expected_feature_id: str,
    expected_task_id: str,
    expected_current_tuple: Mapping[str, object],
    expected_trace_refs: list[str],
) -> str:
    """Verify receipt integrity and its expected ledger/task binding."""
    source = _exact_fields(receipt, _RUNNER_RECEIPT_FIELDS, "runner-receipt")
    if source["receipt_format"] != "runner-receipt-v1":
        raise ArtifactStoreError("unsupported-runner-receipt-format")
    runner = _normalize_runner_record(source["runner_record"])
    runner_ref = _sha256(source["runner_record_ref"], "runner-record-ref")
    command = _argv(source["command"], "receipt-command")
    exit_code = source["exit_code"]
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise ArtifactStoreError("invalid-receipt-exit-code")
    timed_out = source["timed_out"]
    if not isinstance(timed_out, bool):
        raise ArtifactStoreError("invalid-receipt-timed-out")
    result = source["result"]
    if result not in {"pass", "fail"}:
        raise ArtifactStoreError("invalid-receipt-result")
    derived_result = "pass" if runner["exit_code"] == 0 and runner["timed_out"] is False else "fail"
    if (
        runner_ref != runner["evidence_id"]
        or command != runner["argv"]
        or exit_code != runner["exit_code"]
        or timed_out != runner["timed_out"]
        or result != derived_result
    ):
        raise ArtifactStoreError("runner-fact-mismatch")
    tested_sha = _sha256(source["tested_sha"], "tested-sha")
    if tested_sha != runner["code_sha"]:
        raise ArtifactStoreError("tested-sha-runner-mismatch")
    feature_id = _id(source["feature_id"], "feature-id")
    task_id = _id(source["task_id"], "task-id")
    fence = _current_tuple({field: source[field] for field in _FENCE_FIELDS})
    traces = _trace_refs(source["trace_refs"], require_sorted=True)
    receipt_id = _sha256(source["receipt_id"], "runner-receipt-id")
    preimage: dict[str, object] = {
        "receipt_format": "runner-receipt-v1",
        "runner_record_ref": runner_ref,
        "runner_record": runner,
        "command": command,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "result": result,
        "tested_sha": tested_sha,
        "feature_id": feature_id,
        "task_id": task_id,
        **fence,
        "trace_refs": traces,
    }
    if _content_sha256(preimage) != receipt_id:
        raise ArtifactStoreError("receipt-content-hash-mismatch")

    expected_sha = _sha256(expected_tested_sha, "expected-tested-sha")
    expected_feature = _id(expected_feature_id, "expected-feature-id")
    expected_task = _id(expected_task_id, "expected-task-id")
    expected_fence = _current_tuple(expected_current_tuple)
    expected_traces = _trace_refs(expected_trace_refs, require_sorted=False)
    if tested_sha != expected_sha:
        raise ArtifactStoreError("tested-sha-mismatch")
    if feature_id != expected_feature:
        raise ArtifactStoreError("feature-id-mismatch")
    if task_id != expected_task:
        raise ArtifactStoreError("task-id-mismatch")
    if fence != expected_fence:
        raise ArtifactStoreError("current-tuple-mismatch")
    if traces != expected_traces:
        raise ArtifactStoreError("trace-refs-mismatch")
    return receipt_id


def _release_target(value: object) -> dict[str, str]:
    source = _exact_fields(value, _RELEASE_TARGET_FIELDS, "release-target")
    return {
        "environment": _id(source["environment"], "release-environment"),
        "target_type": _id(source["target_type"], "release-target-type"),
        "target_ref": _one_line_text(source["target_ref"], "release-target-ref"),
    }


def _release_artifact(value: object) -> dict[str, str]:
    source = _exact_fields(value, _RELEASE_ARTIFACT_FIELDS, "release-artifact")
    return {
        "artifact_type": _id(source["artifact_type"], "release-artifact-type"),
        "artifact_ref": _one_line_text(source["artifact_ref"], "release-artifact-ref"),
        "artifact_sha256": _sha256(source["artifact_sha256"], "release-artifact-sha256"),
    }


def build_release_receipt(
    runner_record: Mapping[str, object],
    *,
    feature_id: str,
    release_target: Mapping[str, object],
    actual_release_artifact: Mapping[str, object],
    release_sha: str,
    current_tuple: Mapping[str, object],
) -> dict[str, object]:
    """Build release proof only from a successful canonical runner record."""
    runner = _normalize_runner_record(runner_record)
    artifact = _release_artifact(actual_release_artifact)
    tested_code_sha256 = str(runner["code_sha"])
    exit_code = runner["exit_code"]
    timed_out = runner["timed_out"]
    if exit_code != 0 or timed_out is not False:
        raise ArtifactStoreError("release-runner-not-successful")
    fence = _current_tuple(current_tuple)
    preimage: dict[str, object] = {
        "receipt_format": "release-receipt-v2",
        "runner_record_ref": runner["evidence_id"],
        "runner_record": runner,
        "command": runner["argv"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "result": "pass",
        "tested_code_sha256": tested_code_sha256,
        "feature_id": _id(feature_id, "feature-id"),
        "release_target": _release_target(release_target),
        "actual_release_artifact": artifact,
        "release_sha": _git_sha(release_sha, "release-sha"),
        **fence,
    }
    return {**preimage, "receipt_id": _content_sha256(preimage)}


def verify_release_receipt(
    receipt: Mapping[str, object],
    *,
    expected_runner_record_ref: str,
    expected_feature_id: str,
    expected_release_target: Mapping[str, object],
    expected_actual_release_artifact: Mapping[str, object],
    expected_release_sha: str,
    expected_current_tuple: Mapping[str, object],
) -> str:
    """Verify runner success, receipt integrity, and expected release binding."""
    unvalidated = _mapping(receipt, "release-receipt")
    if unvalidated.get("receipt_format") != "release-receipt-v2":
        raise ArtifactStoreError("unsupported-release-receipt-format")
    source = _exact_fields(unvalidated, _RELEASE_RECEIPT_FIELDS, "release-receipt")
    runner = _normalize_runner_record(source["runner_record"])
    runner_ref = _sha256(source["runner_record_ref"], "runner-record-ref")
    command = _argv(source["command"], "release-command")
    exit_code = source["exit_code"]
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise ArtifactStoreError("invalid-release-exit-code")
    timed_out = source["timed_out"]
    if not isinstance(timed_out, bool):
        raise ArtifactStoreError("invalid-release-timed-out")
    result = source["result"]
    if result not in {"pass", "fail"}:
        raise ArtifactStoreError("invalid-release-result")
    derived_result = "pass" if runner["exit_code"] == 0 and runner["timed_out"] is False else "fail"
    if (
        runner_ref != runner["evidence_id"]
        or command != runner["argv"]
        or exit_code != runner["exit_code"]
        or timed_out != runner["timed_out"]
        or result != derived_result
    ):
        raise ArtifactStoreError("release-runner-fact-mismatch")
    if derived_result != "pass":
        raise ArtifactStoreError("release-runner-not-successful")
    tested_code_sha256 = _sha256(
        source["tested_code_sha256"], "tested-code-sha256",
    )
    feature_id = _id(source["feature_id"], "feature-id")
    target = _release_target(source["release_target"])
    artifact = _release_artifact(source["actual_release_artifact"])
    if tested_code_sha256 != runner["code_sha"]:
        raise ArtifactStoreError("release-code-runner-mismatch")
    release_sha = _git_sha(source["release_sha"], "release-sha")
    fence = _current_tuple({field: source[field] for field in _FENCE_FIELDS})
    receipt_id = _sha256(source["receipt_id"], "release-receipt-id")
    preimage: dict[str, object] = {
        "receipt_format": "release-receipt-v2",
        "runner_record_ref": runner_ref,
        "runner_record": runner,
        "command": command,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "result": result,
        "tested_code_sha256": tested_code_sha256,
        "feature_id": feature_id,
        "release_target": target,
        "actual_release_artifact": artifact,
        "release_sha": release_sha,
        **fence,
    }
    if _content_sha256(preimage) != receipt_id:
        raise ArtifactStoreError("receipt-content-hash-mismatch")

    expected_runner_ref = _sha256(expected_runner_record_ref, "expected-runner-record-ref")
    expected_feature = _id(expected_feature_id, "expected-feature-id")
    expected_target = _release_target(expected_release_target)
    expected_artifact = _release_artifact(expected_actual_release_artifact)
    expected_sha = _git_sha(expected_release_sha, "expected-release-sha")
    expected_fence = _current_tuple(expected_current_tuple)
    if runner_ref != expected_runner_ref:
        raise ArtifactStoreError("runner-record-ref-mismatch")
    if feature_id != expected_feature:
        raise ArtifactStoreError("feature-id-mismatch")
    if target != expected_target:
        raise ArtifactStoreError("release-target-mismatch")
    if artifact != expected_artifact:
        raise ArtifactStoreError("actual-release-artifact-mismatch")
    if release_sha != expected_sha:
        raise ArtifactStoreError("release-sha-mismatch")
    if fence != expected_fence:
        raise ArtifactStoreError("current-tuple-mismatch")
    return receipt_id


__all__ = [
    "ArtifactStoreError",
    "build_bundle_artifact",
    "build_release_receipt",
    "build_runner_receipt",
    "canonical_json_bytes",
    "unpack_bundle_artifact",
    "verify_bundle_artifact",
    "verify_release_receipt",
    "verify_runner_receipt",
]
