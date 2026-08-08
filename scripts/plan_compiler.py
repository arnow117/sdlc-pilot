#!/usr/bin/env python3
"""Compile an approved EngineeringSpec into an immutable static DeliveryPlan."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Mapping, Sequence

import trace_lint


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_EXECUTION_MODES = frozenset({"tdd", "static-check", "visual-regression", "contract-check", "typed-attestation"})
_CANONICAL_RUNNABLE_MODES = frozenset({"tdd", "static-check", "visual-regression", "contract-check"})
_FORBIDDEN_RUNTIME_FIELDS = frozenset({
    "status", "owner", "evidence_refs", "tests_passed", "approved", "review_complete", "result", "passed",
})
_TASK_FIELDS = frozenset({
    "id", "title", "depends_on", "write_set", "mutual_exclusion_with", "interface_owner",
    "interface_consumes", "execution_mode", "evidence_strategy", "trace_refs",
})
_PLAN_PREIMAGE_FIELDS = frozenset({
    "plan_format", "feature_id", "engineering_spec_ref", "engineering_spec_revision",
    "engineering_spec_approval_ref", "product_contract_ref", "product_contract_approval_ref",
    "profile_ref", "profile_revision", "profile_sha256", "base_sha", "contract_generation",
    "tasks", "interfaces",
})
_PLAN_ENVELOPE_FIELDS = _PLAN_PREIMAGE_FIELDS | frozenset({
    "delivery_plan_id", "bundle_sha256", "components",
})


class PlanError(ValueError):
    """A plan cannot be derived from the approved EngineeringSpec tuple."""


def canonical_bytes(value: object) -> bytes:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PlanError("non-canonical-plan-value") from exc
    return (payload + "\n").encode("utf-8")


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PlanError(f"invalid-{label}")
    return value


def _git_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        raise PlanError(f"invalid-{label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PlanError(f"invalid-{label}")
    return value


def _task_id(value: object, label: str) -> str:
    task_id = _text(value, label)
    if not _TASK_ID.fullmatch(task_id) or ".." in task_id:
        raise PlanError(f"invalid-{label}")
    return task_id


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise PlanError(f"invalid-{label}")
    return value


def _string_list(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise PlanError(f"invalid-{label}")
    result = [_text(item, f"{label}-item") for item in value]
    if len(result) != len(set(result)):
        raise PlanError(f"duplicate-{label}")
    return sorted(result)


def _ordered_string_list(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    """Validate an ordered argv-style list without changing its execution semantics."""
    if not isinstance(value, list) or (not allow_empty and not value):
        raise PlanError(f"invalid-{label}")
    result = [_text(item, f"{label}-item") for item in value]
    return result


def _safe_write_path(value: object) -> str:
    path = _text(value, "write-set-path")
    pure = PurePosixPath(path)
    if (
        pure.is_absolute() or path != pure.as_posix() or "\\" in path or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise PlanError(f"unsafe-write-set-path:{path}")
    return path


def _write_set(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PlanError("invalid-write-set")
    result = [_safe_write_path(item) for item in value]
    if len(result) != len(set(result)):
        raise PlanError("duplicate-write-set-path")
    return sorted(result)


def _execution_cwd(value: object) -> str:
    """Normalize the repository-relative working directory for a planned command."""
    path = _text(value, "evidence-cwd")
    if path == ".":
        return path
    pure = PurePosixPath(path)
    if (
        pure.is_absolute() or path != pure.as_posix() or "\\" in path or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise PlanError(f"unsafe-evidence-cwd:{path}")
    return path


def _evidence_strategy(value: object, execution_mode: str) -> dict[str, object]:
    source = _mapping(value, "evidence-strategy")
    kind = source.get("kind")
    if kind not in _EXECUTION_MODES:
        raise PlanError("invalid-evidence-strategy-kind")
    if kind != execution_mode:
        raise PlanError("evidence-strategy-does-not-match-execution-mode")
    if kind in _CANONICAL_RUNNABLE_MODES:
        if set(source) not in ({"kind", "argv"}, {"kind", "argv", "cwd"}):
            raise PlanError(f"invalid-{kind}-evidence-strategy")
        argv = _ordered_string_list(source["argv"], "evidence-argv", allow_empty=False)
        return {"kind": kind, "argv": argv, "cwd": _execution_cwd(source.get("cwd", "."))}
    if kind == "typed-attestation":
        if set(source) != {"kind", "attestation_type"}:
            raise PlanError("invalid-attestation-evidence-strategy")
        return {"kind": kind, "attestation_type": _text(source["attestation_type"], "attestation-type")}
    if set(source) != {"kind", "check_ref"}:
        raise PlanError("invalid-check-evidence-strategy")
    return {"kind": kind, "check_ref": _text(source["check_ref"], "evidence-check-ref")}


def _parse_trace_refs(value: object, *, product_id: str, engineering_id: str,
                      implements: set[str], engineering_criteria: set[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PlanError("invalid-task-trace-refs")
    parsed: list[tuple[str, str, str]] = []
    for item in value:
        try:
            parsed.append(trace_lint.parse_trace_ref(item))
        except trace_lint.TraceError as exc:
            raise PlanError("invalid-task-trace-ref") from exc
    if len(parsed) != len(set(parsed)):
        raise PlanError("duplicate-task-trace-ref")
    for namespace, subject, criterion in parsed:
        if namespace == "PC":
            if subject != product_id or criterion not in implements:
                raise PlanError("task-product-trace-not-in-engineering-spec")
        elif subject != engineering_id or criterion not in engineering_criteria:
            raise PlanError("task-engineering-trace-not-in-engineering-spec")
    return sorted(f"{namespace}:{subject}#{criterion}" for namespace, subject, criterion in parsed)


def _owner(value: object, *, engineering_id: str, engineering_criteria: set[str]) -> dict[str, str] | None:
    if value is None:
        return None
    source = _mapping(value, "interface-owner")
    if set(source) != {"id", "criterion_ref"}:
        raise PlanError("invalid-interface-owner")
    interface_id = _task_id(source["id"], "interface-id")
    try:
        namespace, subject, criterion = trace_lint.parse_trace_ref(source["criterion_ref"])
    except trace_lint.TraceError as exc:
        raise PlanError("invalid-interface-criterion-ref") from exc
    if namespace != "ES" or subject != engineering_id or criterion not in engineering_criteria:
        raise PlanError("interface-owner-must-reference-engineering-criterion")
    return {"id": interface_id, "criterion_ref": f"ES:{subject}#{criterion}"}


def _normalize_task_defs(
    task_defs: Sequence[Mapping[str, object]], *, product_id: str, engineering_id: str,
    implements: set[str], engineering_criteria: set[str],
) -> list[dict[str, object]]:
    if isinstance(task_defs, (str, bytes)) or not isinstance(task_defs, Sequence) or not task_defs:
        raise PlanError("invalid-task-definitions")
    result: list[dict[str, object]] = []
    known_ids: set[str] = set()
    for index, raw in enumerate(task_defs):
        task = _mapping(raw, f"task-{index}")
        forbidden = _FORBIDDEN_RUNTIME_FIELDS & set(task)
        if forbidden:
            raise PlanError("plan-task-cannot-contain-runtime-fields:" + ",".join(sorted(forbidden)))
        if set(task) != _TASK_FIELDS:
            raise PlanError("invalid-task-definition-fields")
        task_id = _task_id(task["id"], "task-id")
        if task_id in known_ids:
            raise PlanError("duplicate-task-id")
        known_ids.add(task_id)
        execution_mode = task["execution_mode"]
        if execution_mode not in _EXECUTION_MODES:
            raise PlanError("invalid-execution-mode")
        result.append({
            "id": task_id,
            "title": _text(task["title"], "task-title"),
            "depends_on": _string_list(task["depends_on"], "depends-on"),
            "write_set": _write_set(task["write_set"]),
            "mutual_exclusion_with": _string_list(task["mutual_exclusion_with"], "mutual-exclusion-with"),
            "interface_owner": _owner(task["interface_owner"], engineering_id=engineering_id,
                                        engineering_criteria=engineering_criteria),
            "interface_consumes": _string_list(task["interface_consumes"], "interface-consumes"),
            "execution_mode": execution_mode,
            "evidence_strategy": _evidence_strategy(task["evidence_strategy"], execution_mode),
            "trace_refs": _parse_trace_refs(task["trace_refs"], product_id=product_id,
                                              engineering_id=engineering_id, implements=implements,
                                              engineering_criteria=engineering_criteria),
        })
    ids = {str(task["id"]) for task in result}
    for task in result:
        task_id = str(task["id"])
        if task_id in task["depends_on"] or not set(task["depends_on"]).issubset(ids):
            raise PlanError("unknown-or-self-dependency")
        if task_id in task["mutual_exclusion_with"] or not set(task["mutual_exclusion_with"]).issubset(ids):
            raise PlanError("unknown-or-self-mutual-exclusion")
    return sorted(result, key=lambda item: str(item["id"]))


def _ancestors(tasks: Sequence[Mapping[str, object]]) -> dict[str, set[str]]:
    dependencies = {str(task["id"]): set(task["depends_on"]) for task in tasks}
    ancestors: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def walk(task_id: str) -> set[str]:
        if task_id in ancestors:
            return ancestors[task_id]
        if task_id in visiting:
            raise PlanError("task-dependency-cycle")
        visiting.add(task_id)
        result: set[str] = set()
        for parent in dependencies[task_id]:
            result.add(parent)
            result.update(walk(parent))
        visiting.remove(task_id)
        ancestors[task_id] = result
        return result

    for task_id in sorted(dependencies):
        walk(task_id)
    return ancestors


def _path_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    def root(path: str) -> str:
        return path.split("*", 1)[0].rstrip("/")
    left_root, right_root = root(left), root(right)
    return bool(left_root and right_root and (
        left_root.startswith(right_root + "/") or right_root.startswith(left_root + "/")
    ))


def _validate_interface_and_write_set(tasks: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    ancestors = _ancestors(tasks)
    by_id = {str(task["id"]): task for task in tasks}
    interfaces: dict[str, dict[str, object]] = {}
    for task in tasks:
        owner = task["interface_owner"]
        if owner is None:
            continue
        interface_id = str(owner["id"])
        if interface_id in interfaces:
            raise PlanError("duplicate-interface-owner")
        interfaces[interface_id] = {
            "id": interface_id,
            "owner_task_id": task["id"],
            "criterion_ref": owner["criterion_ref"],
            "consumer_task_ids": [],
        }
    for task in tasks:
        task_id = str(task["id"])
        for interface_id in task["interface_consumes"]:
            interface = interfaces.get(interface_id)
            if interface is None:
                raise PlanError("unknown-interface-consumer")
            owner = str(interface["owner_task_id"])
            if owner not in ancestors[task_id]:
                raise PlanError("interface-owner-is-not-dag-ancestor")
            interface["consumer_task_ids"].append(task_id)
    for left_index, left in enumerate(tasks):
        left_id = str(left["id"])
        for right in tasks[left_index + 1:]:
            right_id = str(right["id"])
            overlap = any(_path_overlap(a, b) for a in left["write_set"] for b in right["write_set"])
            if not overlap:
                continue
            ordered = left_id in ancestors[right_id] or right_id in ancestors[left_id]
            mutual = right_id in left["mutual_exclusion_with"] and left_id in right["mutual_exclusion_with"]
            if not ordered and not mutual:
                raise PlanError("write-set-overlap-without-ordering-or-mutual-exclusion")
    return [
        {
            **interface,
            "consumer_task_ids": sorted(interface["consumer_task_ids"]),
        }
        for _, interface in sorted(interfaces.items())
    ]


def _require_engineering_spec(spec: Mapping[str, object]) -> dict[str, object]:
    source = _mapping(spec, "engineering-spec")
    if source.get("spec_format") != "engineering-spec-v1":
        raise PlanError("unapproved-or-invalid-engineering-spec-format")
    engineering_id = _sha(source.get("engineering_spec_id"), "engineering-spec-id")
    if source.get("bundle_sha256") != engineering_id:
        raise PlanError("engineering-spec-bundle-id-mismatch")
    feature_id = _task_id(source.get("feature_id"), "feature-id")
    product_id = _sha(source.get("product_contract_ref"), "product-contract-ref")
    if source.get("product_contract_revision") != product_id:
        raise PlanError("engineering-spec-product-revision-mismatch")
    product_approval = _sha(source.get("product_contract_approval_ref"), "product-contract-approval-ref")
    profile_ref = _sha(source.get("profile_ref"), "profile-ref")
    profile_revision = _git_sha(source.get("profile_revision"), "profile-revision")
    profile_sha = _sha(source.get("profile_sha256"), "profile-sha")
    base_sha = _git_sha(source.get("specified_against_sha"), "specified-against-sha")
    implements = _string_list(source.get("implements_product_ids"), "implements-product-ids", allow_empty=False)
    criteria = _string_list(source.get("engineering_criterion_ids"), "engineering-criterion-ids", allow_empty=False)
    if any(not item.startswith(("OUT-", "SCN-", "RULE-", "EXP-", "NFR-", "EVAL-")) for item in implements):
        raise PlanError("invalid-implemented-product-criterion")
    if any(not item.startswith(("ARCH-", "API-", "DATA-", "REL-", "SEC-", "TEST-")) for item in criteria):
        raise PlanError("invalid-engineering-criterion")
    return {
        "engineering_spec_id": engineering_id,
        "feature_id": feature_id,
        "product_contract_ref": product_id,
        "product_contract_approval_ref": product_approval,
        "profile_ref": profile_ref,
        "profile_revision": profile_revision,
        "profile_sha256": profile_sha,
        "base_sha": base_sha,
        "implements_product_ids": implements,
        "engineering_criterion_ids": criteria,
        "contract_generation": _generation(source.get("contract_generation", 0)),
    }


def _generation(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlanError("invalid-contract-generation")
    return value


def require_effective_engineering_approval(spec: Mapping[str, object], approval: Mapping[str, object]) -> str:
    """Require a concrete approval-head tuple; a caller boolean is never accepted."""
    source = _mapping(approval, "effective-approval")
    forbidden = {"approved", "approval_complete", "tests_passed"} & set(source)
    if forbidden:
        raise PlanError("self-reported-approval-not-accepted")
    spec_info = _require_engineering_spec(spec)
    approval_id = _sha(source.get("approval_id"), "engineering-approval-id")
    expected = {
        "subject_type": "engineering_spec",
        "scope": "feature",
        "subject_id": spec_info["engineering_spec_id"],
        "subject_ref": spec_info["engineering_spec_id"],
        "subject_revision": spec_info["engineering_spec_id"],
        "subject_sha256": spec_info["engineering_spec_id"],
        "decision": "approve",
        "head_ref": approval_id,
        "head_decision": "approve",
    }
    for field, expected_value in expected.items():
        if source.get(field) != expected_value:
            raise PlanError(f"ineffective-engineering-approval:{field}")
    return approval_id


def _plan_preimage(plan: Mapping[str, object]) -> dict[str, object]:
    if not _PLAN_PREIMAGE_FIELDS.issubset(plan):
        raise PlanError("incomplete-delivery-plan-manifest")
    return {field: plan[field] for field in sorted(_PLAN_PREIMAGE_FIELDS)}


def _validate_coverage(tasks: Sequence[Mapping[str, object]], spec: Mapping[str, object]) -> None:
    covered_product: set[str] = set()
    covered_engineering: set[str] = set()
    for task in tasks:
        for ref in task["trace_refs"]:
            namespace, _, criterion = trace_lint.parse_trace_ref(ref)
            (covered_product if namespace == "PC" else covered_engineering).add(criterion)
    if covered_product != set(spec["implements_product_ids"]):
        raise PlanError("delivery-plan-does-not-cover-implemented-product-criteria")
    if covered_engineering != set(spec["engineering_criterion_ids"]):
        raise PlanError("delivery-plan-does-not-cover-engineering-criteria")


def _expected_plan_binding(spec: Mapping[str, object], approval_id: str) -> dict[str, object]:
    return {
        "feature_id": spec["feature_id"],
        "engineering_spec_ref": spec["engineering_spec_id"],
        "engineering_spec_revision": spec["engineering_spec_id"],
        "engineering_spec_approval_ref": approval_id,
        "product_contract_ref": spec["product_contract_ref"],
        "product_contract_approval_ref": spec["product_contract_approval_ref"],
        "profile_ref": spec["profile_ref"],
        "profile_revision": spec["profile_revision"],
        "profile_sha256": spec["profile_sha256"],
        "base_sha": spec["base_sha"],
        "contract_generation": spec["contract_generation"],
    }


def compile_delivery_plan(
    engineering_spec: Mapping[str, object], effective_approval: Mapping[str, object],
    task_defs: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Compile a static, immutable task DAG from an approved EngineeringSpec."""
    spec = _require_engineering_spec(engineering_spec)
    approval_id = require_effective_engineering_approval(engineering_spec, effective_approval)
    tasks = _normalize_task_defs(
        task_defs, product_id=str(spec["product_contract_ref"]), engineering_id=str(spec["engineering_spec_id"]),
        implements=set(spec["implements_product_ids"]), engineering_criteria=set(spec["engineering_criterion_ids"]),
    )
    interfaces = _validate_interface_and_write_set(tasks)
    _validate_coverage(tasks, spec)
    binding = _expected_plan_binding(spec, approval_id)
    preimage = {
        "plan_format": "delivery-plan-v1",
        **binding,
        "tasks": tasks,
        "interfaces": interfaces,
    }
    plan_id = hashlib.sha256(canonical_bytes(preimage)).hexdigest()
    return {
        **preimage,
        "delivery_plan_id": plan_id,
        "bundle_sha256": plan_id,
        "components": [],
    }


