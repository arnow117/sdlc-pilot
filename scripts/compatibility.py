#!/usr/bin/env python3
"""Pure, exact comparison for Phase 1 legacy-versus-preview parity snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_SNAPSHOT_FIELDS = frozenset({
    "entrypoint", "route", "exit_status", "artifacts", "handoff", "state", "control_tree",
})
_STATE_FIELDS = frozenset({"stage", "status", "next_action"})
_EXCEPTION_FIELDS = frozenset({
    "id", "entrypoint", "path", "baseline", "candidate", "reason", "owner", "approval_ref",
})


class CompatibilityError(ValueError):
    """A parity input or exception registry is not a safe comparison contract."""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CompatibilityError(f"invalid-{label}")
    return value


def _require_snapshot(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) - (_REQUIRED_SNAPSHOT_FIELDS | {"legacy_approval_observation"}):
        raise CompatibilityError(f"invalid-{label}-snapshot-keys")
    missing = _REQUIRED_SNAPSHOT_FIELDS - set(value)
    if missing:
        raise CompatibilityError(f"missing-{label}-snapshot-fields:{','.join(sorted(missing))}")
    if not isinstance(value["entrypoint"], str) or not value["entrypoint"]:
        raise CompatibilityError(f"invalid-{label}-entrypoint")
    if not isinstance(value["exit_status"], int) or isinstance(value["exit_status"], bool):
        raise CompatibilityError(f"invalid-{label}-exit-status")
    if not isinstance(value["state"], dict) or set(value["state"]) != _STATE_FIELDS:
        raise CompatibilityError(f"invalid-{label}-state")
    if not isinstance(value["artifacts"], dict):
        raise CompatibilityError(f"invalid-{label}-artifacts")
    for path, artifact in value["artifacts"].items():
        if not isinstance(path, str) or not isinstance(artifact, dict) or set(artifact) != {"sha256", "schema"}:
            raise CompatibilityError(f"invalid-{label}-artifact")
        _require_sha(artifact["sha256"], f"{label}-artifact-sha")
        if not isinstance(artifact["schema"], str) or not artifact["schema"]:
            raise CompatibilityError(f"invalid-{label}-artifact-schema")
    if not isinstance(value["control_tree"], dict):
        raise CompatibilityError(f"invalid-{label}-control-tree")
    for path, digest in value["control_tree"].items():
        if not isinstance(path, str):
            raise CompatibilityError(f"invalid-{label}-control-path")
        _require_sha(digest, f"{label}-control-sha")
    if "legacy_approval_observation" in value:
        observation = value["legacy_approval_observation"]
        if not isinstance(observation, dict) or set(observation) != {"kind", "scope", "legacy_spec_sha256"}:
            raise CompatibilityError(f"invalid-{label}-legacy-approval-observation")
        if observation["kind"] != "legacy_approval_observation" or observation["scope"] != "preview":
            raise CompatibilityError(f"unsafe-{label}-legacy-approval-observation")
        _require_sha(observation["legacy_spec_sha256"], f"{label}-legacy-spec-sha")
    return value


def _path_join(parent: str, child: str) -> str:
    return child if not parent else f"{parent}.{child}"


def _diff(left: object, right: object, path: str = "") -> list[dict[str, object]]:
    if isinstance(left, dict) and isinstance(right, dict):
        differences: list[dict[str, object]] = []
        for key in sorted(set(left) | set(right)):
            child_path = _path_join(path, str(key))
            if key not in left:
                differences.append({"path": child_path, "baseline": None, "candidate": right[key]})
            elif key not in right:
                differences.append({"path": child_path, "baseline": left[key], "candidate": None})
            else:
                differences.extend(_diff(left[key], right[key], child_path))
        return differences
    if isinstance(left, list) and isinstance(right, list):
        if left == right:
            return []
        return [{"path": path, "baseline": left, "candidate": right}]
    if left != right:
        return [{"path": path, "baseline": left, "candidate": right}]
    return []


def _normalize_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Keep comparison scoped to observable legacy authority and stable byte identities."""
    normalized = {
        "entrypoint": snapshot["entrypoint"],
        "route": snapshot["route"],
        "exit_status": snapshot["exit_status"],
        "artifacts": snapshot["artifacts"],
        "handoff": snapshot["handoff"],
        "state": snapshot["state"],
        "control_tree": snapshot["control_tree"],
    }
    if "legacy_approval_observation" in snapshot:
        normalized["legacy_approval_observation"] = snapshot["legacy_approval_observation"]
    return normalized


def _normalize_exceptions(value: Sequence[object]) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CompatibilityError("invalid-exception-registry")
    normalized: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != _EXCEPTION_FIELDS:
            raise CompatibilityError("invalid-exception-keys")
        item = dict(raw)
        for key in ("id", "entrypoint", "path", "reason", "owner", "approval_ref"):
            if not isinstance(item[key], str) or not item[key]:
                raise CompatibilityError(f"invalid-exception-{key}")
        normalized.append(item)
    if len({str(item["id"]) for item in normalized}) != len(normalized):
        raise CompatibilityError("duplicate-exception-id")
    return sorted(normalized, key=lambda item: str(item["id"]))


def _matching_exception(
    difference: Mapping[str, object], entrypoint: str, exceptions: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    for exception in exceptions:
        if (
            exception["entrypoint"] == entrypoint
            and exception["path"] == difference["path"]
            and exception["baseline"] == difference["baseline"]
            and exception["candidate"] == difference["candidate"]
        ):
            return exception
    return None


def compare_legacy(
    baseline: Mapping[str, object], candidate: Mapping[str, object], exception_registry: Sequence[object] = (),
) -> dict[str, object]:
    """Compare two parity snapshots without writing any repository or control state."""
    baseline = _require_snapshot(baseline, "baseline")
    candidate = _require_snapshot(candidate, "candidate")
    if baseline["entrypoint"] != candidate["entrypoint"]:
        raise CompatibilityError("entrypoint-mismatch")
    exceptions = _normalize_exceptions(exception_registry)
    differences = _diff(_normalize_snapshot(baseline), _normalize_snapshot(candidate))
    classified: list[dict[str, object]] = []
    for difference in differences:
        item = dict(difference)
        match = _matching_exception(item, str(baseline["entrypoint"]), exceptions)
        if match is not None:
            item["exception_id"] = match["id"]
            item["accepted"] = True
        else:
            item["accepted"] = False
        classified.append(item)
    classified.sort(key=lambda item: str(item["path"]))
    accepted = [item for item in classified if item["accepted"]]
    unexpected = [item for item in classified if not item["accepted"]]
    return {
        "entrypoint": baseline["entrypoint"],
        "baseline_sha256": canonical_hash(_normalize_snapshot(baseline)),
        "candidate_sha256": canonical_hash(_normalize_snapshot(candidate)),
        "differences": classified,
        "accepted_differences": accepted,
        "unexpected_differences": unexpected,
        "verdict": "PASS" if not unexpected else "FAIL",
    }
