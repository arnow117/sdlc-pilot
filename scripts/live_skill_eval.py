#!/usr/bin/env python3
"""Provider-neutral repeated runner for the SDLC Skill behavior dataset.

The harness deliberately does not know how to call a model provider.  A caller
supplies a runner command that receives one canonical JSON request on stdin and
returns one canonical JSON response on stdout.  This keeps provider credentials
and product-specific agent launch flags outside the repository while preserving
the inputs, outputs and configuration needed to replay an evaluation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Mapping, Sequence

import eval_skill_behavior as fixture_eval
import skill_baseline
import skill_eval_adapter


RUN_FORMAT = "sdlc-skill-behavior-run-v1"
REPORT_FORMAT = "sdlc-skill-behavior-live-report-v1"
CALIBRATION_FORMAT = "sdlc-skill-evaluator-calibration-v1"
RUNNER_RESULT_KEYS = frozenset({"output", "tool_events", "manifests", "cost", "execution"})
EVALUATOR_RESULT_KEYS = frozenset({"scores", "passed", "critical_failures", "notes", "execution"})
SCORE_KEYS = (
    "lifecycle_method_fit",
    "contract_semantic_sufficiency",
    "role_evidence",
    "context_efficiency",
)
SCORE_WEIGHTS = {
    "lifecycle_method_fit": 0.30,
    "contract_semantic_sufficiency": 0.30,
    "role_evidence": 0.25,
    "context_efficiency": 0.15,
}
REQUIRED_EXECUTION_FIELDS = frozenset({
    "provider", "model", "model_version", "temperature", "max_tokens",
    "tool_versions", "evaluator_model", "evaluator_version",
})
CALIBRATION_KEYS = frozenset({
    "calibration_format", "evaluator", "double_human_review_count", "pass_fail_agreement", "review_record_refs",
})


class LiveEvaluationError(RuntimeError):
    """A runner/evaluator response is incomplete or cannot be trusted."""


def _canonical_bytes(value: object) -> bytes:
    return fixture_eval.canonical_bytes(value)


def _sha256(value: bytes) -> str:
    return fixture_eval.sha256_bytes(value)


def _strict_json(value: bytes, label: str) -> dict[str, object]:
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveEvaluationError(f"invalid-{label}-json") from exc
    if not isinstance(parsed, dict):
        raise LiveEvaluationError(f"invalid-{label}-object")
    return parsed


def _run_command(command: str, payload: Mapping[str, object], *, timeout_seconds: int,
                 label: str) -> dict[str, object]:
    if not isinstance(command, str) or not command.strip():
        raise LiveEvaluationError(f"missing-{label}-command")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise LiveEvaluationError(f"invalid-{label}-command") from exc
    if not argv:
        raise LiveEvaluationError(f"missing-{label}-command")
    try:
        completed = subprocess.run(
            argv,
            input=_canonical_bytes(dict(payload)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except OSError as exc:
        raise LiveEvaluationError(f"cannot-start-{label}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LiveEvaluationError(f"{label}-timeout") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise LiveEvaluationError(f"{label}-failed:{completed.returncode}:{detail}")
    return _strict_json(completed.stdout, label)


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveEvaluationError(f"invalid-{label}")
    return value


def _normalize_execution(value: object, *, expected_runs: int, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LiveEvaluationError(f"invalid-{label}-execution")
    if set(value) != REQUIRED_EXECUTION_FIELDS | {"variant_runs"}:
        raise LiveEvaluationError(f"invalid-{label}-execution-keys")
    result: dict[str, object] = {}
    for key in ("provider", "model", "model_version", "evaluator_model", "evaluator_version"):
        result[key] = _nonempty_text(value[key], f"{label}-execution-{key}")
    temperature = value["temperature"]
    if not isinstance(temperature, (str, int, float)) or isinstance(temperature, bool):
        raise LiveEvaluationError(f"invalid-{label}-execution-temperature")
    result["temperature"] = temperature
    max_tokens = value["max_tokens"]
    if not isinstance(max_tokens, (str, int)) or isinstance(max_tokens, bool):
        raise LiveEvaluationError(f"invalid-{label}-execution-max-tokens")
    result["max_tokens"] = max_tokens
    versions = value["tool_versions"]
    if not isinstance(versions, dict) or not versions:
        raise LiveEvaluationError(f"invalid-{label}-execution-tool-versions")
    result["tool_versions"] = {
        _nonempty_text(name, f"{label}-execution-tool-name"):
        _nonempty_text(version, f"{label}-execution-tool-version")
        for name, version in versions.items()
    }
    if value["variant_runs"] != expected_runs:
        raise LiveEvaluationError(f"{label}-execution-run-count-mismatch")
    result["variant_runs"] = expected_runs
    return result


def _normalize_cost(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LiveEvaluationError(f"invalid-{label}-cost")
    usd = value.get("usd")
    if not isinstance(usd, (int, float)) or isinstance(usd, bool) or usd < 0:
        raise LiveEvaluationError(f"invalid-{label}-cost-usd")
    return {str(key): value[key] for key in sorted(value)}


def _load_calibration(path: str | os.PathLike[str] | None) -> tuple[dict[str, object], bytes] | None:
    """Load the required human calibration evidence for semantic judging.

    Live LLM scores are useful only after their pass/fail interpretation has
    been calibrated against at least 20 independently double-reviewed cases.
    The report holds references, not reviewer credentials or model secrets.
    """
    if path is None:
        return None
    target = Path(path)
    try:
        raw = target.read_bytes()
        value = _strict_json(raw, "calibration")
    except OSError as exc:
        raise LiveEvaluationError("cannot-read-evaluator-calibration") from exc
    if set(value) != CALIBRATION_KEYS or value.get("calibration_format") != CALIBRATION_FORMAT:
        raise LiveEvaluationError("invalid-evaluator-calibration")
    evaluator = value["evaluator"]
    if not isinstance(evaluator, dict) or set(evaluator) != {"provider", "model", "model_version", "evaluator_version"}:
        raise LiveEvaluationError("invalid-evaluator-calibration-evaluator")
    normalized_evaluator = {
        key: _nonempty_text(evaluator[key], f"calibration-evaluator-{key}")
        for key in sorted(evaluator)
    }
    count = value["double_human_review_count"]
    agreement = value["pass_fail_agreement"]
    refs = value["review_record_refs"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 20:
        raise LiveEvaluationError("evaluator-calibration-needs-20-double-human-reviews")
    if (not isinstance(agreement, (int, float)) or isinstance(agreement, bool)
            or agreement < 0 or agreement > 1 or agreement < 0.85):
        raise LiveEvaluationError("evaluator-calibration-agreement-below-85pct")
    if not isinstance(refs, list) or len(refs) < count or any(not isinstance(item, str) or not item for item in refs):
        raise LiveEvaluationError("invalid-evaluator-calibration-review-record-refs")
    return ({
        "calibration_format": CALIBRATION_FORMAT,
        "evaluator": normalized_evaluator,
        "double_human_review_count": count,
        "pass_fail_agreement": agreement,
        "review_record_refs": sorted(set(refs)),
    }, raw)


def _normalize_runner_result(value: Mapping[str, object], *, expected_runs: int) -> dict[str, object]:
    if set(value) != RUNNER_RESULT_KEYS:
        raise LiveEvaluationError("invalid-runner-result-keys")
    try:
        output = fixture_eval._normalize_output(value["output"])
    except fixture_eval.EvaluationError as exc:
        raise LiveEvaluationError(f"invalid-runner-output:{exc}") from exc
    tool_events = value["tool_events"]
    manifests = value["manifests"]
    if not isinstance(tool_events, list):
        raise LiveEvaluationError("invalid-runner-tool-events")
    if not isinstance(manifests, dict) or not manifests:
        raise LiveEvaluationError("invalid-runner-manifests")
    return {
        "output": output,
        "tool_events": tool_events,
        "manifests": manifests,
        "cost": _normalize_cost(value["cost"], "runner"),
        "execution": _normalize_execution(value["execution"], expected_runs=expected_runs, label="runner"),
    }


def _normalize_evaluator_result(value: Mapping[str, object], *, expected_runs: int) -> dict[str, object]:
    if set(value) != EVALUATOR_RESULT_KEYS:
        raise LiveEvaluationError("invalid-evaluator-result-keys")
    scores = value["scores"]
    if not isinstance(scores, dict) or set(scores) != set(SCORE_KEYS):
        raise LiveEvaluationError("invalid-evaluator-scores")
    normalized_scores: dict[str, int] = {}
    for key in SCORE_KEYS:
        score = scores[key]
        if score not in {1, 3, 5}:
            raise LiveEvaluationError(f"invalid-evaluator-score:{key}")
        normalized_scores[key] = int(score)
    if not isinstance(value["passed"], bool):
        raise LiveEvaluationError("invalid-evaluator-passed")
    critical = value["critical_failures"]
    notes = value["notes"]
    if (not isinstance(critical, list) or any(not isinstance(item, str) or not item for item in critical)
            or not isinstance(notes, list) or any(not isinstance(item, str) or not item for item in notes)):
        raise LiveEvaluationError("invalid-evaluator-notes")
    return {
        "scores": normalized_scores,
        "passed": value["passed"],
        "critical_failures": sorted(set(critical)),
        "notes": list(notes),
        "execution": _normalize_execution(value["execution"], expected_runs=expected_runs, label="evaluator"),
    }


def _require_calibrated_evaluator(
    semantic: Mapping[str, object], calibration: Mapping[str, object],
) -> None:
    """Reject scores from a provider/model tuple other than the reviewed one."""
    calibrated = calibration.get("evaluator")
    execution = semantic.get("execution")
    if not isinstance(calibrated, Mapping) or not isinstance(execution, Mapping):
        raise LiveEvaluationError("invalid-evaluator-calibration-identity")
    expected = {
        "provider": calibrated.get("provider"),
        "model": calibrated.get("model"),
        "model_version": calibrated.get("model_version"),
        "evaluator_version": calibrated.get("evaluator_version"),
    }
    actual = {
        "provider": execution.get("provider"),
        "model": execution.get("model"),
        "model_version": execution.get("model_version"),
        "evaluator_version": execution.get("evaluator_version"),
    }
    if actual != expected:
        raise LiveEvaluationError("evaluator-calibration-identity-mismatch")


def _git_commit(repo: Path, ref: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LiveEvaluationError(f"invalid-source-ref:{ref}") from exc
    value = completed.stdout.decode("ascii", errors="strict").strip()
    if len(value) not in {40, 64} or any(char not in "0123456789abcdef" for char in value):
        raise LiveEvaluationError(f"invalid-source-commit:{ref}")
    return value


def _load_inputs(repo: Path, dataset_path: str, baseline_path: str) -> tuple[
        list[dict[str, object]], bytes, dict[str, object], bytes, str, str]:
    dataset_target = (repo / dataset_path).resolve()
    baseline_target = (repo / baseline_path).resolve()
    try:
        dataset_target.relative_to(repo)
        baseline_target.relative_to(repo)
    except ValueError as exc:
        raise LiveEvaluationError("evaluation-input-outside-repository") from exc
    try:
        cases, dataset_bytes = fixture_eval.load_dataset(dataset_target)
        baseline_raw = baseline_target.read_bytes()
        baseline = json.loads(baseline_raw.decode("utf-8"))
        skill_baseline.check_manifest(repo, baseline_target)
    except (OSError, ValueError, json.JSONDecodeError, skill_baseline.BaselineError,
            fixture_eval.EvaluationError) as exc:
        raise LiveEvaluationError(f"invalid-evaluation-input:{exc}") from exc
    if not isinstance(baseline, dict) or not isinstance(baseline.get("source_commit"), str):
        raise LiveEvaluationError("invalid-baseline-manifest")
    return (cases, dataset_bytes, baseline, baseline_raw,
            dataset_target.relative_to(repo).as_posix(), baseline_target.relative_to(repo).as_posix())


def _run_input(case: Mapping[str, object], *, variant: str, source_ref: str, run_index: int,
               planned_runs: int, dataset_path: str, dataset_sha256: str, baseline_path: str,
               baseline_sha256: str) -> dict[str, object]:
    return {
        "run_format": RUN_FORMAT,
        "variant": variant,
        "source_ref": source_ref,
        "run_index": run_index,
        "planned_runs": planned_runs,
        "dataset_contract": {"path": dataset_path, "sha256": dataset_sha256},
        "baseline_contract": {"path": baseline_path, "sha256": baseline_sha256},
        "case": dict(case),
        "invocation": skill_eval_adapter.build_invocation(case, variant=variant),
    }


def _mechanical(case: Mapping[str, object], output: Mapping[str, object], *, variant: str) -> dict[str, object]:
    """Compare a run with the variant's reviewed identifier contract."""
    try:
        expected = skill_eval_adapter.expected_case(case, variant=variant)
    except skill_eval_adapter.SkillEvaluationAdapterError as exc:
        raise LiveEvaluationError(f"invalid-mechanical-expectation:{exc}") from exc
    return fixture_eval._evaluate_case(expected, output)