def verify_delivery_plan(
    plan: Mapping[str, object], *, engineering_spec: Mapping[str, object],
    effective_approval: Mapping[str, object],
) -> str:
    """Strictly verify a plan against its bound EngineeringSpec and approval head."""
    source = _mapping(plan, "delivery-plan")
    if set(source) != _PLAN_ENVELOPE_FIELDS:
        raise PlanError("invalid-delivery-plan-fields")
    if source.get("plan_format") != "delivery-plan-v1":
        raise PlanError("invalid-delivery-plan-format")
    identity = _sha(source.get("delivery_plan_id"), "delivery-plan-id")
    if source.get("bundle_sha256") != identity:
        raise PlanError("delivery-plan-bundle-id-mismatch")
    if source.get("components") != []:
        raise PlanError("delivery-plan-components-must-be-empty")

    spec = _require_engineering_spec(engineering_spec)
    approval_id = require_effective_engineering_approval(engineering_spec, effective_approval)
    for field, expected in _expected_plan_binding(spec, approval_id).items():
        if source.get(field) != expected:
            raise PlanError(f"delivery-plan-binding-mismatch:{field}")

    tasks = _normalize_task_defs(
        source.get("tasks"), product_id=str(spec["product_contract_ref"]),
        engineering_id=str(spec["engineering_spec_id"]),
        implements=set(spec["implements_product_ids"]),
        engineering_criteria=set(spec["engineering_criterion_ids"]),
    )
    if source.get("tasks") != tasks:
        raise PlanError("non-canonical-delivery-plan-tasks")
    interfaces = _validate_interface_and_write_set(tasks)
    if source.get("interfaces") != interfaces:
        raise PlanError("interface-manifest-mismatch")
    _validate_coverage(tasks, spec)

    actual = hashlib.sha256(canonical_bytes(_plan_preimage(source))).hexdigest()
    if actual != identity:
        raise PlanError("delivery-plan-hash-mismatch")
    return identity


