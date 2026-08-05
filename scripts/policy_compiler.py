#!/usr/bin/env python3
"""Compile strict SDLC Policy source JSON into an immutable PolicyManifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import Any, Mapping, Sequence


POLICY_FORMAT = "sdlc-policy-v1"
MODULES_SCHEMA = "sdlc-policy-modules-v1"
PHASES_SCHEMA = "sdlc-policy-phases-v1"
ROLES_SCHEMA = "sdlc-policy-roles-v1"
MANIFEST_SCHEMA = "sdlc-policy-manifest-v1"
COMPILER_ID = "sdlc-policy-compiler"
COMPILER_VERSION = "1.0.0"
SUPPORTED_MIGRATION_VERSIONS = frozenset({"phase1-preview-v1"})

_ID_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_LIFECYCLES = frozenset({"product-design", "software-delivery", "compatibility"})
_TARGET_KINDS = frozenset({"module", "role", "phase", "obligation"})
_RESPONSIBILITIES = frozenset({"accountable", "responsible", "consulted", "reviewer", "approver"})
_INDEPENDENCE_MODES = frozenset({"distinct_actor", "fresh_context"})
_ASSERTION_KINDS = frozenset({"mechanical", "semantic"})
_ASSERTION_SOURCES = frozenset({"runner_evidence", "canonical_state", "typed_attestation"})
_TRANSITION_KINDS = frozenset({"advance", "complete", "cancel"})

_MODULES_DOCUMENT_KEYS = frozenset({"schema_version", "policy", "rules", "modules"})
_POLICY_KEYS = frozenset({"policy_format", "engine_api", "migration_version", "activation"})
_ENGINE_API_KEYS = frozenset({"min_inclusive", "max_exclusive"})
_ACTIVATION_KEYS = frozenset({
    "scope", "explicit_invocation_only", "control_mutations", "output_scope", "unknown_selector",
    "legacy_projection", "legacy_bridge",
})
_RULE_KEYS = frozenset({"id", "kind", "target", "resolution_group", "priority", "when"})
_RULE_TARGET_KEYS = frozenset({"kind", "id"})
_MODULE_KEYS = frozenset({
    "id", "lifecycles", "operations", "selector_rule_ids", "depends_on", "playbook", "max_bytes", "fallback",
})
_PLAYBOOK_KEYS = frozenset({"path", "anchor", "sha256"})
_FALLBACK_KEYS = frozenset({"kind"})
_PHASES_DOCUMENT_KEYS = frozenset({"schema_version", "phases"})
_PHASE_KEYS = frozenset({
    "id", "lifecycle", "stage", "entry_predicate_rule_ids", "input_contracts", "method_module_ids",
    "output_contracts", "completion_assertions", "semantic_attestation_types", "obligations",
    "transition_intent", "rollback_intent", "compatibility_adapter",
})
_INPUT_CONTRACT_KEYS = frozenset({"id", "kind", "state"})
_OUTPUT_CONTRACT_KEYS = frozenset({"id", "kind", "scope"})
_ASSERTION_KEYS = frozenset({"id", "kind", "source", "evidence_type"})
_OBLIGATION_KEYS = frozenset({
    "id", "role_id", "responsibility", "participation", "required_when_rule_id", "min_actors", "max_actors",
    "independence_constraint_ids", "playbook_ref", "completion_assertion_ids", "skip_policy",
})
_PLAYBOOK_REF_KEYS = frozenset({"module_id", "anchor"})
_SKIP_POLICY_KEYS = frozenset({"mode", "allowed_when_rule_id", "override_policy"})
_TRANSITION_KEYS = frozenset({"kind", "target_phase_id", "scope"})
_ROLES_DOCUMENT_KEYS = frozenset({"schema_version", "roles"})
_ROLE_KEYS = frozenset({"id", "responsibility_types", "eligibility_rule_ids", "independence_constraints"})
_INDEPENDENCE_KEYS = frozenset({"id", "mode", "against_role_ids"})


class PolicyError(RuntimeError):
    """Policy source cannot be compiled as an executable deterministic contract."""


def canonical_bytes(value: object) -> bytes:
    """Return the sole JSON encoding used for identities and emitted manifests."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_exact_keys(value: object, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PolicyError(f"invalid-{label}-keys")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PolicyError(f"invalid-{label}")
    return value


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise PolicyError(f"invalid-{label}")
    return value


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyError(f"invalid-{label}")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PolicyError(f"invalid-{label}")
    return value


def _normalize_id_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise PolicyError(f"invalid-{label}")
    normalized = [_require_id(item, f"{label}-item") for item in value]
    if len(set(normalized)) != len(normalized):
        raise PolicyError(f"duplicate-{label}")
    return sorted(normalized)


def _normalize_text_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise PolicyError(f"invalid-{label}")
    normalized = [_require_text(item, f"{label}-item") for item in value]
    if len(set(normalized)) != len(normalized):
        raise PolicyError(f"duplicate-{label}")
    return sorted(normalized)


