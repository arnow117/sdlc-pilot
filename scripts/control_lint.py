#!/usr/bin/env python3
"""Cross-record integrity checks for the SDLC control ledger."""
from __future__ import annotations

import os
from pathlib import PurePosixPath
import re

import control_store


SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STATUSES = {
    "request": {"active", "withdrawn"},
    "requirement": {"captured", "spec'd", "planned", "built", "validated", "shipped"},
    "claim": {"active", "released"},
    "feature": {"active", "validated", "shipped", "abandoned"},
    "task": {"waiting", "ready", "claimed", "in_progress", "awaiting_verification",
             "verified", "blocked", "abandoned", "superseded"},
}
REQUIRED = {
    "request": {"request_id", "title", "status", "created_at", "updated_at"},
    "requirement": {"id", "title", "domain_path", "cross_link", "old_system_ref",
                    "new_domain_path", "status", "priority", "depends_on", "risk_level",
                    "source_request", "updated"},
    "claim": {"leaf_id", "feature_id", "feature_branch", "claimed_base_sha", "owner",
              "status", "claimed_at", "released_at", "release_reason"},
    "feature": {"feature_id", "leaf_id", "source_request", "feature_branch",
                "claimed_base_sha", "integration_sha", "owner", "status", "plan_ref",
                "plan_revision", "feature_evidence_refs", "created_at", "updated_at",
                "review_status", "reviewed_sha", "reviewer", "review_report_refs",
                "reviewed_at"},
    "task": {"feature_id", "task_id", "plan_ref", "plan_revision", "requirements",
             "depends_on_tasks", "write_set", "interface_owner", "interfaces_fixed",
             "runtime_isolated", "read_first", "status", "execution_mode", "branch_name",
             "branch_base_sha", "branch_head_sha", "integrated_source_sha", "merge_method",
             "integration_sha", "merge_status", "owner", "evidence_refs", "blocked_reason",
             "created_at", "updated_at"},
    "evidence": {"evidence_id", "feature_id", "task_id", "scope", "result", "tested_sha",
                 "command", "created_at", "producer"},
}
LIST_FIELDS = {
    "requirement": {"cross_link", "depends_on"},
    "feature": {"feature_evidence_refs", "review_report_refs"},
    "task": {"requirements", "depends_on_tasks", "write_set", "read_first", "evidence_refs"},
}


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(ID_RE.fullmatch(value)) and ".." not in value


def _sha(value: object, *, allow_none: bool = False) -> bool:
    return bool((allow_none and value == "(none)") or (
        isinstance(value, str) and SHA_RE.fullmatch(value)))