def projection_path(
    scope: str, *, run_id: str | None = None, delivery_plan_id: str | None = None,
) -> str:
    if scope == "preview":
        if delivery_plan_id is not None:
            raise PlanError("preview-projection-cannot-have-delivery-plan-id")
        return f".sdlc/preview/{_task_id(run_id, 'preview-run-id')}/plan.shadow.md"
    if scope == "canonical":
        if run_id is not None:
            raise PlanError("canonical-projection-cannot-have-preview-run-id")
        plan_id = _sha(delivery_plan_id, "canonical-delivery-plan-id")
        return f".sdlc/contracts/plans/{plan_id}/plan.projection.md"
    raise PlanError("invalid-projection-scope")


def render_plan_projection(
    plan: Mapping[str, object], *, engineering_spec: Mapping[str, object],
    effective_approval: Mapping[str, object], scope: str = "preview", run_id: str | None = None,
) -> str:
    """Render a one-way review projection; no API parses it back into a plan."""
    plan_id = verify_delivery_plan(
        plan, engineering_spec=engineering_spec, effective_approval=effective_approval,
    )
    marker = "shadow-delivery-plan-v1" if scope == "preview" else "delivery-plan-projection-v1"
    target = projection_path(
        scope, run_id=run_id, delivery_plan_id=plan_id if scope == "canonical" else None,
    )
    lines = [
        "# Delivery Plan Projection",
        "",
        f"plan_format: {marker}",
        f"delivery_plan_ref: {plan_id}",
        f"delivery_plan_sha256: {plan_id}",
        f"engineering_spec_ref: {plan['engineering_spec_ref']}",
        f"scope: {scope}",
        f"projection_path: {target}",
        "",
        "## Tasks",
        "",
    ]
    for task in plan["tasks"]:
        lines.extend([
            f"### {task['id']}: {task['title']}",
            f"- depends_on: {', '.join(task['depends_on']) or '(none)'}",
            f"- execution_mode: {task['execution_mode']}",
            f"- trace_refs: {', '.join(task['trace_refs'])}",
            "",
        ])
    return "\n".join(lines) + "\n"
