#!/usr/bin/env python3
"""Small Git-tracked state store for the default SDLC lifecycle.

``.sdlc-v1/state.json`` is the only progress source. Product and engineering
context remains ordinary Markdown under ``.sdlc-v1/context/`` and is referenced
by path. Git provides history and cross-clone transport; there is no event
ledger, hash chain, journal, compatibility runtime, or automatic Git action.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Iterator, Mapping, Sequence


STATE_DIRECTORY = ".sdlc-v1"
STATE_FILENAME = "state.json"
STATE_FORMAT = "sdlc-lightweight-state-v1"
STATE_VERSION = 3

_STATE_FIELDS = frozenset({"state_format", "state_version", "requirements", "features"})
_REQUIREMENT_FIELDS = frozenset({
    "id", "title", "description", "domain", "priority", "status", "depends_on", "feature_id",
    "product_context_ref", "created_at", "updated_at",
})
_FEATURE_FIELDS = frozenset({
    "id", "requirement_id", "branch", "status", "tasks", "validation", "review", "release",
    "engineering_context_ref", "created_at", "updated_at",
})
_TASK_FIELDS = frozenset({"id", "title", "status", "depends_on", "updated_at"})
_VALIDATION_FIELDS = frozenset({"result", "command", "commit", "at"})
_REVIEW_FIELDS = frozenset({"decision", "by", "at"})
_RELEASE_FIELDS = frozenset({"status", "commit", "at"})

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_REQUIREMENT_STATUSES = frozenset({"captured", "ready", "in_delivery", "validated", "released", "cancelled"})
_FEATURE_STATUSES = frozenset({"planned", "in_progress", "validated", "reviewed", "released", "cancelled"})
_TASK_STATUSES = frozenset({"todo", "in_progress", "done", "blocked", "cancelled"})
_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_TASK_TRANSITIONS = {
    "todo": frozenset({"in_progress", "blocked", "cancelled"}),
    "in_progress": frozenset({"todo", "done", "blocked", "cancelled"}),
    "blocked": frozenset({"todo", "in_progress", "cancelled"}),
    "done": frozenset({"todo"}),
    "cancelled": frozenset(),
}
class LifecycleStateError(RuntimeError):
    """The lightweight lifecycle state is missing, invalid, or inconsistent."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleStateError(f"duplicate-json-field:{key}")
        result[key] = value
    return result


def _repo_root(repo: str | os.PathLike[str]) -> Path:
    path = Path(repo)
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise LifecycleStateError("repository-root-not-found") from exc
    if not root.is_dir():
        raise LifecycleStateError("repository-root-not-directory")
    return root


def _state_directory(root: Path, *, create: bool) -> Path:
    directory = root / STATE_DIRECTORY
    if directory.is_symlink():
        raise LifecycleStateError("state-directory-cannot-be-symlink")
    if not directory.exists():
        if not create:
            return directory
        directory.mkdir(mode=0o755)
    if not directory.is_dir():
        raise LifecycleStateError("state-directory-not-directory")
    return directory


def state_path(repo: str | os.PathLike[str] = ".") -> Path:
    root = _repo_root(repo)
    return _state_directory(root, create=False) / STATE_FILENAME


def _state_file(root: Path, *, require_exists: bool) -> Path:
    """Return the canonical state path without inspecting historical runtimes."""
    path = _state_directory(root, create=False) / STATE_FILENAME
    if path.is_symlink():
        raise LifecycleStateError("state-file-cannot-be-symlink")
    if path.exists() and not path.is_file():
        raise LifecycleStateError("state-file-not-regular")
    if require_exists and not path.exists():
        raise LifecycleStateError("state-not-initialized")
    return path


def _id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise LifecycleStateError(f"invalid-{label}")
    return value


def _text(value: object, *, label: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or (not allow_empty and not value.strip()):
        raise LifecycleStateError(f"invalid-{label}")
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label=label)


def _context_ref(value: object, *, label: str) -> str:
    raw = _text(value, label=label)
    if "\\" in raw:
        raise LifecycleStateError(f"invalid-{label}")
    path = PurePosixPath(raw)
    parts = path.parts
    if (
        path.is_absolute()
        or path.as_posix() != raw
        or any(part in {"", ".", ".."} for part in raw.split("/"))
        or len(parts) < 3
        or parts[:2] != (STATE_DIRECTORY, "context")
        or path.suffix.lower() != ".md"
    ):
        raise LifecycleStateError(f"invalid-{label}")
    return raw


def _require_context_file(root: Path, ref: str, *, label: str) -> None:
    current = root
    for part in PurePosixPath(ref).parts:
        current = current / part
        if current.is_symlink():
            raise LifecycleStateError(f"{label}-cannot-be-symlink:{ref}")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise LifecycleStateError(f"{label}-not-found:{ref}") from exc
    if not resolved.is_file():
        raise LifecycleStateError(f"{label}-not-regular:{ref}")


def _timestamp(value: object, *, label: str) -> str:
    raw = _text(value, label=label)
    parseable = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise LifecycleStateError(f"invalid-{label}") from exc
    if parsed.tzinfo is None:
        raise LifecycleStateError(f"invalid-{label}")
    return raw


def _id_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise LifecycleStateError(f"invalid-{label}")
    result = [_id(item, label=f"{label}-item") for item in value]
    if len(set(result)) != len(result):
        raise LifecycleStateError(f"duplicate-{label}")
    return result