def _record_id(record: Mapping[str, object]) -> str:
    return _sha256(_canonical_bytes(record))


def _aggregate(records: Sequence[Mapping[str, object]], *, runs: int, mechanical_only: bool) -> dict[str, object]:
    candidate = [record for record in records if record["variant"] == "candidate"]
    baseline = [record for record in records if record["variant"] == "baseline"]
    if not candidate or not baseline:
        raise LiveEvaluationError("missing-evaluation-variant")
    critical = sorted({
        item for record in candidate for item in record.get("critical_failures", [])
        if isinstance(item, str)
    })
    mechanical_total = len(candidate)
    mechanical_passed = sum(record["mechanical"]["verdict"] == "PASS" for record in candidate)
    per_case: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in candidate:
        per_case[str(record["case_id"])].append(record)
    per_case_rates = {
        case_id: sum(item["mechanical"]["verdict"] == "PASS" for item in values) / len(values)
        for case_id, values in sorted(per_case.items())
    }
    summary: dict[str, object] = {
        "critical_failures": critical,
        "mechanical": {
            "passed": mechanical_passed,
            "total": mechanical_total,
            "rate": mechanical_passed / mechanical_total,
            "per_case_rate": per_case_rates,
        },
        "verdict": "PASS",
        "reasons": [],
    }
    reasons: list[str] = []
    if critical:
        reasons.append("critical-failure")
    if mechanical_passed != mechanical_total:
        reasons.append("mechanical-assertion-failed")
    if any(rate < 0.80 for rate in per_case_rates.values()):
        reasons.append("candidate-case-rate-below-80pct")
    if mechanical_passed / mechanical_total < 0.90:
        reasons.append("candidate-total-rate-below-90pct")
    if not mechanical_only:
        judged = [record for record in candidate if record.get("semantic") is not None]
        baseline_judged = [record for record in baseline if record.get("semantic") is not None]
        if len(judged) != len(candidate) or len(baseline_judged) != len(baseline):
            raise LiveEvaluationError("missing-semantic-results")
        dimensions = {
            key: sum(record["semantic"]["scores"][key] for record in judged) / len(judged)
            for key in SCORE_KEYS
        }
        weighted = sum(dimensions[key] * SCORE_WEIGHTS[key] for key in SCORE_KEYS)
        candidate_rate = sum(record["semantic"]["passed"] for record in judged) / len(judged)
        baseline_rate = sum(record["semantic"]["passed"] for record in baseline_judged) / len(baseline_judged)
        summary["semantic"] = {
            "candidate_pass_rate": candidate_rate,
            "baseline_pass_rate": baseline_rate,
            "delta": candidate_rate - baseline_rate,
            "weighted_score": weighted,
            "dimensions": dimensions,
        }
        if candidate_rate < 0.90:
            reasons.append("semantic-total-rate-below-90pct")
        if weighted < 4.2:
            reasons.append("semantic-weighted-score-below-4.2")
        if any(value < 3.5 for value in dimensions.values()):
            reasons.append("semantic-dimension-below-3.5")
        if candidate_rate - baseline_rate < -0.05:
            reasons.append("semantic-regression-over-5pp")
    summary["reasons"] = reasons
    summary["verdict"] = "PASS" if not reasons else "FAIL"
    return summary