def _validate_record(kind: str, record: dict[str, object], problems: list[str]) -> None:
    label = f"{kind}:{record.get('_path')}"
    if str(record.get("schema_version")) != str(control_store.SCHEMA_VERSION):
        problems.append(f"bad-schema-version:{label}")
    missing = sorted(REQUIRED[kind] - record.keys())
    if missing:
        problems.append(f"missing-fields:{label}:{missing}")
    if kind in STATUSES and record.get("status") not in STATUSES[kind]:
        problems.append(f"invalid-status:{label}:{record.get('status')}")
    for field in LIST_FIELDS.get(kind, set()):
        if field in record and not isinstance(record[field], list):
            problems.append(f"invalid-list:{label}:{field}")
    if kind == "task":
        for field in ("interfaces_fixed", "runtime_isolated"):
            if not isinstance(record.get(field), bool):
                problems.append(f"invalid-boolean:{label}:{field}")
        if record.get("execution_mode") not in {"undecided", "serial", "task_branch"}:
            problems.append(f"invalid-execution-mode:{label}:{record.get('execution_mode')}")
        if record.get("merge_status") not in {
                "not_applicable", "active", "ready_to_integrate", "integrated", "abandoned"}:
            problems.append(f"invalid-merge-status:{label}:{record.get('merge_status')}")
        if not _sha(record.get("plan_revision")):
            problems.append(f"invalid-sha:{label}:plan_revision")
        for field in ("branch_base_sha", "branch_head_sha", "integrated_source_sha",
                      "integration_sha"):
            if not _sha(record.get(field), allow_none=True):
                problems.append(f"invalid-sha:{label}:{field}")
    elif kind == "claim" and not _sha(record.get("claimed_base_sha")):
        problems.append(f"invalid-sha:{label}:claimed_base_sha")
    elif kind == "feature":
        for field in ("claimed_base_sha", "integration_sha"):
            if not _sha(record.get(field)):
                problems.append(f"invalid-sha:{label}:{field}")
        if not _sha(record.get("plan_revision"), allow_none=True):
            problems.append(f"invalid-sha:{label}:plan_revision")
        if record.get("review_status") not in {"pending", "pass", "fail"}:
            problems.append(f"invalid-review-status:{label}:{record.get('review_status')}")
        if not _sha(record.get("reviewed_sha"), allow_none=True):
            problems.append(f"invalid-sha:{label}:reviewed_sha")
    elif kind == "evidence":
        if record.get("scope") not in {"task", "feature", "release"}:
            problems.append(f"invalid-evidence-scope:{label}:{record.get('scope')}")
        if record.get("result") not in {"pass", "fail"}:
            problems.append(f"invalid-evidence-result:{label}:{record.get('result')}")
        if not _sha(record.get("tested_sha")):
            problems.append(f"invalid-sha:{label}:tested_sha")

    identity_field = {"request": "request_id", "requirement": "id", "claim": "leaf_id",
                      "feature": "feature_id", "task": "task_id", "evidence": "evidence_id"}[kind]
    if not _valid_id(record.get(identity_field)):
        problems.append(f"invalid-id:{label}:{identity_field}")
    path = PurePosixPath(str(record.get("_path", "")))
    expected_name = f"{record.get(identity_field)}.md"
    if path.name != expected_name:
        problems.append(f"path-id-mismatch:{label}:{expected_name}")
    if kind == "task":
        expected = PurePosixPath("tasks", str(record.get("feature_id")),
                                 str(record.get("plan_revision")), expected_name)
        if path != expected:
            problems.append(f"path-identity-mismatch:{label}:{expected}")
    elif kind == "evidence":
        expected = PurePosixPath("evidence", str(record.get("feature_id")),
                                 str(record.get("task_id")), str(record.get("tested_sha")),
                                 expected_name)
        if path != expected:
            problems.append(f"path-identity-mismatch:{label}:{expected}")