def _semver(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _SEMVER_RE.fullmatch(value):
        raise PolicyError(f"invalid-{label}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite-json-constant:{value}")


def _duplicate_key_rejecting_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _load_json(path: Path, keys: frozenset[str], label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_key_rejecting_object,
            parse_constant=_reject_json_constant,
        )
    except PolicyError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise PolicyError(f"invalid-json-{label}:{path}") from exc
    return _require_exact_keys(value, keys, label)


def _json_scalar(value: object, label: str) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise PolicyError(f"invalid-{label}-scalar")


def _canonical_sort_key(value: object) -> bytes:
    return canonical_bytes(value)


def _normalize_selector(value: object, *, depth: int = 0) -> dict[str, object]:
    if depth > 32:
        raise PolicyError("selector-nesting-too-deep")
    if not isinstance(value, dict):
        raise PolicyError("invalid-selector")
    operation = value.get("op")
    if operation == "always":
        _require_exact_keys(value, frozenset({"op"}), "selector-always")
        return {"op": "always"}
    if operation == "eq":
        selector = _require_exact_keys(value, frozenset({"op", "field", "value"}), "selector-eq")
        return {
            "op": "eq",
            "field": _require_text(selector["field"], "selector-field"),
            "value": _json_scalar(selector["value"], "selector-eq"),
        }
    if operation == "in":
        selector = _require_exact_keys(value, frozenset({"op", "field", "values"}), "selector-in")
        raw_values = selector["values"]
        if not isinstance(raw_values, list) or not raw_values:
            raise PolicyError("invalid-selector-in-values")
        values = [_json_scalar(item, "selector-in") for item in raw_values]
        values = sorted(values, key=_canonical_sort_key)
        if len({_canonical_sort_key(item) for item in values}) != len(values):
            raise PolicyError("duplicate-selector-in-value")
        return {"op": "in", "field": _require_text(selector["field"], "selector-field"), "values": values}
    if operation == "present":
        selector = _require_exact_keys(value, frozenset({"op", "field"}), "selector-present")
        return {"op": "present", "field": _require_text(selector["field"], "selector-field")}
    if operation in {"all", "any"}:
        selector = _require_exact_keys(value, frozenset({"op", "terms"}), f"selector-{operation}")
        raw_terms = selector["terms"]
        if not isinstance(raw_terms, list) or not raw_terms:
            raise PolicyError(f"invalid-selector-{operation}-terms")
        terms = [_normalize_selector(term, depth=depth + 1) for term in raw_terms]
        terms = sorted(terms, key=_canonical_sort_key)
        if len({_canonical_sort_key(term) for term in terms}) != len(terms):
            raise PolicyError(f"duplicate-selector-{operation}-term")
        return {"op": operation, "terms": terms}
    if operation == "not":
        selector = _require_exact_keys(value, frozenset({"op", "term"}), "selector-not")
        return {"op": "not", "term": _normalize_selector(selector["term"], depth=depth + 1)}
    raise PolicyError("unsupported-selector-operation")


def _safe_playbook(skill_root: Path, path_value: object) -> tuple[str, Path]:
    path = _require_text(path_value, "playbook-path")
    pure_path = PurePosixPath(path)
    if (
        path != pure_path.as_posix()
        or pure_path.is_absolute()
        or not pure_path.parts
        or any(part in {"", ".", ".."} for part in pure_path.parts)
        or "\\" in path
    ):
        raise PolicyError(f"unsafe-playbook-path:{path}")
    try:
        root = skill_root.resolve(strict=True)
        resolved = root.joinpath(*pure_path.parts).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise PolicyError(f"playbook-path-escapes-skill-root:{path}") from exc
    if not resolved.is_file():
        raise PolicyError(f"playbook-is-not-a-file:{path}")
    return pure_path.as_posix(), resolved


def _normalize_activation(value: object, migration_version: str) -> dict[str, object]:
    activation = _require_exact_keys(value, _ACTIVATION_KEYS, "activation")
    if migration_version not in SUPPORTED_MIGRATION_VERSIONS:
        raise PolicyError("unsupported-migration-version")
    normalized = {
        "scope": _require_text(activation["scope"], "activation-scope"),
        "explicit_invocation_only": _require_bool(activation["explicit_invocation_only"], "activation-explicit"),
        "control_mutations": _require_bool(activation["control_mutations"], "activation-control-mutations"),
        "output_scope": _require_text(activation["output_scope"], "activation-output-scope"),
        "unknown_selector": _require_text(activation["unknown_selector"], "activation-unknown-selector"),
        "legacy_projection": _require_text(activation["legacy_projection"], "activation-legacy-projection"),
        "legacy_bridge": _require_text(activation["legacy_bridge"], "activation-legacy-bridge"),
    }
    if migration_version == "phase1-preview-v1" and normalized != {
        "scope": "preview",
        "explicit_invocation_only": True,
        "control_mutations": False,
        "output_scope": "preview",
        "unknown_selector": "needs_classification",
        "legacy_projection": "legacy-route-projection-v1",
        "legacy_bridge": "legacy-composite-v1",
    }:
        raise PolicyError("invalid-phase1-preview-activation")
    return normalized


def _normalize_rule(value: object) -> dict[str, object]:
    rule = _require_exact_keys(value, _RULE_KEYS, "rule")
    target = _require_exact_keys(rule["target"], _RULE_TARGET_KEYS, "rule-target")
    target_kind = _require_text(target["kind"], "rule-target-kind")
    if target_kind not in _TARGET_KINDS:
        raise PolicyError("invalid-rule-target-kind")
    priority = rule["priority"]
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise PolicyError("invalid-rule-priority")
    if rule["kind"] != "selector":
        raise PolicyError("invalid-rule-kind")
    return {
        "id": _require_id(rule["id"], "rule-id"),
        "kind": "selector",
        "target": {"kind": target_kind, "id": _require_id(target["id"], "rule-target-id")},
        "resolution_group": _require_id(rule["resolution_group"], "rule-resolution-group"),
        "priority": priority,
        "when": _normalize_selector(rule["when"]),
    }


def _normalize_module(value: object, skill_root: Path) -> tuple[dict[str, object], dict[str, object], bytes]:
    module = _require_exact_keys(value, _MODULE_KEYS, "module")
    module_id = _require_id(module["id"], "module-id")
    lifecycles = _normalize_id_list(module["lifecycles"], f"module-lifecycles:{module_id}")
    if any(lifecycle not in _LIFECYCLES for lifecycle in lifecycles):
        raise PolicyError(f"invalid-module-lifecycle:{module_id}")
    playbook = _require_exact_keys(module["playbook"], _PLAYBOOK_KEYS, "playbook")
    playbook_path, resolved_playbook = _safe_playbook(skill_root, playbook["path"])
    try:
        body = resolved_playbook.read_bytes()
        body.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PolicyError(f"invalid-playbook-utf8:{module_id}") from exc
    declared_hash = playbook["sha256"]
    if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
        raise PolicyError(f"invalid-playbook-sha256:{module_id}")
    actual_hash = _sha256(body)
    if declared_hash != actual_hash:
        raise PolicyError(f"playbook-hash-mismatch:{module_id}")
    max_bytes = _require_positive_int(module["max_bytes"], f"module-max-bytes:{module_id}")
    if len(body) > max_bytes:
        raise PolicyError(f"playbook-byte-budget-exceeded:{module_id}")
    anchor = _require_text(playbook["anchor"], f"playbook-anchor:{module_id}")
    if anchor.encode("utf-8") not in body:
        raise PolicyError(f"missing-module-playbook-anchor:{module_id}")
    fallback = _require_exact_keys(module["fallback"], _FALLBACK_KEYS, "module-fallback")
    fallback_kind = _require_text(fallback["kind"], f"module-fallback-kind:{module_id}")
    if fallback_kind not in {"error", "needs_classification"}:
        raise PolicyError(f"invalid-module-fallback:{module_id}")
    normalized = {
        "id": module_id,
        "lifecycles": lifecycles,
        "operations": _normalize_id_list(module["operations"], f"module-operations:{module_id}"),
        "selector_rule_ids": _normalize_id_list(module["selector_rule_ids"], f"module-rules:{module_id}"),
        "depends_on": _normalize_id_list(module["depends_on"], f"module-dependencies:{module_id}", allow_empty=True),
        "playbook": {"path": playbook_path, "anchor": anchor, "sha256": actual_hash},
        "max_bytes": max_bytes,
        "fallback": {"kind": fallback_kind},
    }
    closure = {"path": playbook_path, "sha256": actual_hash, "utf8_bytes": len(body)}
    return normalized, closure, body


def _assert_module_dag(modules: Mapping[str, Mapping[str, object]]) -> None:
    completed: set[str] = set()
    active: list[str] = []

    def visit(module_id: str) -> None:
        if module_id in active:
            start = active.index(module_id)
            raise PolicyError("module-dependency-cycle:" + "->".join(active[start:] + [module_id]))
        if module_id in completed:
            return
        active.append(module_id)
        dependencies = modules[module_id]["depends_on"]
        assert isinstance(dependencies, list)
        for dependency in dependencies:
            if dependency not in modules:
                raise PolicyError(f"unknown-module-dependency:{module_id}:{dependency}")
            visit(dependency)
        active.pop()
        completed.add(module_id)

    for module_id in sorted(modules):
        visit(module_id)


def _normalize_role(value: object, rules: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    role = _require_exact_keys(value, _ROLE_KEYS, "role")
    role_id = _require_id(role["id"], "role-id")
    responsibility_types = _normalize_id_list(role["responsibility_types"], f"role-responsibilities:{role_id}")
    if any(responsibility not in _RESPONSIBILITIES for responsibility in responsibility_types):
        raise PolicyError(f"invalid-role-responsibility:{role_id}")
    eligibility_rule_ids = _normalize_id_list(role["eligibility_rule_ids"], f"role-eligibility-rules:{role_id}")
    for rule_id in eligibility_rule_ids:
        if rule_id not in rules:
            raise PolicyError(f"unknown-role-eligibility-rule:{role_id}:{rule_id}")
    raw_constraints = role["independence_constraints"]
    if not isinstance(raw_constraints, list):
        raise PolicyError(f"invalid-role-independence-constraints:{role_id}")
    constraints: list[dict[str, object]] = []
    for raw_constraint in raw_constraints:
        constraint = _require_exact_keys(raw_constraint, _INDEPENDENCE_KEYS, "independence-constraint")
        mode = _require_text(constraint["mode"], "independence-constraint-mode")
        if mode not in _INDEPENDENCE_MODES:
            raise PolicyError(f"invalid-independence-constraint-mode:{role_id}")
        constraints.append({
            "id": _require_id(constraint["id"], "independence-constraint-id"),
            "mode": mode,
            "against_role_ids": _normalize_id_list(
                constraint["against_role_ids"], f"independence-constraint-against:{role_id}"),
        })
    if len({constraint["id"] for constraint in constraints}) != len(constraints):
        raise PolicyError(f"duplicate-independence-constraint:{role_id}")
    return {
        "id": role_id,
        "responsibility_types": responsibility_types,
        "eligibility_rule_ids": eligibility_rule_ids,
        "independence_constraints": sorted(constraints, key=lambda item: str(item["id"])),
    }


def _normalize_contracts(value: object, label: str, *, output: bool) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise PolicyError(f"invalid-{label}")
    expected_keys = _OUTPUT_CONTRACT_KEYS if output else _INPUT_CONTRACT_KEYS
    contracts: list[dict[str, object]] = []
    for raw_contract in value:
        contract = _require_exact_keys(raw_contract, expected_keys, label)
        normalized = {
            "id": _require_id(contract["id"], f"{label}-id"),
            "kind": _require_text(contract["kind"], f"{label}-kind"),
        }
        if output:
            scope = _require_text(contract["scope"], f"{label}-scope")
            if scope not in {"preview", "canonical"}:
                raise PolicyError(f"invalid-{label}-scope")
            normalized["scope"] = scope
        else:
            normalized["state"] = _require_text(contract["state"], f"{label}-state")
        contracts.append(normalized)
    if len({contract["id"] for contract in contracts}) != len(contracts):
        raise PolicyError(f"duplicate-{label}-id")
    return sorted(contracts, key=lambda item: str(item["id"]))


def _normalize_assertions(value: object, phase_id: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise PolicyError(f"invalid-phase-assertions:{phase_id}")
    assertions: list[dict[str, object]] = []
    for raw_assertion in value:
        assertion = _require_exact_keys(raw_assertion, _ASSERTION_KEYS, "completion-assertion")
        kind = _require_text(assertion["kind"], "completion-assertion-kind")
        source = _require_text(assertion["source"], "completion-assertion-source")
        if kind not in _ASSERTION_KINDS or source not in _ASSERTION_SOURCES:
            raise PolicyError(f"invalid-completion-assertion:{phase_id}")
        if kind == "semantic" and source != "typed_attestation":
            raise PolicyError(f"semantic-assertion-must-use-attestation:{phase_id}")
        if kind == "mechanical" and source == "typed_attestation":
            raise PolicyError(f"mechanical-assertion-cannot-use-attestation:{phase_id}")
        assertions.append({
            "id": _require_id(assertion["id"], "completion-assertion-id"),
            "kind": kind,
            "source": source,
            "evidence_type": _require_text(assertion["evidence_type"], "completion-assertion-evidence-type"),
        })
    if len({assertion["id"] for assertion in assertions}) != len(assertions):
        raise PolicyError(f"duplicate-phase-assertion:{phase_id}")
    return sorted(assertions, key=lambda item: str(item["id"]))


def _normalize_transition(value: object, label: str, required_scope: str, *, rollback: bool = False) -> dict[str, object]:
    transition = _require_exact_keys(value, _TRANSITION_KEYS, label)
    kind = _require_text(transition["kind"], f"{label}-kind")
    if not rollback and kind not in _TRANSITION_KINDS:
        raise PolicyError(f"invalid-{label}-kind")
    target = transition["target_phase_id"]
    if target is not None:
        target = _require_id(target, f"{label}-target")
    if not rollback:
        if kind == "advance" and target is None:
            raise PolicyError(f"advance-requires-{label}-target")
        if kind in {"complete", "cancel"} and target is not None:
            raise PolicyError(f"terminal-{label}-cannot-target-phase")
    scope = _require_text(transition["scope"], f"{label}-scope")
    if scope != required_scope:
        raise PolicyError(f"invalid-{label}-scope")
    return {"kind": kind, "target_phase_id": target, "scope": scope}


def _normalize_obligations(
    value: object,
    phase_id: str,
    lifecycle: str,
    module_ids: set[str],
    roles: Mapping[str, Mapping[str, object]],
    rules: Mapping[str, Mapping[str, object]],
    assertions: Mapping[str, Mapping[str, object]],
    module_bodies: Mapping[str, bytes],
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise PolicyError(f"invalid-phase-obligations:{phase_id}")
    obligations: list[dict[str, object]] = []
    for raw_obligation in value:
        obligation = _require_exact_keys(raw_obligation, _OBLIGATION_KEYS, "obligation")
        obligation_id = _require_id(obligation["id"], "obligation-id")
        role_id = _require_id(obligation["role_id"], f"obligation-role:{obligation_id}")
        role = roles.get(role_id)
        if role is None:
            raise PolicyError(f"unknown-obligation-role:{obligation_id}:{role_id}")
        responsibility = _require_text(obligation["responsibility"], f"obligation-responsibility:{obligation_id}")
        role_responsibilities = role["responsibility_types"]
        assert isinstance(role_responsibilities, list)
        if responsibility not in role_responsibilities:
            raise PolicyError(f"role-cannot-take-responsibility:{obligation_id}")
        participation = _require_text(obligation["participation"], f"obligation-participation:{obligation_id}")
        if participation not in {"required", "conditional"}:
            raise PolicyError(f"invalid-obligation-participation:{obligation_id}")
        required_when_rule_id = _require_id(obligation["required_when_rule_id"], f"obligation-rule:{obligation_id}")
        if required_when_rule_id not in rules:
            raise PolicyError(f"unknown-obligation-rule:{obligation_id}:{required_when_rule_id}")
        min_actors = _require_positive_int(obligation["min_actors"], f"obligation-min-actors:{obligation_id}")
        max_actors = _require_positive_int(obligation["max_actors"], f"obligation-max-actors:{obligation_id}")
        if min_actors > max_actors:
            raise PolicyError(f"invalid-obligation-actor-range:{obligation_id}")
        constraint_ids = _normalize_id_list(
            obligation["independence_constraint_ids"], f"obligation-independence:{obligation_id}", allow_empty=True)
        role_constraints = role["independence_constraints"]
        assert isinstance(role_constraints, list)
        known_constraints = {constraint["id"] for constraint in role_constraints}
        if any(constraint_id not in known_constraints for constraint_id in constraint_ids):
            raise PolicyError(f"unknown-obligation-independence:{obligation_id}")
        playbook_ref = _require_exact_keys(obligation["playbook_ref"], _PLAYBOOK_REF_KEYS, "obligation-playbook-ref")
        module_id = _require_id(playbook_ref["module_id"], f"obligation-module:{obligation_id}")
        if module_id not in module_ids:
            raise PolicyError(f"obligation-module-not-in-phase:{obligation_id}:{module_id}")
        anchor = _require_text(playbook_ref["anchor"], f"obligation-anchor:{obligation_id}")
        if anchor.encode("utf-8") not in module_bodies[module_id]:
            raise PolicyError(f"missing-obligation-playbook-anchor:{obligation_id}")
        assertion_ids = _normalize_id_list(
            obligation["completion_assertion_ids"], f"obligation-assertions:{obligation_id}")
        if any(assertion_id not in assertions for assertion_id in assertion_ids):
            raise PolicyError(f"unknown-obligation-assertion:{obligation_id}")
        skip_policy = _require_exact_keys(obligation["skip_policy"], _SKIP_POLICY_KEYS, "obligation-skip-policy")
        skip_mode = _require_text(skip_policy["mode"], f"obligation-skip-mode:{obligation_id}")
        allowed_when = skip_policy["allowed_when_rule_id"]
        override_policy = _require_text(skip_policy["override_policy"], f"obligation-override-policy:{obligation_id}")
        if participation == "required":
            if skip_mode != "forbidden" or allowed_when is not None or override_policy != "none":
                raise PolicyError(f"required-obligation-cannot-skip:{obligation_id}")
        else:
            if skip_mode != "selector_false_or_typed_override":
                raise PolicyError(f"invalid-conditional-skip-mode:{obligation_id}")
            allowed_when = _require_id(allowed_when, f"conditional-skip-rule:{obligation_id}")
            if allowed_when not in rules or override_policy != "typed-override-v1":
                raise PolicyError(f"invalid-conditional-skip-policy:{obligation_id}")
        obligations.append({
            "id": obligation_id,
            "role_id": role_id,
            "responsibility": responsibility,
            "participation": participation,
            "required_when_rule_id": required_when_rule_id,
            "min_actors": min_actors,
            "max_actors": max_actors,
            "independence_constraint_ids": constraint_ids,
            "playbook_ref": {"module_id": module_id, "anchor": anchor},
            "completion_assertion_ids": assertion_ids,
            "skip_policy": {
                "mode": skip_mode,
                "allowed_when_rule_id": allowed_when,
                "override_policy": override_policy,
            },
        })
    if len({obligation["id"] for obligation in obligations}) != len(obligations):
        raise PolicyError(f"duplicate-obligation-in-phase:{phase_id}")
    return sorted(obligations, key=lambda item: str(item["id"]))


def _normalize_phase(
    value: object,
    modules: Mapping[str, Mapping[str, object]],
    roles: Mapping[str, Mapping[str, object]],
    rules: Mapping[str, Mapping[str, object]],
    module_bodies: Mapping[str, bytes],
    activation: Mapping[str, object],
) -> dict[str, object]:
    phase = _require_exact_keys(value, _PHASE_KEYS, "phase")
    phase_id = _require_id(phase["id"], "phase-id")
    lifecycle = _require_text(phase["lifecycle"], f"phase-lifecycle:{phase_id}")
    if lifecycle not in _LIFECYCLES:
        raise PolicyError(f"invalid-phase-lifecycle:{phase_id}")
    module_ids = _normalize_id_list(phase["method_module_ids"], f"phase-modules:{phase_id}")
    for module_id in module_ids:
        module = modules.get(module_id)
        if module is None:
            raise PolicyError(f"unknown-phase-module:{phase_id}:{module_id}")
        module_lifecycles = module["lifecycles"]
        assert isinstance(module_lifecycles, list)
        if lifecycle not in module_lifecycles:
            raise PolicyError(f"cross-lifecycle-phase-module:{phase_id}:{module_id}")
    entry_rule_ids = _normalize_id_list(phase["entry_predicate_rule_ids"], f"phase-entry-rules:{phase_id}")
    if any(rule_id not in rules for rule_id in entry_rule_ids):
        raise PolicyError(f"unknown-phase-entry-rule:{phase_id}")
    assertions = _normalize_assertions(phase["completion_assertions"], phase_id)
    assertions_by_id = {assertion["id"]: assertion for assertion in assertions}
    attestation_types = _normalize_id_list(
        phase["semantic_attestation_types"], f"phase-attestation-types:{phase_id}", allow_empty=True)
    if any(assertion["kind"] == "semantic" for assertion in assertions) and not attestation_types:
        raise PolicyError(f"semantic-phase-needs-attestation-type:{phase_id}")
    output_contracts = _normalize_contracts(phase["output_contracts"], f"phase-outputs:{phase_id}", output=True)
    expected_output_scope = activation["output_scope"]
    assert isinstance(expected_output_scope, str)
    if any(contract["scope"] != expected_output_scope for contract in output_contracts):
        raise PolicyError(f"invalid-phase-output-scope:{phase_id}")
    transition = _normalize_transition(
        phase["transition_intent"], f"phase-transition:{phase_id}", expected_output_scope)
    raw_rollback = phase["rollback_intent"]
    rollback = None if raw_rollback is None else _normalize_transition(
        raw_rollback, f"phase-rollback:{phase_id}", expected_output_scope, rollback=True)
    adapter = phase["compatibility_adapter"]
    if adapter is not None:
        adapter = _require_text(adapter, f"phase-compatibility-adapter:{phase_id}")
    return {
        "id": phase_id,
        "lifecycle": lifecycle,
        "stage": _require_id(phase["stage"], f"phase-stage:{phase_id}"),
        "entry_predicate_rule_ids": entry_rule_ids,
        "input_contracts": _normalize_contracts(phase["input_contracts"], f"phase-inputs:{phase_id}", output=False),
        "method_module_ids": module_ids,
        "output_contracts": output_contracts,
        "completion_assertions": assertions,
        "semantic_attestation_types": attestation_types,
        "obligations": _normalize_obligations(
            phase["obligations"], phase_id, lifecycle, set(module_ids), roles, rules, assertions_by_id, module_bodies),
        "transition_intent": transition,
        "rollback_intent": rollback,
        "compatibility_adapter": adapter,
    }


def _validate_references(
    rules: Sequence[Mapping[str, object]],
    modules: Mapping[str, Mapping[str, object]],
    roles: Mapping[str, Mapping[str, object]],
    phases: Mapping[str, Mapping[str, object]],
) -> None:
    obligations = {
        obligation["id"]
        for phase in phases.values()
        for obligation in phase["obligations"]  # type: ignore[index]
    }
    entity_ids: Mapping[str, set[object]] = {
        "module": set(modules),
        "role": set(roles),
        "phase": set(phases),
        "obligation": obligations,
    }
    for rule in rules:
        target = rule["target"]
        assert isinstance(target, dict)
        if target["id"] not in entity_ids[str(target["kind"])]:
            raise PolicyError(f"unknown-rule-target:{rule['id']}")
    for role in roles.values():
        for constraint in role["independence_constraints"]:  # type: ignore[index]
            assert isinstance(constraint, dict)
            for against_role_id in constraint["against_role_ids"]:
                if against_role_id not in roles or against_role_id == role["id"]:
                    raise PolicyError(f"invalid-independence-against-role:{constraint['id']}")
    for phase in phases.values():
        transition = phase["transition_intent"]
        assert isinstance(transition, dict)
        rollback = phase["rollback_intent"]
        for intent in (transition, rollback):
            if intent is None:
                continue
            assert isinstance(intent, dict)
            target = intent["target_phase_id"]
            if target is not None:
                target_phase = phases.get(str(target))
                if target_phase is None or target_phase["lifecycle"] != phase["lifecycle"]:
                    raise PolicyError(f"invalid-phase-transition-target:{phase['id']}")


def _validate_legacy_bridges(phases: Sequence[Mapping[str, object]], activation: Mapping[str, object]) -> None:
    bridge_name = activation["legacy_bridge"]
    assert isinstance(bridge_name, str)
    bridges = [phase for phase in phases if phase["compatibility_adapter"] is not None]
    if len(bridges) > 1:
        raise PolicyError("duplicate-compatibility-adapter")
    for phase in bridges:
        if phase["compatibility_adapter"] != bridge_name or phase["lifecycle"] != "compatibility":
            raise PolicyError(f"invalid-compatibility-adapter:{phase['id']}")
        if phase["stage"] != bridge_name:
            raise PolicyError(f"invalid-legacy-bridge-stage:{phase['id']}")
        input_pairs = {(contract["kind"], contract["state"]) for contract in phase["input_contracts"]}  # type: ignore[index]
        output_pairs = {(contract["kind"], contract["scope"]) for contract in phase["output_contracts"]}  # type: ignore[index]
        if input_pairs != {("LegacySpec", "approved"), ("LegacyApprovalObservation", "observed")}:
            raise PolicyError(f"invalid-legacy-bridge-inputs:{phase['id']}")
        if output_pairs != {("LegacyPlan", "preview")}:
            raise PolicyError(f"invalid-legacy-bridge-outputs:{phase['id']}")
        transition = phase["transition_intent"]
        assert isinstance(transition, dict)
        if transition["scope"] != "preview":
            raise PolicyError(f"legacy-bridge-cannot-escape-preview:{phase['id']}")
    for phase in phases:
        if phase["lifecycle"] == "compatibility" and phase["compatibility_adapter"] is None:
            raise PolicyError(f"compatibility-phase-requires-adapter:{phase['id']}")


def _semantic_source_hash(value: object) -> str:
    """Hash a normalized parsed source document, never raw JSON formatting."""
    return _sha256(canonical_bytes(value))


def compile_policy(
    policy_root: str | os.PathLike[str],
    skill_root: str | os.PathLike[str],
    engine_version: str,
    *,
    compiler_version: str = COMPILER_VERSION,
) -> dict[str, object]:
    """Compile three strict source documents into a deterministic immutable manifest."""
    root = Path(policy_root)
    skills = Path(skill_root)
    modules_document = _load_json(root / "modules.json", _MODULES_DOCUMENT_KEYS, "modules")
    phases_document = _load_json(root / "phases.json", _PHASES_DOCUMENT_KEYS, "phases")
    roles_document = _load_json(root / "roles.json", _ROLES_DOCUMENT_KEYS, "roles")
    if modules_document["schema_version"] != MODULES_SCHEMA:
        raise PolicyError("unsupported-modules-schema")
    if phases_document["schema_version"] != PHASES_SCHEMA:
        raise PolicyError("unsupported-phases-schema")
    if roles_document["schema_version"] != ROLES_SCHEMA:
        raise PolicyError("unsupported-roles-schema")
    policy = _require_exact_keys(modules_document["policy"], _POLICY_KEYS, "policy")
    if policy["policy_format"] != POLICY_FORMAT:
        raise PolicyError("unsupported-policy-format")
    migration_version = _require_text(policy["migration_version"], "migration-version")
    activation = _normalize_activation(policy["activation"], migration_version)
    engine_api = _require_exact_keys(policy["engine_api"], _ENGINE_API_KEYS, "engine-api")
    engine = _semver(engine_version, "engine-version")
    minimum = _semver(engine_api["min_inclusive"], "engine-api-min-inclusive")
    maximum = _semver(engine_api["max_exclusive"], "engine-api-max-exclusive")
    if minimum >= maximum or not minimum <= engine < maximum:
        raise PolicyError("engine-version-not-compatible")
    _semver(compiler_version, "compiler-version")

    raw_rules = modules_document["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PolicyError("invalid-rules")
    rules = [_normalize_rule(raw_rule) for raw_rule in raw_rules]
    rules_by_id = {str(rule["id"]): rule for rule in rules}
    if len(rules_by_id) != len(rules):
        raise PolicyError("duplicate-rule-id")
    resolution_priorities = {(rule["resolution_group"], rule["priority"]) for rule in rules}
    if len(resolution_priorities) != len(rules):
        raise PolicyError("rule-priority-conflict")
    rules = sorted(rules, key=lambda rule: (str(rule["resolution_group"]), int(rule["priority"]), str(rule["id"])))

    raw_modules = modules_document["modules"]
    if not isinstance(raw_modules, list) or not raw_modules:
        raise PolicyError("invalid-modules")
    modules: list[dict[str, object]] = []
    module_bodies: dict[str, bytes] = {}
    closure_by_path: dict[str, dict[str, object]] = {}
    for raw_module in raw_modules:
        module, closure, body = _normalize_module(raw_module, skills)
        module_id = str(module["id"])
        modules.append(module)
        module_bodies[module_id] = body
        prior_closure = closure_by_path.setdefault(str(closure["path"]), closure)
        if prior_closure != closure:
            raise PolicyError(f"conflicting-playbook-closure:{closure['path']}")
    modules_by_id = {str(module["id"]): module for module in modules}
    if len(modules_by_id) != len(modules):
        raise PolicyError("duplicate-module-id")
    for module in modules:
        module_id = str(module["id"])
        for rule_id in module["selector_rule_ids"]:  # type: ignore[index]
            rule = rules_by_id.get(str(rule_id))
            if rule is None or rule["target"] != {"kind": "module", "id": module_id}:
                raise PolicyError(f"invalid-module-selector-rule:{module_id}:{rule_id}")
    _assert_module_dag(modules_by_id)
    modules = sorted(modules, key=lambda module: str(module["id"]))

    raw_roles = roles_document["roles"]
    if not isinstance(raw_roles, list) or not raw_roles:
        raise PolicyError("invalid-roles")
    roles = [_normalize_role(raw_role, rules_by_id) for raw_role in raw_roles]
    roles_by_id = {str(role["id"]): role for role in roles}
    if len(roles_by_id) != len(roles):
        raise PolicyError("duplicate-role-id")
    all_constraints = [
        constraint for role in roles for constraint in role["independence_constraints"]  # type: ignore[index]
    ]
    if len({constraint["id"] for constraint in all_constraints}) != len(all_constraints):
        raise PolicyError("duplicate-independence-constraint-id")
    roles = sorted(roles, key=lambda role: str(role["id"]))

    raw_phases = phases_document["phases"]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise PolicyError("invalid-phases")
    phases = [
        _normalize_phase(raw_phase, modules_by_id, roles_by_id, rules_by_id, module_bodies, activation)
        for raw_phase in raw_phases
    ]
    phases_by_id = {str(phase["id"]): phase for phase in phases}
    if len(phases_by_id) != len(phases):
        raise PolicyError("duplicate-phase-id")
    if len({(phase["lifecycle"], phase["stage"]) for phase in phases}) != len(phases):
        raise PolicyError("duplicate-lifecycle-stage")
    all_obligations = [obligation for phase in phases for obligation in phase["obligations"]]  # type: ignore[index]
    if len({obligation["id"] for obligation in all_obligations}) != len(all_obligations):
        raise PolicyError("duplicate-obligation-id")
    _validate_references(rules, modules_by_id, roles_by_id, phases_by_id)
    _validate_legacy_bridges(phases, activation)
    phases = sorted(phases, key=lambda phase: str(phase["id"]))

    normalized_policy = {
        "policy_format": POLICY_FORMAT,
        "engine_api": {
            "min_inclusive": engine_api["min_inclusive"],
            "max_exclusive": engine_api["max_exclusive"],
        },
        "migration_version": migration_version,
        "activation": activation,
    }
    semantic_sources = [
        {
            "path": "modules.json",
            "sha256": _semantic_source_hash({
                "schema_version": MODULES_SCHEMA,
                "policy": normalized_policy,
                "rules": rules,
                "modules": modules,
            }),
        },
        {
            "path": "phases.json",
            "sha256": _semantic_source_hash({"schema_version": PHASES_SCHEMA, "phases": phases}),
        },
        {
            "path": "roles.json",
            "sha256": _semantic_source_hash({"schema_version": ROLES_SCHEMA, "roles": roles}),
        },
    ]
    dependency_closure = [closure_by_path[path] for path in sorted(closure_by_path)]
    preimage = {
        "schema_version": MANIFEST_SCHEMA,
        "policy_format": POLICY_FORMAT,
        "compiler": {"id": COMPILER_ID, "version": compiler_version},
        "engine_api": normalized_policy["engine_api"],
        "migration_version": migration_version,
        "activation": activation,
        "source_files": semantic_sources,
        "rules": rules,
        "modules": modules,
        "phases": phases,
        "roles": roles,
        "dependency_closure": dependency_closure,
    }
    policy_manifest_id = _sha256(canonical_bytes(preimage))
    manifest = dict(preimage)
    manifest["policy_manifest_id"] = policy_manifest_id
    manifest["phases"] = [
        {**phase, "phase_contract_ref": f"{policy_manifest_id}#{phase['id']}"}
        for phase in phases
    ]
    return manifest


def _write_manifest(path: str | os.PathLike[str], manifest: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(manifest))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (commands.add_parser("compile"), commands.add_parser("check")):
        command.add_argument("--policy-root", required=True)
        command.add_argument("--skill-root", required=True)
        command.add_argument("--engine-version", required=True)
        command.add_argument("--compiler-version", default=COMPILER_VERSION)
    commands.choices["compile"].add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = compile_policy(
            args.policy_root,
            args.skill_root,
            args.engine_version,
            compiler_version=args.compiler_version,
        )
        if args.command == "compile":
            _write_manifest(args.out, manifest)
    except PolicyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
