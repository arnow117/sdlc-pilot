#!/usr/bin/env python3
"""Resolve a compiled PolicyManifest into a deterministic preview ContextManifest.

The resolver is intentionally read-only.  Phase 1 accepts only an already
compiled preview policy and returns metadata about the minimum context pack;
it never reads legacy control state or writes repository files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


CONTEXT_SCHEMA = "sdlc-context-manifest-v1"
POLICY_MANIFEST_SCHEMA = "sdlc-policy-manifest-v1"
POLICY_FORMAT = "sdlc-policy-v1"
PREVIEW_MIGRATION_VERSION = "phase1-preview-v1"
DEFAULT_BYTE_BUDGET = 40_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_AUTHORITY_MODES = frozenset({"legacy", "local-serial", "shared-control"})
_DIFF_SCOPES = frozenset({"task", "feature", "legacy", "audit"})
_REQUIRED_REQUEST_KEYS = frozenset({
    "scope",
    "command",
    "lifecycle_run_id",
    "phase_id",
    "lifecycle",
    "operation",
    "work_type",
    "authority_mode",
    "identity",
    "contracts",
    "profile",
    "diff",
    "intent_flags",
    "runtime_event",
    "engine_version",
    "modes",
    "selector_attestation_refs",
})
_OPTIONAL_REQUEST_KEYS = frozenset({"byte_budget"})
_ACTIVATION_EXPECTED = {
    "scope": "preview",
    "explicit_invocation_only": True,
    "control_mutations": False,
    "output_scope": "preview",
    "unknown_selector": "needs_classification",
    "legacy_projection": "legacy-route-projection-v1",
    "legacy_bridge": "legacy-composite-v1",
}
_SECRET_PATH_PARTS = frozenset({
    ".aws",
    ".env",
    "credentials",
    "credential",
    "secret",
    "secrets",
    "private",
    "id_rsa",
})
_SECRET_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx", ".kdbx"})


class ContextError(RuntimeError):
    """The requested context cannot be resolved safely or deterministically."""


@dataclass(frozen=True)
class SelectorResult:
    state: str
    unknown_fields: tuple[str, ...] = ()


@dataclass
class ModuleReason:
    dependency_of: set[str] = field(default_factory=set)
    matched_rule_ids: set[str] = field(default_factory=set)
    required_by_obligation_ids: set[str] = field(default_factory=set)
    unknown_rule_ids: set[str] = field(default_factory=set)


@dataclass
class FilePreflight:
    relative_path: str
    resolved_path: Path
    sha256: str
    utf8_bytes: int
    required_by: set[str] = field(default_factory=set)


def canonical_bytes(value: object) -> bytes:
    """Encode deterministic JSON for identities and emitted manifests."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContextError("non-canonical-json-value") from exc
    return (encoded + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_module_path(root: Path, relative: str) -> Path:
    """Resolve a module file without permitting an absolute or symlink escape."""
    if not isinstance(relative, str) or not relative:
        raise ContextError("invalid-module-path")
    pure_path = PurePosixPath(relative)
    if (
        pure_path.is_absolute()
        or relative != pure_path.as_posix()
        or not pure_path.parts
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in pure_path.parts)
    ):
        raise ContextError(f"unsafe-module-path:{relative}")
    try:
        resolved_root = root.resolve(strict=True)
        if not resolved_root.is_dir():
            raise ContextError("skill-root-is-not-directory")
        resolved = resolved_root.joinpath(*pure_path.parts).resolve(strict=True)
        resolved.relative_to(resolved_root)
    except ContextError:
        raise
    except (OSError, ValueError) as exc:
        raise ContextError(f"module-path-escapes-skill-root:{relative}") from exc
    if not resolved.is_file():
        raise ContextError(f"module-path-is-not-file:{relative}")
    return resolved


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ContextError(f"invalid-{label}")
    return value


def _require_exact_keys(value: object, keys: frozenset[str], label: str) -> Mapping[str, object]:
    mapping = _require_mapping(value, label)
    if set(mapping) != keys:
        raise ContextError(f"invalid-{label}-keys")
    return mapping


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ContextError(f"invalid-{label}")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ContextError(f"invalid-{label}")
    return value


def _require_git_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise ContextError(f"invalid-{label}")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ContextError(f"invalid-{label}")
    return value


