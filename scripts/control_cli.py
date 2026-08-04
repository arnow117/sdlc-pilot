#!/usr/bin/env python3
"""Command-line adapter for the SDLC control ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import control
import control_store
from control_store import ConflictError, ControlError, MissingRecordError, SchemaError


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _add_control_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--control-root", required=True)


def _add_transaction(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-control-sha", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--mode", choices=("shared-control", "local-serial"),
                        default="shared-control")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SDLC control ledger")
    sub = parser.add_subparsers(dest="op", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("--repo-root", required=True)
    init_parser.add_argument("--remote", default="origin")
    init_parser.add_argument("--mode", choices=("shared-control", "local-serial"),
                             default="shared-control")
    init_parser.add_argument("--at", required=True)
    for op in ("lint", "readyqueue"):
        child = sub.add_parser(op)
        _add_control_root(child)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--control-root")
    snapshot.add_argument("--repo-root")
    snapshot.add_argument("--ref", default=control_store.CONTROL_BRANCH)
    snapshot.add_argument("--legacy-requirements-root")
    intake_parser = sub.add_parser("intake")
    _add_transaction(intake_parser)
    intake_parser.add_argument("--request-json", required=True)
    intake_parser.add_argument("--leaves-json", required=True)
    intake_parser.add_argument("--at", required=True)
    capture = sub.add_parser("capture-request")
    _add_transaction(capture)
    capture.add_argument("--request-json", required=True)
    capture.add_argument("--at", required=True)
    decompose = sub.add_parser("decompose-request")
    _add_transaction(decompose)
    decompose.add_argument("--request-id", required=True)
    decompose.add_argument("--leaves-json", required=True)
    decompose.add_argument("--at", required=True)
    claim_parser = sub.add_parser("claim")
    _add_transaction(claim_parser)
    for flag in ("leaf-id", "feature-id", "feature-branch", "claimed-base-sha", "owner", "at"):
        claim_parser.add_argument(f"--{flag}", required=True)
    for op in ("release", "release-claim"):
        release_parser = sub.add_parser(op)
        _add_transaction(release_parser)
        for flag in ("leaf-id", "feature-id", "owner", "at", "reason"):
            release_parser.add_argument(f"--{flag}", required=True)
    plan_parser = sub.add_parser("register-plan")
    _add_transaction(plan_parser)
    for flag in ("feature-id", "plan-file", "at"):
        plan_parser.add_argument(f"--{flag}", required=True)
    plan_parser.add_argument("--tasks-json")
    eligibility = sub.add_parser("task-eligibility")
    _add_control_root(eligibility)
    for flag in ("feature-id", "task-id", "feature-head-sha"):
        eligibility.add_argument(f"--{flag}", required=True)
    task_parser = sub.add_parser("task-event")
    _add_transaction(task_parser)
    for flag in ("feature-id", "task-id", "event", "at"):
        task_parser.add_argument(f"--{flag}", required=True)
    for flag in ("owner", "execution-mode", "branch-name", "branch-base-sha",
                 "branch-head-sha", "feature-head-sha", "evidence-ref", "reason"):
        task_parser.add_argument(f"--{flag}")
    integration = sub.add_parser("record-integration")
    _add_transaction(integration)
    for flag in ("feature-id", "task-id", "source-tip-sha", "integration-sha",
                 "merge-method", "at"):
        integration.add_argument(f"--{flag}", required=True)
    evidence = sub.add_parser("record-evidence")
    _add_transaction(evidence)
    for flag in ("feature-id", "task-id", "scope", "result", "tested-sha",
                 "command", "producer", "at"):
        evidence.add_argument(f"--{flag}", required=True)
    evidence.add_argument("--output", default="")
    validate = sub.add_parser("validate-feature")
    _add_transaction(validate)
    for flag in ("feature-id", "current-head-sha", "evidence-ref", "at"):
        validate.add_argument(f"--{flag}", required=True)
    review = sub.add_parser("record-review")
    _add_transaction(review)
    for flag in ("feature-id", "reviewed-sha", "verdict", "reviewer", "at"):
        review.add_argument(f"--{flag}", required=True)
    review.add_argument("--report-ref", action="append", default=[])
    retire_parser = sub.add_parser("retire")
    _add_transaction(retire_parser)
    retire_parser.add_argument("--feature-id", required=True)
    retire_parser.add_argument("--evidence-ref", required=True)
    retire_parser.add_argument("--current-head-sha", required=True)
    retire_parser.add_argument("--at", required=True)
    retire_parser.add_argument("--release-reason", default="shipped")
    return parser


def _mutation_message(args: argparse.Namespace) -> str:
    identity = getattr(args, "feature_id", None) or getattr(args, "request_id", None) or args.op
    return f"{args.op}: {identity}"


def _apply_mutation(args: argparse.Namespace, control_root: Path) -> Any:
    if args.op == "intake":
        leaves_data = _read_json(args.leaves_json)
        leaves = leaves_data.get("leaves", []) if isinstance(leaves_data, dict) else leaves_data
        return control.intake(control_root, request=_read_json(args.request_json),
                              leaves=leaves, at=args.at)
    if args.op == "capture-request":
        return control.capture_request(
            control_root, request=_read_json(args.request_json), at=args.at)
    if args.op == "decompose-request":
        leaves_data = _read_json(args.leaves_json)
        leaves = leaves_data.get("leaves", []) if isinstance(leaves_data, dict) else leaves_data
        return control.decompose_request(
            control_root, request_id=args.request_id, leaves=leaves, at=args.at)
    if args.op == "claim":
        return control.claim(
            control_root, leaf_id=args.leaf_id, feature_id=args.feature_id,
            feature_branch=args.feature_branch, claimed_base_sha=args.claimed_base_sha,
            owner=args.owner, at=args.at)
    if args.op in {"release", "release-claim"}:
        return control.release(
            control_root, leaf_id=args.leaf_id, feature_id=args.feature_id,
            owner=args.owner, at=args.at, reason=args.reason)
    if args.op == "task-event":
        return control.task_event(
            control_root, feature_id=args.feature_id, task_id=args.task_id,
            event=args.event, at=args.at, owner=args.owner,
            execution_mode=args.execution_mode, branch_name=args.branch_name,
            branch_base_sha=args.branch_base_sha, branch_head_sha=args.branch_head_sha,
            feature_head_sha=args.feature_head_sha, evidence_ref=args.evidence_ref,
            reason=args.reason)
    if args.op == "record-integration":
        return control.record_integration(
            control_root, feature_id=args.feature_id, task_id=args.task_id,
            source_tip_sha=args.source_tip_sha, integration_sha=args.integration_sha,
            merge_method=args.merge_method, at=args.at, repo_root=args.repo_root)
    if args.op == "record-evidence":
        return control.record_evidence(
            control_root, feature_id=args.feature_id, task_id=args.task_id,
            scope=args.scope, result=args.result, tested_sha=args.tested_sha,
            command=args.command, output=args.output, producer=args.producer, at=args.at,
            repo_root=args.repo_root)
    if args.op == "validate-feature":
        return control.validate_feature(
            control_root, feature_id=args.feature_id,
            current_head_sha=args.current_head_sha, evidence_ref=args.evidence_ref,
            at=args.at, repo_root=args.repo_root)
    if args.op == "record-review":
        return control.record_review(
            control_root, feature_id=args.feature_id, reviewed_sha=args.reviewed_sha,
            verdict=args.verdict, report_refs=args.report_ref, reviewer=args.reviewer,
            at=args.at, repo_root=args.repo_root)
    if args.op == "retire":
        return control.retire(
            control_root, feature_id=args.feature_id, evidence_ref=args.evidence_ref,
            at=args.at, release_reason=args.release_reason,
            current_head_sha=args.current_head_sha, repo_root=args.repo_root)
    raise SchemaError(f"unsupported mutation: {args.op}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.op == "init":
            value = control_store.GitControlStore(
                args.repo_root, remote=args.remote, mode=args.mode).initialize(at=args.at)
            _emit(value)
            return 0
        if args.op == "lint":
            problems = control.lint(args.control_root)
            _emit({"clean": not problems, "problems": problems})
            return 0 if not problems else 1
        if args.op == "snapshot":
            value = (control.load_snapshot_from_ref(
                args.repo_root, ref=args.ref,
                legacy_requirements_root=args.legacy_requirements_root)
                if args.repo_root else control.load_control_snapshot(
                    args.control_root, legacy_requirements_root=args.legacy_requirements_root))
            _emit(value)
            return 0
        if args.op == "readyqueue":
            value = control.readyqueue(args.control_root)
        elif args.op == "register-plan":
            supplied = None
            if args.tasks_json:
                tasks_data = _read_json(args.tasks_json)
                supplied = tasks_data.get("tasks", []) if isinstance(tasks_data, dict) else tasks_data
            store = control_store.GitControlStore(
                args.repo_root, remote=args.remote, mode=args.mode)
            value = store.register_plan(
                feature_id=args.feature_id,
                plan_text=Path(args.plan_file).read_text(encoding="utf-8"),
                expected_control_sha=args.expected_control_sha, at=args.at,
                supplied_tasks=supplied)
        elif args.op == "task-eligibility":
            value = control.task_eligibility(args.control_root, feature_id=args.feature_id,
                                             task_id=args.task_id,
                                             feature_head_sha=args.feature_head_sha)
        elif args.op in {"intake", "capture-request", "decompose-request", "claim",
                         "release", "release-claim", "task-event", "record-integration",
                         "record-evidence", "validate-feature", "record-review", "retire"}:
            store = control_store.GitControlStore(
                args.repo_root, remote=args.remote, mode=args.mode)
            published = store.mutate(
                lambda root: _apply_mutation(args, root),
                message=_mutation_message(args),
                expected_control_sha=args.expected_control_sha)
            value = dict(published.get("payload") or {})
            value.update({key: published[key] for key in
                          ("pushed", "control_sha", "previous_sha", "mode", "retries")
                          if key in published})
        else:
            raise SchemaError(f"unsupported operation: {args.op}")
        _emit(value)
        return 0
    except ConflictError as exc:
        print(json.dumps({"error": "conflict", "message": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 3
    except MissingRecordError as exc:
        print(json.dumps({"error": "missing", "message": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    except (SchemaError, ControlError, ValueError) as exc:
        print(json.dumps({"error": "invalid", "message": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 1
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(json.dumps({"error": "missing", "message": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
