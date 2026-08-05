#!/usr/bin/env python3
"""Mechanical ProductContract → EngineeringSpec → Task → Evidence trace checks."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Mapping, Sequence


TRACE_REF = re.compile(r"^(PC|ES):([0-9a-f]{64})#([A-Z][A-Z0-9]*-[0-9]{3,})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CRITERION = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{3,}$")
_PRODUCT_FIELDS = (
    "outcome_ids", "behavior_ids", "domain_rule_ids", "experience_ids", "nfr_ids", "eval_ids",
)
_REQUIRED_PRODUCT_FIELDS = ("behavior_ids", "domain_rule_ids", "nfr_ids", "eval_ids")


class TraceError(ValueError):
    """A trace reference is malformed before graph linting can begin."""


@dataclass(frozen=True)
class TraceIssue:
    code: str
    path: str
    detail: str = ""


@dataclass
class TraceReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[TraceIssue] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return sorted(set(self.errors + self.warnings))

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_trace_ref(value: str) -> tuple[str, str, str]:
    """Parse an immutable, fully-qualified Product or Engineering criterion ref."""
    if not isinstance(value, str):
        raise TraceError("invalid-trace-ref")
    match = TRACE_REF.fullmatch(value)
    if match is None:
        raise TraceError(f"invalid-trace-ref:{value}")
    return match.group(1), match.group(2), match.group(3)


def _error(report: TraceReport, code: str, path: str, detail: object = "") -> None:
    report.errors.append(code)
    report.issues.append(TraceIssue(code, path, str(detail)))


def _mapping(value: object, report: TraceReport, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _error(report, "invalid-record", path)
        return {}
    return value


def _full_sha(value: object, report: TraceReport, path: str, code: str = "invalid-sha256") -> str | None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _error(report, code, path)
        return None
    return value


def _positive_int(value: object, report: TraceReport, path: str) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _error(report, "invalid-contract-generation", path)
        return None
    return value


def _id_list(value: object, report: TraceReport, path: str) -> list[str]:
    if not isinstance(value, list):
        _error(report, "invalid-criterion-list", path)
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _CRITERION.fullmatch(item):
            _error(report, "invalid-criterion-id", f"{path}[{index}]")
            continue
        result.append(item)
    if len(result) != len(set(result)):
        _error(report, "duplicate-criterion", path)
    return result


def _trace_list(value: object, report: TraceReport, path: str, *, required: bool = True) -> list[tuple[str, str, str]]:
    if not isinstance(value, list) or (required and not value):
        _error(report, "missing-trace-refs", path)
        return []
    result: list[tuple[str, str, str]] = []
    for index, item in enumerate(value):
        try:
            result.append(parse_trace_ref(item))
        except TraceError:
            _error(report, "invalid-trace-ref", f"{path}[{index}]", item)
    if len(result) != len(set(result)):
        _error(report, "duplicate-trace-ref", path)
    return result


def _product_criteria(product: Mapping[str, object], report: TraceReport) -> tuple[set[str], set[str]]:
    all_ids: set[str] = set()
    required_ids: set[str] = set()
    for field in _PRODUCT_FIELDS:
        values = _id_list(product.get(field, []), report, f"product.{field}")
        overlap = all_ids & set(values)
        if overlap:
            _error(report, "duplicate-product-criterion", f"product.{field}", ",".join(sorted(overlap)))
        all_ids.update(values)
        if field in _REQUIRED_PRODUCT_FIELDS:
            required_ids.update(values)
    return all_ids, required_ids


def _task_id(record: Mapping[str, object], report: TraceReport, path: str) -> str | None:
    value = record.get("task_id", record.get("id"))
    if not isinstance(value, str) or not value:
        _error(report, "invalid-task-id", path)
        return None
    return value


def _check_tuple(
    record: Mapping[str, object], *, product_id: str | None, engineering_id: str | None,
    plan_id: str | None, generation: int | None, report: TraceReport, path: str,
) -> None:
    expected = {
        "product_contract_ref": product_id,
        "engineering_spec_ref": engineering_id,
        "delivery_plan_ref": plan_id,
        "contract_generation": generation,
    }
    for field, expected_value in expected.items():
        if expected_value is None:
            continue
        actual = record.get(field)
        if actual != expected_value:
            _error(report, "contract-tuple-mismatch", f"{path}.{field}")


def _check_legacy_requirements(record: Mapping[str, object], trace_refs: list[tuple[str, str, str]],
                               report: TraceReport, path: str) -> None:
    if "requirements" not in record:
        return
    raw = record["requirements"]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        _error(report, "invalid-legacy-requirements", f"{path}.requirements")
        return
    try:
        legacy_refs = [parse_trace_ref(item) for item in raw]
    except TraceError:
        _error(report, "legacy-requirements-not-generated-trace-refs", f"{path}.requirements")
        return
    if set(legacy_refs) != set(trace_refs):
        _error(report, "legacy-requirements-trace-mismatch", path)


def _check_ref(
    ref: tuple[str, str, str], *, product_id: str | None, engineering_id: str | None,
    product_criteria: set[str], engineering_criteria: set[str], implements: set[str],
    report: TraceReport, path: str,
) -> None:
    namespace, subject, criterion = ref
    if namespace == "PC":
        if subject != product_id:
            _error(report, "unknown-product-subject", path)
        elif criterion not in product_criteria:
            _error(report, "unknown-criterion", path)
        elif criterion not in implements:
            _error(report, "product-criterion-not-implemented", path)
    else:
        if subject != engineering_id:
            _error(report, "unknown-engineering-subject", path)
        elif criterion not in engineering_criteria:
            _error(report, "unknown-criterion", path)


def _plan_task_ids(plan: Mapping[str, object], report: TraceReport) -> set[str]:
    if "tasks" not in plan:
        return set()
    raw = plan["tasks"]
    if not isinstance(raw, list):
        _error(report, "invalid-plan-tasks", "plan.tasks")
        return set()
    ids: set[str] = set()
    for index, item in enumerate(raw):
        task = _mapping(item, report, f"plan.tasks[{index}]")
        if "status" in task or "evidence_refs" in task or "owner" in task:
            _error(report, "plan-contains-runtime-field", f"plan.tasks[{index}]")
        task_id = _task_id(task, report, f"plan.tasks[{index}].id")
        if task_id is not None:
            if task_id in ids:
                _error(report, "duplicate-plan-task-id", f"plan.tasks[{index}]")
            ids.add(task_id)
    return ids


def lint_trace_graph(
    product: Mapping[str, object], engineering: Mapping[str, object], delivery_plan: Mapping[str, object],
    tasks: Sequence[Mapping[str, object]], evidence: Sequence[Mapping[str, object]],
) -> TraceReport:
    """Lint only mechanically observable trace, tuple, and coverage relationships."""
    report = TraceReport()
    product = _mapping(product, report, "product")
    engineering = _mapping(engineering, report, "engineering")
    plan = _mapping(delivery_plan, report, "plan")
    product_id = _full_sha(product.get("product_contract_id"), report, "product.product_contract_id")
    engineering_id = _full_sha(engineering.get("engineering_spec_id"), report, "engineering.engineering_spec_id")
    plan_id = _full_sha(plan.get("delivery_plan_id"), report, "plan.delivery_plan_id")
    generation = _positive_int(plan.get("contract_generation"), report, "plan.contract_generation")
    product_criteria, required_product_criteria = _product_criteria(product, report)
    engineering_criteria = set(_id_list(
        engineering.get("engineering_criterion_ids"), report, "engineering.engineering_criterion_ids",
    ))
    if not engineering_criteria:
        _error(report, "missing-engineering-criteria", "engineering.engineering_criterion_ids")
    implements = set(_id_list(
        engineering.get("implements_product_ids"), report, "engineering.implements_product_ids",
    ))
    if engineering.get("product_contract_ref") != product_id:
        _error(report, "engineering-product-tuple-mismatch", "engineering.product_contract_ref")
    unknown_implements = implements - product_criteria
    if unknown_implements:
        _error(report, "engineering-implements-unknown-product-criterion", "engineering.implements_product_ids")
    missing_implements = required_product_criteria - implements
    if missing_implements:
        _error(report, "unimplemented-product-criterion", "engineering.implements_product_ids", ",".join(sorted(missing_implements)))
    if plan.get("product_contract_ref") != product_id:
        _error(report, "plan-product-tuple-mismatch", "plan.product_contract_ref")
    if plan.get("engineering_spec_ref") != engineering_id:
        _error(report, "plan-engineering-tuple-mismatch", "plan.engineering_spec_ref")
    if "engineering_spec_approval_ref" in plan and not _full_sha(
        plan.get("engineering_spec_approval_ref"), report, "plan.engineering_spec_approval_ref",
    ):
        pass
    if "engineering_spec_approval_ref" in engineering and (
        plan.get("engineering_spec_approval_ref") != engineering.get("engineering_spec_approval_ref")
    ):
        _error(report, "plan-engineering-approval-tuple-mismatch", "plan.engineering_spec_approval_ref")
    plan_task_ids = _plan_task_ids(plan, report)
    task_by_id: dict[str, Mapping[str, object]] = {}
    task_traces: dict[str, set[tuple[str, str, str]]] = {}
    traced_product: set[str] = set()
    traced_engineering: set[str] = set()
    for index, raw_task in enumerate(tasks):
        task = _mapping(raw_task, report, f"tasks[{index}]")
        task_id = _task_id(task, report, f"tasks[{index}].task_id")
        if task_id is None:
            continue
        if task_id in task_by_id:
            _error(report, "duplicate-task-id", f"tasks[{index}].task_id")
            continue
        task_by_id[task_id] = task
        if plan_task_ids and task_id not in plan_task_ids:
            _error(report, "task-not-in-delivery-plan", f"tasks[{index}].task_id")
        _check_tuple(task, product_id=product_id, engineering_id=engineering_id, plan_id=plan_id,
                     generation=generation, report=report, path=f"tasks[{index}]")
        refs = _trace_list(task.get("trace_refs"), report, f"tasks[{index}].trace_refs")
        _check_legacy_requirements(task, refs, report, f"tasks[{index}]")
        task_traces[task_id] = set(refs)
        for ref_index, ref in enumerate(refs):
            _check_ref(ref, product_id=product_id, engineering_id=engineering_id,
                       product_criteria=product_criteria, engineering_criteria=engineering_criteria,
                       implements=implements, report=report, path=f"tasks[{index}].trace_refs[{ref_index}]")
            if ref[0] == "PC":
                traced_product.add(ref[2])
            else:
                traced_engineering.add(ref[2])
    for criterion in sorted(implements - traced_product):
        _error(report, "unplanned-product-criterion", "tasks", criterion)
    for criterion in sorted(engineering_criteria - traced_engineering):
        _error(report, "unplanned-engineering-criterion", "tasks", criterion)
    proved_by_task: dict[str, set[tuple[str, str, str]]] = {task_id: set() for task_id in task_by_id}
    evidence_ids: set[str] = set()
    for index, raw_evidence in enumerate(evidence):
        item = _mapping(raw_evidence, report, f"evidence[{index}]")
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            _error(report, "invalid-evidence-id", f"evidence[{index}].evidence_id")
        elif evidence_id in evidence_ids:
            _error(report, "duplicate-evidence-id", f"evidence[{index}].evidence_id")
        else:
            evidence_ids.add(evidence_id)
        task_id = item.get("task_id")
        if not isinstance(task_id, str) or task_id not in task_by_id:
            _error(report, "evidence-unknown-task", f"evidence[{index}].task_id")
            continue
        _check_tuple(item, product_id=product_id, engineering_id=engineering_id, plan_id=plan_id,
                     generation=generation, report=report, path=f"evidence[{index}]")
        refs = _trace_list(item.get("trace_refs"), report, f"evidence[{index}].trace_refs")
        for ref_index, ref in enumerate(refs):
            _check_ref(ref, product_id=product_id, engineering_id=engineering_id,
                       product_criteria=product_criteria, engineering_criteria=engineering_criteria,
                       implements=implements, report=report, path=f"evidence[{index}].trace_refs[{ref_index}]")
            if ref not in task_traces[task_id]:
                _error(report, "evidence-trace-not-owned-by-task", f"evidence[{index}].trace_refs[{ref_index}]")
        proved_by_task[task_id].update(refs)
    for task_id, refs in task_traces.items():
        missing = refs - proved_by_task.get(task_id, set())
        if missing:
            _error(report, "unproven-task-criterion", f"tasks.{task_id}", ",".join(
                f"{kind}:{subject}#{criterion}" for kind, subject, criterion in sorted(missing)
            ))
    return report