def _cycle(nodes: Mapping[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str, trail: list[str]) -> list[str] | None:
        if node in visiting:
            return trail[trail.index(node):] + [node]
        if node in visited:
            return None
        visiting.add(node)
        for dependency in nodes[node]:
            found = walk(dependency, [*trail, node])
            if found:
                return found
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(nodes):
        found = walk(node, [])
        if found:
            return found
    return None


def _validate_validation(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _VALIDATION_FIELDS:
        raise LifecycleStateError("invalid-feature-validation-fields")
    result = dict(value)
    if result.get("result") not in {"pending", "pass", "fail"}:
        raise LifecycleStateError("invalid-feature-validation-result")
    result["command"] = _optional_text(result.get("command"), label="feature-validation-command")
    result["commit"] = _optional_text(result.get("commit"), label="feature-validation-commit")
    at = result.get("at")
    result["at"] = None if at is None else _timestamp(at, label="feature-validation-at")
    if result["result"] == "pending" and any(result[field] is not None for field in ("command", "commit", "at")):
        raise LifecycleStateError("pending-feature-validation-cannot-have-record")
    if result["result"] != "pending" and (
        result["commit"] is None or result["at"] is None
    ):
        raise LifecycleStateError("completed-feature-validation-requires-commit-and-at")
    return result


def _validate_review(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _REVIEW_FIELDS:
        raise LifecycleStateError("invalid-feature-review-fields")
    result = dict(value)
    if result.get("decision") not in {"pending", "approved", "changes_requested"}:
        raise LifecycleStateError("invalid-feature-review-decision")
    result["by"] = _optional_text(result.get("by"), label="feature-review-by")
    at = result.get("at")
    result["at"] = None if at is None else _timestamp(at, label="feature-review-at")
    if result["decision"] == "pending" and (result["by"] is not None or result["at"] is not None):
        raise LifecycleStateError("pending-feature-review-cannot-have-record")
    if result["decision"] != "pending" and result["at"] is None:
        raise LifecycleStateError("completed-feature-review-requires-at")
    return result


def _validate_release(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _RELEASE_FIELDS:
        raise LifecycleStateError("invalid-feature-release-fields")
    result = dict(value)
    if result.get("status") not in {"pending", "released"}:
        raise LifecycleStateError("invalid-feature-release-status")
    result["commit"] = _optional_text(result.get("commit"), label="feature-release-commit")
    at = result.get("at")
    result["at"] = None if at is None else _timestamp(at, label="feature-release-at")
    if result["status"] == "pending" and (result["commit"] is not None or result["at"] is not None):
        raise LifecycleStateError("pending-feature-release-cannot-have-record")
    if result["status"] == "released" and (
        result["commit"] is None or result["at"] is None
    ):
        raise LifecycleStateError("released-feature-requires-commit-and-at")
    return result


def _validate_state(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _STATE_FIELDS:
        raise LifecycleStateError("invalid-state-fields")
    state = deepcopy(dict(value))
    if state.get("state_format") != STATE_FORMAT or state.get("state_version") != STATE_VERSION:
        raise LifecycleStateError("unsupported-state-format")
    requirements = state.get("requirements")
    features = state.get("features")
    if not isinstance(requirements, Mapping) or not isinstance(features, Mapping):
        raise LifecycleStateError("invalid-state-collections")
    requirement_records: dict[str, dict[str, object]] = {}
    for key, raw in requirements.items():
        requirement_id = _id(key, label="requirement-key")
        if not isinstance(raw, Mapping) or set(raw) != _REQUIREMENT_FIELDS:
            raise LifecycleStateError(f"invalid-requirement-fields:{requirement_id}")
        record = deepcopy(dict(raw))
        if _id(record.get("id"), label="requirement-id") != requirement_id:
            raise LifecycleStateError(f"requirement-key-id-mismatch:{requirement_id}")
        record["title"] = _text(record.get("title"), label="requirement-title")
        record["description"] = _text(record.get("description"), label="requirement-description", allow_empty=True)
        record["domain"] = _text(record.get("domain"), label="requirement-domain")
        record["product_context_ref"] = _context_ref(
            record.get("product_context_ref"), label="requirement-product-context-ref",
        )
        if record.get("priority") not in _PRIORITIES:
            raise LifecycleStateError(f"invalid-requirement-priority:{requirement_id}")
        if record.get("status") not in _REQUIREMENT_STATUSES:
            raise LifecycleStateError(f"invalid-requirement-status:{requirement_id}")
        record["depends_on"] = _id_list(record.get("depends_on"), label=f"requirement-depends-on:{requirement_id}")
        feature_id = record.get("feature_id")
        record["feature_id"] = None if feature_id is None else _id(feature_id, label="requirement-feature-id")
        record["created_at"] = _timestamp(record.get("created_at"), label="requirement-created-at")
        record["updated_at"] = _timestamp(record.get("updated_at"), label="requirement-updated-at")
        requirement_records[requirement_id] = record
    missing_requirements = sorted({dependency for record in requirement_records.values()
                                   for dependency in record["depends_on"] if dependency not in requirement_records})
    if missing_requirements:
        raise LifecycleStateError("unknown-requirement-dependency:" + ",".join(missing_requirements))
    requirement_cycle = _cycle({key: list(record["depends_on"]) for key, record in requirement_records.items()})
    if requirement_cycle:
        raise LifecycleStateError("requirement-dependency-cycle:" + "->".join(requirement_cycle))

    feature_records: dict[str, dict[str, object]] = {}
    for key, raw in features.items():
        feature_id = _id(key, label="feature-key")
        if not isinstance(raw, Mapping) or set(raw) != _FEATURE_FIELDS:
            raise LifecycleStateError(f"invalid-feature-fields:{feature_id}")
        record = deepcopy(dict(raw))
        if _id(record.get("id"), label="feature-id") != feature_id:
            raise LifecycleStateError(f"feature-key-id-mismatch:{feature_id}")
        requirement_id = _id(record.get("requirement_id"), label="feature-requirement-id")
        if requirement_id not in requirement_records:
            raise LifecycleStateError(f"unknown-feature-requirement:{feature_id}")
        record["requirement_id"] = requirement_id
        record["branch"] = _text(record.get("branch"), label="feature-branch")
        record["engineering_context_ref"] = _context_ref(
            record.get("engineering_context_ref"), label="feature-engineering-context-ref",
        )
        if record.get("status") not in _FEATURE_STATUSES:
            raise LifecycleStateError(f"invalid-feature-status:{feature_id}")
        record["created_at"] = _timestamp(record.get("created_at"), label="feature-created-at")
        record["updated_at"] = _timestamp(record.get("updated_at"), label="feature-updated-at")
        tasks = record.get("tasks")
        if not isinstance(tasks, Mapping):
            raise LifecycleStateError(f"invalid-feature-tasks:{feature_id}")
        task_records: dict[str, dict[str, object]] = {}
        for task_key, task_raw in tasks.items():
            task_id = _id(task_key, label="task-key")
            if not isinstance(task_raw, Mapping) or set(task_raw) != _TASK_FIELDS:
                raise LifecycleStateError(f"invalid-task-fields:{feature_id}/{task_id}")
            task = deepcopy(dict(task_raw))
            if _id(task.get("id"), label="task-id") != task_id:
                raise LifecycleStateError(f"task-key-id-mismatch:{feature_id}/{task_id}")
            task["title"] = _text(task.get("title"), label="task-title")
            if task.get("status") not in _TASK_STATUSES:
                raise LifecycleStateError(f"invalid-task-status:{feature_id}/{task_id}")
            task["depends_on"] = _id_list(task.get("depends_on"), label=f"task-depends-on:{feature_id}/{task_id}")
            task["updated_at"] = _timestamp(task.get("updated_at"), label="task-updated-at")
            task_records[task_id] = task
        unknown_tasks = sorted({dependency for task in task_records.values()
                                for dependency in task["depends_on"] if dependency not in task_records})
        if unknown_tasks:
            raise LifecycleStateError(f"unknown-task-dependency:{feature_id}/" + ",".join(unknown_tasks))
        task_cycle = _cycle({task_id: list(task["depends_on"]) for task_id, task in task_records.items()})
        if task_cycle:
            raise LifecycleStateError(f"task-dependency-cycle:{feature_id}/" + "->".join(task_cycle))
        record["tasks"] = task_records
        record["validation"] = _validate_validation(record.get("validation"))
        record["review"] = _validate_review(record.get("review"))
        record["release"] = _validate_release(record.get("release"))
        feature_records[feature_id] = record

    for requirement_id, requirement in requirement_records.items():
        linked_feature = requirement["feature_id"]
        if linked_feature is None:
            if requirement["status"] not in {"captured", "ready", "cancelled"}:
                raise LifecycleStateError(f"unlinked-requirement-has-delivery-status:{requirement_id}")
            continue
        feature = feature_records.get(linked_feature)
        if feature is None or feature["requirement_id"] != requirement_id:
            raise LifecycleStateError(f"requirement-feature-link-mismatch:{requirement_id}")
        expected_status = {
            "planned": "in_delivery", "in_progress": "in_delivery", "validated": "validated",
            "reviewed": "validated", "released": "released", "cancelled": "cancelled",
        }[str(feature["status"])]
        if requirement["status"] != expected_status:
            raise LifecycleStateError(f"requirement-feature-status-mismatch:{requirement_id}")
    for feature_id, feature in feature_records.items():
        requirement = requirement_records[str(feature["requirement_id"])]
        if requirement["feature_id"] != feature_id:
            raise LifecycleStateError(f"feature-requirement-link-mismatch:{feature_id}")
        validation = feature["validation"]
        review = feature["review"]
        release = feature["release"]
        status = str(feature["status"])
        if status in {"validated", "reviewed", "released"} and validation["result"] != "pass":
            raise LifecycleStateError(f"feature-status-requires-passing-validation:{feature_id}")
        if status in {"reviewed", "released"} and review["decision"] != "approved":
            raise LifecycleStateError(f"feature-status-requires-approved-review:{feature_id}")
        if status == "released" and release["status"] != "released":
            raise LifecycleStateError(f"feature-status-requires-release-record:{feature_id}")
        if status != "released" and release["status"] == "released":
            raise LifecycleStateError(f"release-record-status-mismatch:{feature_id}")
    return {
        "state_format": STATE_FORMAT,
        "state_version": STATE_VERSION,
        "requirements": requirement_records,
        "features": feature_records,
    }


def _empty_state() -> dict[str, object]:
    return {
        "state_format": STATE_FORMAT,
        "state_version": STATE_VERSION,
        "requirements": {},
        "features": {},
    }


def _decode_state(raw: bytes) -> dict[str, object]:
    try:
        source = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except LifecycleStateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleStateError("invalid-state-json") from exc
    return _validate_state(source)


def _read_state(root: Path) -> dict[str, object]:
    path = _state_file(root, require_exists=True)
    try:
        return _decode_state(path.read_bytes())
    except LifecycleStateError:
        raise
    except OSError as exc:
        raise LifecycleStateError("cannot-read-state") from exc


def _state_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise LifecycleStateError("cannot-stat-state") from exc
    if not stat.S_ISREG(info.st_mode):
        raise LifecycleStateError("state-file-not-regular")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_descriptor(descriptor: int) -> bytes:
    with os.fdopen(os.dup(descriptor), "rb", closefd=True) as handle:
        return handle.read()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleStateError("git-is-required-for-lightweight-state") from exc


def _require_git_repository(root: Path) -> None:
    result = _git(root, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise LifecycleStateError("git-repository-required")


def _ensure_state_can_be_tracked(root: Path) -> None:
    """Fail early when a repository ignore rule would defeat cross-clone sync."""
    _require_git_repository(root)
    relative = f"{STATE_DIRECTORY}/{STATE_FILENAME}"
    ignored = _git(root, "check-ignore", "-q", "--", relative)
    if ignored.returncode == 0:
        raise LifecycleStateError("state-path-is-gitignored")
    if ignored.returncode != 1:
        raise LifecycleStateError("cannot-check-state-git-ignore")


def _state_git_status(root: Path) -> dict[str, bool]:
    relative = f"{STATE_DIRECTORY}/{STATE_FILENAME}"
    tracked_result = _git(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked_result.returncode not in {0, 1}:
        raise LifecycleStateError("cannot-check-state-tracking")
    unmerged_result = _git(root, "ls-files", "-u", "--", relative)
    if unmerged_result.returncode != 0:
        raise LifecycleStateError("cannot-check-state-conflicts")
    staged_result = _git(root, "diff", "--cached", "--quiet", "--", relative)
    if staged_result.returncode not in {0, 1}:
        raise LifecycleStateError("cannot-check-staged-state")
    return {
        "tracked": tracked_result.returncode == 0,
        "unmerged": bool(unmerged_result.stdout.strip()),
        "staged": staged_result.returncode == 1,
    }


def _require_tracked_state(root: Path) -> None:
    state_git = _state_git_status(root)
    if state_git["unmerged"]:
        raise LifecycleStateError("state-has-unmerged-index-entries")
    if not state_git["tracked"]:
        raise LifecycleStateError("state-must-be-git-tracked-before-validation")


def _require_tracked_feature_contexts(
    root: Path, state: Mapping[str, object], feature: Mapping[str, object],
) -> None:
    requirements = state["requirements"]
    assert isinstance(requirements, Mapping)
    requirement = requirements[str(feature["requirement_id"])]
    assert isinstance(requirement, Mapping)
    refs = (
        (str(requirement["product_context_ref"]), "product-context"),
        (str(feature["engineering_context_ref"]), "engineering-context"),
    )
    for ref, label in refs:
        _require_context_file(root, ref, label=label)
        tracked = _git(root, "ls-files", "--error-unmatch", "--", ref)
        if tracked.returncode != 0:
            raise LifecycleStateError(f"context-must-be-git-tracked-before-validation:{ref}")
        unmerged = _git(root, "ls-files", "-u", "--", ref)
        if unmerged.returncode != 0:
            raise LifecycleStateError(f"cannot-check-context-conflicts:{ref}")
        if unmerged.stdout.strip():
            raise LifecycleStateError(f"context-has-unmerged-index-entries:{ref}")


def _reject_staged_state(root: Path) -> None:
    """Do not overwrite the index after a caller has started a handoff commit."""
    state_git = _state_git_status(root)
    if state_git["unmerged"]:
        raise LifecycleStateError("state-has-unmerged-index-entries")
    if state_git["staged"]:
        raise LifecycleStateError("state-is-staged-commit-or-unstage-before-update")


def _reject_installed_legacy_hooks(root: Path) -> None:
    """Refuse initialization while copied hooks from the removed runtime remain active."""
    hooks_result = _git(root, "rev-parse", "--git-path", "hooks")
    if hooks_result.returncode != 0 or not hooks_result.stdout.strip():
        raise LifecycleStateError("cannot-locate-git-hooks-directory")
    hooks_directory = Path(hooks_result.stdout.strip())
    if not hooks_directory.is_absolute():
        hooks_directory = root / hooks_directory
    markers = ("sdlc-pilot", "sdlc-guard", ".sdlc/STATE.md", ".sdlc-control/")
    installed: list[str] = []
    for name in ("pre-commit", "pre-push", "post-checkout", "sdlc-guard"):
        candidate = hooks_directory / name
        if not candidate.is_file():
            continue
        try:
            source = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise LifecycleStateError(f"cannot-read-git-hook:{name}") from exc
        if name == "sdlc-guard" or any(marker in source for marker in markers):
            installed.append(name)
    if installed:
        names = ",".join(installed)
        raise LifecycleStateError(
            f"unsupported-sdlc-hooks-installed:{names};remove-manually-from:{hooks_directory}",
        )


def _code_head(
    root: Path, state: Mapping[str, object], feature: Mapping[str, object],
) -> str:
    """Return HEAD when code is clean and lifecycle handoff files are tracked.

    ``.sdlc-v1`` is excluded from code cleanliness so validation evidence and
    progress can be committed after the implementation without invalidating
    the tested code tree.
    """
    _require_git_repository(root)
    _require_tracked_state(root)
    _require_tracked_feature_contexts(root, state, feature)
    dirty = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ".",
        f":(glob,exclude){STATE_DIRECTORY}/**",
    )
    if dirty.returncode != 0:
        raise LifecycleStateError("cannot-check-worktree-status")
    if dirty.stdout:
        raise LifecycleStateError("validation-and-release-require-clean-worktree")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    if head.returncode != 0:
        raise LifecycleStateError("validation-and-release-require-head-commit")
    return head.stdout.strip()


def _implementation_unchanged(root: Path, validated_commit: str, current_head: str) -> bool:
    result = _git(
        root,
        "diff",
        "--quiet",
        validated_commit,
        current_head,
        "--",
        ".",
        f":(glob,exclude){STATE_DIRECTORY}/**",
    )
    if result.returncode not in {0, 1}:
        raise LifecycleStateError("cannot-compare-validation-implementation")
    return result.returncode == 0


@contextmanager
def _locked_state(root: Path) -> Iterator[tuple[dict[str, object], Path, tuple[int, int, int, int]]]:
    """Lock the current state inode; retry if another writer replaced it first."""
    path = _state_file(root, require_exists=True)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(4):
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise LifecycleStateError("cannot-open-state") from exc
        locked = False
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise LifecycleStateError("state-file-not-regular")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            identity = _state_identity(path)
            if (info.st_dev, info.st_ino) != identity[:2]:
                continue
            state = _decode_state(_read_descriptor(descriptor))
            yield state, path, identity
            return
        finally:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
    raise LifecycleStateError("state-changed-during-lock-acquisition")


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(directory, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise LifecycleStateError("cannot-sync-state-directory") from exc


def _write_replacement(
    root: Path, path: Path, state: Mapping[str, object], *, expected_identity: tuple[int, int, int, int],
) -> None:
    """Atomically replace an unchanged state file while holding its advisory lock."""
    checked = _validate_state(state)
    if _state_identity(path) != expected_identity:
        raise LifecycleStateError("state-changed-before-write")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(checked, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if _state_identity(path) != expected_identity:
            raise LifecycleStateError("state-changed-before-replace")
        os.replace(temporary_name, path)
        _sync_directory(path.parent)
    except OSError as exc:
        raise LifecycleStateError("cannot-write-state") from exc
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _create_state(path: Path, state: Mapping[str, object]) -> None:
    checked = _validate_state(state)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise LifecycleStateError("state-already-initialized") from exc
    except OSError as exc:
        raise LifecycleStateError("cannot-create-state") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(checked, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise LifecycleStateError("cannot-write-state") from exc
    _sync_directory(path.parent)


def initialize(repo: str | os.PathLike[str] = ".", *, at: str | None = None) -> dict[str, object]:
    root = _repo_root(repo)
    _ensure_state_can_be_tracked(root)
    _reject_installed_legacy_hooks(root)
    path = _state_file(root, require_exists=False)
    if path.exists():
        raise LifecycleStateError("state-already-initialized")
    path = _state_directory(root, create=True) / STATE_FILENAME
    if at is not None:
        _timestamp(at, label="state-initialized-at")
    state = _empty_state()
    _create_state(path, state)
    return status(root)


def load(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    return deepcopy(_read_state(_repo_root(repo)))


def _mutate(
    repo: str | os.PathLike[str], operation: Callable[[dict[str, object], str], dict[str, object]], *, at: str | None,
) -> dict[str, object]:
    root = _repo_root(repo)
    _ensure_state_can_be_tracked(root)
    with _locked_state(root) as (state, path, identity):
        _reject_staged_state(root)
        timestamp = _timestamp(at, label="operation-at") if at is not None else _now()
        result = operation(state, timestamp)
        _write_replacement(root, path, state, expected_identity=identity)
        return result


def _requirement(state: Mapping[str, object], requirement_id: str) -> dict[str, object]:
    requirements = state["requirements"]
    assert isinstance(requirements, dict)
    record = requirements.get(requirement_id)
    if not isinstance(record, dict):
        raise LifecycleStateError(f"requirement-not-found:{requirement_id}")
    return record


def _feature(state: Mapping[str, object], feature_id: str) -> dict[str, object]:
    features = state["features"]
    assert isinstance(features, dict)
    record = features.get(feature_id)
    if not isinstance(record, dict):
        raise LifecycleStateError(f"feature-not-found:{feature_id}")
    return record


def capture_requirement(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str, title: str,
    description: str = "", domain: str = "general", priority: str = "P2",
    product_context_ref: str, depends_on: Sequence[str] = (), at: str | None = None,
) -> dict[str, object]:
    root = _repo_root(repo)
    requirement_id = _id(requirement_id, label="requirement-id")
    title = _text(title, label="requirement-title")
    description = _text(description, label="requirement-description", allow_empty=True)
    domain = _text(domain, label="requirement-domain")
    product_context_ref = _context_ref(
        product_context_ref, label="requirement-product-context-ref",
    )
    _require_context_file(root, product_context_ref, label="product-context")
    if priority not in _PRIORITIES:
        raise LifecycleStateError("invalid-requirement-priority")
    dependencies = [_id(item, label="requirement-depends-on-item") for item in depends_on]
    if len(set(dependencies)) != len(dependencies) or requirement_id in dependencies:
        raise LifecycleStateError("invalid-requirement-depends-on")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirements = state["requirements"]
        assert isinstance(requirements, dict)
        if requirement_id in requirements:
            raise LifecycleStateError(f"requirement-already-exists:{requirement_id}")
        missing = [item for item in dependencies if item not in requirements]
        if missing:
            raise LifecycleStateError("unknown-requirement-dependency:" + ",".join(sorted(missing)))
        record = {
            "id": requirement_id, "title": title, "description": description, "domain": domain,
            "priority": priority, "status": "captured", "depends_on": list(dependencies), "feature_id": None,
            "product_context_ref": product_context_ref,
            "created_at": timestamp, "updated_at": timestamp,
        }
        requirements[requirement_id] = record
        return {"operation": "capture-requirement", "requirement": deepcopy(record)}

    return _mutate(root, operation, at=at)


def mark_requirement_ready(*, repo: str | os.PathLike[str] = ".", requirement_id: str, at: str | None = None) -> dict[str, object]:
    requirement_id = _id(requirement_id, label="requirement-id")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirement = _requirement(state, requirement_id)
        if requirement["status"] != "captured":
            raise LifecycleStateError(f"requirement-not-captured:{requirement_id}")
        unmet = [item for item in requirement["depends_on"] if _requirement(state, item)["status"] != "released"]
        if unmet:
            raise LifecycleStateError("requirement-dependencies-not-released:" + ",".join(sorted(unmet)))
        requirement["status"] = "ready"
        requirement["updated_at"] = timestamp
        return {"operation": "mark-requirement-ready", "requirement": deepcopy(requirement)}

    return _mutate(repo, operation, at=at)


def start_feature(
    *, repo: str | os.PathLike[str] = ".", requirement_id: str, feature_id: str, branch: str,
    engineering_context_ref: str, at: str | None = None,
) -> dict[str, object]:
    root = _repo_root(repo)
    requirement_id = _id(requirement_id, label="requirement-id")
    feature_id = _id(feature_id, label="feature-id")
    branch = _text(branch, label="feature-branch")
    engineering_context_ref = _context_ref(
        engineering_context_ref, label="feature-engineering-context-ref",
    )
    _require_context_file(root, engineering_context_ref, label="engineering-context")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        requirement = _requirement(state, requirement_id)
        features = state["features"]
        assert isinstance(features, dict)
        if requirement["status"] != "ready" or requirement["feature_id"] is not None:
            raise LifecycleStateError(f"requirement-not-ready-for-feature:{requirement_id}")
        if feature_id in features:
            raise LifecycleStateError(f"feature-already-exists:{feature_id}")
        record = {
            "id": feature_id, "requirement_id": requirement_id, "branch": branch, "status": "planned", "tasks": {},
            "engineering_context_ref": engineering_context_ref,
            "validation": {"result": "pending", "command": None, "commit": None, "at": None},
            "review": {"decision": "pending", "by": None, "at": None},
            "release": {"status": "pending", "commit": None, "at": None},
            "created_at": timestamp, "updated_at": timestamp,
        }
        features[feature_id] = record
        requirement["feature_id"] = feature_id
        requirement["status"] = "in_delivery"
        requirement["updated_at"] = timestamp
        return {"operation": "start-feature", "feature": deepcopy(record), "requirement": deepcopy(requirement)}

    return _mutate(root, operation, at=at)


def add_task(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, task_id: str, title: str,
    depends_on: Sequence[str] = (), at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    task_id = _id(task_id, label="task-id")
    title = _text(title, label="task-title")
    dependencies = [_id(item, label="task-depends-on-item") for item in depends_on]
    if len(set(dependencies)) != len(dependencies) or task_id in dependencies:
        raise LifecycleStateError("invalid-task-depends-on")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        if feature["status"] not in {"planned", "in_progress"}:
            raise LifecycleStateError(f"feature-not-open-for-task:{feature_id}")
        tasks = feature["tasks"]
        assert isinstance(tasks, dict)
        if task_id in tasks:
            raise LifecycleStateError(f"task-already-exists:{feature_id}/{task_id}")
        missing = [item for item in dependencies if item not in tasks]
        if missing:
            raise LifecycleStateError("unknown-task-dependency:" + feature_id + "/" + ",".join(sorted(missing)))
        record = {"id": task_id, "title": title, "status": "todo", "depends_on": list(dependencies), "updated_at": timestamp}
        tasks[task_id] = record
        feature["updated_at"] = timestamp
        return {"operation": "add-task", "task": deepcopy(record), "feature_id": feature_id}

    return _mutate(repo, operation, at=at)


def _reset_delivery_checks(feature: dict[str, object]) -> None:
    feature["validation"] = {"result": "pending", "command": None, "commit": None, "at": None}
    feature["review"] = {"decision": "pending", "by": None, "at": None}
    feature["release"] = {"status": "pending", "commit": None, "at": None}


def set_task_status(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, task_id: str, status: str,
    at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    task_id = _id(task_id, label="task-id")
    if status not in _TASK_STATUSES:
        raise LifecycleStateError("invalid-task-status")

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        if feature["status"] in {"released", "cancelled"}:
            raise LifecycleStateError(f"feature-not-open-for-task:{feature_id}")
        tasks = feature["tasks"]
        assert isinstance(tasks, dict)
        task = tasks.get(task_id)
        if not isinstance(task, dict):
            raise LifecycleStateError(f"task-not-found:{feature_id}/{task_id}")
        old_status = str(task["status"])
        if status == old_status:
            return {"operation": "set-task-status", "idempotent": True, "task": deepcopy(task), "feature_id": feature_id}
        if status not in _TASK_TRANSITIONS[old_status]:
            raise LifecycleStateError(f"invalid-task-transition:{old_status}->{status}")
        if status in {"in_progress", "done"}:
            unmet = [item for item in task["depends_on"] if tasks[item]["status"] != "done"]
            if unmet:
                raise LifecycleStateError("task-dependencies-not-done:" + feature_id + "/" + ",".join(sorted(unmet)))
        task["status"] = status
        task["updated_at"] = timestamp
        if status != "done" or old_status == "done":
            _reset_delivery_checks(feature)
        feature["status"] = "in_progress"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "in_delivery"
        requirement["updated_at"] = timestamp
        return {"operation": "set-task-status", "idempotent": False, "task": deepcopy(task), "feature_id": feature_id}

    return _mutate(repo, operation, at=at)


def record_validation(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, result: str, command: str | None = None,
    commit: str | None = None, at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    if result not in {"pass", "fail"}:
        raise LifecycleStateError("invalid-feature-validation-result")
    command = None if command is None else _text(command, label="feature-validation-command")
    supplied_commit = None if commit is None else _text(commit, label="feature-validation-commit")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        head = _code_head(root, state, feature)
        if supplied_commit is not None and supplied_commit != head:
            raise LifecycleStateError("validation-commit-does-not-match-head")
        if feature["status"] in {"released", "cancelled"}:
            raise LifecycleStateError(f"feature-not-open-for-validation:{feature_id}")
        tasks = feature["tasks"]
        assert isinstance(tasks, dict)
        active_tasks = [task for task in tasks.values() if task["status"] != "cancelled"]
        if result == "pass" and (
            not active_tasks or any(task["status"] != "done" for task in active_tasks)
        ):
            raise LifecycleStateError(f"feature-has-incomplete-active-tasks:{feature_id}")
        feature["validation"] = {"result": result, "command": command, "commit": head, "at": timestamp}
        feature["review"] = {"decision": "pending", "by": None, "at": None}
        feature["release"] = {"status": "pending", "commit": None, "at": None}
        feature["status"] = "validated" if result == "pass" else "in_progress"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "validated" if result == "pass" else "in_delivery"
        requirement["updated_at"] = timestamp
        return {"operation": "record-validation", "feature": deepcopy(feature)}

    return _mutate(root, operation, at=at)


def record_review(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, decision: str, by: str | None = None,
    at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    if decision not in {"approved", "changes_requested"}:
        raise LifecycleStateError("invalid-feature-review-decision")
    by = None if by is None else _text(by, label="feature-review-by")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        head = _code_head(root, state, feature)
        if feature["status"] not in {"validated", "reviewed"}:
            raise LifecycleStateError(f"feature-not-ready-for-review:{feature_id}")
        validation = feature["validation"]
        validated_commit = str(validation["commit"])
        if not _implementation_unchanged(root, validated_commit, head):
            raise LifecycleStateError("review-commit-does-not-match-validation")
        feature["review"] = {"decision": decision, "by": by, "at": timestamp}
        feature["release"] = {"status": "pending", "commit": None, "at": None}
        feature["status"] = "reviewed" if decision == "approved" else "in_progress"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "validated" if decision == "approved" else "in_delivery"
        requirement["updated_at"] = timestamp
        return {
            "operation": "record-review", "feature": deepcopy(feature),
            "requirement": deepcopy(requirement),
        }

    return _mutate(root, operation, at=at)


def record_release(
    *, repo: str | os.PathLike[str] = ".", feature_id: str, commit: str | None = None,
    at: str | None = None,
) -> dict[str, object]:
    feature_id = _id(feature_id, label="feature-id")
    supplied_commit = None if commit is None else _text(commit, label="feature-release-commit")
    root = _repo_root(repo)

    def operation(state: dict[str, object], timestamp: str) -> dict[str, object]:
        feature = _feature(state, feature_id)
        head = _code_head(root, state, feature)
        if feature["status"] != "reviewed":
            raise LifecycleStateError(f"feature-not-ready-for-release:{feature_id}")
        validation = feature["validation"]
        validated_commit = str(validation["commit"])
        if supplied_commit is not None and supplied_commit != validated_commit:
            raise LifecycleStateError("release-commit-does-not-match-validation")
        if not _implementation_unchanged(root, validated_commit, head):
            raise LifecycleStateError("release-commit-does-not-match-validation")
        feature["release"] = {
            "status": "released", "commit": validated_commit, "at": timestamp,
        }
        feature["status"] = "released"
        feature["updated_at"] = timestamp
        requirement = _requirement(state, str(feature["requirement_id"]))
        requirement["status"] = "released"
        requirement["updated_at"] = timestamp
        return {"operation": "record-release", "feature": deepcopy(feature), "requirement": deepcopy(requirement)}

    return _mutate(root, operation, at=at)


def readyqueue(repo: str | os.PathLike[str] = ".") -> list[dict[str, object]]:
    state = load(repo)
    requirements = state["requirements"]
    assert isinstance(requirements, dict)
    result = [{
        "requirement_id": requirement_id,
        "title": record["title"],
        "priority": record["priority"],
        "domain": record["domain"],
        "status": record["status"],
        "product_context_ref": record["product_context_ref"],
    } for requirement_id, record in requirements.items()
              if record["status"] == "ready" and record["feature_id"] is None]
    result.sort(key=lambda item: (_PRIORITY_ORDER[str(item["priority"])], str(item["requirement_id"])))
    return result


def product_projection(*, repo: str | os.PathLike[str] = ".", requirement_id: str) -> dict[str, object]:
    state = load(repo)
    requirement = _requirement(state, _id(requirement_id, label="requirement-id"))
    feature_id = requirement["feature_id"]
    feature = None if feature_id is None else _feature(state, str(feature_id))
    return {"requirement": deepcopy(requirement), "feature": deepcopy(feature)}


def feature_projection(*, repo: str | os.PathLike[str] = ".", feature_id: str) -> dict[str, object]:
    state = load(repo)
    feature = _feature(state, _id(feature_id, label="feature-id"))
    requirement = _requirement(state, str(feature["requirement_id"]))
    return {"feature": deepcopy(feature), "requirement": deepcopy(requirement)}


def _feature_next_stage(feature: Mapping[str, object]) -> tuple[str, str]:
    status_value = str(feature["status"])
    tasks = feature["tasks"]
    review = feature["review"]
    assert isinstance(tasks, Mapping) and isinstance(review, Mapping)
    if status_value == "planned":
        if not tasks:
            return "plan", "feature-needs-task-plan"
        return "build", "planned-tasks-are-ready"
    if status_value == "in_progress":
        if review["decision"] == "changes_requested":
            return "build", "review-requested-changes"
        if any(task["status"] == "blocked" for task in tasks.values()):
            return "build", "blocked-tasks-require-work"
        active_tasks = [task for task in tasks.values() if task["status"] != "cancelled"]
        if active_tasks and all(task["status"] == "done" for task in active_tasks):
            return "validate", "all-active-tasks-are-complete"
        return "build", "feature-has-incomplete-tasks"
    if status_value == "validated":
        return "review", "validation-passed"
    if status_value == "reviewed":
        return "ship", "review-approved"
    raise LifecycleStateError(f"feature-has-no-next-stage:{feature['id']}")


def next_action(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    """Return one deterministic stage, or explicit candidates when selection is needed."""
    state = load(repo)
    requirements = state["requirements"]
    features = state["features"]
    assert isinstance(requirements, dict) and isinstance(features, dict)

    active_features = [
        feature for feature in features.values()
        if feature["status"] not in {"released", "cancelled"}
    ]
    active_features.sort(key=lambda feature: (
        _PRIORITY_ORDER[str(requirements[str(feature["requirement_id"])]["priority"])],
        str(feature["requirement_id"]),
        str(feature["id"]),
    ))
    if len(active_features) > 1:
        candidates = []
        for feature in active_features:
            stage, _ = _feature_next_stage(feature)
            candidates.append({
                "requirement_id": feature["requirement_id"],
                "feature_id": feature["id"],
                "stage": stage,
            })
        return {
            "stage": "needs_selection", "requirement_id": None, "feature_id": None,
            "reason": "multiple-active-features", "candidates": candidates,
        }
    if active_features:
        feature = active_features[0]
        stage, reason = _feature_next_stage(feature)
        return {
            "stage": stage, "requirement_id": feature["requirement_id"], "feature_id": feature["id"],
            "reason": reason, "candidates": [],
        }

    def pending(status_value: str) -> list[dict[str, object]]:
        records = [
            requirement for requirement in requirements.values()
            if requirement["status"] == status_value and requirement["feature_id"] is None
        ]
        records.sort(key=lambda requirement: (
            _PRIORITY_ORDER[str(requirement["priority"])], str(requirement["id"]),
        ))
        return records

    for requirement_status, stage, reason in (
        ("ready", "plan", "requirement-ready-for-engineering"),
        ("captured", "spec", "requirement-needs-product-definition"),
    ):
        records = pending(requirement_status)
        if len(records) > 1:
            return {
                "stage": "needs_selection", "requirement_id": None, "feature_id": None,
                "reason": f"multiple-{requirement_status}-requirements",
                "candidates": [
                    {"requirement_id": requirement["id"], "feature_id": None, "stage": stage}
                    for requirement in records
                ],
            }
        if records:
            return {
                "stage": stage, "requirement_id": records[0]["id"], "feature_id": None,
                "reason": reason, "candidates": [],
            }

    if requirements:
        return {
            "stage": "done", "requirement_id": None, "feature_id": None,
            "reason": "all-requirements-are-terminal", "candidates": [],
        }
    return {
        "stage": "intake", "requirement_id": None, "feature_id": None,
        "reason": "no-requirements-captured", "candidates": [],
    }


def status(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    root = _repo_root(repo)
    state = _read_state(root)
    requirements = state["requirements"]
    features = state["features"]
    assert isinstance(requirements, dict) and isinstance(features, dict)
    git_status = _state_git_status(root)
    return {
        "state_format": STATE_FORMAT,
        "state_version": STATE_VERSION,
        "state_path": str(_state_directory(root, create=False) / STATE_FILENAME),
        "git": git_status,
        "requirements": len(requirements),
        "features": len(features),
        "ready_requirements": len(readyqueue(root)),
    }


def _split_ids(value: str) -> list[str]:
    if not value:
        return []
    result = [item.strip() for item in value.split(",") if item.strip()]
    if len(set(result)) != len(result):
        raise LifecycleStateError("duplicate-id-list-item")
    return result


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git-tracked lightweight SDLC lifecycle state")
    parser.add_argument("--repo", default=".", help="target repository root")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create .sdlc-v1/state.json")
    init.add_argument("--at")
    commands.add_parser("status", help="show state summary")
    capture = commands.add_parser("capture-requirement", help="capture a product requirement")
    capture.add_argument("--id", required=True)
    capture.add_argument("--title", required=True)
    capture.add_argument("--description", default="")
    capture.add_argument("--domain", default="general")
    capture.add_argument("--priority", default="P2", choices=sorted(_PRIORITIES))
    capture.add_argument("--product-context-ref", required=True)
    capture.add_argument("--depends-on", default="", help="comma-separated requirement IDs")
    capture.add_argument("--at")
    ready = commands.add_parser("mark-requirement-ready", help="mark a captured requirement ready for delivery")
    ready.add_argument("--requirement-id", required=True)
    ready.add_argument("--at")
    start = commands.add_parser("start-feature", help="link a ready requirement to one feature branch")
    start.add_argument("--requirement-id", required=True)
    start.add_argument("--feature-id", required=True)
    start.add_argument("--branch", required=True)
    start.add_argument("--engineering-context-ref", required=True)
    start.add_argument("--at")
    add = commands.add_parser("add-task", help="add a delivery task")
    add.add_argument("--feature-id", required=True)
    add.add_argument("--task-id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--depends-on", default="", help="comma-separated task IDs")
    add.add_argument("--at")
    task = commands.add_parser("set-task-status", help="update one task")
    task.add_argument("--feature-id", required=True)
    task.add_argument("--task-id", required=True)
    task.add_argument("--status", required=True, choices=sorted(_TASK_STATUSES))
    task.add_argument("--at")
    validation = commands.add_parser("record-validation", help="record the feature test result")
    validation.add_argument("--feature-id", required=True)
    validation.add_argument("--result", required=True, choices=("pass", "fail"))
    validation.add_argument("--test-command")
    validation.add_argument("--commit")
    validation.add_argument("--at")
    review = commands.add_parser("record-review", help="record the feature review result")
    review.add_argument("--feature-id", required=True)
    review.add_argument("--decision", required=True, choices=("approved", "changes_requested"))
    review.add_argument("--by")
    review.add_argument("--at")
    release = commands.add_parser("record-release", help="record a completed release")
    release.add_argument("--feature-id", required=True)
    release.add_argument("--commit")
    release.add_argument("--at")
    commands.add_parser("readyqueue", help="list requirements ready for delivery")
    commands.add_parser("next", help="show the next lifecycle stage")
    product = commands.add_parser("product-projection", help="show one requirement and its feature")
    product.add_argument("--requirement-id", required=True)
    feature = commands.add_parser("feature-projection", help="show one feature and its requirement")
    feature.add_argument("--feature-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(args.repo, at=args.at)
        elif args.command == "status":
            result = status(args.repo)
        elif args.command == "capture-requirement":
            result = capture_requirement(
                repo=args.repo, requirement_id=args.id, title=args.title, description=args.description,
                domain=args.domain, priority=args.priority, product_context_ref=args.product_context_ref,
                depends_on=_split_ids(args.depends_on), at=args.at,
            )
        elif args.command == "mark-requirement-ready":
            result = mark_requirement_ready(repo=args.repo, requirement_id=args.requirement_id, at=args.at)
        elif args.command == "start-feature":
            result = start_feature(
                repo=args.repo, requirement_id=args.requirement_id, feature_id=args.feature_id,
                branch=args.branch, engineering_context_ref=args.engineering_context_ref, at=args.at,
            )
        elif args.command == "add-task":
            result = add_task(
                repo=args.repo, feature_id=args.feature_id, task_id=args.task_id, title=args.title,
                depends_on=_split_ids(args.depends_on), at=args.at,
            )
        elif args.command == "set-task-status":
            result = set_task_status(
                repo=args.repo, feature_id=args.feature_id, task_id=args.task_id, status=args.status, at=args.at,
            )
        elif args.command == "record-validation":
            result = record_validation(
                repo=args.repo, feature_id=args.feature_id, result=args.result, command=args.test_command,
                commit=args.commit, at=args.at,
            )
        elif args.command == "record-review":
            result = record_review(
                repo=args.repo, feature_id=args.feature_id, decision=args.decision, by=args.by, at=args.at,
            )
        elif args.command == "record-release":
            result = record_release(repo=args.repo, feature_id=args.feature_id, commit=args.commit, at=args.at)
        elif args.command == "readyqueue":
            result = readyqueue(args.repo)
        elif args.command == "next":
            result = next_action(args.repo)
        elif args.command == "product-projection":
            result = product_projection(repo=args.repo, requirement_id=args.requirement_id)
        else:
            result = feature_projection(repo=args.repo, feature_id=args.feature_id)
    except LifecycleStateError as exc:
        print(f"lifecycle-state-error: {exc}", file=sys.stderr)
        return 2
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LifecycleStateError", "STATE_DIRECTORY", "STATE_FILENAME", "STATE_FORMAT", "STATE_VERSION",
    "add_task", "capture_requirement", "feature_projection", "initialize", "load", "main",
    "mark_requirement_ready", "next_action", "product_projection", "readyqueue", "record_release",
    "record_review", "record_validation", "set_task_status", "start_feature", "state_path", "status",
]
