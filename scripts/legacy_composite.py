#!/usr/bin/env python3
"""Render the Phase 1 legacy ``spec -> plan`` bridge as a preview artifact.

This module deliberately has no dependency on the control store, approval
records, or engineering-contract types.  It accepts only an already approved
legacy spec plus its *observation*, then emits a non-authoritative
``LegacyPlan`` under ``.sdlc/preview``.  The output is a diagnostic artifact;
it cannot advance a lifecycle or stand in for an EngineeringSpec.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping


RENDERER_VERSION = "legacy-composite-preview-renderer-v1"
POLICY_MANIFEST_SCHEMA = "sdlc-policy-manifest-v1"
PHASE_ID = "phase.compatibility.legacy-composite-v1"
ADAPTER_ID = "legacy-composite-v1"
PLAN_FILENAME = "plan.shadow.md"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PREVIEW_ACTIVATION = {
    "scope": "preview",
    "explicit_invocation_only": True,
    "control_mutations": False,
    "output_scope": "preview",
    "unknown_selector": "needs_classification",
    "legacy_projection": "legacy-route-projection-v1",
    "legacy_bridge": ADAPTER_ID,
}


class LegacyCompositeError(ValueError):
    """A preview bridge input would be ambiguous or escape its authority."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: object) -> bytes:
    """Encode metadata deterministically before calculating its identity."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LegacyCompositeError("non-canonical-observation") from exc
    return (encoded + "\n").encode("utf-8")


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise LegacyCompositeError(f"invalid-{label}")
    return value


def _require_run_id(value: object) -> str:
    if not isinstance(value, str) or not _RUN_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise LegacyCompositeError("invalid-lifecycle-run-id")
    return value


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LegacyCompositeError(f"invalid-{label}")
    return value


def _validate_observation(
    legacy_spec_bytes: object,
    legacy_approval_observation: object,
) -> tuple[bytes, Mapping[str, object], str, str]:
    if not isinstance(legacy_spec_bytes, bytes):
        raise LegacyCompositeError("invalid-approved-legacy-spec-bytes")
    observation = _require_mapping(legacy_approval_observation, "legacy-approval-observation")
    expected_keys = {"kind", "scope", "legacy_spec_sha256"}
    if set(observation) != expected_keys:
        raise LegacyCompositeError("invalid-legacy-approval-observation-keys")
    if observation["kind"] != "legacy_approval_observation":
        raise LegacyCompositeError("invalid-legacy-approval-observation-kind")
    if observation["scope"] != "preview":
        raise LegacyCompositeError("invalid-legacy-approval-observation-scope")
    observed_spec_sha = _require_sha256(
        observation["legacy_spec_sha256"], "legacy-approval-observation-spec-sha256")
    actual_spec_sha = sha256_bytes(legacy_spec_bytes)
    if observed_spec_sha != actual_spec_sha:
        raise LegacyCompositeError("legacy-approval-observation-spec-sha256-mismatch")
    return legacy_spec_bytes, observation, actual_spec_sha, sha256_bytes(canonical_bytes(observation))


def _contract_pairs(
    value: object,
    *,
    state_key: str,
    label: str,
) -> set[tuple[object, object]]:
    if not isinstance(value, list) or not value:
        raise LegacyCompositeError(f"invalid-{label}")
    pairs: set[tuple[object, object]] = set()
    for item in value:
        contract = _require_mapping(item, label)
        if set(contract) != {"id", "kind", state_key}:
            raise LegacyCompositeError(f"invalid-{label}")
        if not isinstance(contract["id"], str) or not contract["id"]:
            raise LegacyCompositeError(f"invalid-{label}")
        if not isinstance(contract["kind"], str) or not contract["kind"]:
            raise LegacyCompositeError(f"invalid-{label}")
        if not isinstance(contract[state_key], str) or not contract[state_key]:
            raise LegacyCompositeError(f"invalid-{label}")
        pairs.add((contract["kind"], contract[state_key]))
    if len(pairs) != len(value):
        raise LegacyCompositeError(f"duplicate-{label}")
    return pairs


def _resolve_legacy_composite_phase(
    policy_manifest: object,
    policy_manifest_ref: object,
    phase_contract_ref: object,
) -> tuple[str, str]:
    manifest = _require_mapping(policy_manifest, "policy-manifest")
    if manifest.get("schema_version") != POLICY_MANIFEST_SCHEMA:
        raise LegacyCompositeError("unsupported-policy-manifest-schema")
    manifest_id = _require_sha256(manifest.get("policy_manifest_id"), "policy-manifest-id")
    if _require_sha256(policy_manifest_ref, "policy-manifest-ref") != manifest_id:
        raise LegacyCompositeError("policy-manifest-ref-mismatch")
    activation = _require_mapping(manifest.get("activation"), "policy-activation")
    if dict(activation) != _PREVIEW_ACTIVATION:
        raise LegacyCompositeError("non-preview-policy-activation")
    if manifest.get("migration_version") != "phase1-preview-v1":
        raise LegacyCompositeError("unsupported-policy-migration")
    if not isinstance(phase_contract_ref, str) or not phase_contract_ref:
        raise LegacyCompositeError("invalid-phase-contract-ref")
    phases = manifest.get("phases")
    if not isinstance(phases, list):
        raise LegacyCompositeError("invalid-policy-phases")
    matching = [
        _require_mapping(phase, "policy-phase")
        for phase in phases
        if isinstance(phase, Mapping) and phase.get("phase_contract_ref") == phase_contract_ref
    ]
    if len(matching) != 1:
        raise LegacyCompositeError("unknown-phase-contract-ref")
    phase = matching[0]
    expected_ref = f"{manifest_id}#{PHASE_ID}"
    if phase_contract_ref != expected_ref:
        raise LegacyCompositeError("not-legacy-composite-phase")
    if (
        phase.get("id") != PHASE_ID
        or phase.get("lifecycle") != "compatibility"
        or phase.get("stage") != ADAPTER_ID
        or phase.get("compatibility_adapter") != ADAPTER_ID
    ):
        raise LegacyCompositeError("invalid-legacy-composite-phase")
    if _contract_pairs(phase.get("input_contracts"), state_key="state", label="legacy-bridge-input-contracts") != {
        ("LegacySpec", "approved"),
        ("LegacyApprovalObservation", "observed"),
    }:
        raise LegacyCompositeError("invalid-legacy-bridge-input-contracts")
    if _contract_pairs(phase.get("output_contracts"), state_key="scope", label="legacy-bridge-output-contracts") != {
        ("LegacyPlan", "preview"),
    }:
        raise LegacyCompositeError("invalid-legacy-bridge-output-contracts")
    transition = _require_mapping(phase.get("transition_intent"), "legacy-bridge-transition")
    if transition.get("scope") != "preview":
        raise LegacyCompositeError("legacy-bridge-transition-escapes-preview")
    return manifest_id, expected_ref


def render_legacy_composite_preview(
    *,
    legacy_spec_bytes: bytes,
    legacy_approval_observation: Mapping[str, object],
    policy_manifest: Mapping[str, object],
    policy_manifest_ref: str,
    phase_contract_ref: str,
    lifecycle_run_id: str,
) -> str:
    """Return a deterministic ``LegacyPlan`` preview without writing state.

    ``legacy_approval_observation`` remains observational input only.  This
    function does not derive an approval, an EngineeringSpec, or a control
    record from it.
    """
    run_id = _require_run_id(lifecycle_run_id)
    _, observation, spec_sha, observation_sha = _validate_observation(
        legacy_spec_bytes, legacy_approval_observation)
    manifest_id, resolved_phase_ref = _resolve_legacy_composite_phase(
        policy_manifest, policy_manifest_ref, phase_contract_ref)
    lines = [
        "# Legacy Composite Preview Plan",
        "",
        "artifact_kind: LegacyPlan",
        "scope: preview",
        "plan_format: shadow-delivery-plan-v1",
        f"adapter: {ADAPTER_ID}",
        f"renderer_version: {RENDERER_VERSION}",
        f"lifecycle_run_id: {run_id}",
        f"policy_manifest_ref: {manifest_id}",
        f"phase_contract_ref: {resolved_phase_ref}",
        f"legacy_spec_sha256: {spec_sha}",
        f"legacy_approval_observation_sha256: {observation_sha}",
        f"legacy_approval_observation_kind: {observation['kind']}",
        f"legacy_approval_observation_scope: {observation['scope']}",
        "",
        "## Preview boundary",
        "",
        "- This artifact is a Phase 1 preview diagnostic only.",
        "- It does not create an EngineeringSpec, an approval record, or a control record.",
        "- The approved legacy spec is preserved by its byte hash and is not reclassified.",
        "",
    ]
    return "\n".join(lines)


def preview_plan_path(repo_root: str | os.PathLike[str], lifecycle_run_id: str) -> Path:
    """Return the only legal Phase 1 output path; do not create it."""
    return Path(repo_root) / ".sdlc" / "preview" / _require_run_id(lifecycle_run_id) / PLAN_FILENAME


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_preview_directory(repo_root: str | os.PathLike[str], lifecycle_run_id: str) -> Path:
    try:
        root = Path(repo_root).resolve(strict=True)
    except OSError as exc:
        raise LegacyCompositeError("preview-repository-root-does-not-exist") from exc
    if not root.is_dir():
        raise LegacyCompositeError("preview-repository-root-not-directory")
    current = root
    for component in (".sdlc", "preview", _require_run_id(lifecycle_run_id)):
        current = current / component
        if current.is_symlink():
            raise LegacyCompositeError("preview-path-symlink-not-allowed")
        try:
            current.mkdir(exist_ok=True)
        except OSError as exc:
            raise LegacyCompositeError("preview-directory-unavailable") from exc
        if not current.is_dir():
            raise LegacyCompositeError("preview-path-not-directory")
        resolved = current.resolve(strict=True)
        if not _is_within(resolved, root):
            raise LegacyCompositeError("preview-path-escapes-repository")
    return current


def write_legacy_composite_preview(
    repo_root: str | os.PathLike[str],
    *,
    legacy_spec_bytes: bytes,
    legacy_approval_observation: Mapping[str, object],
    policy_manifest: Mapping[str, object],
    policy_manifest_ref: str,
    phase_contract_ref: str,
    lifecycle_run_id: str,
) -> Path:
    """Render and create one preview artifact without touching ``.sdlc/plan.md``.

    The target is created with exclusive creation semantics.  A prior preview
    artifact is immutable, so this function never replaces it.
    """
    text = render_legacy_composite_preview(
        legacy_spec_bytes=legacy_spec_bytes,
        legacy_approval_observation=legacy_approval_observation,
        policy_manifest=policy_manifest,
        policy_manifest_ref=policy_manifest_ref,
        phase_contract_ref=phase_contract_ref,
        lifecycle_run_id=lifecycle_run_id,
    )
    destination_dir = _ensure_preview_directory(repo_root, lifecycle_run_id)
    destination = destination_dir / PLAN_FILENAME
    if destination.exists() or destination.is_symlink():
        raise LegacyCompositeError("preview-artifact-already-exists")
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise LegacyCompositeError("preview-artifact-already-exists") from exc
    except OSError as exc:
        raise LegacyCompositeError("preview-artifact-create-failed") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LegacyCompositeError("preview-artifact-write-failed") from exc
    return destination
