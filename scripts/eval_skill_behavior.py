#!/usr/bin/env python3
"""Evaluate dual-lifecycle Skill behavior in deterministic or live mode.

``fixture`` is an offline contract test.  ``live`` delegates to the repeated,
provider-neutral harness and requires explicit runner/evaluator commands; this
module itself never chooses a provider or launches one implicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import Mapping, Sequence

import skill_baseline


FIXTURE_FORMAT = "sdlc-skill-behavior-fixture-v1"
REPORT_FORMAT = "sdlc-skill-behavior-report-v1"
DEFAULT_DATASET = "evals/dual-lifecycle-skill-v1.jsonl"
DEFAULT_BASELINE = "evals/baselines/legacy-0.19.2.json"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_CONTRACT_KEYS = frozenset({"path", "sha256"})
_FIXTURE_KEYS = frozenset({
    "fixture_format",
    "mode",
    "dataset_contract",
    "baseline_contract",
    "policy_bindings",
    "run_config",
    "outputs",
})
_POLICY_BINDING_KEYS = frozenset({"policy_id", "sha256"})
_RUN_CONFIG_KEYS = frozenset({"source_model_run_config", "execution"})
_SOURCE_MODEL_CONFIG_KEYS = frozenset({"required_binding_fields", "variant_runs"})
_OFFLINE_REQUIRED_BINDINGS = frozenset({
    "provider", "model", "model_version", "temperature", "max_tokens", "tool_versions",
    "evaluator_model", "evaluator_version",
})
_OUTPUT_KEYS = frozenset({
    "case_id", "route", "modules", "roles", "obligations", "artifacts", "actions", "transition",
})
_TRANSITION_KEYS = frozenset({"decision", "route"})


class EvaluationError(ValueError):
    """A fixture, data binding, or evaluation mode is unsafe or invalid."""


def canonical_bytes(value: object) -> bytes:
    """Return the repository's stable JSON byte representation."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_json_constant(value: str) -> object:
    raise EvaluationError(f"invalid-json-constant:{value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError(f"duplicate-json-key:{key}")
        result[key] = value
    return result


def _strict_json_loads(value: str, label: str) -> object:
    try:
        return json.loads(
            value,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except EvaluationError:
        raise
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"invalid-{label}-json") from exc


def _read_json_object(path: str | os.PathLike[str], label: str) -> tuple[dict[str, object], bytes]:
    target = Path(path)
    try:
        raw = target.read_bytes()
        decoded = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"cannot-read-{label}:{target}") from exc
    value = _strict_json_loads(decoded, label)
    if not isinstance(value, dict):
        raise EvaluationError(f"{label}-must-be-an-object")
    return value, raw


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvaluationError(f"invalid-{label}")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EvaluationError(f"invalid-{label}")
    return value


def _string_list(value: object, label: str, *, nonempty: bool = True) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list) or (nonempty and not value):
        raise EvaluationError(f"invalid-{label}")
    if any(not isinstance(item, str) or not item for item in value):
        raise EvaluationError(f"invalid-{label}")
    if len(set(value)) != len(value):
        raise EvaluationError(f"duplicate-{label}")
    return list(value)