def _normalize_json(value: object, label: str, *, depth: int = 0) -> object:
    if depth > 32:
        raise ContextError(f"{label}-too-deep")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContextError(f"invalid-{label}-number")
        return value
    if isinstance(value, list):
        return [_normalize_json(item, label, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key in sorted(value):
            if not isinstance(key, str) or not key:
                raise ContextError(f"invalid-{label}-key")
            result[key] = _normalize_json(value[key], label, depth=depth + 1)
        return result
    raise ContextError(f"invalid-{label}")


def _normalize_object(value: object, label: str, *, allow_empty: bool = False) -> dict[str, object]:
    mapping = _require_mapping(value, label)
    if not mapping and not allow_empty:
        raise ContextError(f"empty-{label}")
    normalized = _normalize_json(mapping, label)
    assert isinstance(normalized, dict)
    return normalized


def _normalize_string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContextError(f"invalid-{label}")
    normalized = [_require_text(item, f"{label}-item") for item in value]
    if len(set(normalized)) != len(normalized):
        raise ContextError(f"duplicate-{label}")
    return sorted(normalized)


def _semver(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _SEMVER_RE.fullmatch(value):
        raise ContextError(f"invalid-{label}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _normalize_request(request: Mapping[str, object]) -> dict[str, object]:
    source = _require_mapping(request, "context-request")
    if not _REQUIRED_REQUEST_KEYS.issubset(source) or not set(source).issubset(
        _REQUIRED_REQUEST_KEYS | _OPTIONAL_REQUEST_KEYS
    ):
        raise ContextError("invalid-context-request-keys")
    if source["scope"] != "preview":
        raise ContextError("preview-scope-required")
    authority_mode = _require_text(source["authority_mode"], "authority-mode")
    if authority_mode not in _AUTHORITY_MODES:
        raise ContextError("unsupported-authority-mode")
    profile = _require_exact_keys(source["profile"], frozenset({"sha256"}), "profile")
    diff = _require_exact_keys(
        source["diff"],
        frozenset({"scope", "base_sha", "head_sha", "dirty", "staged", "untracked"}),
        "diff",
    )
    diff_scope = _require_text(diff["scope"], "diff-scope")
    if diff_scope not in _DIFF_SCOPES:
        raise ContextError("unsupported-diff-scope")
    if not all(isinstance(diff[field], bool) for field in ("dirty", "staged", "untracked")):
        raise ContextError("invalid-diff-worktree-flags")
    runtime_event = _normalize_object(source["runtime_event"], "runtime-event")
    _require_text(runtime_event.get("type"), "runtime-event-type")
    return {
        "scope": "preview",
        "command": _require_text(source["command"], "command"),
        "lifecycle_run_id": _require_text(source["lifecycle_run_id"], "lifecycle-run-id"),
        "phase_id": _require_text(source["phase_id"], "phase-id"),
        "lifecycle": _require_text(source["lifecycle"], "lifecycle"),
        "operation": _require_text(source["operation"], "operation"),
        "work_type": _require_text(source["work_type"], "work-type"),
        "authority_mode": authority_mode,
        "identity": _normalize_object(source["identity"], "identity"),
        "contracts": _normalize_object(source["contracts"], "contracts", allow_empty=True),
        "profile": {"sha256": _require_sha256(profile["sha256"], "profile-sha256")},
        "diff": {
            "scope": diff_scope,
            "base_sha": _require_git_sha(diff["base_sha"], "diff-base-sha"),
            "head_sha": _require_git_sha(diff["head_sha"], "diff-head-sha"),
            "dirty": diff["dirty"],
            "staged": diff["staged"],
            "untracked": diff["untracked"],
        },
        "intent_flags": _normalize_object(source["intent_flags"], "intent-flags", allow_empty=True),
        "runtime_event": runtime_event,
        "engine_version": _require_text(source["engine_version"], "engine-version"),
        "modes": _normalize_string_list(source["modes"], "modes", allow_empty=True),
        "selector_attestation_refs": _normalize_string_list(
            source["selector_attestation_refs"], "selector-attestation-refs", allow_empty=True),
        "byte_budget": _require_positive_int(source.get("byte_budget", DEFAULT_BYTE_BUDGET), "byte-budget"),
    }


def _index_by_id(value: object, label: str) -> dict[str, Mapping[str, object]]:
    if not isinstance(value, list) or not value:
        raise ContextError(f"invalid-{label}")
    indexed: dict[str, Mapping[str, object]] = {}
    for item in value:
        mapping = _require_mapping(item, f"{label}-item")
        item_id = _require_text(mapping.get("id"), f"{label}-id")
        if item_id in indexed:
            raise ContextError(f"duplicate-{label}-id:{item_id}")
        indexed[item_id] = mapping
    return indexed


def _rule_ids(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    return _normalize_string_list(value, label, allow_empty=allow_empty)


def _validate_preview_policy(
    policy_manifest: Mapping[str, object],
    request: Mapping[str, object],
) -> tuple[
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
    Mapping[str, object],
    dict[str, Mapping[str, object]],
]:
    manifest = _require_mapping(policy_manifest, "policy-manifest")
    if manifest.get("schema_version") != POLICY_MANIFEST_SCHEMA:
        raise ContextError("unsupported-policy-manifest-schema")
    if manifest.get("policy_format") != POLICY_FORMAT:
        raise ContextError("unsupported-policy-format")
    _require_sha256(manifest.get("policy_manifest_id"), "policy-manifest-id")
    if manifest.get("migration_version") != PREVIEW_MIGRATION_VERSION:
        raise ContextError("preview-policy-required")
    activation = _require_mapping(manifest.get("activation"), "policy-activation")
    if dict(activation) != _ACTIVATION_EXPECTED:
        raise ContextError("preview-policy-required")
    engine_api = _require_mapping(manifest.get("engine_api"), "policy-engine-api")
    minimum = _semver(engine_api.get("min_inclusive"), "policy-engine-min")
    maximum = _semver(engine_api.get("max_exclusive"), "policy-engine-max")
    engine = _semver(request["engine_version"], "engine-version")
    if minimum >= maximum or not minimum <= engine < maximum:
        raise ContextError("engine-version-not-compatible")

    rules = _index_by_id(manifest.get("rules"), "policy-rule")
    modules = _index_by_id(manifest.get("modules"), "policy-module")
    roles = _index_by_id(manifest.get("roles"), "policy-role")
    phases = _index_by_id(manifest.get("phases"), "policy-phase")

    closure_source = manifest.get("dependency_closure")
    if not isinstance(closure_source, list) or not closure_source:
        raise ContextError("invalid-policy-dependency-closure")
    closure: dict[str, Mapping[str, object]] = {}
    for item in closure_source:
        mapping = _require_mapping(item, "policy-dependency-closure-item")
        path = _require_text(mapping.get("path"), "policy-dependency-path")
        _require_sha256(mapping.get("sha256"), "policy-dependency-sha256")
        _require_positive_int(mapping.get("utf8_bytes"), "policy-dependency-bytes")
        if path in closure:
            raise ContextError(f"duplicate-policy-dependency-path:{path}")
        closure[path] = mapping

    for rule_id, rule in rules.items():
        if rule.get("kind") != "selector":
            raise ContextError(f"invalid-policy-rule-kind:{rule_id}")
        target = _require_mapping(rule.get("target"), f"policy-rule-target:{rule_id}")
        _require_text(target.get("kind"), f"policy-rule-target-kind:{rule_id}")
        _require_text(target.get("id"), f"policy-rule-target-id:{rule_id}")
        _evaluate_selector(rule.get("when"), {}, validate_only=True)
    for module_id, module in modules.items():
        lifecycles = _normalize_string_list(module.get("lifecycles"), f"policy-module-lifecycles:{module_id}")
        if not lifecycles:
            raise ContextError(f"invalid-policy-module-lifecycles:{module_id}")
        dependencies = _rule_ids(module.get("depends_on"), f"policy-module-dependencies:{module_id}", allow_empty=True)
        if any(dependency not in modules for dependency in dependencies):
            raise ContextError(f"unknown-policy-module-dependency:{module_id}")
        selector_ids = _rule_ids(module.get("selector_rule_ids"), f"policy-module-rules:{module_id}")
        if any(rule_id not in rules for rule_id in selector_ids):
            raise ContextError(f"unknown-policy-module-rule:{module_id}")
        for rule_id in selector_ids:
            if rules[rule_id].get("target") != {"kind": "module", "id": module_id}:
                raise ContextError(f"invalid-policy-module-rule-target:{module_id}:{rule_id}")
        playbook = _require_mapping(module.get("playbook"), f"policy-module-playbook:{module_id}")
        path = _require_text(playbook.get("path"), f"policy-module-path:{module_id}")
        sha256 = _require_sha256(playbook.get("sha256"), f"policy-module-sha256:{module_id}")
        max_bytes = _require_positive_int(module.get("max_bytes"), f"policy-module-max-bytes:{module_id}")
        closure_item = closure.get(path)
        if closure_item is None:
            raise ContextError(f"module-missing-policy-closure:{module_id}")
        if closure_item["sha256"] != sha256:
            raise ContextError(f"module-policy-closure-hash-mismatch:{module_id}")
        if int(closure_item["utf8_bytes"]) > max_bytes:
            raise ContextError(f"module-policy-byte-budget-exceeded:{module_id}")
    for role_id, role in roles.items():
        eligibility = _rule_ids(role.get("eligibility_rule_ids"), f"policy-role-rules:{role_id}", allow_empty=True)
        if any(rule_id not in rules for rule_id in eligibility):
            raise ContextError(f"unknown-policy-role-rule:{role_id}")

    policy_id = str(manifest["policy_manifest_id"])
    for phase_id, phase in phases.items():
        lifecycle = _require_text(phase.get("lifecycle"), f"policy-phase-lifecycle:{phase_id}")
        method_modules = _rule_ids(phase.get("method_module_ids"), f"policy-phase-modules:{phase_id}")
        if any(module_id not in modules for module_id in method_modules):
            raise ContextError(f"unknown-policy-phase-module:{phase_id}")
        if any(lifecycle not in _normalize_string_list(modules[module_id].get("lifecycles"), f"policy-module-lifecycles:{module_id}")
               for module_id in method_modules):
            raise ContextError(f"cross-lifecycle-policy-module:{phase_id}")
        entry_rules = _rule_ids(phase.get("entry_predicate_rule_ids"), f"policy-phase-entry-rules:{phase_id}")
        if any(rule_id not in rules for rule_id in entry_rules):
            raise ContextError(f"unknown-policy-phase-entry-rule:{phase_id}")
        if phase.get("phase_contract_ref") != f"{policy_id}#{phase_id}":
            raise ContextError(f"invalid-phase-contract-ref:{phase_id}")
        outputs = phase.get("output_contracts")
        if not isinstance(outputs, list) or not outputs:
            raise ContextError(f"invalid-policy-phase-outputs:{phase_id}")
        for output in outputs:
            if _require_mapping(output, f"policy-phase-output:{phase_id}").get("scope") != "preview":
                raise ContextError(f"non-preview-phase-output:{phase_id}")
        transition = _require_mapping(phase.get("transition_intent"), f"policy-phase-transition:{phase_id}")
        if transition.get("scope") != "preview":
            raise ContextError(f"non-preview-phase-transition:{phase_id}")
        obligations = phase.get("obligations")
        if not isinstance(obligations, list):
            raise ContextError(f"invalid-policy-phase-obligations:{phase_id}")
        for obligation in obligations:
            item = _require_mapping(obligation, f"policy-obligation:{phase_id}")
            obligation_id = _require_text(item.get("id"), f"policy-obligation-id:{phase_id}")
            role_id = _require_text(item.get("role_id"), f"policy-obligation-role:{obligation_id}")
            if role_id not in roles:
                raise ContextError(f"unknown-policy-obligation-role:{obligation_id}")
            rule_id = _require_text(item.get("required_when_rule_id"), f"policy-obligation-rule:{obligation_id}")
            if rule_id not in rules:
                raise ContextError(f"unknown-policy-obligation-rule:{obligation_id}")
            playbook_ref = _require_mapping(item.get("playbook_ref"), f"policy-obligation-playbook:{obligation_id}")
            module_id = _require_text(playbook_ref.get("module_id"), f"policy-obligation-module:{obligation_id}")
            if module_id not in method_modules:
                raise ContextError(f"obligation-module-not-in-phase:{obligation_id}")
    return rules, modules, roles, phases, activation, closure


def _field_value(context: Mapping[str, object], field_name: str) -> tuple[bool, object | None]:
    if not isinstance(field_name, str) or not field_name or field_name.startswith(".") or field_name.endswith("."):
        raise ContextError("invalid-selector-field")
    current: object = context
    for part in field_name.split("."):
        if not part:
            raise ContextError("invalid-selector-field")
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _selector_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ContextError("invalid-selector-scalar")


def _merge_unknown(results: Sequence[SelectorResult], state: str) -> SelectorResult:
    fields = tuple(sorted({field for result in results for field in result.unknown_fields}))
    return SelectorResult(state, fields if state == "unknown" else ())


def _all_results(results: Sequence[SelectorResult]) -> SelectorResult:
    if not results:
        return SelectorResult("true")
    if any(result.state == "false" for result in results):
        return SelectorResult("false")
    if any(result.state == "unknown" for result in results):
        return _merge_unknown(results, "unknown")
    return SelectorResult("true")


def _evaluate_selector(
    selector: object,
    context: Mapping[str, object],
    *,
    validate_only: bool = False,
    depth: int = 0,
) -> SelectorResult:
    if depth > 32:
        raise ContextError("selector-nesting-too-deep")
    value = _require_mapping(selector, "selector")
    operation = value.get("op")
    if operation == "always":
        if set(value) != {"op"}:
            raise ContextError("invalid-selector-always")
        return SelectorResult("true")
    if operation == "eq":
        if set(value) != {"op", "field", "value"}:
            raise ContextError("invalid-selector-eq")
        field_name = _require_text(value["field"], "selector-field")
        expected = _selector_scalar(value["value"])
        if validate_only:
            return SelectorResult("true")
        found, actual = _field_value(context, field_name)
        return SelectorResult("true" if found and actual == expected else "false") if found else SelectorResult("unknown", (field_name,))
    if operation == "in":
        if set(value) != {"op", "field", "values"}:
            raise ContextError("invalid-selector-in")
        field_name = _require_text(value["field"], "selector-field")
        values = value["values"]
        if not isinstance(values, list) or not values:
            raise ContextError("invalid-selector-in-values")
        expected = [_selector_scalar(item) for item in values]
        if validate_only:
            return SelectorResult("true")
        found, actual = _field_value(context, field_name)
        return SelectorResult("true" if found and actual in expected else "false") if found else SelectorResult("unknown", (field_name,))
    if operation == "present":
        if set(value) != {"op", "field"}:
            raise ContextError("invalid-selector-present")
        field_name = _require_text(value["field"], "selector-field")
        if validate_only:
            return SelectorResult("true")
        found, _ = _field_value(context, field_name)
        return SelectorResult("true" if found else "false")
    if operation in {"all", "any"}:
        if set(value) != {"op", "terms"}:
            raise ContextError(f"invalid-selector-{operation}")
        terms = value["terms"]
        if not isinstance(terms, list) or not terms:
            raise ContextError(f"invalid-selector-{operation}-terms")
        results = [_evaluate_selector(term, context, validate_only=validate_only, depth=depth + 1) for term in terms]
        if operation == "all":
            return _all_results(results)
        if any(result.state == "true" for result in results):
            return SelectorResult("true")
        if any(result.state == "unknown" for result in results):
            return _merge_unknown(results, "unknown")
        return SelectorResult("false")
    if operation == "not":
        if set(value) != {"op", "term"}:
            raise ContextError("invalid-selector-not")
        result = _evaluate_selector(value["term"], context, validate_only=validate_only, depth=depth + 1)
        if result.state == "unknown":
            return result
        return SelectorResult("false" if result.state == "true" else "true")
    raise ContextError("unsupported-selector-operation")


def _is_secret_path(relative_path: str) -> bool:
    pure_path = PurePosixPath(relative_path)
    for part in pure_path.parts:
        lowered = part.lower()
        if lowered in _SECRET_PATH_PARTS or lowered.startswith(".env"):
            return True
    return pure_path.suffix.lower() in _SECRET_SUFFIXES


def _preflight_modules(
    selected_reasons: Mapping[str, ModuleReason],
    modules: Mapping[str, Mapping[str, object]],
    closure: Mapping[str, Mapping[str, object]],
    skill_root: Path,
    byte_budget: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    module_files: dict[str, FilePreflight] = {}
    files_by_path: dict[str, FilePreflight] = {}
    for module_id in sorted(selected_reasons):
        module = modules[module_id]
        playbook = _require_mapping(module.get("playbook"), f"policy-module-playbook:{module_id}")
        relative_path = _require_text(playbook.get("path"), f"policy-module-path:{module_id}")
        if _is_secret_path(relative_path):
            raise ContextError(f"secret-module-path:{relative_path}")
        expected_hash = _require_sha256(playbook.get("sha256"), f"policy-module-sha256:{module_id}")
        max_bytes = _require_positive_int(module.get("max_bytes"), f"policy-module-max-bytes:{module_id}")
        closure_item = closure.get(relative_path)
        if closure_item is None:
            raise ContextError(f"module-missing-policy-closure:{module_id}")
        if closure_item.get("sha256") != expected_hash:
            raise ContextError(f"module-policy-closure-hash-mismatch:{module_id}")
        resolved = safe_module_path(skill_root, relative_path)
        try:
            utf8_bytes = resolved.stat().st_size
        except OSError as exc:
            raise ContextError(f"module-stat-failed:{relative_path}") from exc
        if utf8_bytes > max_bytes:
            raise ContextError(f"module-byte-budget-exceeded:{module_id}")
        if closure_item.get("utf8_bytes") != utf8_bytes:
            raise ContextError(f"module-policy-closure-bytes-mismatch:{module_id}")
        prior = files_by_path.get(relative_path)
        if prior is None:
            prior = FilePreflight(relative_path, resolved, expected_hash, utf8_bytes)
            files_by_path[relative_path] = prior
        elif (prior.sha256, prior.utf8_bytes, prior.resolved_path) != (expected_hash, utf8_bytes, resolved):
            raise ContextError(f"conflicting-module-file:{relative_path}")
        prior.required_by.add(module_id)
        module_files[module_id] = prior
    total_bytes = sum(item.utf8_bytes for item in files_by_path.values())
    if total_bytes > byte_budget:
        largest = max(files_by_path.values(), key=lambda item: (item.utf8_bytes, item.relative_path))
        raise ContextError(
            f"context-byte-budget-exceeded:{largest.relative_path}:{total_bytes}:{byte_budget}")

    # Every path, budget and declared hash is checked above before any body is read.
    for descriptor in sorted(files_by_path.values(), key=lambda item: item.relative_path):
        try:
            body = descriptor.resolved_path.read_bytes()
            body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContextError(f"module-not-utf8:{descriptor.relative_path}") from exc
        except OSError as exc:
            raise ContextError(f"module-read-failed:{descriptor.relative_path}") from exc
        if len(body) != descriptor.utf8_bytes:
            raise ContextError(f"module-size-changed:{descriptor.relative_path}")
        if sha256_bytes(body) != descriptor.sha256:
            module_ids = ",".join(sorted(descriptor.required_by))
            raise ContextError(f"module-hash-mismatch:{module_ids}")

    selected_modules: list[dict[str, object]] = []
    for module_id in sorted(selected_reasons):
        descriptor = module_files[module_id]
        reason = selected_reasons[module_id]
        selected_modules.append({
            "id": module_id,
            "path": descriptor.relative_path,
            "sha256": descriptor.sha256,
            "bytes": descriptor.utf8_bytes,
            "reason": {
                "dependency_of": sorted(reason.dependency_of),
                "matched_rule_ids": sorted(reason.matched_rule_ids),
                "required_by_obligation_ids": sorted(reason.required_by_obligation_ids),
                "unknown_rule_ids": sorted(reason.unknown_rule_ids),
            },
        })
    dependency_closure = [
        {
            "path": descriptor.relative_path,
            "sha256": descriptor.sha256,
            "bytes": descriptor.utf8_bytes,
            "required_by": sorted(descriptor.required_by),
        }
        for descriptor in sorted(files_by_path.values(), key=lambda item: item.relative_path)
    ]
    return selected_modules, dependency_closure, total_bytes


def resolve_context(
    request: Mapping[str, object],
    policy_manifest: Mapping[str, object],
    repo_root: str | os.PathLike[str],
    skill_root: str | os.PathLike[str],
) -> dict[str, object]:
    """Return an immutable, read-only Phase 1 ContextManifest.

    The caller must select a phase explicitly.  The resolver only evaluates
    PolicyManifest selectors against explicit request fields; it never derives
    product or engineering semantics from repository paths.
    """
    normalized_request = _normalize_request(request)
    try:
        resolved_repo_root = Path(repo_root).resolve(strict=True)
        resolved_skill_root = Path(skill_root).resolve(strict=True)
    except OSError as exc:
        raise ContextError("context-root-does-not-exist") from exc
    if not resolved_repo_root.is_dir() or not resolved_skill_root.is_dir():
        raise ContextError("context-root-is-not-directory")

    rules, modules, roles, phases, activation, closure = _validate_preview_policy(policy_manifest, normalized_request)
    phase_id = str(normalized_request["phase_id"])
    phase = phases.get(phase_id)
    if phase is None:
        raise ContextError(f"unknown-policy-phase:{phase_id}")
    if phase.get("lifecycle") != normalized_request["lifecycle"]:
        raise ContextError(f"phase-lifecycle-mismatch:{phase_id}")
    if phase.get("stage") != normalized_request["operation"]:
        raise ContextError(f"phase-operation-mismatch:{phase_id}")
    phase_contract_ref = _require_text(phase.get("phase_contract_ref"), f"phase-contract-ref:{phase_id}")

    selector_context: dict[str, object] = {
        key: normalized_request[key]
        for key in (
            "command",
            "lifecycle_run_id",
            "phase_id",
            "lifecycle",
            "operation",
            "work_type",
            "authority_mode",
            "identity",
            "contracts",
            "profile",
            "diff",
            "intent_flags",
            "runtime_event",
            "modes",
        )
    }
    # Policy selectors may address an explicit intent flag directly (for example
    # `domain_model_needed`) or through `intent_flags.domain_model_needed`.
    # Neither form is inferred from repository paths.  Reserved request fields
    # cannot be overridden by a caller-provided flag.
    intent_flags = normalized_request["intent_flags"]
    assert isinstance(intent_flags, Mapping)
    for flag_name, flag_value in intent_flags.items():
        if flag_name in selector_context:
            raise ContextError(f"intent-flag-reserved-name:{flag_name}")
        selector_context[flag_name] = flag_value
    rule_cache: dict[str, SelectorResult] = {}

    def evaluate_rule(rule_id: str) -> SelectorResult:
        cached = rule_cache.get(rule_id)
        if cached is not None:
            return cached
        rule = rules.get(rule_id)
        if rule is None:
            raise ContextError(f"unknown-policy-rule:{rule_id}")
        result = _evaluate_selector(rule.get("when"), selector_context)
        rule_cache[rule_id] = result
        return result

    classification: dict[tuple[str, str, str], dict[str, object]] = {}
    matched_rule_ids: set[str] = set()

    def observe_rule(target_kind: str, target_id: str, rule_id: str) -> SelectorResult:
        result = evaluate_rule(rule_id)
        if result.state == "true":
            matched_rule_ids.add(rule_id)
        elif result.state == "unknown":
            rule = rules[rule_id]
            classification[(target_kind, target_id, rule_id)] = {
                "target_kind": target_kind,
                "target_id": target_id,
                "rule_id": rule_id,
                "selector": _normalize_json(rule["when"], "selector"),
                "unknown_fields": list(result.unknown_fields),
            }
        return result

    phase_entry_rule_ids = _rule_ids(phase.get("entry_predicate_rule_ids"), f"policy-phase-entry-rules:{phase_id}")
    phase_entry_results = [observe_rule("phase", phase_id, rule_id) for rule_id in phase_entry_rule_ids]
    phase_entry = _all_results(phase_entry_results)
    if phase_entry.state == "false":
        raise ContextError(f"phase-entry-predicate-false:{phase_id}")

    module_results: dict[str, tuple[SelectorResult, list[tuple[str, SelectorResult]]]] = {}

    def evaluate_module(module_id: str) -> tuple[SelectorResult, list[tuple[str, SelectorResult]]]:
        cached = module_results.get(module_id)
        if cached is not None:
            return cached
        module = modules[module_id]
        rule_ids = _rule_ids(module.get("selector_rule_ids"), f"policy-module-rules:{module_id}")
        results = [(rule_id, evaluate_rule(rule_id)) for rule_id in rule_ids]
        cached = (_all_results([result for _, result in results]), results)
        module_results[module_id] = cached
        return cached

    selected_reasons: dict[str, ModuleReason] = {}

    def select_module(module_id: str, *, dependency_of: str | None = None, obligation_id: str | None = None,
                      include_selector_result: bool = True) -> None:
        if module_id not in modules:
            raise ContextError(f"unknown-policy-module:{module_id}")
        module = modules[module_id]
        lifecycle_values = _normalize_string_list(module.get("lifecycles"), f"policy-module-lifecycles:{module_id}")
        if normalized_request["lifecycle"] not in lifecycle_values:
            raise ContextError(f"module-lifecycle-mismatch:{module_id}")
        reason = selected_reasons.setdefault(module_id, ModuleReason())
        if dependency_of is not None:
            reason.dependency_of.add(dependency_of)
        if obligation_id is not None:
            reason.required_by_obligation_ids.add(obligation_id)
        if include_selector_result:
            status, individual_results = evaluate_module(module_id)
            if status.state == "unknown":
                for rule_id, result in individual_results:
                    if result.state == "unknown":
                        reason.unknown_rule_ids.add(rule_id)
                        observe_rule("module", module_id, rule_id)
            for rule_id, result in individual_results:
                if result.state == "true":
                    reason.matched_rule_ids.add(rule_id)
                    matched_rule_ids.add(rule_id)

    method_module_ids = _rule_ids(phase.get("method_module_ids"), f"policy-phase-modules:{phase_id}")
    for module_id in method_module_ids:
        status, _ = evaluate_module(module_id)
        if status.state != "false":
            select_module(module_id)

    selected_obligation_ids: list[str] = []
    skipped_obligations: list[dict[str, object]] = []
    selected_obligations: list[Mapping[str, object]] = []
    obligations = phase.get("obligations")
    assert isinstance(obligations, list)
    normalized_obligations = sorted((_require_mapping(item, f"policy-obligation:{phase_id}") for item in obligations),
                                    key=lambda item: _require_text(item.get("id"), "policy-obligation-id"))
    for obligation in normalized_obligations:
        obligation_id = _require_text(obligation.get("id"), "policy-obligation-id")
        rule_id = _require_text(obligation.get("required_when_rule_id"), f"policy-obligation-rule:{obligation_id}")
        participation = _require_text(obligation.get("participation"), f"policy-obligation-participation:{obligation_id}")
        if participation not in {"required", "conditional"}:
            raise ContextError(f"invalid-policy-obligation-participation:{obligation_id}")
        result = observe_rule("obligation", obligation_id, rule_id)
        if result.state == "false":
            if participation == "required":
                raise ContextError(f"required-obligation-selector-false:{obligation_id}")
            skipped_obligations.append({
                "id": obligation_id,
                "selector_proof": {"rule_id": rule_id, "result": "false"},
            })
            continue
        playbook_ref = _require_mapping(obligation.get("playbook_ref"), f"policy-obligation-playbook:{obligation_id}")
        module_id = _require_text(playbook_ref.get("module_id"), f"policy-obligation-module:{obligation_id}")
        select_module(module_id, obligation_id=obligation_id)
        selected_obligation_ids.append(obligation_id)
        selected_obligations.append(obligation)

    dependency_active: list[str] = []

    def add_dependencies(module_id: str) -> None:
        if module_id in dependency_active:
            cycle = "->".join(dependency_active + [module_id])
            raise ContextError(f"module-dependency-cycle:{cycle}")
        dependency_active.append(module_id)
        module = modules[module_id]
        for dependency_id in _rule_ids(module.get("depends_on"), f"policy-module-dependencies:{module_id}", allow_empty=True):
            select_module(dependency_id, dependency_of=module_id)
            add_dependencies(dependency_id)
        dependency_active.pop()

    for module_id in sorted(tuple(selected_reasons)):
        add_dependencies(module_id)

    role_details: dict[str, dict[str, object]] = {}
    warnings: set[str] = set()
    for obligation in selected_obligations:
        obligation_id = _require_text(obligation.get("id"), "policy-obligation-id")
        role_id = _require_text(obligation.get("role_id"), f"policy-obligation-role:{obligation_id}")
        role = roles[role_id]
        eligibility_ids = _rule_ids(role.get("eligibility_rule_ids"), f"policy-role-rules:{role_id}", allow_empty=True)
        eligibility_results = [observe_rule("role", role_id, rule_id) for rule_id in eligibility_ids]
        eligibility = _all_results(eligibility_results)
        detail = role_details.setdefault(role_id, {
            "id": role_id,
            "obligation_ids": [],
            "eligibility_rule_ids": eligibility_ids,
            "eligibility": eligibility.state,
        })
        obligation_ids = detail["obligation_ids"]
        assert isinstance(obligation_ids, list)
        obligation_ids.append(obligation_id)
        if eligibility.state == "false":
            warnings.add(f"role-ineligible:{role_id}")

    selected_modules, dependency_closure, total_bytes = _preflight_modules(
        selected_reasons, modules, closure, resolved_skill_root, int(normalized_request["byte_budget"]))

    classification_requests = [
        classification[key]
        for key in sorted(classification, key=lambda item: (item[0], item[1], item[2]))
    ]
    needs_classification = bool(classification_requests)
    if needs_classification:
        warnings.add("needs_classification")
    role_selection = []
    for role_id in sorted(role_details):
        detail = role_details[role_id]
        role_selection.append({
            "id": role_id,
            "obligation_ids": sorted(detail["obligation_ids"]),
            "eligibility_rule_ids": detail["eligibility_rule_ids"],
            "eligibility": detail["eligibility"],
        })

    context_input = {
        "policy_manifest_id": policy_manifest["policy_manifest_id"],
        "phase_contract_ref": phase_contract_ref,
        "request": normalized_request,
    }
    manifest: dict[str, object] = {
        "schema_version": CONTEXT_SCHEMA,
        "scope": "preview",
        "activation": dict(activation),
        "policy_manifest_id": policy_manifest["policy_manifest_id"],
        "phase_contract_ref": phase_contract_ref,
        "lifecycle_run_id": normalized_request["lifecycle_run_id"],
        "context_input_sha256": sha256_bytes(canonical_bytes(context_input)),
        "command": normalized_request["command"],
        "lifecycle": normalized_request["lifecycle"],
        "operation": normalized_request["operation"],
        "work_type": normalized_request["work_type"],
        "identity": normalized_request["identity"],
        "authority_mode": normalized_request["authority_mode"],
        "contracts": normalized_request["contracts"],
        "profile": normalized_request["profile"],
        "diff": normalized_request["diff"],
        "intent_flags": normalized_request["intent_flags"],
        "runtime_event": normalized_request["runtime_event"],
        "engine_version": normalized_request["engine_version"],
        "selector_attestation_refs": normalized_request["selector_attestation_refs"],
        "phase_entry_state": phase_entry.state,
        "matched_rule_ids": sorted(matched_rule_ids),
        "selected_modules": selected_modules,
        "dependency_closure": dependency_closure,
        "roles": sorted(role_details),
        "role_selection": role_selection,
        "modes": normalized_request["modes"],
        "selected_obligation_ids": sorted(selected_obligation_ids),
        "skipped_obligations": skipped_obligations,
        "classification_requests": classification_requests,
        "needs_classification": needs_classification,
        "total_bytes": total_bytes,
        "byte_budget": normalized_request["byte_budget"],
        "warnings": sorted(warnings),
    }
    manifest["context_manifest_id"] = sha256_bytes(canonical_bytes(manifest))
    return manifest
