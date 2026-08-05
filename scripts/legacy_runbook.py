#!/usr/bin/env python3
"""Load an exact legacy SDLC runbook without putting it in every active skill.

The compatibility adapters deliberately contain only routing.  On an ordinary
legacy invocation they load the byte-pinned 0.19.2 runbook from the repository
object database and verify the digest before using it.  A missing Git object is
an explicit compatibility error, never a quiet fallback to the new lifecycle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Mapping


SCHEMA_VERSION = "sdlc-legacy-runbook-v1"
MANIFEST_RELATIVE_PATH = Path("skills/sdlc/references/legacy/0.19.2.json")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STAGE_RE = re.compile(r"^(driver|spec|plan|build|validate|review)$")
_TOP_LEVEL_KEYS = frozenset({"schema_version", "version", "source_commit", "runbooks"})
_RUNBOOK_KEYS = frozenset({"path", "sha256", "utf8_bytes"})


class LegacyRunbookError(RuntimeError):
    """The declared legacy source cannot be loaded exactly and safely."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _safe_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise LegacyRunbookError("invalid-legacy-runbook-path")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts or "\\" in value:
        raise LegacyRunbookError("unsafe-legacy-runbook-path")
    normalized = path.as_posix()
    if normalized != value:
        raise LegacyRunbookError("non-canonical-legacy-runbook-path")
    return normalized


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise LegacyRunbookError(f"invalid-{label}")
    return value


def _require_commit(value: object) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise LegacyRunbookError("invalid-legacy-source-commit")
    return value


def _require_size(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise LegacyRunbookError("invalid-legacy-runbook-size")
    return value


def _repository_root(value: str | Path | None) -> Path:
    root = Path(value) if value is not None else Path(__file__).resolve().parent.parent
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise LegacyRunbookError("legacy-repository-root-unavailable") from exc
    if not resolved.is_dir():
        raise LegacyRunbookError("legacy-repository-root-not-directory")
    return resolved


def manifest_path(repo_root: str | Path | None = None) -> Path:
    return _repository_root(repo_root) / MANIFEST_RELATIVE_PATH


def load_manifest(repo_root: str | Path | None = None) -> dict[str, object]:
    """Read and strictly validate the one pinned legacy runbook manifest."""
    path = manifest_path(repo_root)
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw.decode("utf-8"))
    except FileNotFoundError as exc:
        raise LegacyRunbookError("legacy-runbook-manifest-missing") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyRunbookError("invalid-legacy-runbook-manifest-json") from exc
    if not isinstance(parsed, dict) or set(parsed) != _TOP_LEVEL_KEYS:
        raise LegacyRunbookError("invalid-legacy-runbook-manifest-keys")
    if parsed["schema_version"] != SCHEMA_VERSION:
        raise LegacyRunbookError("unsupported-legacy-runbook-schema")
    if not isinstance(parsed["version"], str) or not parsed["version"]:
        raise LegacyRunbookError("invalid-legacy-runbook-version")
    source_commit = _require_commit(parsed["source_commit"])
    raw_runbooks = parsed["runbooks"]
    if not isinstance(raw_runbooks, dict) or set(raw_runbooks) != {
        "driver", "spec", "plan", "build", "validate", "review"
    }:
        raise LegacyRunbookError("invalid-legacy-runbook-stages")
    runbooks: dict[str, dict[str, object]] = {}
    paths: set[str] = set()
    for stage in sorted(raw_runbooks):
        item = raw_runbooks[stage]
        if not isinstance(item, dict) or set(item) != _RUNBOOK_KEYS:
            raise LegacyRunbookError(f"invalid-legacy-runbook-record:{stage}")
        record = {
            "path": _safe_path(item["path"]),
            "sha256": _require_sha256(item["sha256"], f"legacy-runbook-sha256:{stage}"),
            "utf8_bytes": _require_size(item["utf8_bytes"]),
        }
        if record["path"] in paths:
            raise LegacyRunbookError("duplicate-legacy-runbook-path")
        paths.add(str(record["path"]))
        runbooks[stage] = record
    return {
        "schema_version": SCHEMA_VERSION,
        "version": parsed["version"],
        "source_commit": source_commit,
        "runbooks": runbooks,
    }


def _git(repo_root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise LegacyRunbookError("git-not-found-for-legacy-runbook") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise LegacyRunbookError(f"legacy-runbook-git-object-unavailable:{detail}") from exc
    return result.stdout


def load_runbook(stage: str, repo_root: str | Path | None = None) -> bytes:
    """Return the exact historical bytes for a named legacy stage.

    The working-tree version of the skill is never read here.  That prevents an
    adapter edit, user local edit, or a new lifecycle module from silently
    changing normal legacy behavior.
    """
    if not isinstance(stage, str) or not _STAGE_RE.fullmatch(stage):
        raise LegacyRunbookError("invalid-legacy-runbook-stage")
    root = _repository_root(repo_root)
    manifest = load_manifest(root)
    source_commit = str(manifest["source_commit"])
    _git(root, "cat-file", "-e", f"{source_commit}^{{commit}}")
    record = dict(cast_mapping(manifest["runbooks"])[stage])
    path = str(record["path"])
    try:
        payload = _git(root, "show", f"{source_commit}:{path}")
    except LegacyRunbookError as exc:
        raise LegacyRunbookError(f"legacy-runbook-unavailable:{stage}") from exc
    if len(payload) != record["utf8_bytes"]:
        raise LegacyRunbookError(f"legacy-runbook-size-mismatch:{stage}")
    if sha256_bytes(payload) != record["sha256"]:
        raise LegacyRunbookError(f"legacy-runbook-digest-mismatch:{stage}")
    if not payload.startswith(b"---\n"):
        raise LegacyRunbookError(f"legacy-runbook-frontmatter-missing:{stage}")
    return payload


def cast_mapping(value: object) -> Mapping[str, Mapping[str, object]]:
    if not isinstance(value, Mapping):
        raise LegacyRunbookError("invalid-legacy-runbook-manifest")
    return value  # type: ignore[return-value]


def verify(repo_root: str | Path | None = None) -> dict[str, object]:
    """Verify all pinned historical objects and return a stable audit report."""
    manifest = load_manifest(repo_root)
    digests = {
        stage: sha256_bytes(load_runbook(stage, repo_root))
        for stage in sorted(cast_mapping(manifest["runbooks"]))
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "version": manifest["version"],
        "source_commit": manifest["source_commit"],
        "runbook_sha256": digests,
    }
    report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None, help="plugin repository root (default: script parent)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    show = subparsers.add_parser("show", help="write one verified runbook to stdout")
    show.add_argument("--stage", required=True, choices=("driver", "spec", "plan", "build", "validate", "review"))
    subparsers.add_parser("verify", help="verify every pinned legacy runbook")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "show":
            sys.stdout.buffer.write(load_runbook(arguments.stage, arguments.repo_root))
        else:
            sys.stdout.buffer.write(canonical_bytes(verify(arguments.repo_root)))
    except LegacyRunbookError as exc:
        print(f"legacy-runbook-error:{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
