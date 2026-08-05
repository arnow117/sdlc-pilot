#!/usr/bin/env python3
"""Capture and verify a deterministic legacy Skill baseline from Git blobs.

The baseline is intentionally independent of the caller's checkout.  It records
only source-commit facts and scenario load sets, so later context-pack changes
cannot accidentally rewrite the legacy comparison point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


BASELINE_FORMAT = "sdlc-skill-baseline-v1"
PLUGIN_PATH = ".claude-plugin/plugin.json"
_SCENARIO_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")

# These are the fixed legacy framework inputs used for the five context-budget
# comparisons.  They deliberately reference only files available at 0.19.2.
DEFAULT_SCENARIOS: dict[str, list[str]] = {
    "product-small": [
        "skills/sdlc/SKILL.md",
        "skills/sdlc-spec/SKILL.md",
    ],
    "engineering-plan": [
        "skills/sdlc/SKILL.md",
        "skills/sdlc-plan/SKILL.md",
        "skills/sdlc/references/role-routing.md",
    ],
    "single-surface-build": [
        "skills/sdlc/SKILL.md",
        "skills/sdlc-build/SKILL.md",
        "skills/sdlc/references/role-routing.md",
        "skills/sdlc/references/roles/qa.md",
    ],
    "hotfix-build": [
        "skills/sdlc/SKILL.md",
        "skills/sdlc-build/SKILL.md",
        "skills/sdlc/references/roles/qa.md",
    ],
    "validate-review": [
        "skills/sdlc/SKILL.md",
        "skills/sdlc-validate/SKILL.md",
        "skills/sdlc-review/SKILL.md",
        "skills/sdlc/references/role-routing.md",
        "skills/sdlc/references/validate-modes/correctness.md",
    ],
}

REQUIRED_CATEGORIES = frozenset({
    "ambiguous-feature",
    "small-feature",
    "hotfix",
    "remediation",
    "complex-domain",
    "experience-change",
    "reliability-security",
    "ai-output",
    "brownfield-no-contract",
    "implementation-spec-gap",
    "forged-completion",
    "context-policy-change",
})
_CASE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_POLICY_ID_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CASE_KEYS = frozenset({
    "authority_mode",
    "case_id",
    "category",
    "expected_modules",
    "expected_obligations",
    "expected_roles",
    "expected_route",
    "forbidden_actions",
    "intent_flags",
    "legacy_source_ref",
    "model_run_config",
    "policy_input",
    "reference_semantics",
    "repository_fixture",
    "repository_snapshot",
    "request",
    "required_artifacts",
})
_SNAPSHOT_KEYS = frozenset({
    "base_sha",
    "control_sha256",
    "profile_sha256",
    "source_ref",
    "state_sha256",
})
_POLICY_INPUT_KEYS = frozenset({"policy_id", "sha256"})
_MODEL_RUN_CONFIG_KEYS = frozenset({"required_binding_fields", "variant_runs"})
_REQUIRED_MODEL_BINDINGS = frozenset({
    "evaluator_model",
    "evaluator_version",
    "max_tokens",
    "model",
    "model_version",
    "provider",
    "temperature",
    "tool_versions",
})
_AUTHORITY_MODES = frozenset({"legacy", "local-serial", "shared-control"})


class BaselineError(RuntimeError):
    """The source revision, manifest, or scenario input is invalid."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _git(repo: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise BaselineError("git-not-found") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise BaselineError(f"git-command-failed:{' '.join(args)}:{detail}") from exc
    return completed.stdout


