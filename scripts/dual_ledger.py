#!/usr/bin/env python3
"""Durable local CAS ledger for the canonical dual-lifecycle reducer.

The legacy SDLC control files deliberately remain untouched.  This module owns
``.sdlc-control/dual-lifecycle/ledger.json`` plus a small fsynced execution
recovery marker, and keeps the complete canonical snapshot plus its append-only
audit events in one atomically replaced JSON document.

The local filesystem is the authority boundary in v1: callers should invoke
``DualLifecycleLedger.apply`` inside any higher-level control transaction they
already use.  This module does not attempt a Git ref update or remote lease.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Iterator, Mapping, Sequence

import approval
import dual_artifact_store
import dual_authority
import evidence_runner
import lifecycle_reducer
import review_attestation


LEDGER_FORMAT = "dual-lifecycle-ledger-wrapper-v1"
LEDGER_VERSION = 1
EVENT_FORMAT = "dual-lifecycle-ledger-event-v3"
CONTROL_DIRECTORY = ".sdlc-control"
NAMESPACE_DIRECTORY = "dual-lifecycle"
LEDGER_FILENAME = "ledger.json"
LOCK_FILENAME = "ledger.lock"
AUTHORITY_FILENAME = "authority.json"
EXECUTION_JOURNAL_FILENAME = "execution.json"
EXECUTION_JOURNAL_FORMAT = "dual-lifecycle-execution-journal-v1"

# This is intentionally not a SHA-256 value.  It is accepted only when the
# ledger file does not exist, and the first event records it as its predecessor.
ABSENT_SNAPSHOT_SHA256 = "absent"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WRAPPER_FIELDS = frozenset({"ledger_format", "ledger_version", "snapshot", "snapshot_sha256", "events"})
_EVENT_FIELDS = frozenset({
    "event_format", "sequence", "idempotency_key",
    "requested_intent", "requested_intent_sha256", "intent", "intent_sha256",
    "previous_snapshot_sha256", "next_snapshot_sha256", "timestamp", "event_sha256",
})
_EXECUTION_JOURNAL_FIELDS = frozenset({
    "journal_format", "idempotency_key", "requested_intent_sha256", "operation",
})
_RAW_INTERNAL_OPERATIONS = frozenset({
    "apply_approval", "accept_change_request", "reject_change_request", "cancel_change_request",
    "record_evidence", "review_feature", "ship_feature",
})
_PUBLIC_APPROVAL_FORBIDDEN_FIELDS = frozenset({
    "approval_record", "authorization_policy", "authorization_policy_ref", "policy", "policy_id",
    "principal", "principal_ref", "principal_role", "roles", "authn_method", "authn_assurance",
    "previous_approval_ref", "predecessor", "authority_mode", "authority_format",
})
_PUBLIC_REQUEST_APPROVAL_REQUIRED_FIELDS = frozenset({
    "operation", "subject_type", "subject_id", "decision", "decision_intent_ref", "at",
})
_PUBLIC_REQUEST_APPROVAL_OPTIONAL_FIELDS = frozenset({"resolves_change_requests"})
_PUBLIC_DECIDE_CHANGE_REQUEST_FIELDS = frozenset({
    "operation", "change_request_id", "decision", "at",
})
_CHANGE_REQUEST_INTERNAL_OPERATION = {
    "accept": "accept_change_request",
    "reject": "reject_change_request",
    "cancel": "cancel_change_request",
}
_PUBLIC_EXECUTE_TASK_EVIDENCE_FIELDS = frozenset({
    "operation", "feature_id", "task_id", "fence", "argv", "cwd", "timeout_seconds",
    "policy_manifest_ref", "context_manifest_ref", "tool_version", "at",
})
_PUBLIC_PUBLISH_FEATURE_FIELDS = frozenset({
    "operation", "feature_id", "fence", "release_target", "actual_release_artifact",
    "artifact_path", "argv", "cwd", "timeout_seconds", "policy_manifest_ref",
    "context_manifest_ref", "tool_version", "at",
})
_PUBLIC_SUBMIT_FEATURE_REVIEW_FIELDS = frozenset({
    "operation", "feature_id", "fence", "decision", "evidence_refs", "rationale_ref",
    "policy_manifest_ref", "context_manifest_ref", "at",
})
_PUBLIC_RELEASE_TARGET_FIELDS = frozenset({"environment", "target_type", "target_ref"})
_PUBLIC_RELEASE_ARTIFACT_FIELDS = frozenset({"artifact_type", "artifact_ref"})
_MAX_CANONICAL_TIMEOUT_SECONDS = 300.0
_MAX_RELEASE_ARTIFACT_BYTES = 128 * 1024 * 1024
_LIFECYCLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHELL_EXECUTABLES = frozenset({"sh", "bash", "dash", "zsh", "ksh", "fish", "cmd", "powershell", "pwsh"})


class LedgerError(RuntimeError):
    """Base class for durable dual-lifecycle ledger failures."""


class LedgerParseError(LedgerError):
    """JSON is malformed, non-canonical, or carries duplicate keys."""


class LedgerIntegrityError(LedgerError):
    """A persisted wrapper does not satisfy its content-address contracts."""


class LedgerConflictError(LedgerError):
    """The supplied compare-and-swap or idempotency contract is stale."""


class LedgerNotInitializedError(LedgerError):
    """A read requiring a snapshot was made before the first successful apply."""


class LedgerTransitionError(LedgerError):
    """The pure lifecycle reducer rejected an intent."""


class LedgerAuthorityError(LedgerError):
    """The local authority file is missing, unsafe, or rejects a public request."""


@dataclass(frozen=True)
class LedgerStatus:
    """A detached, read-only view of the currently durable local ledger."""

    initialized: bool
    snapshot_sha256: str
    event_count: int
    ledger_path: str
    snapshot: dict[str, object] | None
    events: tuple[dict[str, object], ...]

    def to_dict(self, *, include_snapshot: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "initialized": self.initialized,
            "snapshot_sha256": self.snapshot_sha256,
            "event_count": self.event_count,
            "ledger_path": self.ledger_path,
        }
        if include_snapshot:
            result["snapshot"] = deepcopy(self.snapshot)
        return result


@dataclass(frozen=True)
class ApplyResult:
    """The durable result of one intent, including its audit binding."""

    idempotent: bool
    idempotency_key: str
    requested_intent_sha256: str
    intent_sha256: str
    previous_snapshot_sha256: str
    next_snapshot_sha256: str
    current_snapshot_sha256: str
    event: dict[str, object]
    event_count: int
    snapshot: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "idempotent": self.idempotent,
            "idempotency_key": self.idempotency_key,
            "requested_intent_sha256": self.requested_intent_sha256,
            "intent_sha256": self.intent_sha256,
            "previous_snapshot_sha256": self.previous_snapshot_sha256,
            "next_snapshot_sha256": self.next_snapshot_sha256,
            "current_snapshot_sha256": self.current_snapshot_sha256,
            "event": deepcopy(self.event),
            "event_count": self.event_count,
        }


@dataclass(frozen=True)
class _ValidatedWrapper:
    """Validated persisted state plus every deterministic replay checkpoint."""

    snapshot: dict[str, object]
    snapshot_sha256: str
    events: tuple[dict[str, object], ...]
    snapshots_after_events: tuple[dict[str, object], ...]


def _reject_duplicate_keys(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LedgerParseError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise LedgerParseError(f"invalid-json-constant:{value}")


def _normalize_json(value: object, *, label: str = "json-value") -> object:
    """Return JSON-only data and reject values with ambiguous encodings."""
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        # Lifecycle state itself rejects fractional values where they are not
        # part of its schema.  Canonical runner records, however, deliberately
        # carry a fractional timeout (for example, 0.02 seconds).  JSON's
        # encoder gives finite Python floats one deterministic persisted form;
        # NaN and infinities have no portable JSON meaning and remain invalid.
        if not math.isfinite(value):
            raise LedgerParseError(f"non-finite-json-number:{label}")
        return value
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise LedgerParseError(f"invalid-unicode-scalar:{label}")
        return value
    if isinstance(value, list):
        return [_normalize_json(item, label=f"{label}[]") for item in value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise LedgerParseError(f"non-string-json-key:{label}")
        result: dict[str, object] = {}
        for key in sorted(value):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in key):
                raise LedgerParseError(f"invalid-unicode-key:{label}")
            result[key] = _normalize_json(value[key], label=f"{label}.{key}")
        return result
    raise LedgerParseError(f"non-json-value:{label}")


def canonical_json_bytes(value: object) -> bytes:
    """Encode a value as the ledger's sole canonical UTF-8 JSON form."""
    try:
        rendered = json.dumps(
            _normalize_json(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # Defensive: _normalize_json is strict.
        raise LedgerParseError("non-canonical-json-value") from exc
    try:
        return (rendered + "\n").encode("utf-8")
    except UnicodeEncodeError as exc:
        raise LedgerParseError("invalid-utf8-json-value") from exc


def parse_strict_json_bytes(raw: bytes, *, label: str = "json", require_canonical: bool = False) -> object:
    """Parse UTF-8 JSON while rejecting duplicate keys and NaN-like values."""
    if not isinstance(raw, bytes):
        raise LedgerParseError(f"invalid-{label}-bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerParseError(f"invalid-{label}-utf8") from exc
    if text.startswith("\ufeff"):
        raise LedgerParseError(f"invalid-{label}-utf8-bom")
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_json_constant)
    except LedgerParseError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LedgerParseError(f"invalid-{label}-json") from exc
    normalized = _normalize_json(value, label=label)
    if require_canonical and raw != canonical_json_bytes(normalized):
        raise LedgerParseError(f"non-canonical-{label}-json")
    return normalized


def sha256_json(value: object) -> str:
    """Return SHA-256 of canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def snapshot_sha256(snapshot: Mapping[str, object]) -> str:
    """Validate then content-address a canonical lifecycle snapshot."""
    try:
        lifecycle_reducer.validate_snapshot(snapshot)
    except lifecycle_reducer.ReducerError as exc:
        raise LedgerIntegrityError(str(exc)) from exc
    return sha256_json(snapshot)


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LedgerIntegrityError(f"invalid-{label}")
    return value


def _idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY_KEY.fullmatch(value):
        raise LedgerConflictError("invalid-idempotency-key")
    return value


def _expected_snapshot_sha(value: object) -> str:
    if value == ABSENT_SNAPSHOT_SHA256:
        return ABSENT_SNAPSHOT_SHA256
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LedgerConflictError("invalid-expected-snapshot-sha256")
    return value


def _timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value or "\x00" in value:
        raise LedgerError("invalid-event-timestamp")
    parseable = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise LedgerError("invalid-event-timestamp") from exc
    if parsed.tzinfo is None:
        raise LedgerError("event-timestamp-requires-timezone")
    return value


def _public_operation(source: Mapping[str, object], *, error_type: type[LedgerError]) -> str:
    operation = source.get("operation")
    if not isinstance(operation, str) or not operation:
        raise error_type("invalid-public-lifecycle-operation")
    return operation


def _strict_public_mapping(
    value: object, *, label: str, error_type: type[LedgerError],
) -> dict[str, object]:
    normalized = _normalize_json(value, label=label)
    if not isinstance(normalized, dict):
        raise error_type(f"invalid-{label}")
    return normalized


def _parse_public_request_approval(
    request: Mapping[str, object], *, error_type: type[LedgerError],
) -> dict[str, object]:
    source = _strict_public_mapping(request, label="request-approval", error_type=error_type)
    supplied_forbidden = sorted(_PUBLIC_APPROVAL_FORBIDDEN_FIELDS & set(source))
    if supplied_forbidden:
        raise error_type("public-request-cannot-supply:" + ",".join(supplied_forbidden))
    expected = _PUBLIC_REQUEST_APPROVAL_REQUIRED_FIELDS | _PUBLIC_REQUEST_APPROVAL_OPTIONAL_FIELDS
    if not _PUBLIC_REQUEST_APPROVAL_REQUIRED_FIELDS.issubset(source) or not set(source).issubset(expected):
        raise error_type("invalid-request-approval-fields")
    if source.get("operation") != "request_approval":
        raise error_type("invalid-request-approval-operation")
    try:
        subject = lifecycle_reducer.approval_subject(
            str(source.get("subject_type")), str(source.get("subject_id")),
        )
    except lifecycle_reducer.ReducerError as exc:
        raise error_type(str(exc)) from exc
    decision = source.get("decision")
    if decision not in {"approve", "reject", "revoke"}:
        raise error_type("invalid-request-approval-decision")
    decision_intent_ref = source.get("decision_intent_ref")
    if not isinstance(decision_intent_ref, str) or not decision_intent_ref:
        raise error_type("invalid-request-approval-decision-intent-ref")
    at = source.get("at")
    if not isinstance(at, str):
        raise error_type("invalid-request-approval-at")
    try:
        _timestamp(at)
    except LedgerError as exc:
        raise error_type(str(exc)) from exc
    resolves = source.get("resolves_change_requests", [])
    if not isinstance(resolves, list) or any(not isinstance(item, str) or not item for item in resolves):
        raise error_type("invalid-request-approval-resolves-change-requests")
    if len(resolves) != len(set(resolves)):
        raise error_type("duplicate-request-approval-resolves-change-requests")
    return {
        "subject": subject,
        "decision": str(decision),
        "decision_intent_ref": decision_intent_ref,
        "at": at,
        "resolves_change_requests": list(resolves),
    }


def _parse_public_decide_change_request(
    request: Mapping[str, object], *, error_type: type[LedgerError],
) -> dict[str, str]:
    source = _strict_public_mapping(request, label="decide-change-request", error_type=error_type)
    if set(source) != _PUBLIC_DECIDE_CHANGE_REQUEST_FIELDS:
        raise error_type("invalid-decide-change-request-fields")
    if source.get("operation") != "decide_change_request":
        raise error_type("invalid-decide-change-request-operation")
    change_request_id = source.get("change_request_id")
    if not isinstance(change_request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", change_request_id):
        raise error_type("invalid-decide-change-request-id")
    decision = source.get("decision")
    if not isinstance(decision, str) or decision not in _CHANGE_REQUEST_INTERNAL_OPERATION:
        raise error_type("invalid-decide-change-request-decision")
    at = source.get("at")
    if not isinstance(at, str):
        raise error_type("invalid-decide-change-request-at")
    try:
        _timestamp(at)
    except LedgerError as exc:
        raise error_type(str(exc)) from exc
    return {"change_request_id": change_request_id, "decision": decision, "at": at}


def _public_id(value: object, *, label: str, error_type: type[LedgerError]) -> str:
    if not isinstance(value, str) or not _LIFECYCLE_ID.fullmatch(value) or ".." in value:
        raise error_type(f"invalid-{label}")
    return value


def _public_one_line_text(value: object, *, label: str, error_type: type[LedgerError]) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value:
        raise error_type(f"invalid-{label}")
    return value


def _public_sha256(value: object, *, label: str, error_type: type[LedgerError]) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise error_type(f"invalid-{label}")
    return value


def _public_relative_path(value: object, *, label: str, error_type: type[LedgerError]) -> str:
    """Validate syntax only; the ledger resolves this below its repo root later."""
    text = _public_one_line_text(value, label=label, error_type=error_type)
    if "\\" in text:
        raise error_type(f"invalid-{label}")
    path = Path(text)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise error_type(f"invalid-{label}")
    return text


def _public_argv(value: object, *, label: str, error_type: type[LedgerError]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise error_type(f"invalid-{label}")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item or "\x00" in item:
            raise error_type(f"invalid-{label}-{index}")
        result.append(item)
    if Path(result[0]).name.lower() in _SHELL_EXECUTABLES:
        raise error_type("shell-argv-not-allowed")
    return result


def _public_timeout(value: object, *, error_type: type[LedgerError]) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise error_type("invalid-timeout-seconds")
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > _MAX_CANONICAL_TIMEOUT_SECONDS:
        raise error_type("invalid-timeout-seconds")
    return timeout


def _public_fence(value: object, *, error_type: type[LedgerError]) -> dict[str, object]:
    source = _strict_public_mapping(value, label="contract-fence", error_type=error_type)
    if set(source) != set(lifecycle_reducer.FENCE_FIELDS):
        raise error_type("invalid-contract-fence-fields")
    generation = source.get("contract_generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise error_type("invalid-contract-fence-generation")
    result: dict[str, object] = {"contract_generation": generation}
    for field in lifecycle_reducer.FENCE_FIELDS[1:]:
        result[field] = _public_sha256(
            source.get(field), label=field.replace("_", "-"), error_type=error_type,
        )
    return result


def _public_sha256_refs(value: object, *, label: str, error_type: type[LedgerError]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise error_type(f"invalid-{label}")
    refs = [_public_sha256(item, label=f"{label}-item", error_type=error_type) for item in value]
    if refs != sorted(refs) or len(refs) != len(set(refs)):
        raise error_type(f"invalid-{label}")
    return refs


def _parse_public_submit_feature_review(
    request: Mapping[str, object], *, error_type: type[LedgerError],
) -> dict[str, object]:
    source = _strict_public_mapping(request, label="submit-feature-review", error_type=error_type)
    if set(source) != _PUBLIC_SUBMIT_FEATURE_REVIEW_FIELDS:
        raise error_type("invalid-submit-feature-review-fields")
    if source.get("operation") != "submit_feature_review":
        raise error_type("invalid-submit-feature-review-operation")
    decision = source.get("decision")
    if decision not in {"approve", "reject"}:
        raise error_type("invalid-submit-feature-review-decision")
    at = source.get("at")
    if not isinstance(at, str):
        raise error_type("invalid-submit-feature-review-at")
    try:
        _timestamp(at)
    except LedgerError as exc:
        raise error_type(str(exc)) from exc
    return {
        "feature_id": _public_id(source.get("feature_id"), label="feature-id", error_type=error_type),
        "fence": _public_fence(source.get("fence"), error_type=error_type),
        "decision": str(decision),
        "evidence_refs": _public_sha256_refs(
            source.get("evidence_refs"), label="review-evidence-refs", error_type=error_type,
        ),
        "rationale_ref": _public_sha256(
            source.get("rationale_ref"), label="review-rationale-ref", error_type=error_type,
        ),
        "policy_manifest_ref": _public_sha256(
            source.get("policy_manifest_ref"), label="review-policy-manifest-ref", error_type=error_type,
        ),
        "context_manifest_ref": _public_sha256(
            source.get("context_manifest_ref"), label="review-context-manifest-ref", error_type=error_type,
        ),
        "at": at,
    }


def _public_release_target(value: object, *, error_type: type[LedgerError]) -> dict[str, str]:
    source = _strict_public_mapping(value, label="release-target", error_type=error_type)
    if set(source) != _PUBLIC_RELEASE_TARGET_FIELDS:
        raise error_type("invalid-release-target-fields")
    return {
        "environment": _public_id(source.get("environment"), label="release-environment", error_type=error_type),
        "target_type": _public_id(source.get("target_type"), label="release-target-type", error_type=error_type),
        "target_ref": _public_one_line_text(source.get("target_ref"), label="release-target-ref", error_type=error_type),
    }


def _public_release_artifact(value: object, *, error_type: type[LedgerError]) -> dict[str, str]:
    source = _strict_public_mapping(value, label="actual-release-artifact", error_type=error_type)
    if set(source) != _PUBLIC_RELEASE_ARTIFACT_FIELDS:
        raise error_type("invalid-actual-release-artifact-fields")
    return {
        "artifact_type": _public_id(source.get("artifact_type"), label="release-artifact-type", error_type=error_type),
        "artifact_ref": _public_one_line_text(source.get("artifact_ref"), label="release-artifact-ref", error_type=error_type),
    }


def _parse_public_execute_task_evidence(
    request: Mapping[str, object], *, error_type: type[LedgerError],
) -> dict[str, object]:
    source = _strict_public_mapping(request, label="execute-task-evidence", error_type=error_type)
    if set(source) != _PUBLIC_EXECUTE_TASK_EVIDENCE_FIELDS:
        raise error_type("invalid-execute-task-evidence-fields")
    if source.get("operation") != "execute_task_evidence":
        raise error_type("invalid-execute-task-evidence-operation")
    at = source.get("at")
    if not isinstance(at, str):
        raise error_type("invalid-execute-task-evidence-at")
    try:
        _timestamp(at)
    except LedgerError as exc:
        raise error_type(str(exc)) from exc
    return {
        "feature_id": _public_id(source.get("feature_id"), label="feature-id", error_type=error_type),
        "task_id": _public_id(source.get("task_id"), label="task-id", error_type=error_type),
        "fence": _public_fence(source.get("fence"), error_type=error_type),
        "argv": _public_argv(source.get("argv"), label="argv", error_type=error_type),
        "cwd": _public_relative_path(source.get("cwd"), label="cwd", error_type=error_type),
        "timeout_seconds": _public_timeout(source.get("timeout_seconds"), error_type=error_type),
        "policy_manifest_ref": _public_sha256(
            source.get("policy_manifest_ref"), label="policy-manifest-ref", error_type=error_type,
        ),
        "context_manifest_ref": _public_sha256(
            source.get("context_manifest_ref"), label="context-manifest-ref", error_type=error_type,
        ),
        "tool_version": _public_one_line_text(
            source.get("tool_version"), label="tool-version", error_type=error_type,
        ),
        "at": at,
    }


def _parse_public_publish_feature(
    request: Mapping[str, object], *, error_type: type[LedgerError],
) -> dict[str, object]:
    source = _strict_public_mapping(request, label="publish-feature", error_type=error_type)
    if set(source) != _PUBLIC_PUBLISH_FEATURE_FIELDS:
        raise error_type("invalid-publish-feature-fields")
    if source.get("operation") != "publish_feature":
        raise error_type("invalid-publish-feature-operation")
    at = source.get("at")
    if not isinstance(at, str):
        raise error_type("invalid-publish-feature-at")
    try:
        _timestamp(at)
    except LedgerError as exc:
        raise error_type(str(exc)) from exc
    return {
        "feature_id": _public_id(source.get("feature_id"), label="feature-id", error_type=error_type),
        "fence": _public_fence(source.get("fence"), error_type=error_type),
        "release_target": _public_release_target(source.get("release_target"), error_type=error_type),
        "actual_release_artifact": _public_release_artifact(
            source.get("actual_release_artifact"), error_type=error_type,
        ),
        "artifact_path": _public_relative_path(
            source.get("artifact_path"), label="artifact-path", error_type=error_type,
        ),
        "argv": _public_argv(source.get("argv"), label="argv", error_type=error_type),
        "cwd": _public_relative_path(source.get("cwd"), label="cwd", error_type=error_type),
        "timeout_seconds": _public_timeout(source.get("timeout_seconds"), error_type=error_type),
        "policy_manifest_ref": _public_sha256(
            source.get("policy_manifest_ref"), label="policy-manifest-ref", error_type=error_type,
        ),
        "context_manifest_ref": _public_sha256(
            source.get("context_manifest_ref"), label="context-manifest-ref", error_type=error_type,
        ),
        "tool_version": _public_one_line_text(
            source.get("tool_version"), label="tool-version", error_type=error_type,
        ),
        "at": at,
    }


def _cwd_identity(relative_cwd: str, *, artifact_path: str | None = None) -> str:
    """A replayable identity for an already-contained execution location.

    Publishing additionally binds the local artifact source path to the runner
    observation.  The helper never exposes an absolute host path in events.
    """
    preimage: dict[str, object] = {"cwd": relative_cwd, "format": "dual-lifecycle-repo-cwd-v1"}
    if artifact_path is not None:
        preimage["artifact_path"] = artifact_path
    return sha256_json(preimage)


def _canonical_runner_for_public_request(
    runner_record: object, request: Mapping[str, object], *, error_type: type[LedgerError],
) -> dict[str, object]:
    """Check the request-to-observed-runner binding without launching anything."""
    source = _strict_public_mapping(runner_record, label="canonical-runner-record", error_type=error_type)
    required = {
        "schema_version", "scope", "argv", "cwd_identity", "timeout_seconds", "timed_out",
        "exit_code", "stdout", "stderr", "tool_version", "code_sha", "policy_manifest_ref",
        "context_manifest_ref", "evidence_id",
    }
    if set(source) != required:
        raise error_type("invalid-canonical-runner-record-fields")
    if source.get("schema_version") != "canonical-runner-evidence-v1" or source.get("scope") != "canonical":
        raise error_type("invalid-canonical-runner-record-scope")
    if source.get("argv") != request.get("argv"):
        raise error_type("canonical-runner-argv-mismatch")
    timeout = source.get("timeout_seconds")
    if not isinstance(timeout, float) or not math.isfinite(timeout) or timeout != request.get("timeout_seconds"):
        raise error_type("canonical-runner-timeout-mismatch")
    artifact_path = request.get("artifact_path")
    if artifact_path is not None and not isinstance(artifact_path, str):
        raise error_type("invalid-canonical-runner-artifact-path")
    if source.get("cwd_identity") != _cwd_identity(str(request["cwd"]), artifact_path=artifact_path):
        raise error_type("canonical-runner-cwd-mismatch")
    if source.get("policy_manifest_ref") != request.get("policy_manifest_ref"):
        raise error_type("canonical-runner-policy-mismatch")
    if source.get("context_manifest_ref") != request.get("context_manifest_ref"):
        raise error_type("canonical-runner-context-mismatch")
    if source.get("tool_version") != request.get("tool_version"):
        raise error_type("canonical-runner-tool-version-mismatch")
    _public_sha256(source.get("code_sha"), label="canonical-runner-code-sha", error_type=error_type)
    _public_sha256(source.get("evidence_id"), label="canonical-runner-evidence-id", error_type=error_type)
    return source


def _validate_execute_task_evidence_pair(
    requested: Mapping[str, object], replay_intent: Mapping[str, object],
) -> None:
    request = _parse_public_execute_task_evidence(requested, error_type=LedgerIntegrityError)
    required = {"operation", "runner_record", "tested_sha", "feature_id", "task_id", "fence", "at"}
    if set(replay_intent) != required or replay_intent.get("operation") != "record_evidence":
        raise LedgerIntegrityError("invalid-canonical-execute-task-evidence-fields")
    runner = _canonical_runner_for_public_request(
        replay_intent.get("runner_record"), request, error_type=LedgerIntegrityError,
    )
    if (
        replay_intent.get("feature_id") != request["feature_id"]
        or replay_intent.get("task_id") != request["task_id"]
        or replay_intent.get("fence") != request["fence"]
        or replay_intent.get("at") != request["at"]
    ):
        raise LedgerIntegrityError("canonical-execute-task-evidence-lifecycle-mismatch")
    tested_sha = _public_sha256(
        replay_intent.get("tested_sha"), label="canonical-tested-sha", error_type=LedgerIntegrityError,
    )
    if tested_sha != runner["code_sha"]:
        raise LedgerIntegrityError("canonical-tested-sha-runner-mismatch")


def _validate_submit_feature_review_pair(
    requested: Mapping[str, object], replay_intent: Mapping[str, object],
) -> None:
    request = _parse_public_submit_feature_review(requested, error_type=LedgerIntegrityError)
    required = {"operation", "feature_id", "fence", "attestation", "at"}
    if set(replay_intent) != required or replay_intent.get("operation") != "review_feature":
        raise LedgerIntegrityError("invalid-canonical-submit-feature-review-fields")
    if (
        replay_intent.get("feature_id") != request["feature_id"]
        or replay_intent.get("fence") != request["fence"]
        or replay_intent.get("at") != request["at"]
    ):
        raise LedgerIntegrityError("canonical-submit-feature-review-lifecycle-mismatch")
    attestation = replay_intent.get("attestation")
    if not isinstance(attestation, Mapping):
        raise LedgerIntegrityError("invalid-canonical-review-attestation")
    try:
        review_attestation.verify_review_attestation(
            attestation,
            expected_feature_id=str(request["feature_id"]),
            expected_current_tuple=request["fence"],  # type: ignore[arg-type]
            expected_decision=str(request["decision"]),
            expected_reviewed_at=str(request["at"]),
        )
    except review_attestation.ReviewAttestationError as exc:
        raise LedgerIntegrityError(f"invalid-canonical-review-attestation:{exc}") from exc
    if (
        attestation.get("evidence_refs") != request["evidence_refs"]
        or attestation.get("rationale_ref") != request["rationale_ref"]
        or attestation.get("policy_manifest_ref") != request["policy_manifest_ref"]
        or attestation.get("context_manifest_ref") != request["context_manifest_ref"]
    ):
        raise LedgerIntegrityError("canonical-submit-feature-review-input-mismatch")


def _validate_publish_feature_pair(
    requested: Mapping[str, object], replay_intent: Mapping[str, object],
) -> None:
    request = _parse_public_publish_feature(requested, error_type=LedgerIntegrityError)
    required = {"operation", "feature_id", "fence", "release_receipt", "at"}
    if set(replay_intent) != required or replay_intent.get("operation") != "ship_feature":
        raise LedgerIntegrityError("invalid-canonical-publish-feature-fields")
    if (
        replay_intent.get("feature_id") != request["feature_id"]
        or replay_intent.get("fence") != request["fence"]
        or replay_intent.get("at") != request["at"]
    ):
        raise LedgerIntegrityError("canonical-publish-feature-lifecycle-mismatch")
    receipt = _strict_public_mapping(
        replay_intent.get("release_receipt"), label="canonical-release-receipt", error_type=LedgerIntegrityError,
    )
    runner = _canonical_runner_for_public_request(
        receipt.get("runner_record"), request, error_type=LedgerIntegrityError,
    )
    target = receipt.get("release_target")
    artifact = receipt.get("actual_release_artifact")
    if target != request["release_target"]:
        raise LedgerIntegrityError("canonical-release-target-mismatch")
    if not isinstance(artifact, Mapping) or set(artifact) != {"artifact_type", "artifact_ref", "artifact_sha256"}:
        raise LedgerIntegrityError("invalid-canonical-release-artifact")
    if {
        "artifact_type": artifact.get("artifact_type"), "artifact_ref": artifact.get("artifact_ref"),
    } != request["actual_release_artifact"]:
        raise LedgerIntegrityError("canonical-release-artifact-mismatch")
    try:
        receipt_id = dual_artifact_store.verify_release_receipt(
            receipt,
            expected_runner_record_ref=str(runner["evidence_id"]),
            expected_feature_id=str(request["feature_id"]),
            expected_release_target=request["release_target"],
            expected_actual_release_artifact=artifact,
            expected_release_sha=str(receipt.get("release_sha")),
            expected_current_tuple=request["fence"],
        )
    except dual_artifact_store.ArtifactStoreError as exc:
        raise LedgerIntegrityError(f"invalid-canonical-release-receipt:{exc}") from exc
    if receipt.get("receipt_id") != receipt_id:
        raise LedgerIntegrityError("canonical-release-receipt-id-mismatch")


def _validate_requested_to_replay_pair(
    requested: Mapping[str, object], replay_intent: Mapping[str, object],
) -> None:
    """Validate public/internal binding without consulting mutable authority.json."""
    operation = _public_operation(requested, error_type=LedgerIntegrityError)
    if operation in _RAW_INTERNAL_OPERATIONS:
        raise LedgerIntegrityError("persisted-public-request-cannot-use-raw-internal-operation")
    if operation == "execute_task_evidence":
        _validate_execute_task_evidence_pair(requested, replay_intent)
        return
    if operation == "submit_feature_review":
        _validate_submit_feature_review_pair(requested, replay_intent)
        return
    if operation == "publish_feature":
        _validate_publish_feature_pair(requested, replay_intent)
        return
    if operation not in {"request_approval", "decide_change_request"}:
        if canonical_json_bytes(requested) != canonical_json_bytes(replay_intent):
            raise LedgerIntegrityError("ordinary-request-must-equal-replay-intent")
        return
    if operation == "request_approval":
        request = _parse_public_request_approval(requested, error_type=LedgerIntegrityError)
        if set(replay_intent) != {"operation", "approval_record", "authorization_policy", "at"}:
            raise LedgerIntegrityError("invalid-canonical-request-approval-fields")
        if replay_intent.get("operation") != "apply_approval" or replay_intent.get("at") != request["at"]:
            raise LedgerIntegrityError("invalid-canonical-request-approval-operation-or-time")
        record = replay_intent.get("approval_record")
        policy = replay_intent.get("authorization_policy")
        if not isinstance(record, Mapping) or not isinstance(policy, Mapping):
            raise LedgerIntegrityError("invalid-canonical-request-approval-record-or-policy")
        for field, value in request["subject"].items():
            if record.get(field) != value:
                raise LedgerIntegrityError("canonical-request-approval-subject-mismatch")
        if record.get("decision") != request["decision"]:
            raise LedgerIntegrityError("canonical-request-approval-decision-mismatch")
        if record.get("decision_intent_ref") != request["decision_intent_ref"]:
            raise LedgerIntegrityError("canonical-request-approval-intent-ref-mismatch")
        if record.get("decided_at") != request["at"]:
            raise LedgerIntegrityError("canonical-request-approval-decided-at-mismatch")
        if record.get("resolves_change_requests") != sorted(request["resolves_change_requests"]):
            raise LedgerIntegrityError("canonical-request-approval-resolves-mismatch")
        if policy.get("policy_id") != record.get("authorization_policy_ref"):
            raise LedgerIntegrityError("canonical-request-approval-policy-mismatch")
        return
    request = _parse_public_decide_change_request(requested, error_type=LedgerIntegrityError)
    expected_operation = _CHANGE_REQUEST_INTERNAL_OPERATION[request["decision"]]
    expected_fields = {"operation", "change_request_id", "at"}
    if request["decision"] == "accept":
        expected_fields.add("accepted_by")
    if set(replay_intent) != expected_fields:
        raise LedgerIntegrityError("invalid-canonical-decide-change-request-fields")
    if (
        replay_intent.get("operation") != expected_operation
        or replay_intent.get("change_request_id") != request["change_request_id"]
        or replay_intent.get("at") != request["at"]
    ):
        raise LedgerIntegrityError("canonical-decide-change-request-mismatch")
    if request["decision"] == "accept":
        actor = replay_intent.get("accepted_by")
        if not isinstance(actor, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", actor):
            raise LedgerIntegrityError("invalid-canonical-change-request-actor")


def _event_preimage(
    *, sequence: int, idempotency_key: str,
    requested_intent: Mapping[str, object], requested_intent_sha256: str,
    intent: Mapping[str, object], intent_sha256: str,
    previous_snapshot_sha256: str, next_snapshot_sha256: str, timestamp: str,
) -> dict[str, object]:
    normalized_requested_intent = _normalize_json(requested_intent, label="ledger-event-requested-intent")
    normalized_intent = _normalize_json(intent, label="ledger-event-intent")
    if not isinstance(normalized_requested_intent, dict):
        raise LedgerIntegrityError("invalid-ledger-event-requested-intent")
    if not isinstance(normalized_intent, dict):
        raise LedgerIntegrityError("invalid-ledger-event-intent")
    return {
        "event_format": EVENT_FORMAT,
        "sequence": sequence,
        "idempotency_key": idempotency_key,
        "requested_intent": normalized_requested_intent,
        "requested_intent_sha256": requested_intent_sha256,
        "intent": normalized_intent,
        "intent_sha256": intent_sha256,
        "previous_snapshot_sha256": previous_snapshot_sha256,
        "next_snapshot_sha256": next_snapshot_sha256,
        "timestamp": timestamp,
    }


def _build_event(
    *, sequence: int, idempotency_key: str,
    requested_intent: Mapping[str, object], requested_intent_sha256: str,
    intent: Mapping[str, object], intent_sha256: str,
    previous_snapshot_sha256: str, next_snapshot_sha256: str, timestamp: str,
) -> dict[str, object]:
    preimage = _event_preimage(
        sequence=sequence, idempotency_key=idempotency_key,
        requested_intent=requested_intent, requested_intent_sha256=requested_intent_sha256,
        intent=intent, intent_sha256=intent_sha256,
        previous_snapshot_sha256=previous_snapshot_sha256, next_snapshot_sha256=next_snapshot_sha256,
        timestamp=timestamp,
    )
    return {**preimage, "event_sha256": sha256_json(preimage)}


def _validate_event(event: object, *, sequence: int, expected_previous: str) -> dict[str, object]:
    if not isinstance(event, Mapping) or set(event) != _EVENT_FIELDS:
        raise LedgerIntegrityError("invalid-ledger-event-fields")
    normalized = _normalize_json(event, label="ledger-event")
    if not isinstance(normalized, dict):  # For type checkers; Mapping normalizes to dict.
        raise LedgerIntegrityError("invalid-ledger-event")
    if normalized.get("event_format") != EVENT_FORMAT:
        raise LedgerIntegrityError("unsupported-ledger-event-format")
    event_sequence = normalized.get("sequence")
    if not isinstance(event_sequence, int) or isinstance(event_sequence, bool) or event_sequence != sequence:
        raise LedgerIntegrityError("invalid-ledger-event-sequence")
    key = normalized.get("idempotency_key")
    if not isinstance(key, str) or not _IDEMPOTENCY_KEY.fullmatch(key):
        raise LedgerIntegrityError("invalid-ledger-event-idempotency-key")
    requested_intent = normalized.get("requested_intent")
    if not isinstance(requested_intent, dict):
        raise LedgerIntegrityError("invalid-ledger-event-requested-intent")
    requested_intent_sha = _sha(
        normalized.get("requested_intent_sha256"), "ledger-event-requested-intent-sha256",
    )
    if requested_intent_sha != sha256_json(requested_intent):
        raise LedgerIntegrityError("ledger-event-requested-intent-content-hash-mismatch")
    intent = normalized.get("intent")
    if not isinstance(intent, dict):
        raise LedgerIntegrityError("invalid-ledger-event-intent")
    intent_sha = _sha(normalized.get("intent_sha256"), "ledger-event-intent-sha256")
    if intent_sha != sha256_json(intent):
        raise LedgerIntegrityError("ledger-event-intent-content-hash-mismatch")
    _validate_requested_to_replay_pair(requested_intent, intent)
    previous = normalized.get("previous_snapshot_sha256")
    if previous != expected_previous:
        raise LedgerIntegrityError("broken-ledger-event-snapshot-chain")
    if previous != ABSENT_SNAPSHOT_SHA256:
        _sha(previous, "ledger-event-previous-snapshot-sha256")
    next_sha = _sha(normalized.get("next_snapshot_sha256"), "ledger-event-next-snapshot-sha256")
    if next_sha == ABSENT_SNAPSHOT_SHA256:  # Kept explicit even though _sha already excludes it.
        raise LedgerIntegrityError("invalid-ledger-event-next-snapshot-sha256")
    timestamp = normalized.get("timestamp")
    if not isinstance(timestamp, str):
        raise LedgerIntegrityError("invalid-ledger-event-timestamp")
    try:
        _timestamp(timestamp)
    except LedgerError as exc:
        raise LedgerIntegrityError(str(exc)) from exc
    preimage = _event_preimage(
        sequence=sequence, idempotency_key=key,
        requested_intent=requested_intent, requested_intent_sha256=requested_intent_sha,
        intent=intent, intent_sha256=intent_sha,
        previous_snapshot_sha256=str(previous), next_snapshot_sha256=next_sha, timestamp=timestamp,
    )
    actual_event_sha = _sha(normalized.get("event_sha256"), "ledger-event-sha256")
    if actual_event_sha != sha256_json(preimage):
        raise LedgerIntegrityError("ledger-event-content-hash-mismatch")
    return deepcopy(normalized)


def _build_wrapper(snapshot: Mapping[str, object], events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    snapshot_copy = _normalize_json(snapshot, label="lifecycle-snapshot")
    if not isinstance(snapshot_copy, dict):
        raise LedgerIntegrityError("invalid-lifecycle-snapshot")
    return {
        "ledger_format": LEDGER_FORMAT,
        "ledger_version": LEDGER_VERSION,
        "snapshot": snapshot_copy,
        "snapshot_sha256": snapshot_sha256(snapshot_copy),
        "events": [_normalize_json(event, label="ledger-event") for event in events],
    }


def _validate_wrapper(wrapper: object) -> _ValidatedWrapper:
    """Validate bytes, event chain, and a full reducer replay without repair.

    A persisted snapshot is a cache of immutable event history, never a second
    source of truth.  Reads fail closed if that cache cannot be reproduced from
    ``empty_snapshot()`` by the same dispatcher used for a new apply.
    """
    if not isinstance(wrapper, Mapping) or set(wrapper) != _WRAPPER_FIELDS:
        raise LedgerIntegrityError("invalid-ledger-wrapper-fields")
    normalized = _normalize_json(wrapper, label="ledger-wrapper")
    if not isinstance(normalized, dict):
        raise LedgerIntegrityError("invalid-ledger-wrapper")
    if normalized.get("ledger_format") != LEDGER_FORMAT or normalized.get("ledger_version") != LEDGER_VERSION:
        raise LedgerIntegrityError("unsupported-ledger-wrapper")
    snapshot = normalized.get("snapshot")
    if not isinstance(snapshot, dict):
        raise LedgerIntegrityError("invalid-ledger-snapshot")
    actual_snapshot_sha = snapshot_sha256(snapshot)
    declared_snapshot_sha = _sha(normalized.get("snapshot_sha256"), "ledger-snapshot-sha256")
    if actual_snapshot_sha != declared_snapshot_sha:
        raise LedgerIntegrityError("ledger-snapshot-content-hash-mismatch")
    raw_events = normalized.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise LedgerIntegrityError("ledger-requires-at-least-one-event")
    events: list[dict[str, object]] = []
    snapshots_after_events: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    expected_previous = ABSENT_SNAPSHOT_SHA256
    replayed_snapshot = lifecycle_reducer.empty_snapshot()
    for sequence, event in enumerate(raw_events, start=1):
        validated = _validate_event(event, sequence=sequence, expected_previous=expected_previous)
        key = str(validated["idempotency_key"])
        if key in seen_keys:
            raise LedgerIntegrityError("duplicate-ledger-event-idempotency-key")
        seen_keys.add(key)
        replayed_previous_sha = (
            ABSENT_SNAPSHOT_SHA256 if sequence == 1 else snapshot_sha256(replayed_snapshot)
        )
        if replayed_previous_sha != validated["previous_snapshot_sha256"]:
            raise LedgerIntegrityError("ledger-event-replay-predecessor-mismatch")
        intent = validated["intent"]
        if not isinstance(intent, Mapping):  # _validate_event already narrows this; keep replay explicit.
            raise LedgerIntegrityError("invalid-ledger-event-intent")
        try:
            replayed_snapshot = lifecycle_reducer.reduce(replayed_snapshot, intent)
            lifecycle_reducer.validate_snapshot(replayed_snapshot)
        except lifecycle_reducer.ReducerError as exc:
            raise LedgerIntegrityError(f"ledger-event-replay-rejected:{exc}") from exc
        replayed_next_sha = snapshot_sha256(replayed_snapshot)
        if replayed_next_sha != validated["next_snapshot_sha256"]:
            raise LedgerIntegrityError("ledger-event-replay-next-snapshot-mismatch")
        expected_previous = str(validated["next_snapshot_sha256"])
        events.append(validated)
        snapshots_after_events.append(deepcopy(dict(replayed_snapshot)))
    if canonical_json_bytes(snapshot) != canonical_json_bytes(replayed_snapshot):
        raise LedgerIntegrityError("ledger-replay-final-snapshot-mismatch")
    if expected_previous != declared_snapshot_sha:
        raise LedgerIntegrityError("ledger-final-event-does-not-bind-current-snapshot")
    return _ValidatedWrapper(
        snapshot=deepcopy(snapshot), snapshot_sha256=declared_snapshot_sha,
        events=tuple(events), snapshots_after_events=tuple(snapshots_after_events),
    )


class DualLifecycleLedger:
    """File-backed, local compare-and-swap wrapper around ``lifecycle.reduce``."""

    def __init__(self, repo_root: str | os.PathLike[str] = ".") -> None:
        root = Path(repo_root).expanduser()
        if not root.exists() or not root.is_dir():
            raise LedgerError(f"invalid-repository-root:{root}")
        if root.is_symlink():
            raise LedgerError(f"repository-root-cannot-be-symlink:{root}")
        self.repo_root = root.resolve()

    @property
    def namespace_path(self) -> Path:
        return self.repo_root / CONTROL_DIRECTORY / NAMESPACE_DIRECTORY

    @property
    def ledger_path(self) -> Path:
        return self.namespace_path / LEDGER_FILENAME

    @property
    def lock_path(self) -> Path:
        return self.namespace_path / LOCK_FILENAME

    @property
    def authority_path(self) -> Path:
        return self.namespace_path / AUTHORITY_FILENAME

    @property
    def execution_journal_path(self) -> Path:
        return self.namespace_path / EXECUTION_JOURNAL_FILENAME

    def _ensure_namespace(self) -> None:
        control = self.repo_root / CONTROL_DIRECTORY
        if control.is_symlink():
            raise LedgerError(f"control-directory-cannot-be-symlink:{control}")
        control.mkdir(mode=0o755, exist_ok=True)
        if not control.is_dir():
            raise LedgerError(f"control-directory-is-not-directory:{control}")
        namespace = self.namespace_path
        if namespace.is_symlink():
            raise LedgerError(f"dual-lifecycle-namespace-cannot-be-symlink:{namespace}")
        namespace.mkdir(mode=0o755, exist_ok=True)
        if not namespace.is_dir():
            raise LedgerError(f"dual-lifecycle-namespace-is-not-directory:{namespace}")
        for path in (self.ledger_path, self.lock_path, self.execution_journal_path):
            if path.is_symlink():
                raise LedgerError(f"ledger-path-cannot-be-symlink:{path}")
            if path.exists() and not stat.S_ISREG(path.stat().st_mode):
                raise LedgerError(f"ledger-path-must-be-regular-file:{path}")

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        self._ensure_namespace()
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise LedgerError(f"unable-to-open-ledger-lock:{self.lock_path}") from exc
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise LedgerError("ledger-lock-must-be-regular-file")
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _load_locked(self) -> _ValidatedWrapper | None:
        path = self.ledger_path
        if path.is_symlink():
            raise LedgerIntegrityError("ledger-file-must-be-regular-non-symlink")
        if not path.exists():
            return None
        if not stat.S_ISREG(path.stat().st_mode):
            raise LedgerIntegrityError("ledger-file-must-be-regular-non-symlink")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise LedgerError(f"unable-to-read-ledger:{path}") from exc
        wrapper = parse_strict_json_bytes(raw, label="ledger", require_canonical=True)
        return _validate_wrapper(wrapper)

    def _load_execution_journal_locked(self) -> dict[str, object] | None:
        """Load one crash-recovery marker without trusting a symlink or loose JSON."""
        path = self.execution_journal_path
        if path.is_symlink():
            raise LedgerIntegrityError("execution-journal-must-be-regular-non-symlink")
        if not path.exists():
            return None
        if not stat.S_ISREG(path.stat().st_mode):
            raise LedgerIntegrityError("execution-journal-must-be-regular-non-symlink")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise LedgerError("unable-to-read-execution-journal") from exc
        journal = parse_strict_json_bytes(raw, label="execution-journal", require_canonical=True)
        if not isinstance(journal, dict) or set(journal) != _EXECUTION_JOURNAL_FIELDS:
            raise LedgerIntegrityError("invalid-execution-journal-fields")
        if journal.get("journal_format") != EXECUTION_JOURNAL_FORMAT:
            raise LedgerIntegrityError("unsupported-execution-journal-format")
        key = journal.get("idempotency_key")
        if not isinstance(key, str) or not _IDEMPOTENCY_KEY.fullmatch(key):
            raise LedgerIntegrityError("invalid-execution-journal-idempotency-key")
        _sha(journal.get("requested_intent_sha256"), "execution-journal-requested-intent-sha256")
        if journal.get("operation") not in {"execute_task_evidence", "publish_feature"}:
            raise LedgerIntegrityError("invalid-execution-journal-operation")
        return journal

    def _write_execution_journal_locked(
        self, *, idempotency_key: str, requested_intent_sha256: str, operation: str,
    ) -> None:
        """Durably reserve one external execution before invoking a process."""
        current = self._load_execution_journal_locked()
        if current is not None:
            if (
                current["idempotency_key"] == idempotency_key
                and current["requested_intent_sha256"] == requested_intent_sha256
                and current["operation"] == operation
            ):
                raise LedgerConflictError("execution-recovery-required-for-idempotency-key")
            raise LedgerConflictError("another-execution-recovery-required")
        journal = {
            "journal_format": EXECUTION_JOURNAL_FORMAT,
            "idempotency_key": idempotency_key,
            "requested_intent_sha256": requested_intent_sha256,
            "operation": operation,
        }
        payload = canonical_json_bytes(journal)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".execution.", suffix=".tmp", dir=self.namespace_path,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.execution_journal_path)
            self._fsync_namespace_locked()
        except OSError as exc:
            raise LedgerError("unable-to-write-execution-journal") from exc
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _clear_execution_journal_locked(
        self, *, idempotency_key: str, requested_intent_sha256: str, operation: str,
    ) -> None:
        """Clear only the reservation made by this now-durable external event."""
        current = self._load_execution_journal_locked()
        if current is None:
            raise LedgerIntegrityError("execution-journal-missing-after-execution")
        if (
            current["idempotency_key"] != idempotency_key
            or current["requested_intent_sha256"] != requested_intent_sha256
            or current["operation"] != operation
        ):
            raise LedgerIntegrityError("execution-journal-mismatch-after-execution")
        try:
            self.execution_journal_path.unlink()
            self._fsync_namespace_locked()
        except OSError as exc:
            raise LedgerError("ledger-committed-but-unable-to-clear-execution-journal") from exc

    def _fsync_namespace_locked(self) -> None:
        try:
            directory_fd = os.open(self.namespace_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    def _load_authority_locked(self) -> dual_authority.AuthorityConfig:
        """Read authority.json once through a non-symlink regular-file handle."""
        path = self.authority_path
        try:
            before = os.lstat(path)
        except FileNotFoundError as exc:
            raise LedgerAuthorityError("authority-config-missing") from exc
        except OSError as exc:
            raise LedgerAuthorityError("cannot-stat-authority-config") from exc
        if stat.S_ISLNK(before.st_mode):
            raise LedgerAuthorityError("authority-config-cannot-be-symlink")
        if not stat.S_ISREG(before.st_mode):
            raise LedgerAuthorityError("authority-config-must-be-regular-file")
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError as exc:
            raise LedgerAuthorityError("authority-config-missing") from exc
        except OSError as exc:
            raise LedgerAuthorityError("cannot-open-authority-config") from exc
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise LedgerAuthorityError("authority-config-must-be-regular-file")
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise LedgerAuthorityError("authority-config-changed-during-open")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                payload = handle.read()
        except OSError as exc:
            raise LedgerAuthorityError("cannot-read-authority-config") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        try:
            return dual_authority.parse_config_bytes(payload)
        except dual_authority.AuthorityConfigError as exc:
            raise LedgerAuthorityError(f"invalid-authority-config:{exc}") from exc

    @staticmethod
    def _current_previous_approval_ref(
        snapshot: Mapping[str, object], subject: Mapping[str, object],
    ) -> str | None:
        heads = snapshot.get("approval_heads")
        if not isinstance(heads, Mapping):
            raise LedgerTransitionError("invalid-current-approval-heads")
        try:
            key = approval.subject_key(subject)
        except approval.ApprovalError as exc:
            raise LedgerTransitionError(str(exc)) from exc
        head = heads.get(key)
        if head is None:
            return None
        if not isinstance(head, Mapping):
            raise LedgerTransitionError("invalid-current-approval-head")
        previous = head.get("head_ref")
        if not isinstance(previous, str) or not _SHA256.fullmatch(previous):
            raise LedgerTransitionError("invalid-current-approval-head-ref")
        return previous

    @staticmethod
    def _policy_mapping(policy: approval.AuthorizationPolicy) -> dict[str, object]:
        result: dict[str, object] = {
            "policy_id": policy.policy_id,
            "allowed_roles": list(policy.allowed_roles),
            "min_authn_assurance": policy.min_authn_assurance,
        }
        if policy.subject_type is not None:
            result["subject_type"] = policy.subject_type
        if policy.scope is not None:
            result["scope"] = policy.scope
        return result

    def _resolve_repo_relative_locked(
        self, relative_path: str, *, label: str, require_directory: bool = False,
        require_regular_file: bool = False,
    ) -> Path:
        """Resolve one request path without allowing a repository escape.

        The resolver is deliberately stricter than ``Path.resolve`` alone: all
        requested components must be ordinary path components below the repo;
        a symlink is rejected even when it currently points inward, so a later
        replacement cannot silently redirect a canonical command or artifact
        read.
        """
        _public_relative_path(relative_path, label=label, error_type=LedgerTransitionError)
        raw = Path(relative_path)
        if raw.parts and raw.parts[0] in {".git", CONTROL_DIRECTORY}:
            raise LedgerTransitionError(f"invalid-{label}")
        candidate = self.repo_root.joinpath(*raw.parts)
        cursor = self.repo_root
        for part in raw.parts:
            if part in {"", "."}:
                continue
            cursor = cursor / part
            try:
                mode = os.lstat(cursor).st_mode
            except FileNotFoundError as exc:
                raise LedgerTransitionError(f"missing-{label}") from exc
            except OSError as exc:
                raise LedgerTransitionError(f"unreadable-{label}") from exc
            if stat.S_ISLNK(mode):
                raise LedgerTransitionError(f"symlink-{label}-is-not-allowed")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.repo_root)
        except (OSError, ValueError) as exc:
            raise LedgerTransitionError(f"invalid-{label}") from exc
        if require_directory and not resolved.is_dir():
            raise LedgerTransitionError(f"{label}-is-not-a-directory")
        if require_regular_file:
            try:
                mode = os.stat(resolved, follow_symlinks=False).st_mode
            except OSError as exc:
                raise LedgerTransitionError(f"unreadable-{label}") from exc
            if not stat.S_ISREG(mode):
                raise LedgerTransitionError(f"{label}-must-be-a-regular-file")
        return resolved

    def _read_release_artifact_locked(self, artifact_path: str) -> tuple[Path, str]:
        """Read and hash a bounded, non-symlink artifact below ``repo_root``."""
        resolved = self._resolve_repo_relative_locked(
            artifact_path, label="artifact-path", require_regular_file=True,
        )
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(resolved, flags)
        except OSError as exc:
            raise LedgerTransitionError("cannot-open-artifact-path") from exc
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise LedgerTransitionError("artifact-path-must-be-a-regular-file")
            digest = hashlib.sha256()
            total = 0
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_RELEASE_ARTIFACT_BYTES:
                        raise LedgerTransitionError("release-artifact-too-large")
                    digest.update(chunk)
            return resolved, digest.hexdigest()
        except OSError as exc:
            raise LedgerTransitionError("cannot-read-artifact-path") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _git_output_locked(self, *arguments: str) -> bytes:
        """Run a fixed Git query without using a shell or request-supplied argv."""
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.repo_root), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError as exc:
            raise LedgerTransitionError("git-is-not-available") from exc
        if completed.returncode != 0:
            raise LedgerTransitionError("repository-is-not-a-git-worktree")
        return completed.stdout

    def _release_git_sha_locked(self) -> str:
        raw = self._git_output_locked("rev-parse", "--verify", "HEAD").strip()
        try:
            value = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise LedgerTransitionError("invalid-release-git-sha") from exc
        if not _GIT_SHA.fullmatch(value):
            raise LedgerTransitionError("invalid-release-git-sha")
        return value

    def _worktree_code_sha_locked(self) -> str:
        """Fingerprint the checked-out commit plus tracked and untracked bytes.

        ``HEAD`` alone would silently identify two different dirty worktrees as
        the same code.  The content address below includes Git's binary diff
        against HEAD and the bytes of each non-control untracked file.  The
        ledger's own control directory is intentionally excluded so recording
        evidence cannot change the code identity it is recording.
        """
        head = self._release_git_sha_locked().encode("ascii")
        binary_diff = self._git_output_locked("diff", "--binary", "HEAD", "--")
        untracked = self._git_output_locked("ls-files", "--others", "--exclude-standard", "-z")
        names = [item for item in untracked.split(b"\x00") if item]
        digest = hashlib.sha256()

        def add(label: bytes, payload: bytes) -> None:
            digest.update(label)
            digest.update(b"\x00")
            digest.update(str(len(payload)).encode("ascii"))
            digest.update(b"\x00")
            digest.update(payload)
            digest.update(b"\x00")

        add(b"format", b"dual-lifecycle-worktree-v1")
        add(b"head", head)
        add(b"tracked-diff", binary_diff)
        for raw_name in sorted(names):
            try:
                relative = raw_name.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise LedgerTransitionError("invalid-untracked-worktree-path") from exc
            path = Path(relative)
            if path.parts and path.parts[0] == CONTROL_DIRECTORY:
                continue
            resolved = self._resolve_repo_relative_locked(
                relative, label="untracked-worktree-path", require_regular_file=True,
            )
            try:
                payload = resolved.read_bytes()
            except OSError as exc:
                raise LedgerTransitionError("cannot-read-untracked-worktree-path") from exc
            add(b"untracked-path", raw_name)
            add(b"untracked-bytes", payload)
        return digest.hexdigest()

    @staticmethod
    def _require_exact_current_fence(
        snapshot: Mapping[str, object], *, feature_id: str, supplied_fence: Mapping[str, object],
    ) -> dict[str, object]:
        try:
            current = lifecycle_reducer.current_fence(snapshot, feature_id=feature_id)
        except lifecycle_reducer.ReducerError as exc:
            raise LedgerTransitionError(str(exc)) from exc
        if canonical_json_bytes(current) != canonical_json_bytes(supplied_fence):
            raise LedgerTransitionError("stale-contract-fence")
        return current

    @staticmethod
    def _preflight_current_task(
        snapshot: Mapping[str, object], *, feature_id: str, task_id: str, fence: Mapping[str, object],
        argv: Sequence[str], cwd: str,
    ) -> None:
        tasks = snapshot.get("tasks")
        if not isinstance(tasks, Mapping):
            raise LedgerTransitionError("invalid-current-tasks")
        matches = [
            raw for raw in tasks.values()
            if isinstance(raw, Mapping)
            and raw.get("feature_id") == feature_id
            and raw.get("task_id") == task_id
            and raw.get("delivery_plan_ref") == fence.get("delivery_plan_ref")
            and raw.get("contract_generation") == fence.get("contract_generation")
        ]
        if len(matches) != 1:
            raise LedgerTransitionError("unknown-current-task")
        if matches[0].get("status") in {"verified", "abandoned", "superseded"}:
            raise LedgerTransitionError("cannot-attach-evidence-to-terminal-task")
        strategy = matches[0].get("evidence_strategy")
        if not isinstance(strategy, Mapping) or strategy.get("kind") != "tdd":
            raise LedgerTransitionError("canonical-execution-strategy-not-supported")
        planned_argv = strategy.get("argv")
        planned_cwd = strategy.get("cwd")
        if not isinstance(planned_argv, list) or not all(isinstance(item, str) for item in planned_argv):
            raise LedgerTransitionError("invalid-task-evidence-strategy")
        if planned_argv != list(argv):
            raise LedgerTransitionError("evidence-command-does-not-match-delivery-plan")
        if planned_cwd != cwd:
            raise LedgerTransitionError("evidence-cwd-does-not-match-delivery-plan")

    @staticmethod
    def _preflight_publish(snapshot: Mapping[str, object], *, feature_id: str) -> None:
        """Avoid launching a release command when obvious release facts fail."""
        features = snapshot.get("features")
        claims = snapshot.get("claims")
        change_requests = snapshot.get("change_requests")
        feature = features.get(feature_id) if isinstance(features, Mapping) else None
        if not isinstance(feature, Mapping):
            raise LedgerTransitionError("unknown-feature")
        if feature.get("status") != "validated" or feature.get("validation_status") != "passed":
            raise LedgerTransitionError("ship-requires-validated-feature")
        if feature.get("review_status") != "approved":
            raise LedgerTransitionError("ship-requires-approved-review")
        leaf_id = feature.get("leaf_id")
        claim = claims.get(leaf_id) if isinstance(claims, Mapping) and isinstance(leaf_id, str) else None
        if not isinstance(claim, Mapping) or claim.get("feature_id") != feature_id or claim.get("status") != "active":
            raise LedgerTransitionError("ship-requires-active-feature-claim")
        if isinstance(change_requests, Mapping):
            blocking = sorted(
                str(change_request_id)
                for change_request_id, raw in change_requests.items()
                if isinstance(raw, Mapping)
                and raw.get("feature_id") == feature_id
                and raw.get("blocking") is True
                and raw.get("status") in {"open", "triaged", "accepted"}
            )
            if blocking:
                raise LedgerTransitionError("blocking-change-request-prevents-release:" + ",".join(blocking))

    def _canonicalize_requested_intent_locked(
        self, requested_intent: Mapping[str, object], snapshot: Mapping[str, object], *,
        idempotency_key: str | None = None, requested_intent_sha256: str | None = None,
    ) -> dict[str, object]:
        """Turn a public request into the one reducer intent persisted for replay.

        Only this new-apply path reads authority.json.  Event replay and an
        idempotent retry use the already stored canonical intent instead.
        """
        source = _strict_public_mapping(
            requested_intent, label="public-lifecycle-request", error_type=LedgerTransitionError,
        )
        operation = _public_operation(source, error_type=LedgerTransitionError)
        if operation in _RAW_INTERNAL_OPERATIONS:
            raise LedgerTransitionError(f"raw-internal-operation-is-not-public:{operation}")
        if operation == "request_approval":
            request = _parse_public_request_approval(source, error_type=LedgerTransitionError)
            config = self._load_authority_locked()
            previous = self._current_previous_approval_ref(snapshot, request["subject"])
            try:
                policy = dual_authority.select_policy(
                    config,
                    subject_type=str(request["subject"]["subject_type"]),
                    scope=str(request["subject"]["scope"]),
                    caller_payload=source,
                )
                approval_record = dual_authority.build_configured_approval(
                    config,
                    subject=request["subject"], decision=str(request["decision"]),
                    previous_approval_ref=previous,
                    decision_intent_ref=str(request["decision_intent_ref"]),
                    decided_at=str(request["at"]),
                    resolves_change_requests=request["resolves_change_requests"],
                    caller_payload=source,
                )
            except dual_authority.AuthorityConfigError as exc:
                raise LedgerAuthorityError(f"authority-request-rejected:{exc}") from exc
            return {
                "operation": "apply_approval",
                "approval_record": approval_record,
                "authorization_policy": self._policy_mapping(policy),
                "at": request["at"],
            }
        if operation == "decide_change_request":
            request = _parse_public_decide_change_request(source, error_type=LedgerTransitionError)
            config = self._load_authority_locked()
            try:
                actor = dual_authority.authorize_change_request(
                    config, action=request["decision"], caller_payload=source,
                )
            except dual_authority.AuthorityConfigError as exc:
                raise LedgerAuthorityError(f"authority-request-rejected:{exc}") from exc
            internal_operation = _CHANGE_REQUEST_INTERNAL_OPERATION[request["decision"]]
            canonical: dict[str, object] = {
                "operation": internal_operation,
                "change_request_id": request["change_request_id"],
                "at": request["at"],
            }
            if request["decision"] == "accept":
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", actor):
                    raise LedgerAuthorityError("configured-change-request-actor-is-not-lifecycle-id")
                canonical["accepted_by"] = actor
            return canonical
        if operation == "submit_feature_review":
            request = _parse_public_submit_feature_review(source, error_type=LedgerTransitionError)
            self._require_exact_current_fence(
                snapshot, feature_id=str(request["feature_id"]), supplied_fence=request["fence"],  # type: ignore[arg-type]
            )
            config = self._load_authority_locked()
            try:
                policy = dual_authority.select_policy(
                    config, subject_type="feature_review", scope="feature", caller_payload=source,
                )
                principal = dual_authority.resolve_configured_principal(config, caller_payload=source)
                attestation = review_attestation.build_review_attestation(
                    feature_id=str(request["feature_id"]),
                    decision=str(request["decision"]),
                    current_tuple=request["fence"],  # type: ignore[arg-type]
                    reviewer=principal,
                    authorization_policy=policy,
                    evidence_refs=request["evidence_refs"],  # type: ignore[arg-type]
                    rationale_ref=str(request["rationale_ref"]),
                    policy_manifest_ref=str(request["policy_manifest_ref"]),
                    context_manifest_ref=str(request["context_manifest_ref"]),
                    reviewed_at=str(request["at"]),
                )
            except (dual_authority.AuthorityConfigError, review_attestation.ReviewAttestationError) as exc:
                raise LedgerAuthorityError(f"review-authority-request-rejected:{exc}") from exc
            return {
                "operation": "review_feature",
                "feature_id": request["feature_id"],
                "fence": request["fence"],
                "attestation": attestation,
                "at": request["at"],
            }
        if operation == "execute_task_evidence":
            request = _parse_public_execute_task_evidence(source, error_type=LedgerTransitionError)
            self._require_exact_current_fence(
                snapshot, feature_id=str(request["feature_id"]), supplied_fence=request["fence"],  # type: ignore[arg-type]
            )
            cwd = self._resolve_repo_relative_locked(
                str(request["cwd"]), label="cwd", require_directory=True,
            )
            self._preflight_current_task(
                snapshot,
                feature_id=str(request["feature_id"]),
                task_id=str(request["task_id"]),
                fence=request["fence"],  # type: ignore[arg-type]
                argv=request["argv"],  # type: ignore[arg-type]
                cwd=str(request["cwd"]),
            )
            code_sha = self._worktree_code_sha_locked()
            if idempotency_key is None or requested_intent_sha256 is None:
                raise LedgerTransitionError("external-execution-missing-idempotency-context")
            self._write_execution_journal_locked(
                idempotency_key=idempotency_key,
                requested_intent_sha256=requested_intent_sha256,
                operation="execute_task_evidence",
            )
            try:
                runner_record = evidence_runner.run_canonical(
                    request["argv"],  # type: ignore[arg-type]
                    cwd=cwd,
                    timeout_seconds=float(request["timeout_seconds"]),
                    policy_manifest_ref=str(request["policy_manifest_ref"]),
                    context_manifest_ref=str(request["context_manifest_ref"]),
                    code_sha=code_sha,
                    tool_version=str(request["tool_version"]),
                    cwd_identity=_cwd_identity(str(request["cwd"])),
                )
                if self._worktree_code_sha_locked() != code_sha:
                    raise LedgerTransitionError("worktree-code-changed-during-canonical-execution")
            except evidence_runner.EvidenceError as exc:
                raise LedgerTransitionError(f"canonical-evidence-run-failed:{exc}") from exc
            return {
                "operation": "record_evidence",
                "runner_record": runner_record,
                "tested_sha": code_sha,
                "feature_id": request["feature_id"],
                "task_id": request["task_id"],
                "fence": request["fence"],
                "at": request["at"],
            }
        if operation == "publish_feature":
            request = _parse_public_publish_feature(source, error_type=LedgerTransitionError)
            self._require_exact_current_fence(
                snapshot, feature_id=str(request["feature_id"]), supplied_fence=request["fence"],  # type: ignore[arg-type]
            )
            self._preflight_publish(snapshot, feature_id=str(request["feature_id"]))
            cwd = self._resolve_repo_relative_locked(
                str(request["cwd"]), label="cwd", require_directory=True,
            )
            # Resolve before side effects, then hash after the canonical command:
            # the receipt binds the file that is actually present at publication.
            self._resolve_repo_relative_locked(
                str(request["artifact_path"]), label="artifact-path", require_regular_file=True,
            )
            release_sha = self._release_git_sha_locked()
            code_sha = self._worktree_code_sha_locked()
            if idempotency_key is None or requested_intent_sha256 is None:
                raise LedgerTransitionError("external-execution-missing-idempotency-context")
            self._write_execution_journal_locked(
                idempotency_key=idempotency_key,
                requested_intent_sha256=requested_intent_sha256,
                operation="publish_feature",
            )
            try:
                runner_record = evidence_runner.run_canonical(
                    request["argv"],  # type: ignore[arg-type]
                    cwd=cwd,
                    timeout_seconds=float(request["timeout_seconds"]),
                    policy_manifest_ref=str(request["policy_manifest_ref"]),
                    context_manifest_ref=str(request["context_manifest_ref"]),
                    code_sha=code_sha,
                    tool_version=str(request["tool_version"]),
                    cwd_identity=_cwd_identity(
                        str(request["cwd"]), artifact_path=str(request["artifact_path"]),
                    ),
                )
                if self._worktree_code_sha_locked() != code_sha:
                    raise LedgerTransitionError("worktree-code-changed-during-canonical-execution")
                _, artifact_sha256 = self._read_release_artifact_locked(str(request["artifact_path"]))
                if self._release_git_sha_locked() != release_sha:
                    raise LedgerTransitionError("release-commit-changed-during-command")
                release_receipt = dual_artifact_store.build_release_receipt(
                    runner_record,
                    feature_id=str(request["feature_id"]),
                    release_target=request["release_target"],  # type: ignore[arg-type]
                    actual_release_artifact={
                        **request["actual_release_artifact"],  # type: ignore[arg-type]
                        "artifact_sha256": artifact_sha256,
                    },
                    release_sha=release_sha,
                    current_tuple=request["fence"],  # type: ignore[arg-type]
                )
            except evidence_runner.EvidenceError as exc:
                raise LedgerTransitionError(f"canonical-release-run-failed:{exc}") from exc
            except dual_artifact_store.ArtifactStoreError as exc:
                # There is no lifecycle state for a failed publish.  Keep the
                # fsynced execution reservation so retry requires explicit
                # recovery instead of silently re-running an unknown deploy.
                raise LedgerTransitionError(f"canonical-release-receipt-rejected:{exc}") from exc
            return {
                "operation": "ship_feature",
                "feature_id": request["feature_id"],
                "fence": request["fence"],
                "release_receipt": release_receipt,
                "at": request["at"],
            }
        return deepcopy(source)

    def _write_locked(self, wrapper: Mapping[str, object]) -> None:
        path = self.ledger_path
        if path.is_symlink() or (path.exists() and not stat.S_ISREG(path.stat().st_mode)):
            raise LedgerIntegrityError("ledger-file-must-be-regular-non-symlink")
        payload = canonical_json_bytes(wrapper)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".ledger.", suffix=".tmp", dir=self.namespace_path)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            try:
                directory_fd = os.open(self.namespace_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            raise LedgerError(f"unable-to-atomically-write-ledger:{path}") from exc
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def status(self) -> LedgerStatus:
        """Read a detached view; absence is represented by the explicit sentinel."""
        with self._locked(exclusive=False):
            loaded = self._load_locked()
        if loaded is None:
            return LedgerStatus(
                initialized=False, snapshot_sha256=ABSENT_SNAPSHOT_SHA256, event_count=0,
                ledger_path=str(self.ledger_path), snapshot=None, events=(),
            )
        snapshot, current_sha, events = loaded.snapshot, loaded.snapshot_sha256, loaded.events
        return LedgerStatus(
            initialized=True, snapshot_sha256=current_sha, event_count=len(events),
            ledger_path=str(self.ledger_path), snapshot=deepcopy(snapshot),
            events=tuple(deepcopy(event) for event in events),
        )

    def snapshot(self) -> dict[str, object]:
        """Return the current canonical snapshot, or fail before initialization."""
        status = self.status()
        if status.snapshot is None:
            raise LedgerNotInitializedError("dual-lifecycle-ledger-is-not-initialized")
        return deepcopy(status.snapshot)

    def replay_snapshot(self) -> dict[str, object]:
        """Reconstruct the current snapshot from immutable events without writing.

        Loading already verifies the persisted snapshot equals this replay.  The
        method makes that verification boundary explicit to callers that audit
        a ledger; it never tries to replace a corrupt on-disk snapshot.
        """
        with self._locked(exclusive=False):
            loaded = self._load_locked()
        if loaded is None:
            raise LedgerNotInitializedError("dual-lifecycle-ledger-is-not-initialized")
        return deepcopy(loaded.snapshots_after_events[-1])

    def apply(
        self, *, intent: Mapping[str, object], expected_snapshot_sha256: str,
        idempotency_key: str, timestamp: str | None = None,
    ) -> ApplyResult:
        """Apply one public request and durably append its audit event under CAS.

        The absence sentinel is accepted only while no ledger file exists.  A
        repeated key with exactly the same public request returns the original
        event without re-reading authority.json or performing another transition.
        """
        expected = _expected_snapshot_sha(expected_snapshot_sha256)
        key = _idempotency_key(idempotency_key)
        normalized_requested_intent = _normalize_json(intent, label="public-lifecycle-request")
        if not isinstance(normalized_requested_intent, dict):
            raise LedgerTransitionError("invalid-public-lifecycle-request")
        requested_intent_hash = sha256_json(normalized_requested_intent)
        external_operation = normalized_requested_intent.get("operation")
        if external_operation not in {"execute_task_evidence", "publish_feature"}:
            external_operation = None
        event_timestamp = _timestamp(timestamp)

        with self._locked(exclusive=True):
            loaded = self._load_locked()
            if loaded is None:
                current_snapshot = lifecycle_reducer.empty_snapshot()
                current_sha = ABSENT_SNAPSHOT_SHA256
                events: list[dict[str, object]] = []
                snapshots_after_events: list[dict[str, object]] = []
            else:
                current_snapshot = loaded.snapshot
                current_sha = loaded.snapshot_sha256
                events = list(loaded.events)
                snapshots_after_events = list(loaded.snapshots_after_events)

            existing_index = next(
                (index for index, event in enumerate(events) if event["idempotency_key"] == key), None)
            if existing_index is not None:
                existing = events[existing_index]
                if existing["requested_intent_sha256"] != requested_intent_hash:
                    raise LedgerConflictError("idempotency-key-intent-mismatch")
                # A process can stop after the ledger event has been fsynced
                # but before its matching external-execution journal is
                # removed.  The durable event proves this exact request did
                # commit, so the same idempotency retry can clean only that
                # exact reservation without running the command again.
                unresolved_execution = self._load_execution_journal_locked()
                if (
                    unresolved_execution is not None
                    and unresolved_execution["idempotency_key"] == key
                    and unresolved_execution["requested_intent_sha256"] == requested_intent_hash
                ):
                    requested_operation = normalized_requested_intent.get("operation")
                    if (
                        requested_operation not in {"execute_task_evidence", "publish_feature"}
                        or unresolved_execution["operation"] != requested_operation
                    ):
                        raise LedgerIntegrityError("execution-journal-does-not-match-committed-event")
                    self._clear_execution_journal_locked(
                        idempotency_key=key,
                        requested_intent_sha256=requested_intent_hash,
                        operation=str(requested_operation),
                    )
                committed_snapshot = snapshots_after_events[existing_index]
                committed_sha = str(existing["next_snapshot_sha256"])
                return ApplyResult(
                    idempotent=True,
                    idempotency_key=key,
                    requested_intent_sha256=requested_intent_hash,
                    intent_sha256=str(existing["intent_sha256"]),
                    previous_snapshot_sha256=str(existing["previous_snapshot_sha256"]),
                    next_snapshot_sha256=committed_sha,
                    current_snapshot_sha256=committed_sha,
                    event=deepcopy(existing), event_count=existing_index + 1,
                    snapshot=deepcopy(committed_snapshot),
                )

            unresolved_execution = self._load_execution_journal_locked()
            if unresolved_execution is not None:
                if (
                    unresolved_execution["idempotency_key"] == key
                    and unresolved_execution["requested_intent_sha256"] == requested_intent_hash
                ):
                    raise LedgerConflictError("execution-recovery-required-for-idempotency-key")
                raise LedgerConflictError("another-execution-recovery-required")

            if expected != current_sha:
                raise LedgerConflictError(
                    f"stale-snapshot-cas:expected={expected}:actual={current_sha}")
            # An absence sentinel cannot be used against a persisted ledger,
            # including a ledger whose current snapshot happens to be empty.
            if expected == ABSENT_SNAPSHOT_SHA256 and loaded is not None:
                raise LedgerConflictError("absence-sentinel-is-only-valid-for-initialization")
            canonical_intent = self._canonicalize_requested_intent_locked(
                normalized_requested_intent, current_snapshot,
                idempotency_key=key, requested_intent_sha256=requested_intent_hash,
            )
            canonical_intent_hash = sha256_json(canonical_intent)
            try:
                lifecycle_reducer.validate_snapshot(current_snapshot)
                next_snapshot = lifecycle_reducer.reduce(current_snapshot, canonical_intent)
                lifecycle_reducer.validate_snapshot(next_snapshot)
            except lifecycle_reducer.ReducerError as exc:
                raise LedgerTransitionError(str(exc)) from exc
            next_sha = snapshot_sha256(next_snapshot)
            event = _build_event(
                sequence=len(events) + 1, idempotency_key=key,
                requested_intent=normalized_requested_intent,
                requested_intent_sha256=requested_intent_hash,
                intent=canonical_intent, intent_sha256=canonical_intent_hash,
                previous_snapshot_sha256=current_sha, next_snapshot_sha256=next_sha,
                timestamp=event_timestamp,
            )
            wrapper = _build_wrapper(next_snapshot, [*events, event])
            # Validate before persistence so the same contract protects both
            # in-memory construction and later reads.
            _validate_wrapper(wrapper)
            self._write_locked(wrapper)
            if external_operation is not None:
                self._clear_execution_journal_locked(
                    idempotency_key=key,
                    requested_intent_sha256=requested_intent_hash,
                    operation=external_operation,
                )
            return ApplyResult(
                idempotent=False,
                idempotency_key=key,
                requested_intent_sha256=requested_intent_hash,
                intent_sha256=canonical_intent_hash,
                previous_snapshot_sha256=current_sha,
                next_snapshot_sha256=next_sha,
                current_snapshot_sha256=next_sha,
                event=deepcopy(event), event_count=len(events) + 1,
                snapshot=deepcopy(dict(next_snapshot)),
            )

    def product_projection(self, *, leaf_id: str) -> dict[str, object]:
        """Return the reducer's read-only product-side delivery projection."""
        return lifecycle_reducer.project_delivery_status(self.snapshot(), leaf_id=leaf_id)

    def feature_projection(self, *, feature_id: str) -> dict[str, object]:
        """Return only one Feature's current delivery context for lazy skill loading."""
        return lifecycle_reducer.project_feature_status(self.snapshot(), feature_id=feature_id)


def _load_intent_from_args(args: argparse.Namespace) -> Mapping[str, object]:
    if args.intent_file is not None:
        try:
            raw = Path(args.intent_file).read_bytes()
        except OSError as exc:
            raise LedgerError(f"unable-to-read-intent-file:{args.intent_file}") from exc
    else:
        raw = args.intent_json.encode("utf-8")
    value = parse_strict_json_bytes(raw, label="intent", require_canonical=False)
    if not isinstance(value, Mapping):
        raise LedgerError("intent-must-be-a-json-object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable local dual-lifecycle ledger")
    parser.add_argument("--repo", default=".", help="repository root (default: current directory)")
    subcommands = parser.add_subparsers(dest="command", required=True)
    status = subcommands.add_parser("status", help="show ledger identity and initialization state")
    status.add_argument("--include-snapshot", action="store_true", help="include the full immutable snapshot")
    apply = subcommands.add_parser("apply", help="CAS-apply exactly one lifecycle intent")
    apply.add_argument("--expected-sha", required=True, help=f"current SHA-256 or {ABSENT_SNAPSHOT_SHA256!r} for first apply")
    apply.add_argument("--idempotency-key", required=True, help="stable request identity")
    source = apply.add_mutually_exclusive_group(required=True)
    source.add_argument("--intent-file", help="path to a JSON intent object")
    source.add_argument("--intent-json", help="inline JSON intent object")
    apply.add_argument("--timestamp", help="optional RFC 3339 timestamp for deterministic local audit tests")
    projection = subcommands.add_parser("product-projection", help="read the product-side delivery projection")
    projection.add_argument("--leaf-id", required=True)
    feature_projection = subcommands.add_parser(
        "feature-projection", help="read one Feature's minimal current delivery context",
    )
    feature_projection.add_argument("--feature-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        ledger = DualLifecycleLedger(args.repo)
        if args.command == "status":
            output = ledger.status().to_dict(include_snapshot=bool(args.include_snapshot))
        elif args.command == "apply":
            output = ledger.apply(
                intent=_load_intent_from_args(args), expected_snapshot_sha256=args.expected_sha,
                idempotency_key=args.idempotency_key, timestamp=args.timestamp,
            ).to_dict()
        elif args.command == "product-projection":
            output = ledger.product_projection(leaf_id=args.leaf_id)
        elif args.command == "feature-projection":
            output = ledger.feature_projection(feature_id=args.feature_id)
        else:  # argparse's required choices make this unreachable.
            raise LedgerError("unknown-command")
    except LedgerError as exc:
        print(f"dual-ledger-error: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes(output).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ABSENT_SNAPSHOT_SHA256", "ApplyResult", "AUTHORITY_FILENAME", "CONTROL_DIRECTORY", "DualLifecycleLedger",
    "EXECUTION_JOURNAL_FILENAME",
    "EVENT_FORMAT", "LEDGER_FILENAME", "LEDGER_FORMAT", "LEDGER_VERSION", "LedgerConflictError",
    "LedgerAuthorityError", "LedgerError", "LedgerIntegrityError", "LedgerNotInitializedError", "LedgerParseError",
    "LedgerStatus", "LedgerTransitionError", "NAMESPACE_DIRECTORY", "canonical_json_bytes",
    "parse_strict_json_bytes", "sha256_json", "snapshot_sha256",
]