def _find_cycle(nodes: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            return stack[stack.index(node):] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in nodes.get(node, []):
            if dependency in nodes:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in nodes:
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def lint_snapshot(snapshot: dict[str, object]) -> list[str]:
    problems = list(snapshot["warnings"])
    requests = snapshot["requests_by_id"]
    requirements = snapshot["requirements_by_id"]
    claims = snapshot["claims_by_leaf"]
    features = snapshot["features_by_id"]

    all_tasks = [task for values in snapshot["tasks_by_feature"].values() for task in values]
    all_evidence_records = [
        record for mapping in (snapshot["evidence_by_task"],
                               snapshot["feature_evidence_by_feature"])
        for values in mapping.values() for record in values]
    for kind, records in (("request", requests.values()),
                          ("requirement", requirements.values()),
                          ("claim", claims.values()), ("feature", features.values()),
                          ("task", all_tasks), ("evidence", all_evidence_records)):
        for record in records:
            _validate_record(kind, record, problems)
    for leaf_id, leaf in requirements.items():
        source = leaf.get("source_request")
        if source not in requests:
            problems.append(f"missing-source-request:{leaf_id}:{source}")
        for dependency in leaf.get("depends_on") or []:
            if dependency not in requirements:
                problems.append(f"dangling-requirement-dep:{leaf_id}:{dependency}")
    req_graph = {leaf_id: list(leaf.get("depends_on") or [])
                 for leaf_id, leaf in requirements.items()}
    req_cycle = _find_cycle(req_graph)
    if req_cycle:
        problems.append("requirement-cycle:" + "->".join(req_cycle))

    for leaf_id, claim_record in claims.items():
        feature = features.get(claim_record.get("feature_id"))
        if leaf_id not in requirements:
            problems.append(f"claim-missing-leaf:{leaf_id}")
        if not feature:
            problems.append(f"claim-missing-feature:{leaf_id}:{claim_record.get('feature_id')}")
        elif feature.get("leaf_id") != leaf_id:
            problems.append(f"claim-feature-leaf-mismatch:{leaf_id}:{feature.get('leaf_id')}")
    leaf_to_features: dict[str, list[str]] = {}
    for feature_id, feature in features.items():
        leaf_to_features.setdefault(str(feature.get("leaf_id")), []).append(feature_id)
        claim_record = claims.get(feature.get("leaf_id"))
        if feature.get("status") == "shipped" and (
                not claim_record or claim_record.get("status") != "released"):
            problems.append(f"shipped-feature-has-active-claim:{feature_id}")
    for leaf_id, feature_ids in leaf_to_features.items():
        active = [feature_id for feature_id in feature_ids
                  if features[feature_id].get("status") in {"active", "validated"}]
        if len(active) > 1:
            problems.append(f"multiple-active-features:{leaf_id}:{active}")

    all_evidence = {record.get("_path"): record for record in all_evidence_records}
    for feature_id, tasks in snapshot["tasks_by_feature"].items():
        by_revision: dict[str, list[dict[str, object]]] = {}
        for task in tasks:
            by_revision.setdefault(str(task.get("plan_revision")), []).append(task)
        for revision, revision_tasks in by_revision.items():
            by_id = {str(task["task_id"]): task for task in revision_tasks}
            graph = {task_id: list(task.get("depends_on_tasks") or [])
                     for task_id, task in by_id.items()}
            for task_id, dependencies in graph.items():
                for dependency in dependencies:
                    if dependency not in by_id:
                        problems.append(
                            f"dangling-task-dep:{feature_id}/{revision}/{task_id}:{dependency}")
            cycle = _find_cycle(graph)
            if cycle:
                problems.append(f"task-cycle:{feature_id}/{revision}:" + "->".join(cycle))
            for task_id, item in by_id.items():
                if item.get("status") == "verified":
                    valid = any(
                        all_evidence.get(ref, {}).get("record_type") == "evidence"
                        and all_evidence.get(ref, {}).get("feature_id") == feature_id
                        and all_evidence.get(ref, {}).get("task_id") == task_id
                        and all_evidence.get(ref, {}).get("scope") == "task"
                        and all_evidence.get(ref, {}).get("result") == "pass"
                        and all_evidence.get(ref, {}).get("tested_sha") == item.get("integration_sha")
                        for ref in item.get("evidence_refs") or [])
                    if not valid:
                        problems.append(
                            f"verified-task-missing-evidence:{feature_id}/{revision}/{task_id}")
    for feature_id, feature in features.items():
        if feature.get("status") == "validated":
            evidence_records = snapshot["feature_evidence_by_feature"].get(feature_id, [])
            current_tasks = [task for task in snapshot["tasks_by_feature"].get(feature_id, [])
                             if task.get("plan_revision") == feature.get("plan_revision")]
            if not current_tasks:
                problems.append(f"validated-feature-missing-current-tasks:{feature_id}")
            incomplete = [str(task.get("task_id")) for task in current_tasks
                          if task.get("status") not in {"verified", "superseded"}]
            if incomplete:
                problems.append(f"validated-feature-incomplete-tasks:{feature_id}:{incomplete}")
            if not any(record.get("scope") == "feature"
                       and record.get("feature_id") == feature_id
                       and record.get("result") == "pass"
                       and record.get("tested_sha") == feature.get("integration_sha")
                       for record in evidence_records):
                problems.append(f"validated-feature-missing-current-evidence:{feature_id}")
        if feature.get("status") == "shipped" and (
                feature.get("review_status") != "pass"
                or feature.get("reviewed_sha") != feature.get("integration_sha")):
            problems.append(f"shipped-feature-missing-current-review:{feature_id}")
        if feature.get("status") == "shipped":
            evidence_records = snapshot["feature_evidence_by_feature"].get(feature_id, [])
            if not any(record.get("scope") == "release"
                       and record.get("feature_id") == feature_id
                       and record.get("result") == "pass"
                       and record.get("tested_sha") == feature.get("integration_sha")
                       for record in evidence_records):
                problems.append(f"shipped-feature-missing-release-evidence:{feature_id}")
    return sorted(set(problems))


def lint(control_root: str | os.PathLike[str]) -> list[str]:
    return lint_snapshot(control_store.load_control_snapshot(control_root))