def evaluate_live(
    repo: str | os.PathLike[str], *, dataset_path: str, baseline_path: str, runner_cmd: str,
    evaluator_cmd: str | None, runs: int, mechanical_only: bool, timeout_seconds: int,
    calibration_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    if not isinstance(runs, int) or runs < 1:
        raise LiveEvaluationError("invalid-run-count")
    if not mechanical_only and not evaluator_cmd:
        raise LiveEvaluationError("missing-evaluator-command")
    calibration = _load_calibration(calibration_path)
    if not mechanical_only and calibration is None:
        raise LiveEvaluationError("evaluator-calibration-required-for-semantic-evaluation")
    repository = Path(repo).resolve()
    if not repository.is_dir():
        raise LiveEvaluationError("invalid-repository")
    cases, dataset_bytes, baseline, baseline_bytes, dataset_relative, baseline_relative = _load_inputs(
        repository, dataset_path, baseline_path)
    baseline_commit = _git_commit(repository, str(baseline["source_commit"]))
    candidate_commit = _git_commit(repository, "HEAD")
    dataset_sha256 = _sha256(dataset_bytes)
    baseline_sha256 = _sha256(baseline_bytes)
    records: list[dict[str, object]] = []
    for variant, source_ref in (("baseline", baseline_commit), ("candidate", candidate_commit)):
        for case in cases:
            for run_index in range(runs):
                request = _run_input(
                    case, variant=variant, source_ref=source_ref, run_index=run_index,
                    planned_runs=runs,
                    dataset_path=dataset_relative, dataset_sha256=dataset_sha256,
                    baseline_path=baseline_relative, baseline_sha256=baseline_sha256,
                )
                runner = _normalize_runner_result(
                    _run_command(runner_cmd, request, timeout_seconds=timeout_seconds, label="runner"),
                    expected_runs=runs,
                )
                mechanical = _mechanical(case, runner["output"], variant=variant)
                record: dict[str, object] = {
                    "variant": variant,
                    "source_ref": source_ref,
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "run_index": run_index,
                    "request": request,
                    "runner": runner,
                    "mechanical": mechanical,
                    "critical_failures": [],
                    "semantic": None,
                }
                if not mechanical_only:
                    evaluator_request = {
                        "evaluation_format": "sdlc-skill-behavior-evaluator-input-v1",
                        "case": dict(case),
                        "run": record,
                        "rubric": {
                            "weights": SCORE_WEIGHTS,
                            "score_values": [1, 3, 5],
                            "critical_failures": [
                                "forged-approval-or-evidence", "missing-required-obligation",
                                "delivery-mutates-product-contract", "invalid-lifecycle-transition",
                                "stale-context-or-evidence",
                            ],
                        },
                    }
                    semantic = _normalize_evaluator_result(
                        _run_command(evaluator_cmd or "", evaluator_request,
                                     timeout_seconds=timeout_seconds, label="evaluator"),
                        expected_runs=runs,
                    )
                    assert calibration is not None
                    _require_calibrated_evaluator(semantic, calibration[0])
                    record["semantic"] = semantic
                    record["critical_failures"] = semantic["critical_failures"]
                record["record_id"] = _record_id(record)
                records.append(record)
    summary = _aggregate(records, runs=runs, mechanical_only=mechanical_only)
    preimage: dict[str, object] = {
        "report_format": REPORT_FORMAT,
        "inputs": {
            "dataset": {"path": dataset_relative, "sha256": dataset_sha256, "case_count": len(cases)},
            "baseline": {"path": baseline_relative, "sha256": baseline_sha256, "source_commit": baseline_commit},
            "candidate": {"source_commit": candidate_commit},
            "evaluator_calibration": (
                None if calibration is None else {
                    "sha256": _sha256(calibration[1]),
                    "evaluator": calibration[0]["evaluator"],
                    "double_human_review_count": calibration[0]["double_human_review_count"],
                    "pass_fail_agreement": calibration[0]["pass_fail_agreement"],
                }
            ),
        },
        "run_config": {
            "runs": runs,
            "mechanical_only": mechanical_only,
            "runner_command_sha256": _sha256(runner_cmd.encode("utf-8")),
            "evaluator_command_sha256": None if evaluator_cmd is None else _sha256(evaluator_cmd.encode("utf-8")),
        },
        "records": records,
        "summary": summary,
    }
    return {**preimage, "run_id": _sha256(_canonical_bytes(preimage))}


def write_report(path: str | os.PathLike[str], report: Mapping[str, object]) -> None:
    if not isinstance(report.get("run_id"), str):
        raise LiveEvaluationError("missing-report-id")
    preimage = {key: value for key, value in report.items() if key != "run_id"}
    if report["run_id"] != _sha256(_canonical_bytes(preimage)):
        raise LiveEvaluationError("report-content-address-mismatch")
    fixture_eval.write_report(path, report)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--dataset", default="evals/dual-lifecycle-skill-v1.jsonl")
    parser.add_argument("--baseline-manifest", default="evals/baselines/legacy-0.19.2.json")
    parser.add_argument("--runner-cmd", required=True)
    parser.add_argument("--evaluator-cmd")
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--mechanical-only", action="store_true")
    parser.add_argument("--calibration-report")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--report", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = evaluate_live(
            args.repo, dataset_path=args.dataset, baseline_path=args.baseline_manifest,
            runner_cmd=args.runner_cmd, evaluator_cmd=args.evaluator_cmd, runs=args.runs,
            mechanical_only=args.mechanical_only, timeout_seconds=args.timeout_seconds,
            calibration_path=args.calibration_report,
        )
        write_report(args.report, report)
    except LiveEvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_canonical_bytes({"run_id": report["run_id"], "summary": report["summary"]}))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