def _safe_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvaluationError(f"invalid-{label}-path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value:
        raise EvaluationError(f"unsafe-{label}-path:{value}")
    normalized = path.as_posix()
    if normalized != value:
        raise EvaluationError(f"noncanonical-{label}-path:{value}")
    return normalized


def _repo_path(repo: Path, value: str | os.PathLike[str], label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (repo / _safe_relative_path(str(value), label)).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError as exc:
        raise EvaluationError(f"{label}-path-outside-repository:{value}") from exc
    return candidate


def _relative_to_repo(repo: Path, value: Path, label: str) -> str:
    try:
        return value.resolve().relative_to(repo).as_posix()
    except ValueError as exc:
        raise EvaluationError(f"{label}-path-outside-repository:{value}") from exc


def load_dataset(path: str | os.PathLike[str]) -> tuple[list[dict[str, object]], bytes]:
    """Strictly parse and validate the existing v1 JSONL dataset."""
    target = Path(path)
    try:
        raw = target.read_bytes()
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"cannot-read-dataset:{target}") from exc
    if not lines or any(not line.strip() for line in lines):
        raise EvaluationError("dataset-has-blank-line")
    for line_number, line in enumerate(lines, start=1):
        value = _strict_json_loads(line, f"dataset-line-{line_number}")
        if not isinstance(value, dict):
            raise EvaluationError(f"dataset-line-must-be-an-object:{line_number}")
    try:
        cases = skill_baseline.load_cases(target)
    except skill_baseline.BaselineError as exc:
        raise EvaluationError(f"dataset-schema-invalid:{exc}") from exc
    return cases, raw


def _normalize_contract(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != _CONTRACT_KEYS:
        raise EvaluationError(f"invalid-{label}-contract")
    return {
        "path": _safe_relative_path(value["path"], label),
        "sha256": _require_sha256(value["sha256"], f"{label}-contract-sha256"),
    }


def _load_baseline(
    repo: Path,
    baseline_path: Path,
    *,
    dataset_relative_path: str,
    dataset_sha256: str,
) -> tuple[dict[str, object], bytes]:
    baseline, raw = _read_json_object(baseline_path, "baseline")
    try:
        skill_baseline.check_manifest(repo, baseline_path)
    except skill_baseline.BaselineError as exc:
        raise EvaluationError(f"baseline-manifest-invalid:{exc}") from exc
    if baseline.get("baseline_format") != skill_baseline.BASELINE_FORMAT:
        raise EvaluationError("unsupported-baseline-format")
    contract = _normalize_contract(baseline.get("dataset_contract"), "baseline-dataset")
    if contract != {"path": dataset_relative_path, "sha256": dataset_sha256}:
        raise EvaluationError("baseline-dataset-contract-mismatch")
    source_commit = baseline.get("source_commit")
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        raise EvaluationError("invalid-baseline-source-commit")
    return baseline, raw


def _baseline_file_hashes(baseline: Mapping[str, object]) -> set[str]:
    files = baseline.get("files")
    if not isinstance(files, list) or not files:
        raise EvaluationError("invalid-baseline-files")
    hashes: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "utf8_bytes"}:
            raise EvaluationError("invalid-baseline-file")
        _safe_relative_path(item["path"], "baseline-file")
        hashes.add(_require_sha256(item["sha256"], "baseline-file-sha256"))
    return hashes


def _validate_case_bindings(
    repo: Path,
    cases: Sequence[Mapping[str, object]],
    baseline: Mapping[str, object],
) -> None:
    """Bind every dataset row to the baseline commit and checked-in fixture bytes."""
    source_commit = str(baseline["source_commit"])
    file_hashes = _baseline_file_hashes(baseline)
    for case in cases:
        case_id = str(case["case_id"])
        snapshot = case["repository_snapshot"]
        policy = case["policy_input"]
        if not isinstance(snapshot, Mapping) or not isinstance(policy, Mapping):
            raise EvaluationError(f"invalid-validated-case:{case_id}")
        if case["legacy_source_ref"] != source_commit:
            raise EvaluationError(f"case-legacy-source-mismatch:{case_id}")
        if snapshot["source_ref"] != source_commit or snapshot["base_sha"] != source_commit:
            raise EvaluationError(f"case-snapshot-source-mismatch:{case_id}")
        policy_sha = _require_sha256(policy["sha256"], f"case-policy-sha256:{case_id}")
        if policy_sha not in file_hashes:
            raise EvaluationError(f"case-policy-not-bound-by-baseline:{case_id}")

        fixture_root = _repo_path(repo, str(case["repository_fixture"]), f"case-fixture:{case_id}")
        expected = {
            "PROFILE.md": snapshot["profile_sha256"],
            "STATE.md": snapshot["state_sha256"],
            "control-snapshot.json": snapshot["control_sha256"],
        }
        for filename, digest in expected.items():
            target = (fixture_root / filename).resolve()
            try:
                target.relative_to(fixture_root)
                actual = sha256_bytes(target.read_bytes())
            except (OSError, ValueError) as exc:
                raise EvaluationError(f"cannot-read-case-fixture:{case_id}:{filename}") from exc
            if actual != _require_sha256(digest, f"case-fixture-sha256:{case_id}:{filename}"):
                raise EvaluationError(f"case-fixture-hash-mismatch:{case_id}:{filename}")


def _normalize_source_model_config(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _SOURCE_MODEL_CONFIG_KEYS:
        raise EvaluationError(f"invalid-{label}")
    fields = sorted(_string_list(value["required_binding_fields"], f"{label}-required-binding-fields"))
    runs = value["variant_runs"]
    if not isinstance(runs, int) or isinstance(runs, bool) or runs < 1:
        raise EvaluationError(f"invalid-{label}-variant-runs")
    return {"required_binding_fields": fields, "variant_runs": runs}


def _dataset_model_config(cases: Sequence[Mapping[str, object]]) -> dict[str, object]:
    configs = {
        canonical_bytes(_normalize_source_model_config(case["model_run_config"], "dataset-model-run-config"))
        for case in cases
    }
    if len(configs) != 1:
        raise EvaluationError("dataset-model-run-config-must-be-uniform")
    return json.loads(next(iter(configs)).decode("utf-8"))


def _normalize_execution(value: object, required_fields: Sequence[str]) -> dict[str, object]:
    if set(required_fields) != _OFFLINE_REQUIRED_BINDINGS:
        raise EvaluationError("unsupported-fixture-binding-fields")
    if not isinstance(value, dict):
        raise EvaluationError("invalid-fixture-execution")
    expected_keys = set(required_fields) | {"variant_runs"}
    if set(value) != expected_keys:
        raise EvaluationError("invalid-fixture-execution-keys")
    if value["provider"] != "fixture" or value["model"] != "none" or value["model_version"] != "none":
        raise EvaluationError("remote-model-mode-is-not-supported")
    if (not isinstance(value["temperature"], (int, float))
            or isinstance(value["temperature"], bool)
            or value["temperature"] != 0):
        raise EvaluationError("fixture-execution-temperature-must-be-zero")
    if (not isinstance(value["max_tokens"], int)
            or isinstance(value["max_tokens"], bool)
            or value["max_tokens"] != 0):
        raise EvaluationError("fixture-execution-max-tokens-must-be-zero")
    if (not isinstance(value["variant_runs"], int)
            or isinstance(value["variant_runs"], bool)
            or value["variant_runs"] != 0):
        raise EvaluationError("fixture-execution-variant-runs-must-be-zero")
    if value["evaluator_model"] != "deterministic-fixture":
        raise EvaluationError("remote-model-mode-is-not-supported")
    evaluator_version = _require_text(value["evaluator_version"], "fixture-evaluator-version")
    tool_versions = value["tool_versions"]
    if not isinstance(tool_versions, dict) or not tool_versions:
        raise EvaluationError("invalid-fixture-tool-versions")
    normalized_versions: dict[str, str] = {}
    for name, version in tool_versions.items():
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise EvaluationError("invalid-fixture-tool-versions")
        normalized_versions[name] = version
    return {
        "provider": "fixture",
        "model": "none",
        "model_version": "none",
        "temperature": 0,
        "max_tokens": 0,
        "tool_versions": dict(sorted(normalized_versions.items())),
        "evaluator_model": "deterministic-fixture",
        "evaluator_version": evaluator_version,
        "variant_runs": 0,
    }


def _normalize_policy_bindings(value: object, expected: Mapping[str, str]) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise EvaluationError("invalid-policy-bindings")
    bindings: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != _POLICY_BINDING_KEYS:
            raise EvaluationError("invalid-policy-binding")
        policy_id = _require_text(item["policy_id"], "policy-binding-id")
        if policy_id in bindings:
            raise EvaluationError(f"duplicate-policy-binding:{policy_id}")
        bindings[policy_id] = _require_sha256(item["sha256"], "policy-binding-sha256")
    if bindings != dict(expected):
        raise EvaluationError("policy-binding-mismatch")
    return [
        {"policy_id": policy_id, "sha256": bindings[policy_id]}
        for policy_id in sorted(bindings)
    ]


def _dataset_policy_bindings(cases: Sequence[Mapping[str, object]]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for case in cases:
        case_id = str(case["case_id"])
        policy = case["policy_input"]
        if not isinstance(policy, Mapping):
            raise EvaluationError(f"invalid-validated-case-policy:{case_id}")
        policy_id = _require_text(policy["policy_id"], f"case-policy-id:{case_id}")
        digest = _require_sha256(policy["sha256"], f"case-policy-sha256:{case_id}")
        existing = bindings.get(policy_id)
        if existing is not None and existing != digest:
            raise EvaluationError(f"dataset-policy-binding-conflict:{policy_id}")
        bindings[policy_id] = digest
    return bindings


def _normalize_transition(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _TRANSITION_KEYS:
        raise EvaluationError(f"invalid-{label}-transition")
    decision = value["decision"]
    if decision not in {"route", "reject"}:
        raise EvaluationError(f"invalid-{label}-transition-decision")
    return {
        "decision": decision,
        "route": _string_list(value["route"], f"{label}-transition-route"),
    }


def _normalize_output(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _OUTPUT_KEYS:
        raise EvaluationError("invalid-fixture-output-keys")
    case_id = _require_text(value["case_id"], "fixture-output-case-id")
    return {
        "case_id": case_id,
        "route": _string_list(value["route"], f"fixture-output-route:{case_id}"),
        "modules": _string_list(value["modules"], f"fixture-output-modules:{case_id}"),
        "roles": _string_list(value["roles"], f"fixture-output-roles:{case_id}"),
        "obligations": _string_list(value["obligations"], f"fixture-output-obligations:{case_id}"),
        "artifacts": _string_list(value["artifacts"], f"fixture-output-artifacts:{case_id}"),
        "actions": _string_list(value["actions"], f"fixture-output-actions:{case_id}", nonempty=False),
        "transition": _normalize_transition(value["transition"], f"fixture-output:{case_id}"),
    }


def _load_fixture(
    path: str | os.PathLike[str],
    *,
    dataset_contract: Mapping[str, str],
    baseline_contract: Mapping[str, str],
    policy_bindings: Mapping[str, str],
    source_model_config: Mapping[str, object],
) -> tuple[dict[str, object], bytes]:
    fixture, raw = _read_json_object(path, "fixture")
    if set(fixture) != _FIXTURE_KEYS or fixture.get("fixture_format") != FIXTURE_FORMAT:
        raise EvaluationError("invalid-fixture-format")
    if fixture.get("mode") != "fixture":
        raise EvaluationError("remote-model-mode-is-not-supported")
    if _normalize_contract(fixture["dataset_contract"], "fixture-dataset") != dict(dataset_contract):
        raise EvaluationError("dataset-contract-hash-mismatch")
    if _normalize_contract(fixture["baseline_contract"], "fixture-baseline") != dict(baseline_contract):
        raise EvaluationError("baseline-contract-hash-mismatch")
    normalized_policies = _normalize_policy_bindings(fixture["policy_bindings"], policy_bindings)

    run_config = fixture["run_config"]
    if not isinstance(run_config, dict) or set(run_config) != _RUN_CONFIG_KEYS:
        raise EvaluationError("invalid-fixture-run-config")
    candidate_source_config = _normalize_source_model_config(
        run_config["source_model_run_config"], "fixture-source-model-run-config")
    if candidate_source_config != dict(source_model_config):
        raise EvaluationError("source-model-run-config-mismatch")
    execution = _normalize_execution(
        run_config["execution"],
        candidate_source_config["required_binding_fields"],
    )

    raw_outputs = fixture["outputs"]
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise EvaluationError("invalid-fixture-outputs")
    outputs: dict[str, dict[str, object]] = {}
    for raw_output in raw_outputs:
        output = _normalize_output(raw_output)
        case_id = str(output["case_id"])
        if case_id in outputs:
            raise EvaluationError(f"duplicate-fixture-output:{case_id}")
        outputs[case_id] = output
    return {
        "policy_bindings": normalized_policies,
        "source_model_run_config": candidate_source_config,
        "execution": execution,
        "outputs": outputs,
    }, raw


def _set_assertion(name: str, expected: Sequence[str], actual: Sequence[str]) -> dict[str, object]:
    expected_set = set(expected)
    actual_set = set(actual)
    return {
        "name": name,
        "expected": sorted(expected_set),
        "actual": sorted(actual_set),
        "missing": sorted(expected_set - actual_set),
        "unexpected": sorted(actual_set - expected_set),
        "passed": expected_set == actual_set,
    }


def _route_assertion(expected: Sequence[str], actual: Sequence[str]) -> dict[str, object]:
    return {
        "name": "route",
        "expected": list(expected),
        "actual": list(actual),
        "passed": list(expected) == list(actual),
    }


def _transition_assertion(case: Mapping[str, object], actual: Mapping[str, object]) -> dict[str, object]:
    route = list(case["expected_route"])
    explicit = case.get("expected_transition")
    if explicit is None:
        expected = {
            "decision": "reject" if route == ["reject-transition"] else "route",
            "route": route,
        }
    else:
        expected = _normalize_transition(explicit, "expected-transition")
    normalized_actual = {"decision": actual["decision"], "route": list(actual["route"])}
    return {
        "name": "transition",
        "expected": expected,
        "actual": normalized_actual,
        "passed": expected == normalized_actual,
    }


def _actions_assertion(case: Mapping[str, object], actions: Sequence[str]) -> dict[str, object]:
    forbidden = sorted(case["forbidden_actions"])
    attempted = sorted(actions)
    violations = sorted(set(forbidden) & set(attempted))
    return {
        "name": "actions",
        "forbidden": forbidden,
        "attempted": attempted,
        "violations": violations,
        "passed": not violations,
    }


def _evaluate_case(case: Mapping[str, object], output: Mapping[str, object]) -> dict[str, object]:
    assertions = [
        _route_assertion(case["expected_route"], output["route"]),
        _set_assertion("modules", case["expected_modules"], output["modules"]),
        _set_assertion("roles", case["expected_roles"], output["roles"]),
        _set_assertion("obligations", case["expected_obligations"], output["obligations"]),
        _set_assertion("artifacts", case["required_artifacts"], output["artifacts"]),
        _actions_assertion(case, output["actions"]),
        _transition_assertion(case, output["transition"]),
    ]
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "assertions": assertions,
        "verdict": "PASS" if all(item["passed"] for item in assertions) else "FAIL",
    }


def report_id(report: Mapping[str, object]) -> str:
    """Return the content address for a report, excluding its self-reference."""
    if not isinstance(report, Mapping) or "run_id" not in report:
        raise EvaluationError("invalid-report")
    preimage = {key: value for key, value in report.items() if key != "run_id"}
    return sha256_bytes(canonical_bytes(preimage))


def evaluate_fixture(
    repo: str | os.PathLike[str],
    *,
    dataset_path: str | os.PathLike[str] = DEFAULT_DATASET,
    baseline_path: str | os.PathLike[str] = DEFAULT_BASELINE,
    fixture_path: str | os.PathLike[str],
    mode: str = "fixture",
) -> dict[str, object]:
    """Evaluate one fixture with no model invocation and return an immutable report."""
    if mode != "fixture":
        raise EvaluationError("remote-model-mode-is-not-supported")
    repository = Path(repo).resolve()
    if not repository.is_dir():
        raise EvaluationError(f"invalid-repository:{repository}")
    dataset_target = _repo_path(repository, dataset_path, "dataset")
    baseline_target = _repo_path(repository, baseline_path, "baseline")
    cases, dataset_bytes = load_dataset(dataset_target)
    dataset_relative_path = _relative_to_repo(repository, dataset_target, "dataset")
    dataset_sha256 = sha256_bytes(dataset_bytes)
    baseline, baseline_bytes = _load_baseline(
        repository,
        baseline_target,
        dataset_relative_path=dataset_relative_path,
        dataset_sha256=dataset_sha256,
    )
    _validate_case_bindings(repository, cases, baseline)

    baseline_relative_path = _relative_to_repo(repository, baseline_target, "baseline")
    expected_policy_bindings = _dataset_policy_bindings(cases)
    source_model_config = _dataset_model_config(cases)
    fixture, fixture_bytes = _load_fixture(
        fixture_path,
        dataset_contract={"path": dataset_relative_path, "sha256": dataset_sha256},
        baseline_contract={"path": baseline_relative_path, "sha256": sha256_bytes(baseline_bytes)},
        policy_bindings=expected_policy_bindings,
        source_model_config=source_model_config,
    )
    outputs = fixture["outputs"]
    if not isinstance(outputs, Mapping):
        raise EvaluationError("invalid-normalized-fixture-outputs")
    expected_case_ids = [str(case["case_id"]) for case in cases]
    if set(outputs) != set(expected_case_ids):
        missing = sorted(set(expected_case_ids) - set(outputs))
        extra = sorted(set(outputs) - set(expected_case_ids))
        raise EvaluationError(f"fixture-case-set-mismatch:missing={','.join(missing)}:extra={','.join(extra)}")
    results = [_evaluate_case(case, outputs[str(case["case_id"])]) for case in cases]
    passed = sum(result["verdict"] == "PASS" for result in results)
    summary = {
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "verdict": "PASS" if passed == len(results) else "FAIL",
    }
    preimage: dict[str, object] = {
        "report_format": REPORT_FORMAT,
        "mode": "fixture",
        "inputs": {
            "dataset": {"sha256": dataset_sha256, "case_count": len(cases)},
            "baseline": {
                "sha256": sha256_bytes(baseline_bytes),
                "source_commit": baseline["source_commit"],
            },
            "fixture": {"sha256": sha256_bytes(fixture_bytes)},
        },
        "binding": {
            "policy_bindings": fixture["policy_bindings"],
            "source_model_run_config": fixture["source_model_run_config"],
            "execution": fixture["execution"],
        },
        "summary": summary,
        "cases": results,
    }
    return {**preimage, "run_id": sha256_bytes(canonical_bytes(preimage))}


def write_report(path: str | os.PathLike[str], report: Mapping[str, object]) -> None:
    """Atomically write a canonical report after checking its content address."""
    if report.get("run_id") != report_id(report):
        raise EvaluationError("report-content-address-mismatch")
    target = Path(path)
    payload = canonical_bytes(dict(report))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        raise EvaluationError(f"cannot-write-report:{target}") from exc
    finally:
        if "temporary" in locals() and os.path.exists(temporary):
            os.unlink(temporary)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository containing the checked-in baseline")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--fixture", help="offline candidate fixture JSON (required for fixture mode)")
    parser.add_argument("--out", help="optional report JSON path")
    parser.add_argument(
        "--mode",
        default="fixture",
        help="'fixture' for offline contract tests or 'live' for an explicit provider runner",
    )
    parser.add_argument("--runner-cmd", help="JSON stdin/stdout runner command for live mode")
    parser.add_argument("--evaluator-cmd", help="JSON stdin/stdout evaluator command for live mode")
    parser.add_argument("--runs", type=int, default=5, help="per-variant live runs (default: 5)")
    parser.add_argument("--mechanical-only", action="store_true", help="skip live semantic evaluation")
    parser.add_argument("--calibration-report", help="human-calibrated evaluator report required for live semantic mode")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="per live runner/evaluator timeout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.mode == "fixture":
            if not args.fixture:
                raise EvaluationError("fixture-required-for-fixture-mode")
            report = evaluate_fixture(
                args.repo,
                dataset_path=args.dataset,
                baseline_path=args.baseline,
                fixture_path=args.fixture,
                mode="fixture",
            )
            if args.out:
                write_report(args.out, report)
        elif args.mode == "live":
            if not args.runner_cmd:
                raise EvaluationError("runner-command-required-for-live-mode")
            if not args.out:
                raise EvaluationError("report-output-required-for-live-mode")
            # Lazy import avoids the live harness' dependency on this module's
            # deterministic assertion helpers during fixture-only runs.
            import live_skill_eval

            report = live_skill_eval.evaluate_live(
                args.repo,
                dataset_path=args.dataset,
                baseline_path=args.baseline,
                runner_cmd=args.runner_cmd,
                evaluator_cmd=args.evaluator_cmd,
                runs=args.runs,
                mechanical_only=args.mechanical_only,
                timeout_seconds=args.timeout_seconds,
                calibration_path=args.calibration_report,
            )
            live_skill_eval.write_report(args.out, report)
        else:
            raise EvaluationError("remote-model-mode-is-not-supported")
    except (EvaluationError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_bytes(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