def _safe_source_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise BaselineError(f"invalid-source-path:{value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value:
        raise BaselineError(f"unsafe-source-path:{value}")
    normalized = path.as_posix()
    if normalized != value:
        raise BaselineError(f"non-canonical-source-path:{value}")
    return normalized


def _resolve_commit(repo: Path, source_ref: str) -> str:
    if not isinstance(source_ref, str) or not source_ref:
        raise BaselineError("missing-source-ref")
    commit = _git(repo, "rev-parse", "--verify", f"{source_ref}^{{commit}}")
    resolved = commit.decode("ascii", errors="strict").strip()
    if not _COMMIT_RE.fullmatch(resolved):
        raise BaselineError(f"invalid-source-commit:{resolved!r}")
    return resolved


def _tree_paths(repo: Path, source_commit: str) -> set[str]:
    raw = _git(repo, "ls-tree", "-r", "-z", "--name-only", source_commit)
    try:
        paths = [entry.decode("utf-8") for entry in raw.split(b"\0") if entry]
    except UnicodeDecodeError as exc:
        raise BaselineError("source-tree-has-non-utf8-path") from exc
    return set(paths)


def git_blob(repo: Path, source_ref: str, path: str) -> bytes:
    """Read a blob from Git, never from the working tree."""
    _safe_source_path(path)
    return _git(repo, "show", f"{source_ref}:{path}")


def _normalize_scenarios(scenarios: Mapping[str, Sequence[str]]) -> list[tuple[str, list[str]]]:
    if not isinstance(scenarios, Mapping) or not scenarios:
        raise BaselineError("scenarios-must-be-a-nonempty-mapping")
    normalized: list[tuple[str, list[str]]] = []
    for scenario_id, raw_paths in scenarios.items():
        if not isinstance(scenario_id, str) or not _SCENARIO_ID_RE.fullmatch(scenario_id):
            raise BaselineError(f"invalid-scenario-id:{scenario_id!r}")
        if isinstance(raw_paths, (str, bytes)) or not isinstance(raw_paths, Sequence) or not raw_paths:
            raise BaselineError(f"scenario-needs-paths:{scenario_id}")
        paths = [_safe_source_path(path) for path in raw_paths]
        if len(paths) != len(set(paths)):
            raise BaselineError(f"duplicate-scenario-path:{scenario_id}")
        normalized.append((scenario_id, sorted(paths)))
    if len({scenario_id for scenario_id, _ in normalized}) != len(normalized):
        raise BaselineError("duplicate-scenario-id")
    return sorted(normalized, key=lambda item: item[0])


def _plugin_record(repo: Path, source_commit: str, tree_paths: set[str]) -> dict[str, object]:
    if PLUGIN_PATH not in tree_paths:
        raise BaselineError(f"missing-plugin-metadata:{PLUGIN_PATH}")
    blob = git_blob(repo, source_commit, PLUGIN_PATH)
    try:
        plugin = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError("invalid-plugin-metadata") from exc
    version = plugin.get("version") if isinstance(plugin, dict) else None
    if not isinstance(version, str) or not version:
        raise BaselineError("missing-plugin-version")
    return {
        "path": PLUGIN_PATH,
        "sha256": sha256_bytes(blob),
        "utf8_bytes": len(blob),
        "version": version,
    }


def capture_from_git(repo: str | os.PathLike[str], source_ref: str,
                     scenarios: Mapping[str, Sequence[str]] = DEFAULT_SCENARIOS) -> dict[str, object]:
    """Capture scenario input facts from a resolved Git commit."""
    repository = Path(repo).resolve()
    source_commit = _resolve_commit(repository, source_ref)
    tree_paths = _tree_paths(repository, source_commit)
    normalized_scenarios = _normalize_scenarios(scenarios)
    requested_paths = sorted({path for _, paths in normalized_scenarios for path in paths})
    missing = [path for path in requested_paths if path not in tree_paths]
    if missing:
        raise BaselineError(f"source-path-not-in-tree:{','.join(missing)}")

    blobs = {path: git_blob(repository, source_commit, path) for path in requested_paths}
    files = [
        {"path": path, "sha256": sha256_bytes(blobs[path]), "utf8_bytes": len(blobs[path])}
        for path in requested_paths
    ]
    scenario_records = [
        {
            "scenario_id": scenario_id,
            "paths": paths,
            "total_utf8_bytes": sum(len(blobs[path]) for path in paths),
        }
        for scenario_id, paths in normalized_scenarios
    ]
    return {
        "baseline_format": BASELINE_FORMAT,
        "dataset_contract": None,
        "files": files,
        "plugin": _plugin_record(repository, source_commit, tree_paths),
        "scenarios": scenario_records,
        "source_commit": source_commit,
    }


def _require_nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaselineError(f"invalid-case-{field}")
    return value


def _require_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise BaselineError(f"invalid-case-{field}")
    if any(not isinstance(item, str) or not item for item in value):
        raise BaselineError(f"invalid-case-{field}")
    if len(set(value)) != len(value):
        raise BaselineError(f"duplicate-case-{field}")
    return value


def _validate_case(value: object, *, line_number: int) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _CASE_KEYS:
        raise BaselineError(f"invalid-case-keys:line-{line_number}")
    case_id = value.get("case_id")
    if not isinstance(case_id, str) or not _CASE_ID_RE.fullmatch(case_id):
        raise BaselineError(f"invalid-case-id:line-{line_number}")
    category = value.get("category")
    if category not in REQUIRED_CATEGORIES:
        raise BaselineError(f"invalid-case-category:line-{line_number}")
    _require_nonempty_string(value.get("request"), "request")
    _safe_source_path(value.get("repository_fixture"))
    authority_mode = value.get("authority_mode")
    if authority_mode not in _AUTHORITY_MODES:
        raise BaselineError(f"invalid-case-authority-mode:{case_id}")
    intent_flags = value.get("intent_flags")
    if not isinstance(intent_flags, dict) or not intent_flags or any(
            not isinstance(key, str) or not key for key in intent_flags):
        raise BaselineError(f"invalid-case-intent-flags:{case_id}")

    snapshot = value.get("repository_snapshot")
    if not isinstance(snapshot, dict) or set(snapshot) != _SNAPSHOT_KEYS:
        raise BaselineError(f"invalid-case-snapshot:{case_id}")
    for key, raw in snapshot.items():
        matcher = _COMMIT_RE if key in {"source_ref", "base_sha"} else _SHA256_RE
        if not isinstance(raw, str) or not matcher.fullmatch(raw):
            raise BaselineError(f"invalid-case-snapshot-{key}:{case_id}")
    if snapshot["source_ref"] != snapshot["base_sha"]:
        raise BaselineError(f"case-source-base-mismatch:{case_id}")
    legacy_source_ref = value.get("legacy_source_ref")
    if not isinstance(legacy_source_ref, str) or not _COMMIT_RE.fullmatch(legacy_source_ref):
        raise BaselineError(f"invalid-legacy-source-ref:{case_id}")

    policy = value.get("policy_input")
    if not isinstance(policy, dict) or set(policy) != _POLICY_INPUT_KEYS:
        raise BaselineError(f"invalid-case-policy-input:{case_id}")
    if (not isinstance(policy["policy_id"], str)
            or not _POLICY_ID_RE.fullmatch(policy["policy_id"])
            or not isinstance(policy["sha256"], str)
            or not _SHA256_RE.fullmatch(policy["sha256"])):
        raise BaselineError(f"invalid-case-policy-input:{case_id}")

    model_config = value.get("model_run_config")
    if not isinstance(model_config, dict) or set(model_config) != _MODEL_RUN_CONFIG_KEYS:
        raise BaselineError(f"invalid-model-run-config:{case_id}")
    if model_config["variant_runs"] != 5:
        raise BaselineError(f"invalid-model-run-count:{case_id}")
    bindings = _require_string_list(model_config["required_binding_fields"], "model-run-bindings")
    if not _REQUIRED_MODEL_BINDINGS.issubset(bindings):
        raise BaselineError(f"missing-model-run-binding:{case_id}")

    for field in (
        "expected_route",
        "expected_modules",
        "expected_roles",
        "expected_obligations",
        "required_artifacts",
        "forbidden_actions",
    ):
        _require_string_list(value.get(field), field)
    _require_nonempty_string(value.get("reference_semantics"), "reference-semantics")
    return value


def load_cases(path: str | os.PathLike[str]) -> list[dict[str, object]]:
    """Load the exact v1 behavior-evaluation dataset without loose fields."""
    dataset_path = Path(path)
    try:
        lines = dataset_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BaselineError(f"cannot-read-dataset:{dataset_path}") from exc
    if any(not line.strip() for line in lines):
        raise BaselineError("dataset-has-blank-line")
    cases: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BaselineError(f"invalid-dataset-json:line-{line_number}") from exc
        cases.append(_validate_case(raw, line_number=line_number))
    case_ids = [str(case["case_id"]) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise BaselineError("duplicate-dataset-case-id")
    categories = [str(case["category"]) for case in cases]
    if len(cases) != len(REQUIRED_CATEGORIES) or set(categories) != REQUIRED_CATEGORIES:
        raise BaselineError("dataset-must-have-one-case-per-required-category")
    return cases


def _read_manifest(path: str | os.PathLike[str]) -> tuple[dict[str, object], bytes]:
    manifest_path = Path(path)
    try:
        raw = manifest_path.read_bytes()
    except OSError as exc:
        raise BaselineError(f"cannot-read-manifest:{manifest_path}") from exc
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError("invalid-manifest-json") from exc
    if not isinstance(value, dict):
        raise BaselineError("manifest-must-be-an-object")
    if raw != canonical_bytes(value):
        raise BaselineError("manifest-is-not-canonical-json")
    return value, raw


def _scenarios_from_manifest(value: dict[str, object]) -> dict[str, list[str]]:
    raw_scenarios = value.get("scenarios")
    if not isinstance(raw_scenarios, list):
        raise BaselineError("manifest-scenarios-must-be-a-list")
    scenarios: dict[str, list[str]] = {}
    for item in raw_scenarios:
        if not isinstance(item, dict) or set(item) != {"scenario_id", "paths", "total_utf8_bytes"}:
            raise BaselineError("invalid-manifest-scenario")
        scenario_id = item["scenario_id"]
        paths = item["paths"]
        if not isinstance(scenario_id, str) or not isinstance(paths, list):
            raise BaselineError("invalid-manifest-scenario-types")
        if scenario_id in scenarios:
            raise BaselineError(f"duplicate-manifest-scenario:{scenario_id}")
        scenarios[scenario_id] = paths
    return scenarios


def _validate_dataset_contract(repo: Path, value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise BaselineError("invalid-dataset-contract")
    path = _safe_source_path(value["path"])
    expected = value["sha256"]
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise BaselineError("invalid-dataset-contract-sha256")
    target = (repo / path).resolve()
    try:
        target.relative_to(repo.resolve())
        actual = sha256_bytes(target.read_bytes())
    except OSError as exc:
        raise BaselineError(f"cannot-read-dataset:{path}") from exc
    if actual != expected:
        raise BaselineError(f"dataset-contract-hash-mismatch:{path}")
    return {"path": path, "sha256": expected}


def check_manifest(repo: str | os.PathLike[str], manifest_path: str | os.PathLike[str]) -> None:
    """Recompute a manifest from Git and reject any source or dataset drift."""
    repository = Path(repo).resolve()
    manifest, _ = _read_manifest(manifest_path)
    expected_keys = {"baseline_format", "dataset_contract", "files", "plugin", "scenarios", "source_commit"}
    if set(manifest) != expected_keys:
        raise BaselineError("unexpected-manifest-keys")
    if manifest.get("baseline_format") != BASELINE_FORMAT:
        raise BaselineError("unsupported-baseline-format")
    source_commit = manifest.get("source_commit")
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        raise BaselineError("invalid-manifest-source-commit")
    scenarios = _scenarios_from_manifest(manifest)
    actual = capture_from_git(repository, source_commit, scenarios)
    actual["dataset_contract"] = _validate_dataset_contract(repository, manifest.get("dataset_contract"))
    if canonical_bytes(actual) != canonical_bytes(manifest):
        raise BaselineError("baseline-manifest-does-not-match-source")


def write_manifest(path: str | os.PathLike[str], manifest: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(manifest)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture", help="capture a source-commit baseline")
    capture.add_argument("--repo", default=".")
    capture.add_argument("--source-ref", required=True)
    capture.add_argument("--out", required=True)
    check = commands.add_parser("check", help="recompute and verify a baseline")
    check.add_argument("--repo", default=".")
    check.add_argument("--manifest", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "capture":
            write_manifest(args.out, capture_from_git(args.repo, args.source_ref))
        else:
            check_manifest(args.repo, args.manifest)
    except BaselineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
