#!/usr/bin/env python3
"""SDLC control ledger: requirements, claims, tasks, integration, and evidence.

Domain functions operate on an already selected `.sdlc-control` directory. Public
mutations must enter through control_cli + GitControlStore CAS transactions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

import control_store
from control_model import (
    atomic_write_record, derive_task_readiness, find_cycle as _find_cycle,
    load_control_snapshot_from_files, parse_plan_tasks, render_control_record,
)
from control_store import ConflictError, ControlError, MissingRecordError, SchemaError


SCHEMA_VERSION = control_store.SCHEMA_VERSION
REQUEST_STATUSES = {"active", "withdrawn"}
CLAIM_STATUSES = {"active", "released"}
FEATURE_STATUSES = {"active", "validated", "shipped", "abandoned"}
TASK_STATUSES = {
    "waiting", "ready", "claimed", "in_progress", "awaiting_verification",
    "verified", "blocked", "abandoned", "superseded",
}
EXECUTION_MODES = {"undecided", "serial", "task_branch"}
MERGE_STATUSES = {
    "not_applicable", "active", "ready_to_integrate", "integrated", "abandoned",
}
EVIDENCE_RESULTS = {"pass", "fail"}
EVIDENCE_SCOPES = {"task", "feature", "release"}
REVIEW_RESULTS = {"pass", "fail"}
ACTIVE_TASK_STATUSES = {"claimed", "in_progress", "awaiting_verification"}
TERMINAL_TASK_STATUSES = {"verified", "abandoned", "superseded"}
REQUIREMENT_STATUSES = {"captured", "spec'd", "planned", "built", "validated", "shipped"}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
REQUIREMENT_FIELDS = [
    "id", "title", "domain_path", "cross_link", "old_system_ref",
    "new_domain_path", "status", "priority", "depends_on", "risk_level",
    "source_request",
]
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")


# Stable read-only API consumed by board.py.
load_control_snapshot = control_store.load_control_snapshot
load_snapshot_from_ref = control_store.load_snapshot_from_ref


def _require_fields(record: dict[str, Any], fields: list[str], *, label: str) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        raise SchemaError(f"{label}: missing fields {missing}")


def _require_sha(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise SchemaError(f"{field} must be a full Git object id")
    return value


def _require_git_commit(repo_root: str | os.PathLike[str], sha: str, *, field: str) -> str:
    _require_sha(sha, field=field)
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise ConflictError(f"{field} is not an existing commit: {sha}")
    return sha


def _resolve_feature_head(repo_root: str | os.PathLike[str], feature_branch: str) -> str:
    candidates = (f"refs/heads/{feature_branch}", f"refs/remotes/origin/{feature_branch}")
    for ref in candidates:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True, text=True)
        if proc.returncode == 0:
            return proc.stdout.strip()
    raise MissingRecordError(f"feature branch not found: {feature_branch}")


def _require_actual_feature_head(repo_root: str | os.PathLike[str] | None,
                                 feature: dict[str, Any], supplied_sha: str) -> None:
    if not repo_root:
        return
    _require_git_commit(repo_root, supplied_sha, field="feature_head_sha")
    actual = _resolve_feature_head(repo_root, str(feature.get("feature_branch", "")))
    if actual != supplied_sha:
        raise ConflictError(f"feature-head-mismatch: ref={actual} supplied={supplied_sha}")


def _record_path(root: str | os.PathLike[str], *parts: str) -> Path:
    return control_store.safe_record_path(root, *parts)


def _write_existing(root: str | os.PathLike[str], record: dict[str, Any]) -> None:
    path = Path(root) / str(record["_path"])
    control_store.write_record(path, record, body=record.get("_body", ""))


def _body_section(title: str, value: str) -> str:
    return f"## {title}\n{value.strip()}"


def requirement_record(leaf: dict[str, Any]) -> dict[str, Any]:
    _require_fields(leaf, REQUIREMENT_FIELDS, label=f"requirement:{leaf.get('id', '?')}")
    leaf_id = control_store.validate_id(str(leaf["id"]), field="requirement id")
    if leaf["status"] not in REQUIREMENT_STATUSES:
        raise SchemaError(f"requirement:{leaf_id}: invalid status {leaf['status']!r}")
    if leaf["priority"] not in PRIORITY_ORDER:
        raise SchemaError(f"requirement:{leaf_id}: invalid priority {leaf['priority']!r}")
    if not isinstance(leaf["depends_on"], list) or not isinstance(leaf["cross_link"], list):
        raise SchemaError(f"requirement:{leaf_id}: depends_on/cross_link must be lists")
    record = dict(leaf)
    record.update({"schema_version": str(SCHEMA_VERSION), "record_type": "requirement"})
    return record


def _request_record(request: dict[str, Any], at: str) -> dict[str, Any]:
    request_id = control_store.validate_id(str(request.get("request_id", "")), field="request_id")
    title = str(request.get("title", "")).strip()
    if not title:
        raise SchemaError("request title is required")
    status = str(request.get("status", "active"))
    if status not in REQUEST_STATUSES:
        raise SchemaError(f"invalid request status: {status}")
    return {
        "schema_version": str(SCHEMA_VERSION),
        "record_type": "request",
        "request_id": request_id,
        "title": title,
        "status": status,
        "created_at": str(request.get("created_at", at)),
        "updated_at": at,
    }


def intake(control_root: str | os.PathLike[str], *, request: dict[str, Any],
           leaves: list[dict[str, Any]], at: str) -> dict[str, Any]:
    """Write one source request and its independently deliverable leaves."""
    request_rec = _request_record(request, at)
    request_id = request_rec["request_id"]
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_leaf in leaves:
        leaf = dict(raw_leaf)
        leaf.setdefault("source_request", request_id)
        if leaf["source_request"] != request_id:
            raise SchemaError(f"leaf {leaf.get('id')} points to a different source_request")
        record = requirement_record(leaf)
        record["updated"] = at
        if record["id"] in seen:
            raise SchemaError(f"duplicate requirement id in intake: {record['id']}")
        seen.add(record["id"])
        normalized.append(record)
    if not normalized:
        raise SchemaError("intake requires at least one requirement leaf")

    snapshot = load_control_snapshot(control_root)
    existing_request = snapshot["requests_by_id"].get(request_id)
    if existing_request:
        raise ConflictError(f"request-id-in-use: {request_id}")
    existing_ids = set(snapshot["requirements_by_id"])
    collisions = sorted(seen & existing_ids)
    if collisions:
        raise ConflictError(f"requirement-id-in-use: {collisions}")
    known = existing_ids | seen
    graph = {leaf_id: list(item.get("depends_on") or [])
             for leaf_id, item in snapshot["requirements_by_id"].items()}
    graph.update({record["id"]: list(record.get("depends_on") or [])
                  for record in normalized})
    missing = sorted({dep for deps in graph.values() for dep in deps if dep not in known})
    if missing:
        raise SchemaError(f"requirement dependencies are missing: {missing}")
    cycle = _find_cycle(graph)
    if cycle:
        raise SchemaError("requirement dependency cycle: " + " -> ".join(cycle))

    root = Path(control_root)
    prepared_paths: list[tuple[dict[str, Any], Path]] = []
    for record in normalized:
        domain_parts = str(record["domain_path"]).split("/")
        if len(domain_parts) < 2 or any(part in ("", ".", "..") for part in domain_parts):
            raise SchemaError(f"requirement:{record['id']}: domain_path needs at least two parts")
        path = _record_path(root, "requirements", *domain_parts, f"{record['id']}.md")
        prepared_paths.append((record, path))
    request_path = _record_path(root, "requests", f"{request_id}.md")
    request_body = _body_section("Raw request", str(request.get("body", "")))
    control_store.write_record(request_path, request_rec, body=request_body)
    for record, path in prepared_paths:
        control_store.write_record(path, record, body=str(record.get("body", "")))
    return {"request_id": request_id, "leaf_ids": sorted(seen), "written": len(normalized)}


def _requirements_ready(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = snapshot["requirements_by_id"]
    claims = snapshot["claims_by_leaf"]
    ready: list[dict[str, Any]] = []
    for leaf in requirements.values():
        if leaf.get("status") == "shipped":
            continue
        claim = claims.get(leaf.get("id"))
        if claim and claim.get("status") == "active":
            continue
        dependencies = leaf.get("depends_on") or []
        if all(requirements.get(dep, {}).get("status") == "shipped" for dep in dependencies):
            ready.append(leaf)
    ready.sort(key=lambda leaf: (PRIORITY_ORDER.get(str(leaf.get("priority")), 99),
                                 str(leaf.get("id", ""))))
    return ready


def readyqueue(control_root: str | os.PathLike[str]) -> list[dict[str, Any]]:
    snapshot = load_control_snapshot(control_root)
    return [{
        "leaf_id": leaf.get("id"),
        "title": leaf.get("title"),
        "priority": leaf.get("priority"),
        "deps_resolved": True,
        "old_system_ref": leaf.get("old_system_ref"),
        "risk_level": leaf.get("risk_level"),
        "status": leaf.get("status"),
    } for leaf in _requirements_ready(snapshot)]


def claim(control_root: str | os.PathLike[str], *, leaf_id: str, feature_id: str,
          feature_branch: str, claimed_base_sha: str, owner: str, at: str) -> dict[str, Any]:
    """Prepare an active claim; caller must fast-forward push it before starting work."""
    control_store.validate_id(leaf_id, field="leaf_id")
    control_store.validate_id(feature_id, field="feature_id")
    _require_sha(claimed_base_sha, field="claimed_base_sha")
    if not feature_branch or "\n" in feature_branch:
        raise SchemaError("feature_branch is required and must be one line")
    snapshot = load_control_snapshot(control_root)
    leaf = snapshot["requirements_by_id"].get(leaf_id)
    if not leaf:
        raise MissingRecordError(f"requirement not found: {leaf_id}")
    existing_claim = snapshot["claims_by_leaf"].get(leaf_id)
    if existing_claim and existing_claim.get("status") == "active":
        same_identity = all((
            existing_claim.get("feature_id") == feature_id,
            existing_claim.get("feature_branch") == feature_branch,
            existing_claim.get("claimed_base_sha") == claimed_base_sha,
            existing_claim.get("owner") == owner,
        ))
        if same_identity:
            return dict(existing_claim, prepared=False, idempotent=True)
        raise ConflictError(
            "active-claim: "
            f"leaf={leaf_id} owner={existing_claim.get('owner')} "
            f"feature={existing_claim.get('feature_id')} "
            f"branch={existing_claim.get('feature_branch')}")
    existing_feature = snapshot["features_by_id"].get(feature_id)
    if existing_feature:
        raise ConflictError(
            f"feature-id-in-use: {feature_id} leaf={existing_feature.get('leaf_id')}")
    if leaf_id not in {item["leaf_id"] for item in readyqueue(control_root)}:
        raise ConflictError(f"requirement-not-ready: {leaf_id}")
    request_id = str(leaf.get("source_request", ""))
    claim_record = {
        "schema_version": str(SCHEMA_VERSION), "record_type": "claim",
        "leaf_id": leaf_id, "feature_id": feature_id, "feature_branch": feature_branch,
        "claimed_base_sha": claimed_base_sha, "owner": owner, "status": "active",
        "claimed_at": at, "released_at": "(none)", "release_reason": "(none)",
    }
    feature_record = {
        "schema_version": str(SCHEMA_VERSION), "record_type": "feature",
        "feature_id": feature_id, "leaf_id": leaf_id, "source_request": request_id,
        "feature_branch": feature_branch, "claimed_base_sha": claimed_base_sha,
        "integration_sha": claimed_base_sha, "owner": owner, "status": "active",
        "plan_ref": "(none)", "plan_revision": "(none)",
        "feature_evidence_refs": [], "created_at": at, "updated_at": at,
        "review_status": "pending", "reviewed_sha": "(none)",
        "reviewer": "(none)", "review_report_refs": [], "reviewed_at": "(none)",
    }
    # All validation occurs before either file is written. In a Git transaction the
    # disposable worktree is discarded if a later step fails.
    control_store.write_record(_record_path(control_root, "claims", f"{leaf_id}.md"),
                               claim_record)
    control_store.write_record(_record_path(control_root, "features", f"{feature_id}.md"),
                               feature_record)
    return dict(claim_record, prepared=True, idempotent=False)


def release(control_root: str | os.PathLike[str], *, leaf_id: str, feature_id: str,
            owner: str, at: str, reason: str) -> dict[str, Any]:
    snapshot = load_control_snapshot(control_root)
    claim_record = snapshot["claims_by_leaf"].get(leaf_id)
    if not claim_record:
        raise MissingRecordError(f"claim not found: {leaf_id}")
    if claim_record.get("feature_id") != feature_id:
        raise ConflictError(
            f"claim-feature-mismatch: expected={claim_record.get('feature_id')} got={feature_id}")
    if claim_record.get("owner") != owner:
        raise ConflictError(
            f"claim-owner-mismatch: expected={claim_record.get('owner')} got={owner}")
    if claim_record.get("status") == "released":
        return claim_record
    claim_record.update({"status": "released", "released_at": at, "release_reason": reason})
    _write_existing(control_root, claim_record)
    feature = snapshot["features_by_id"].get(feature_id)
    if feature and feature.get("status") not in {"shipped", "abandoned"}:
        feature.update({"status": "abandoned", "updated_at": at})
        _write_existing(control_root, feature)
    return claim_record


def _normalize_write_entry(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SchemaError(f"invalid write_set entry: {value!r}")
    directory = value.endswith("/")
    path = PurePosixPath(value.rstrip("/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise SchemaError(f"write_set must be repo-relative without traversal: {value!r}")
    if any(char in value for char in ("*", "?", "[", "]")):
        raise SchemaError(f"write_set glob syntax is unsupported: {value!r}")
    normalized = str(path)
    return normalized + "/" if directory else normalized


def normalize_write_set(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not values:
        raise SchemaError("write_set must be a non-empty inline list")
    return sorted(set(_normalize_write_entry(value) for value in values))


def _write_entries_overlap(left: str, right: str) -> bool:
    left_dir, right_dir = left.endswith("/"), right.endswith("/")
    left_base, right_base = left.rstrip("/"), right.rstrip("/")
    if left_base == right_base:
        return True
    if left_dir and right_base.startswith(left_base + "/"):
        return True
    if right_dir and left_base.startswith(right_base + "/"):
        return True
    return False


def write_sets_overlap(left: list[str], right: list[str]) -> bool:
    return any(_write_entries_overlap(a, b) for a in left for b in right)


def _task_record(feature_id: str, plan_ref: str, plan_revision: str,
                 raw: dict[str, Any], *, at: str, task_ids: set[str]) -> dict[str, Any]:
    required = [
        "task_id", "requirements", "depends_on_tasks", "write_set", "interface_owner",
        "interfaces_fixed", "runtime_isolated", "read_first", "action", "acceptance_criteria",
    ]
    _require_fields(raw, required, label=f"task:{raw.get('task_id', '?')}")
    task_id = control_store.validate_id(str(raw["task_id"]), field="task_id")
    for list_field in ("requirements", "depends_on_tasks", "read_first"):
        if not isinstance(raw[list_field], list):
            raise SchemaError(f"task:{task_id}: {list_field} must be a list")
    for bool_field in ("interfaces_fixed", "runtime_isolated"):
        if not isinstance(raw[bool_field], bool):
            raise SchemaError(f"task:{task_id}: {bool_field} must be a boolean")
    unknown = sorted(set(raw["depends_on_tasks"]) - task_ids)
    if unknown:
        raise SchemaError(f"task:{task_id}: missing dependencies {unknown}")
    status = "ready" if not raw["depends_on_tasks"] else "waiting"
    record = {
        "schema_version": str(SCHEMA_VERSION), "record_type": "task",
        "feature_id": feature_id, "task_id": task_id,
        "plan_ref": plan_ref, "plan_revision": plan_revision,
        "requirements": list(raw["requirements"]),
        "depends_on_tasks": list(raw["depends_on_tasks"]),
        "write_set": normalize_write_set(raw["write_set"]),
        "interface_owner": str(raw["interface_owner"]),
        "interfaces_fixed": raw["interfaces_fixed"],
        "runtime_isolated": raw["runtime_isolated"],
        "read_first": list(raw["read_first"]),
        "status": status, "execution_mode": "undecided",
        "branch_name": "(none)", "branch_base_sha": "(none)",
        "branch_head_sha": "(none)", "integrated_source_sha": "(none)",
        "merge_method": "(none)", "integration_sha": "(none)",
        "merge_status": "not_applicable", "owner": "(none)",
        "evidence_refs": [], "blocked_reason": "(none)",
        "created_at": at, "updated_at": at,
    }
    record["_body"] = "\n\n".join((
        _body_section("Action", str(raw["action"])),
        _body_section("Acceptance criteria", str(raw["acceptance_criteria"])),
    ))
    return record


def plan_content_id(plan_text: str) -> str:
    return hashlib.sha256(plan_text.encode("utf-8")).hexdigest()[:16]


def store_plan_artifact(control_root: str | os.PathLike[str], *, feature_id: str,
                        plan_ref: str, plan_text: str) -> dict[str, Any]:
    control_store.validate_id(feature_id, field="feature_id")
    expected = f"features/{feature_id}/plans/{plan_content_id(plan_text)}.md"
    if plan_ref != expected:
        raise SchemaError(f"plan_ref must be {expected}")
    path = _record_path(control_root, *PurePosixPath(plan_ref).parts)
    written = control_store.write_text_atomic(path, plan_text, immutable=True)
    return {"feature_id": feature_id, "plan_ref": plan_ref, "written": written}


def register_plan(control_root: str | os.PathLike[str], *, feature_id: str,
                  plan_ref: str, plan_revision: str, plan_text: str,
                  tasks: list[dict[str, Any]], at: str,
                  require_git_revision: bool = False) -> dict[str, Any]:
    _require_sha(plan_revision, field="plan_revision")
    expected_ref = f"features/{feature_id}/plans/{plan_content_id(plan_text)}.md"
    if plan_ref != expected_ref:
        raise SchemaError(f"plan_ref must be {expected_ref}")
    plan_path = _record_path(control_root, *PurePosixPath(plan_ref).parts)
    if not plan_path.is_file() or plan_path.read_text(encoding="utf-8") != plan_text:
        raise ConflictError("approved plan artifact is missing or has different bytes")
    if require_git_revision:
        worktree = str(Path(control_root).parent)
        ancestor = subprocess.run(
            ["git", "-C", worktree, "merge-base", "--is-ancestor", plan_revision, "HEAD"],
            capture_output=True, text=True)
        artifact = subprocess.run(
            ["git", "-C", worktree, "show",
             f"{plan_revision}:{control_store.CONTROL_DIR}/{plan_ref}"],
            capture_output=True, text=True)
        if ancestor.returncode != 0 or artifact.returncode != 0 or artifact.stdout != plan_text:
            raise ConflictError(
                f"plan_revision {plan_revision} does not contain the approved plan bytes")
    snapshot = load_control_snapshot(control_root)
    feature = snapshot["features_by_id"].get(feature_id)
    if not feature:
        raise MissingRecordError(f"feature not found: {feature_id}")
    if feature.get("status") not in {"active", "validated"}:
        raise ConflictError(f"feature cannot be planned: {feature_id}/{feature.get('status')}")
    task_ids = [str(item.get("task_id", "")) for item in tasks]
    if len(set(task_ids)) != len(task_ids) or not all(task_ids):
        raise SchemaError("task ids must be present and unique")
    ids = set(task_ids)
    graph = {str(item["task_id"]): list(item.get("depends_on_tasks") or []) for item in tasks}
    missing = sorted({dep for deps in graph.values() for dep in deps if dep not in ids})
    if missing:
        raise SchemaError(f"task dependencies are missing: {missing}")
    cycle = _find_cycle(graph)
    if cycle:
        raise SchemaError(f"task dependency cycle: {' -> '.join(cycle)}")
    records = [_task_record(feature_id, plan_ref, plan_revision, raw, at=at, task_ids=ids)
               for raw in tasks]
    current_revision = str(feature.get("plan_revision", "(none)"))
    if current_revision == plan_revision:
        current = [task for task in snapshot["tasks_by_feature"].get(feature_id, [])
                   if task.get("plan_revision") == plan_revision]
        if current and {str(task["task_id"]) for task in current} == ids:
            return {"feature_id": feature_id, "plan_ref": plan_ref,
                    "plan_revision": plan_revision, "task_ids": sorted(task_ids),
                    "registered": 0, "idempotent": True}
        raise ConflictError(f"plan revision already registered with different tasks: {feature_id}")
    for prior in snapshot["tasks_by_feature"].get(feature_id, []):
        if prior.get("plan_revision") != current_revision:
            continue
        if prior.get("status") not in TERMINAL_TASK_STATUSES:
            prior.update({"status": "superseded", "merge_status": "abandoned",
                          "blocked_reason": "superseded by replan", "updated_at": at})
            _write_existing(control_root, prior)
    for record in records:
        path = _record_path(
            control_root, "tasks", feature_id, plan_revision, f"{record['task_id']}.md")
        control_store.write_record(path, record, body=record["_body"], immutable=True)
    feature.update({
        "plan_ref": plan_ref, "plan_revision": plan_revision, "updated_at": at,
        "status": "active", "review_status": "pending", "reviewed_sha": "(none)",
        "reviewer": "(none)", "review_report_refs": [], "reviewed_at": "(none)",
    })
    _write_existing(control_root, feature)
    return {"feature_id": feature_id, "plan_ref": plan_ref, "plan_revision": plan_revision,
            "task_ids": sorted(task_ids), "registered": len(records), "idempotent": False}


def _tasks_by_id(snapshot: dict[str, Any], feature_id: str) -> dict[str, dict[str, Any]]:
    feature = snapshot["features_by_id"].get(feature_id, {})
    revision = feature.get("plan_revision")
    return {str(task["task_id"]): task
            for task in snapshot["tasks_by_feature"].get(feature_id, [])
            if task.get("plan_revision") == revision}


def _dependencies_verified(task: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> bool:
    return all(tasks.get(dep, {}).get("status") == "verified"
               for dep in (task.get("depends_on_tasks") or []))


def _refresh_readiness(control_root: str | os.PathLike[str], feature_id: str, at: str) -> None:
    snapshot = load_control_snapshot(control_root)
    tasks = _tasks_by_id(snapshot, feature_id)
    for item in tasks.values():
        if item.get("status") != "waiting":
            continue
        if _dependencies_verified(item, tasks):
            item.update({"status": "ready", "updated_at": at})
            _write_existing(control_root, item)


def task_eligibility(control_root: str | os.PathLike[str], *, feature_id: str,
                     task_id: str, feature_head_sha: str) -> dict[str, Any]:
    _require_sha(feature_head_sha, field="feature_head_sha")
    snapshot = load_control_snapshot(control_root)
    feature = snapshot["features_by_id"].get(feature_id)
    tasks = _tasks_by_id(snapshot, feature_id)
    item = tasks.get(task_id)
    if not feature or not item:
        raise MissingRecordError(f"feature/task not found: {feature_id}/{task_id}")
    reasons: list[str] = []
    if feature.get("status") != "active":
        reasons.append("feature-not-active")
    if feature.get("integration_sha") != feature_head_sha:
        reasons.append("feature-head-mismatch")
    if item.get("status") != "ready":
        reasons.append(f"task-not-ready:{item.get('status')}")
    if not _dependencies_verified(item, tasks):
        reasons.append("dependencies-unverified")
    if item.get("interfaces_fixed") is not True:
        reasons.append("interfaces-not-fixed")
    if item.get("runtime_isolated") is not True:
        reasons.append("runtime-not-isolated")
    if item.get("interface_owner") not in tasks:
        reasons.append("invalid-interface-owner")
    active = [task for task in tasks.values()
              if task.get("task_id") != task_id and task.get("status") in ACTIVE_TASK_STATUSES]
    serial = [task for task in active if task.get("execution_mode") == "serial"]
    if serial:
        reasons.append(f"serial-task-active:{serial[0]['task_id']}")
    branches = [task for task in active if task.get("execution_mode") == "task_branch"]
    if len(branches) >= 3:
        reasons.append("active-branch-limit")
    for active_task in branches:
        if write_sets_overlap(item.get("write_set") or [], active_task.get("write_set") or []):
            reasons.append(f"write-set-overlap:{active_task['task_id']}")
    reasons = list(dict.fromkeys(reasons))
    return {
        "feature_id": feature_id, "task_id": task_id, "eligible": not reasons,
        "reasons": reasons,
        "recommended_mode": "task_branch" if not reasons else (
            "wait" if any(reason.startswith(("task-not-ready", "dependencies-", "feature-"))
                          for reason in reasons) else "serial"),
        "active_task_branches": len(branches), "max_active_task_branches": 3,
    }


def _load_evidence_ref(control_root: str | os.PathLike[str], evidence_ref: str) -> dict[str, Any]:
    parts = PurePosixPath(evidence_ref).parts
    if not parts or parts[0] != "evidence" or any(part in ("", ".", "..") for part in parts):
        raise SchemaError(f"invalid evidence_ref: {evidence_ref}")
    path = _record_path(control_root, *parts)
    if not path.is_file():
        raise MissingRecordError(f"evidence not found: {evidence_ref}")
    record = control_store.read_record(path)
    record["_path"] = evidence_ref
    return record


def task_event(control_root: str | os.PathLike[str], *, feature_id: str, task_id: str,
               event: str, at: str, owner: str | None = None,
               execution_mode: str | None = None, branch_name: str | None = None,
               branch_base_sha: str | None = None, branch_head_sha: str | None = None,
               feature_head_sha: str | None = None, evidence_ref: str | None = None,
               reason: str | None = None) -> dict[str, Any]:
    snapshot = load_control_snapshot(control_root)
    tasks = _tasks_by_id(snapshot, feature_id)
    item = tasks.get(task_id)
    feature = snapshot["features_by_id"].get(feature_id)
    if not item or not feature:
        raise MissingRecordError(f"task not found: {feature_id}/{task_id}")
    status = str(item.get("status"))

    if event == "claim":
        if status != "ready":
            raise ConflictError(f"invalid-task-transition: {status} -> claimed")
        if execution_mode not in {"serial", "task_branch"}:
            raise SchemaError("claim requires execution_mode=serial|task_branch")
        if not feature_head_sha:
            raise SchemaError("claim requires feature_head_sha")
        _require_sha(feature_head_sha, field="feature_head_sha")
        if feature.get("integration_sha") != feature_head_sha:
            raise ConflictError(
                f"feature-head-mismatch: recorded={feature.get('integration_sha')} "
                f"actual={feature_head_sha}")
        active = [task for task in tasks.values()
                  if task.get("task_id") != task_id and task.get("status") in ACTIVE_TASK_STATUSES]
        if execution_mode == "serial":
            if active:
                raise ConflictError(f"serial-task-requires-exclusive-feature:{active[0]['task_id']}")
            merge_status = "not_applicable"
            branch_value = "(none)"
            base_value = feature_head_sha
        else:
            eligibility = task_eligibility(
                control_root, feature_id=feature_id, task_id=task_id,
                feature_head_sha=feature_head_sha)
            if not eligibility["eligible"]:
                raise ConflictError("task-branch-ineligible: " + ",".join(eligibility["reasons"]))
            if not branch_name or not branch_base_sha:
                raise SchemaError("task_branch claim requires branch_name and branch_base_sha")
            _require_sha(branch_base_sha, field="branch_base_sha")
            if branch_base_sha != feature_head_sha:
                raise ConflictError("task branch must start at current feature integration head")
            merge_status = "active"
            branch_value = branch_name
            base_value = branch_base_sha
        item.update({
            "status": "claimed", "execution_mode": execution_mode,
            "branch_name": branch_value, "branch_base_sha": base_value,
            "merge_status": merge_status, "owner": owner or "(none)",
            "blocked_reason": "(none)", "updated_at": at,
        })
    elif event == "start":
        if status != "claimed":
            raise ConflictError(f"invalid-task-transition: {status} -> in_progress")
        item.update({"status": "in_progress", "updated_at": at})
    elif event == "submit":
        if status != "in_progress":
            raise ConflictError(f"invalid-task-transition: {status} -> awaiting_verification")
        if not branch_head_sha:
            raise SchemaError("submit requires branch_head_sha")
        _require_sha(branch_head_sha, field="branch_head_sha")
        item.update({"status": "awaiting_verification", "branch_head_sha": branch_head_sha,
                     "merge_status": "ready_to_integrate", "updated_at": at})
    elif event == "verify":
        if status != "awaiting_verification":
            raise ConflictError(f"invalid-task-transition: {status} -> verified")
        if not evidence_ref:
            raise SchemaError("verify requires evidence_ref")
        evidence = _load_evidence_ref(control_root, evidence_ref)
        if (evidence.get("record_type") != "evidence"
                or evidence.get("scope") != "task"
                or evidence.get("feature_id") != feature_id
                or evidence.get("task_id") != task_id):
            raise ConflictError("evidence does not belong to this task")
        if evidence.get("result") != "pass":
            raise ConflictError("task verification requires passing evidence")
        if evidence.get("tested_sha") != item.get("integration_sha"):
            raise ConflictError(
                f"evidence-sha-mismatch: tested={evidence.get('tested_sha')} "
                f"integration={item.get('integration_sha')}")
        refs = list(item.get("evidence_refs") or [])
        if evidence_ref not in refs:
            refs.append(evidence_ref)
        item.update({"status": "verified", "evidence_refs": refs, "updated_at": at})
    elif event == "block":
        if status in TERMINAL_TASK_STATUSES:
            raise ConflictError(f"terminal task cannot be blocked: {status}")
        item.update({"status": "blocked", "blocked_reason": reason or "unspecified",
                     "updated_at": at})
    elif event == "resume":
        if status != "blocked":
            raise ConflictError(f"invalid-task-transition: {status} -> resume")
        next_status = "ready" if _dependencies_verified(item, tasks) else "waiting"
        item.update({"status": next_status, "blocked_reason": "(none)", "updated_at": at})
    elif event in {"abandon", "supersede"}:
        if status in TERMINAL_TASK_STATUSES:
            raise ConflictError(f"terminal task cannot transition: {status} -> {event}")
        target = "abandoned" if event == "abandon" else "superseded"
        item.update({"status": target, "merge_status": "abandoned",
                     "blocked_reason": reason or "(none)", "updated_at": at})
    elif event == "retry":
        if status != "awaiting_verification":
            raise ConflictError(f"invalid-task-transition: {status} -> in_progress")
        item.update({"status": "in_progress", "merge_status": "active", "updated_at": at})
    else:
        raise SchemaError(f"unknown task event: {event}")
    _write_existing(control_root, item)
    if item.get("status") == "verified":
        _refresh_readiness(control_root, feature_id, at)
    return item


def record_integration(control_root: str | os.PathLike[str], *, feature_id: str,
                       task_id: str, source_tip_sha: str, integration_sha: str,
                       merge_method: str, at: str,
                       repo_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    _require_sha(source_tip_sha, field="source_tip_sha")
    _require_sha(integration_sha, field="integration_sha")
    if merge_method not in {"merge", "rebase", "squash", "serial"}:
        raise SchemaError(f"invalid merge_method: {merge_method}")
    snapshot = load_control_snapshot(control_root)
    item = _tasks_by_id(snapshot, feature_id).get(task_id)
    feature = snapshot["features_by_id"].get(feature_id)
    if not item or not feature:
        raise MissingRecordError(f"feature/task not found: {feature_id}/{task_id}")
    if repo_root:
        _require_git_commit(repo_root, source_tip_sha, field="source_tip_sha")
        _require_actual_feature_head(repo_root, feature, integration_sha)
    if item.get("status") != "awaiting_verification":
        raise ConflictError(f"task is not awaiting verification: {item.get('status')}")
    if item.get("branch_head_sha") != source_tip_sha:
        raise ConflictError(
            f"integration-source-mismatch: recorded={item.get('branch_head_sha')} got={source_tip_sha}")
    item.update({
        "integrated_source_sha": source_tip_sha, "merge_method": merge_method,
        "integration_sha": integration_sha, "merge_status": "integrated", "updated_at": at,
    })
    feature.update({
        "integration_sha": integration_sha, "updated_at": at, "status": "active",
        "review_status": "pending", "reviewed_sha": "(none)", "reviewer": "(none)",
        "review_report_refs": [], "reviewed_at": "(none)",
    })
    _write_existing(control_root, item)
    _write_existing(control_root, feature)
    return item


def record_evidence(control_root: str | os.PathLike[str], *, feature_id: str,
                    task_id: str, scope: str, result: str, tested_sha: str,
                    command: str, output: str, producer: str, at: str,
                    repo_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    _require_sha(tested_sha, field="tested_sha")
    if scope not in EVIDENCE_SCOPES or result not in EVIDENCE_RESULTS:
        raise SchemaError(f"invalid evidence scope/result: {scope}/{result}")
    if scope in {"feature", "release"} and task_id != "_feature":
        raise SchemaError(f"{scope} evidence must use task_id=_feature")
    if scope == "task" and task_id == "_feature":
        raise SchemaError("task evidence needs a real task_id")
    snapshot = load_control_snapshot(control_root)
    feature = snapshot["features_by_id"].get(feature_id)
    if not feature:
        raise MissingRecordError(f"feature not found: {feature_id}")
    if repo_root:
        _require_git_commit(repo_root, tested_sha, field="tested_sha")
    if scope == "task" and task_id not in _tasks_by_id(snapshot, feature_id):
        raise MissingRecordError(f"task not found: {feature_id}/{task_id}")
    canonical = json.dumps({
        "feature_id": feature_id, "task_id": task_id, "scope": scope, "result": result,
        "tested_sha": tested_sha, "command": command, "output": output,
        "producer": producer, "created_at": at,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    evidence_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    record = {
        "schema_version": str(SCHEMA_VERSION), "record_type": "evidence",
        "evidence_id": evidence_id, "feature_id": feature_id, "task_id": task_id,
        "scope": scope, "result": result, "tested_sha": tested_sha,
        "command": " ".join(command.split()), "created_at": at, "producer": producer,
    }
    body = "\n\n".join((_body_section("Command", command),
                           _body_section("Output summary", output)))
    path = _record_path(
        control_root, "evidence", feature_id, task_id, tested_sha, f"{evidence_id}.md")
    control_store.write_record(path, record, body=body, immutable=True)
    evidence_ref = str(path.relative_to(control_root))
    if scope == "task":
        item = _tasks_by_id(snapshot, feature_id)[task_id]
        refs = list(item.get("evidence_refs") or [])
        if evidence_ref not in refs:
            refs.append(evidence_ref)
            item.update({"evidence_refs": refs, "updated_at": at})
            _write_existing(control_root, item)
    else:
        refs = list(feature.get("feature_evidence_refs") or [])
        if evidence_ref not in refs:
            refs.append(evidence_ref)
            feature.update({"feature_evidence_refs": refs, "updated_at": at})
            _write_existing(control_root, feature)
    return dict(record, evidence_ref=evidence_ref)


def compute_freshness(task_record: dict[str, Any], *, current_head_sha: str,
                      changed_paths: list[str] | None = None,
                      repo_root: str | os.PathLike[str] | None = None) -> str:
    integration_sha = task_record.get("integration_sha")
    if not integration_sha or integration_sha == "(none)":
        return "missing"
    if integration_sha == current_head_sha:
        return "fresh"
    if changed_paths is None and repo_root:
        if control_store.git_is_ancestor(repo_root, str(integration_sha), current_head_sha) is not True:
            return "unknown"
        try:
            changed_paths = control_store.git_changed_paths(
                repo_root, str(integration_sha), current_head_sha)
        except ControlError:
            return "unknown"
    if changed_paths is None:
        return "unknown"
    write_set = task_record.get("write_set") or []
    for changed in changed_paths:
        normalized = _normalize_write_entry(changed)
        if any(_write_entries_overlap(entry, normalized) for entry in write_set):
            return "stale"
    return "fresh"


def validate_feature(control_root: str | os.PathLike[str], *, feature_id: str,
                     current_head_sha: str, evidence_ref: str, at: str,
                     repo_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    _require_sha(current_head_sha, field="current_head_sha")
    snapshot = load_control_snapshot(control_root)
    feature = snapshot["features_by_id"].get(feature_id)
    if not feature:
        raise MissingRecordError(f"feature not found: {feature_id}")
    _require_actual_feature_head(repo_root, feature, current_head_sha)
    if feature.get("integration_sha") != current_head_sha:
        raise ConflictError(
            f"feature-head-mismatch: recorded={feature.get('integration_sha')} actual={current_head_sha}")
    current_tasks = [task for task in snapshot["tasks_by_feature"].get(feature_id, [])
                     if task.get("plan_revision") == feature.get("plan_revision")]
    if feature.get("plan_revision") == "(none)" or not current_tasks:
        raise ConflictError("feature validation requires a registered current plan with tasks")
    incomplete = [task["task_id"] for task in current_tasks
                  if task.get("status") not in {"verified", "superseded"}]
    if incomplete:
        raise ConflictError(f"feature has incomplete tasks: {incomplete}")
    evidence = _load_evidence_ref(control_root, evidence_ref)
    if (evidence.get("scope") != "feature" or evidence.get("feature_id") != feature_id
            or evidence.get("result") != "pass"):
        raise ConflictError("feature validation requires passing feature evidence")
    if evidence.get("tested_sha") != current_head_sha:
        raise ConflictError(
            f"feature-evidence-stale: tested={evidence.get('tested_sha')} head={current_head_sha}")
    refs = list(feature.get("feature_evidence_refs") or [])
    if evidence_ref not in refs:
        refs.append(evidence_ref)
    feature.update({"status": "validated", "feature_evidence_refs": refs, "updated_at": at})
    _write_existing(control_root, feature)
    leaf = snapshot["requirements_by_id"].get(feature.get("leaf_id"))
    if leaf:
        leaf.update({"status": "validated", "updated": at})
        _write_existing(control_root, leaf)
    return feature


def record_review(control_root: str | os.PathLike[str], *, feature_id: str,
                  reviewed_sha: str, verdict: str, report_refs: list[str],
                  reviewer: str, at: str,
                  repo_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    _require_sha(reviewed_sha, field="reviewed_sha")
    if verdict not in REVIEW_RESULTS:
        raise SchemaError(f"invalid review verdict: {verdict}")
    if not isinstance(report_refs, list) or not all(
            isinstance(ref, str) and ref and "\n" not in ref for ref in report_refs):
        raise SchemaError("report_refs must be a list of non-empty one-line paths")
    snapshot = load_control_snapshot(control_root)
    feature = snapshot["features_by_id"].get(feature_id)
    if not feature:
        raise MissingRecordError(f"feature not found: {feature_id}")
    if feature.get("status") != "validated":
        raise ConflictError(f"review requires validated feature: {feature.get('status')}")
    if feature.get("integration_sha") != reviewed_sha:
        raise ConflictError(
            f"review-sha-mismatch: integration={feature.get('integration_sha')} reviewed={reviewed_sha}")
    _require_actual_feature_head(repo_root, feature, reviewed_sha)
    feature.update({
        "review_status": verdict, "reviewed_sha": reviewed_sha,
        "reviewer": reviewer, "review_report_refs": report_refs, "reviewed_at": at,
        "updated_at": at,
    })
    _write_existing(control_root, feature)
    return feature


def retire(control_root: str | os.PathLike[str], *, feature_id: str,
           evidence_ref: str | None, at: str,
           release_reason: str = "shipped", current_head_sha: str | None = None,
           repo_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    snapshot = load_control_snapshot(control_root)
    feature = snapshot["features_by_id"].get(feature_id)
    if not feature:
        raise MissingRecordError(f"feature not found: {feature_id}")
    if feature.get("status") == "shipped":
        return {"feature_id": feature_id, "feature_status": "shipped",
                "leaf_status": "shipped", "claim_status": "released", "idempotent": True}
    if feature.get("status") != "validated":
        raise ConflictError(f"feature must be validated before retire: {feature.get('status')}")
    actual_head = current_head_sha or str(feature.get("integration_sha"))
    _require_sha(actual_head, field="current_head_sha")
    _require_actual_feature_head(repo_root, feature, actual_head)
    if actual_head != feature.get("integration_sha"):
        raise ConflictError(
            f"feature-head-mismatch: recorded={feature.get('integration_sha')} actual={actual_head}")
    if (feature.get("review_status") != "pass"
            or feature.get("reviewed_sha") != feature.get("integration_sha")):
        raise ConflictError("retire requires a passing durable review at current integration SHA")
    if not evidence_ref:
        raise SchemaError("retire requires passing release evidence")
    evidence = _load_evidence_ref(control_root, evidence_ref)
    if (evidence.get("scope") != "release" or evidence.get("feature_id") != feature_id
            or evidence.get("result") != "pass"):
        raise ConflictError("retire requires passing release evidence")
    if evidence.get("tested_sha") != feature.get("integration_sha"):
        raise ConflictError(
            f"release-evidence-stale: tested={evidence.get('tested_sha')} "
            f"integration={feature.get('integration_sha')}")
    leaf_id = str(feature.get("leaf_id"))
    leaf = snapshot["requirements_by_id"].get(leaf_id)
    claim_record = snapshot["claims_by_leaf"].get(leaf_id)
    if not leaf or not claim_record or claim_record.get("feature_id") != feature_id:
        raise ConflictError("feature/leaf/claim linkage is incomplete")
    feature.update({"status": "shipped", "updated_at": at})
    leaf.update({"status": "shipped", "updated": at})
    claim_record.update({"status": "released", "released_at": at,
                         "release_reason": release_reason})
    _write_existing(control_root, feature)
    _write_existing(control_root, leaf)
    _write_existing(control_root, claim_record)
    return {"feature_id": feature_id, "feature_status": "shipped",
            "leaf_status": "shipped", "claim_status": "released", "idempotent": False}


def lint(control_root: str | os.PathLike[str]) -> list[str]:
    """Validate a complete snapshot; kept here as the stable public API."""
    from control_lint import lint as lint_snapshot
    return lint_snapshot(control_root)


# Stable protocol names used by skills and external adapters.
parse_control_record = control_store.parse_record
evaluate_branch_eligibility = task_eligibility
apply_task_event = task_event
record_evidence_immutable = record_evidence
compute_task_freshness = compute_freshness
validate_feature_from_evidence = validate_feature
retire_feature = retire


def capture_request(control_root: str | os.PathLike[str], *, request: dict[str, Any],
                    at: str) -> dict[str, Any]:
    from control_intake import capture_request as capture
    return capture(control_root, request=request, at=at)


def decompose_request(control_root: str | os.PathLike[str], *, request_id: str,
                      leaves: list[dict[str, Any]], at: str) -> dict[str, Any]:
    from control_intake import decompose_request as decompose
    return decompose(control_root, request_id=request_id, leaves=leaves, at=at)


def lint_control_snapshot(snapshot: dict[str, Any]) -> list[str]:
    from control_lint import lint_snapshot
    return lint_snapshot(snapshot)


def verify_task_from_evidence(control_root: str | os.PathLike[str], *,
                              feature_id: str, task_id: str,
                              evidence_ref: str, at: str) -> dict[str, Any]:
    return task_event(control_root, feature_id=feature_id, task_id=task_id,
                      event="verify", evidence_ref=evidence_ref, at=at)


def build_parser() -> Any:
    from control_cli import build_parser as build_cli_parser
    return build_cli_parser()


def main(argv: list[str] | None = None) -> int:
    from control_cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
