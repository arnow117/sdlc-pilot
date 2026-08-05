#!/usr/bin/env python3
"""Strict, file-backed storage for the SDLC control ledger.

The module deliberately depends only on the Python standard library and Git.  It
does not change the caller's checkout when reading a control ref.
"""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from typing import Any, Callable

import preview_scope


SCHEMA_VERSION = 1
CONTROL_DIR = ".sdlc-control"
CONTROL_BRANCH = "sdlc-control"
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ControlError(RuntimeError):
    """Base class for deterministic control-ledger failures."""


class SchemaError(ControlError):
    """A record or path does not conform to schema v1."""


class ConflictError(ControlError):
    """The requested update conflicts with current durable state."""


class MissingRecordError(ControlError):
    """A requested control record or artifact does not exist."""


class ConcurrentControlUpdate(ConflictError):
    """The control ref changed after a transaction selected its base."""


class ClaimConflict(ConcurrentControlUpdate):
    def __init__(self, leaf_id: str, owner: str, feature_id: str, feature_branch: str):
        self.leaf_id = leaf_id
        self.owner = owner
        self.feature_id = feature_id
        self.feature_branch = feature_branch
        super().__init__(
            f"active-claim: leaf={leaf_id} owner={owner} feature={feature_id} "
            f"branch={feature_branch}")


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        items = []
        for item in value:
            text = str(item)
            if any(ch in text for ch in (",", "[", "]", "\n", "\r")):
                raise SchemaError(f"inline-list item is not portable: {text!r}")
            items.append(text)
        return "[" + ", ".join(items) + "]"
    if value is None:
        return "(none)"
    text = str(value)
    if "\n" in text or "\r" in text:
        raise SchemaError("frontmatter scalar must be one line")
    if text.startswith("[") and text.endswith("]"):
        raise SchemaError("scalar is ambiguous with an inline list")
    return text


def render_record(record: dict[str, Any], *, body: str | None = None,
                  field_order: list[str] | None = None) -> str:
    """Render deterministic flat frontmatter plus an optional Markdown body."""
    fields = {k: v for k, v in record.items() if not k.startswith("_")}
    if body is None:
        body = str(record.get("_body", ""))
    preferred = field_order or ["schema_version", "record_type"]
    ordered = [k for k in preferred if k in fields]
    ordered.extend(sorted(k for k in fields if k not in ordered))
    lines = ["---"]
    for key in ordered:
        if not _KEY_RE.fullmatch(key):
            raise SchemaError(f"invalid frontmatter key: {key!r}")
        lines.append(f"{key}: {_format_value(fields[key])}")
    lines.append("---")
    text = "\n".join(lines) + "\n"
    if body:
        text += "\n" + body.rstrip("\n") + "\n"
    return text


def parse_record(text: str, *, path: str = "<memory>") -> dict[str, Any]:
    """Parse schema-v1 flat frontmatter, rejecting ambiguous YAML features."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise SchemaError(f"{path}: missing opening frontmatter delimiter")
    record: dict[str, Any] = {}
    closing = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            closing = index
            break
        if not line:
            continue
        if line[:1].isspace() or ":" not in line:
            raise SchemaError(f"{path}:{index + 1}: nested or malformed frontmatter")
        key, value = line.split(":", 1)
        if not _KEY_RE.fullmatch(key):
            raise SchemaError(f"{path}:{index + 1}: invalid key {key!r}")
        if key in record:
            raise SchemaError(f"{path}:{index + 1}: duplicate key {key!r}")
        value = value.strip()
        if value.startswith("[") or value.endswith("]"):
            if not (value.startswith("[") and value.endswith("]")):
                raise SchemaError(f"{path}:{index + 1}: malformed inline list")
            inner = value[1:-1].strip()
            if "[" in inner or "]" in inner:
                raise SchemaError(f"{path}:{index + 1}: nested lists are unsupported")
            record[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        elif value == "true":
            record[key] = True
        elif value == "false":
            record[key] = False
        else:
            record[key] = value
    if closing is None:
        raise SchemaError(f"{path}: missing closing frontmatter delimiter")
    record["_body"] = "\n".join(lines[closing + 1:]).strip("\n")
    return record


def validate_id(value: str, *, field: str = "id") -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or ".." in value:
        raise SchemaError(f"invalid {field}: {value!r}")
    return value


def safe_record_path(root: str | os.PathLike[str], *parts: str) -> Path:
    """Resolve a record path while rejecting traversal and symlink parents."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    if root_path.is_symlink():
        raise SchemaError(f"control root cannot be a symlink: {root_path}")
    for part in parts:
        if (not isinstance(part, str) or not part or part in (".", "..")
                or os.path.isabs(part) or "/" in part or "\\" in part or ".." in part):
            raise SchemaError(f"unsafe control path component: {part!r}")
    current = root_path
    for part in parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise SchemaError(f"symlink parent is forbidden: {current}")
    target = root_path.joinpath(*parts)
    if target.exists() and target.is_symlink():
        raise SchemaError(f"record path cannot be a symlink: {target}")
    root_real = root_path.resolve()
    target_parent = target.parent.resolve(strict=False)
    try:
        target_parent.relative_to(root_real)
    except ValueError as exc:
        raise SchemaError(f"record escapes control root: {target}") from exc
    return target


def write_record(path: str | os.PathLike[str], record: dict[str, Any], *,
                 body: str | None = None, immutable: bool = False) -> bool:
    """Atomically write a record; immutable writes are idempotent by content."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.parent.is_symlink():
        raise SchemaError(f"refusing to write through symlink: {target}")
    rendered = render_record(record, body=body)
    if immutable and target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing == rendered:
            return False
        raise ConflictError(f"immutable record already exists with different content: {target}")
    if immutable:
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            existing = target.read_text(encoding="utf-8")
            if existing == rendered:
                return False
            raise ConflictError(f"immutable record already exists with different content: {target}")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        return True
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return True


def write_text_atomic(path: str | os.PathLike[str], text: str, *,
                      immutable: bool = False) -> bool:
    """Atomically write a non-record artifact such as an approved plan snapshot."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.parent.is_symlink():
        raise SchemaError(f"refusing to write through symlink: {target}")
    if immutable and target.exists():
        if target.read_text(encoding="utf-8") == text:
            return False
        raise ConflictError(f"immutable artifact already exists with different content: {target}")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if immutable and target.exists():
            if target.read_text(encoding="utf-8") == text:
                return False
            raise ConflictError(f"immutable artifact already exists with different content: {target}")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return True


def read_record(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    if target.is_symlink():
        raise SchemaError(f"record cannot be a symlink: {target}")
    record = parse_record(target.read_text(encoding="utf-8"), path=str(target))
    return record


def _empty_snapshot(mode: str, control_root: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "control_root": control_root,
        "requests_by_id": {},
        "requirements_by_id": {},
        "claims_by_leaf": {},
        "features_by_id": {},
        "tasks_by_feature": {},
        "evidence_by_task": {},
        "feature_evidence_by_feature": {},
        "local_state": None,
        "warnings": [],
    }


def _parse_legacy_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    record: dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            record[key.strip()] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        else:
            record[key.strip()] = value
    return record


def _load_legacy_requirements(snapshot: dict[str, Any], root: str | os.PathLike[str] | None) -> None:
    if not root or not Path(root).is_dir():
        return
    for path in sorted(Path(root).rglob("*.md")):
        if path.name.startswith("_") or path.is_symlink():
            continue
        record = _parse_legacy_frontmatter(path.read_text(encoding="utf-8"))
        leaf_id = record.get("id")
        if leaf_id:
            record["_path"] = str(path.relative_to(root))
            snapshot["requirements_by_id"][leaf_id] = record


def _read_local_state(path: str | os.PathLike[str] | None) -> dict[str, str] | None:
    if not path or not Path(path).is_file():
        return None
    result: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _repo_has_control_ref(repo_root: str | os.PathLike[str] | None) -> bool:
    if not repo_root:
        return False
    for ref in (f"refs/remotes/origin/{CONTROL_BRANCH}", f"refs/heads/{CONTROL_BRANCH}"):
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show-ref", "--verify", "--quiet", ref],
            capture_output=True,
        )
        if proc.returncode == 0:
            return True
    return False


def load_control_snapshot(control_root: str | os.PathLike[str] | None, *,
                          repo_root: str | os.PathLike[str] | None = None,
                          current_heads: dict[str, str] | None = None,
                          legacy_requirements_root: str | os.PathLike[str] | None = None,
                          local_state_path: str | os.PathLike[str] | None = None,
                          mode: str | None = None) -> dict[str, Any]:
    """Load normalized control records without creating or migrating missing data."""
    root = Path(control_root) if control_root else None
    if root is None or not root.is_dir():
        snapshot = _empty_snapshot("legacy", str(root) if root else None)
        _load_legacy_requirements(snapshot, legacy_requirements_root)
        snapshot["local_state"] = _read_local_state(local_state_path)
        return snapshot
    selected_mode = mode or (
        "shared-control" if _repo_has_control_ref(repo_root) else "local-serial")
    snapshot = _empty_snapshot(selected_mode, str(root))

    def load_group(directory: str, expected_type: str, id_key: str,
                   destination: dict[str, Any], *, recursive: bool = True) -> None:
        base = root / directory
        if not base.is_dir():
            return
        iterator = base.rglob("*.md") if recursive else base.glob("*.md")
        for path in sorted(iterator):
            if path.is_symlink() or (expected_type == "feature" and path.name == "plan.md"):
                continue
            try:
                record = read_record(path)
            except (OSError, SchemaError) as exc:
                snapshot["warnings"].append(f"invalid-record:{path.relative_to(root)}:{exc}")
                continue
            record["_path"] = str(path.relative_to(root))
            if record.get("record_type") != expected_type:
                snapshot["warnings"].append(
                    f"wrong-record-type:{record['_path']}:{record.get('record_type')}")
                continue
            record_id = record.get(id_key) or record.get("id")
            if not record_id:
                snapshot["warnings"].append(f"missing-id:{record['_path']}:{id_key}")
                continue
            if record_id in destination:
                snapshot["warnings"].append(f"duplicate-id:{expected_type}:{record_id}")
                continue
            destination[record_id] = record

    load_group("requests", "request", "request_id", snapshot["requests_by_id"])
    load_group("requirements", "requirement", "id", snapshot["requirements_by_id"])
    load_group("claims", "claim", "leaf_id", snapshot["claims_by_leaf"], recursive=False)
    load_group("features", "feature", "feature_id", snapshot["features_by_id"], recursive=False)

    # Task ids are only unique inside one Feature/revision.  Loading them through
    # the generic global-id map made common ids such as P1-T1 collide across
    # unrelated Features and silently dropped the later record.
    task_base = root / "tasks"
    task_keys: set[tuple[str, str, str]] = set()
    if task_base.is_dir():
        for path in sorted(task_base.rglob("*.md")):
            if path.is_symlink():
                continue
            try:
                record = read_record(path)
            except (OSError, SchemaError) as exc:
                snapshot["warnings"].append(
                    f"invalid-record:{path.relative_to(root)}:{exc}")
                continue
            record["_path"] = str(path.relative_to(root))
            if record.get("record_type") != "task":
                snapshot["warnings"].append(
                    f"wrong-record-type:{record['_path']}:{record.get('record_type')}")
                continue
            key = (str(record.get("feature_id", "")),
                   str(record.get("plan_revision", "")),
                   str(record.get("task_id", "")))
            if not all(key):
                snapshot["warnings"].append(f"missing-id:{record['_path']}:task identity")
                continue
            if key in task_keys:
                snapshot["warnings"].append(
                    f"duplicate-id:task:{key[0]}/{key[1]}/{key[2]}")
                continue
            task_keys.add(key)
            snapshot["tasks_by_feature"].setdefault(key[0], []).append(record)
    for values in snapshot["tasks_by_feature"].values():
        values.sort(key=lambda item: (str(item.get("task_id", "")), str(item.get("_path", ""))))

    evidence: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    evidence_base = root / "evidence"
    if evidence_base.is_dir():
        for path in sorted(evidence_base.rglob("*.md")):
            if path.is_symlink():
                continue
            try:
                record = read_record(path)
            except (OSError, SchemaError) as exc:
                snapshot["warnings"].append(
                    f"invalid-record:{path.relative_to(root)}:{exc}")
                continue
            record["_path"] = str(path.relative_to(root))
            if record.get("record_type") != "evidence":
                snapshot["warnings"].append(
                    f"wrong-record-type:{record['_path']}:{record.get('record_type')}")
                continue
            key = (str(record.get("feature_id", "")), str(record.get("task_id", "")),
                   str(record.get("tested_sha", "")), str(record.get("evidence_id", "")))
            if not all(key):
                snapshot["warnings"].append(
                    f"missing-id:{record['_path']}:evidence identity")
                continue
            if key in evidence:
                snapshot["warnings"].append(
                    f"duplicate-id:evidence:{'/'.join(key)}")
                continue
            evidence[key] = record
    for record in evidence.values():
        feature_id = str(record.get("feature_id", ""))
        task_id = str(record.get("task_id", ""))
        if record.get("scope") in {"feature", "release"} or task_id == "_feature":
            snapshot["feature_evidence_by_feature"].setdefault(feature_id, []).append(record)
        else:
            snapshot["evidence_by_task"].setdefault(f"{feature_id}/{task_id}", []).append(record)
    for mapping in (snapshot["evidence_by_task"], snapshot["feature_evidence_by_feature"]):
        for values in mapping.values():
            values.sort(key=lambda item: (str(item.get("created_at", "")),
                                          str(item.get("evidence_id", ""))))
    snapshot["local_state"] = _read_local_state(local_state_path)

    if current_heads:
        try:
            import control  # Lazy import avoids a module cycle at import time.
            for feature_id, tasks_for_feature in snapshot["tasks_by_feature"].items():
                head = current_heads.get(feature_id)
                if not head:
                    continue
                for task in tasks_for_feature:
                    task["freshness"] = control.compute_freshness(
                        task, current_head_sha=head, repo_root=str(repo_root) if repo_root else None)
        except (ImportError, AttributeError) as exc:
            snapshot["warnings"].append(f"freshness-unavailable:{exc}")
    return snapshot


def _run_git(repo_root: str | os.PathLike[str], *args: str,
             check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise ControlError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc


def load_snapshot_from_ref(repo_root: str | os.PathLike[str], *, ref: str = CONTROL_BRANCH,
                           legacy_requirements_root: str | os.PathLike[str] | None = None,
                           local_state_path: str | os.PathLike[str] | None = None,
                           current_heads: dict[str, str] | None = None) -> dict[str, Any]:
    """Read `.sdlc-control` from a Git ref without checkout or worktree mutation."""
    exists = _run_git(repo_root, "cat-file", "-e", f"{ref}^{{commit}}")
    if exists.returncode != 0:
        snapshot = load_control_snapshot(
            None, legacy_requirements_root=legacy_requirements_root,
            local_state_path=local_state_path)
        snapshot["warnings"].append(f"control-ref-missing:{ref}")
        return snapshot
    raw = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", ref, CONTROL_DIR],
        capture_output=True,
    )
    if raw.returncode != 0:
        snapshot = load_control_snapshot(
            None, legacy_requirements_root=legacy_requirements_root,
            local_state_path=local_state_path)
        snapshot["warnings"].append(f"control-dir-missing:{ref}")
        return snapshot
    with tempfile.TemporaryDirectory(prefix="sdlc-control-read-") as tmp:
        temp_root = Path(tmp)
        with tarfile.open(fileobj=BytesIO(raw.stdout), mode="r:") as archive_file:
            for member in archive_file.getmembers():
                if not member.isfile():
                    continue
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise SchemaError(f"unsafe path in git archive: {member.name}")
                extracted = archive_file.extractfile(member)
                if extracted is None:
                    continue
                target = temp_root / member_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(extracted.read())
        return load_control_snapshot(
            temp_root / CONTROL_DIR, repo_root=None, current_heads=current_heads,
            legacy_requirements_root=legacy_requirements_root,
            local_state_path=local_state_path, mode="shared-control")


def remote_branch_sha(repo_root: str | os.PathLike[str], *, remote: str = "origin",
                      branch: str = CONTROL_BRANCH) -> str | None:
    proc = _run_git(repo_root, "ls-remote", remote, f"refs/heads/{branch}")
    if proc.returncode != 0:
        raise ControlError(proc.stderr.strip() or f"cannot read {remote}/{branch}")
    line = proc.stdout.strip()
    return line.split()[0] if line else None


def push_control_head(repo_root: str | os.PathLike[str], *, expected_remote_sha: str,
                      remote: str = "origin", branch: str = CONTROL_BRANCH) -> dict[str, Any]:
    """Plain fast-forward push; a changed remote tip raises ConflictError."""
    current = remote_branch_sha(repo_root, remote=remote, branch=branch)
    if current != expected_remote_sha:
        raise ConflictError(
            f"control-tip-changed: expected={expected_remote_sha} current={current or '(missing)'}")
    local_head = _run_git(repo_root, "rev-parse", "HEAD", check=True).stdout.strip()
    proc = _run_git(repo_root, "push", remote, f"HEAD:refs/heads/{branch}")
    if proc.returncode != 0:
        latest = remote_branch_sha(repo_root, remote=remote, branch=branch)
        raise ConflictError(
            f"control-push-rejected: expected={expected_remote_sha} current={latest or '(missing)'}")
    return {"pushed": True, "previous_sha": expected_remote_sha,
            "control_sha": local_head, "branch": branch, "remote": remote}


def git_changed_paths(repo_root: str | os.PathLike[str], from_sha: str, to_sha: str) -> list[str]:
    proc = _run_git(repo_root, "diff", "--name-only", f"{from_sha}..{to_sha}")
    if proc.returncode != 0:
        raise ControlError(proc.stderr.strip() or "git diff failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def git_is_ancestor(repo_root: str | os.PathLike[str], ancestor: str, descendant: str) -> bool | None:
    proc = _run_git(repo_root, "merge-base", "--is-ancestor", ancestor, descendant)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def run_ff_transaction(repo_root: str | os.PathLike[str], mutator: Callable[[Path], Any], *,
                       message: str, remote: str = "origin",
                       branch: str = CONTROL_BRANCH) -> dict[str, Any]:
    """Prepare, commit, and plain-push one isolated control-branch transaction."""
    fetch = _run_git(repo_root, "fetch", remote, branch)
    if fetch.returncode != 0:
        raise ControlError(fetch.stderr.strip() or f"cannot fetch {remote}/{branch}")
    remote_ref = f"refs/remotes/{remote}/{branch}"
    base = _run_git(repo_root, "rev-parse", remote_ref, check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="sdlc-control-txn-") as tmp_parent:
        worktree = Path(tmp_parent) / "worktree"
        added = _run_git(repo_root, "worktree", "add", "--detach", str(worktree), base)
        if added.returncode != 0:
            raise ControlError(added.stderr.strip() or "cannot create control worktree")
        try:
            payload = mutator(worktree / CONTROL_DIR)
            import control
            problems = control.lint(worktree / CONTROL_DIR)
            if problems:
                raise SchemaError("control lint failed: " + "; ".join(problems))
            _run_git(worktree, "add", CONTROL_DIR, check=True)
            diff = _run_git(worktree, "diff", "--cached", "--quiet")
            if diff.returncode == 0:
                return {"pushed": False, "control_sha": base, "payload": payload}
            commit = _run_git(
                worktree, "-c", "user.name=sdlc-control", "-c",
                "user.email=sdlc-control@local", "commit", "-m", message)
            if commit.returncode != 0:
                raise ControlError(commit.stderr.strip() or "control commit failed")
            pushed = push_control_head(
                worktree, expected_remote_sha=base, remote=remote, branch=branch)
            pushed["payload"] = payload
            return pushed
        finally:
            _run_git(repo_root, "worktree", "remove", "--force", str(worktree))


class GitControlStore:
    """Git-backed control ref supporting shared and repository-local CAS modes."""

    def __init__(self, repo: str | os.PathLike[str], *, remote: str = "origin",
                 branch: str = CONTROL_BRANCH, mode: str = "shared-control"):
        if mode not in {"shared-control", "local-serial"}:
            raise SchemaError(f"invalid control mode: {mode}")
        self.repo = Path(repo).resolve()
        self.remote = remote
        self.branch = branch
        self.mode = mode
        self.ref = f"refs/heads/{branch}"
        if _run_git(self.repo, "rev-parse", "--git-dir").returncode != 0:
            raise SchemaError(f"not a Git repository: {self.repo}")

    def _git(self, *args: str, input_text: str | None = None,
             env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], input=input_text,
            capture_output=True, text=True, env=env)

    def _fetch(self) -> str | None:
        sha = remote_branch_sha(self.repo, remote=self.remote, branch=self.branch)
        if not sha:
            return None
        proc = self._git(
            "fetch", self.remote,
            f"refs/heads/{self.branch}:refs/remotes/{self.remote}/{self.branch}")
        if proc.returncode != 0:
            raise ControlError(proc.stderr.strip() or "control fetch failed")
        return sha

    def current_sha(self, *, refresh: bool = True) -> str | None:
        if self.mode == "shared-control":
            if refresh:
                return self._fetch()
            ref = f"refs/remotes/{self.remote}/{self.branch}"
        else:
            ref = self.ref
        proc = self._git("rev-parse", "--verify", ref)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def _orphan_commit(self, at: str) -> str:
        meta = render_record({
            "schema_version": str(SCHEMA_VERSION), "record_type": "meta",
            "control_mode": self.mode, "control_ref": self.branch, "created_at": at,
        })
        blob = self._git("hash-object", "-w", "--stdin", input_text=meta)
        if blob.returncode != 0:
            raise ControlError(blob.stderr.strip() or "cannot write control metadata")
        with tempfile.TemporaryDirectory(prefix="sdlc-control-index-") as tmp:
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
            empty = self._git("read-tree", "--empty", env=env)
            cached = self._git(
                "update-index", "--add", "--cacheinfo",
                f"100644,{blob.stdout.strip()},{CONTROL_DIR}/meta.md", env=env)
            tree = self._git("write-tree", env=env)
            if empty.returncode or cached.returncode or tree.returncode:
                raise ControlError("cannot construct orphan control tree")
        identity = os.environ.copy()
        identity.update({
            "GIT_AUTHOR_NAME": "sdlc-control", "GIT_AUTHOR_EMAIL": "sdlc-control@local",
            "GIT_COMMITTER_NAME": "sdlc-control", "GIT_COMMITTER_EMAIL": "sdlc-control@local",
        })
        commit = self._git("commit-tree", tree.stdout.strip(), "-m", "init sdlc-control",
                           env=identity)
        if commit.returncode != 0:
            raise ControlError(commit.stderr.strip() or "cannot create control commit")
        return commit.stdout.strip()

    def initialize(self, *, at: str) -> dict[str, Any]:
        existing = self.current_sha(refresh=True)
        if existing:
            return {"initialized": False, "control_sha": existing, "mode": self.mode}
        commit = self._orphan_commit(at)
        if self.mode == "shared-control":
            pushed = self._git("push", self.remote, f"{commit}:{self.ref}")
            if pushed.returncode != 0:
                raise ConcurrentControlUpdate(pushed.stderr.strip() or "control init push failed")
            self._fetch()
        else:
            zeros = "0" * len(commit)
            updated = self._git("update-ref", self.ref, commit, zeros)
            if updated.returncode != 0:
                raise ConcurrentControlUpdate(updated.stderr.strip() or "control init CAS failed")
        return {"initialized": True, "control_sha": commit, "mode": self.mode}

    def begin(self, *, expected_control_sha: str | None = None) -> "ControlTransaction":
        current = self.current_sha(refresh=True)
        if not current:
            raise SchemaError("control ref is not initialized")
        if expected_control_sha and expected_control_sha != current:
            raise ConcurrentControlUpdate(
                f"control-tip-changed: expected={expected_control_sha} current={current}")
        return ControlTransaction(self, current)

    def snapshot(self, *, refresh: bool = True) -> dict[str, Any]:
        current = self.current_sha(refresh=refresh)
        if not current:
            snapshot = _empty_snapshot("legacy", None)
            snapshot["warnings"].append(f"control-ref-missing:{self.branch}")
            return snapshot
        ref = (f"refs/remotes/{self.remote}/{self.branch}"
               if self.mode == "shared-control" else self.ref)
        snapshot = load_snapshot_from_ref(self.repo, ref=ref)
        snapshot["mode"] = self.mode
        return snapshot

    def mutate(self, mutator: Callable[[Path], Any], *, message: str,
               expected_control_sha: str, retry_unrelated: bool = True) -> dict[str, Any]:
        """Publish one logical mutation and replay it once after an unrelated race.

        The callback is always re-run against the newly fetched snapshot; filesystem
        changes from the rejected transaction are never copied forward blindly.
        Claim collisions remain terminal and include the durable winner identity.
        """
        attempts = 0
        expected = expected_control_sha
        while True:
            with self.begin(expected_control_sha=expected) as tx:
                payload = mutator(tx.control_root)
                try:
                    published = tx.commit_and_publish(message)
                except ClaimConflict:
                    raise
                except ConcurrentControlUpdate:
                    if not retry_unrelated or attempts >= 1:
                        raise
                    current = self.current_sha(refresh=True)
                    if not current:
                        raise
                    expected = current
                    attempts += 1
                    continue
            published["payload"] = payload
            published["retries"] = attempts
            return published

    def register_plan(self, *, feature_id: str, plan_text: str,
                      expected_control_sha: str, at: str,
                      supplied_tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Publish immutable plan commit A, then revision-bound records commit B."""
        import control

        preview_scope.reject_preview(plan_text, field="plan_text", error_cls=SchemaError)
        tasks = control.parse_plan_tasks(plan_text)
        if supplied_tasks is not None and supplied_tasks != tasks:
            raise SchemaError("tasks manifest does not exactly match approved plan")
        plan_id = control.plan_content_id(plan_text)
        plan_ref = f"features/{feature_id}/plans/{plan_id}.md"

        def store_plan(root: Path) -> dict[str, Any]:
            return control.store_plan_artifact(
                root, feature_id=feature_id, plan_ref=plan_ref, plan_text=plan_text)

        first = self.mutate(
            store_plan, message=f"plan({feature_id}): store approved plan",
            expected_control_sha=expected_control_sha)
        plan_revision = str(first["control_sha"])

        def bind_records(root: Path) -> dict[str, Any]:
            return control.register_plan(
                root, feature_id=feature_id, plan_ref=plan_ref,
                plan_revision=plan_revision, plan_text=plan_text,
                tasks=tasks, at=at, require_git_revision=True)

        second = self.mutate(
            bind_records, message=f"plan({feature_id}): register tasks",
            expected_control_sha=plan_revision)
        second["plan_commit_sha"] = plan_revision
        second["plan_ref"] = plan_ref
        second["plan_payload"] = first["payload"]
        return second


class ControlTransaction:
    def __init__(self, store: GitControlStore, expected_control_sha: str):
        self.store = store
        self.expected_control_sha = expected_control_sha
        self._tmp = tempfile.TemporaryDirectory(prefix="sdlc-control-txn-")
        self.worktree = Path(self._tmp.name) / "worktree"
        created = _run_git(
            store.repo, "worktree", "add", "--detach", str(self.worktree),
            expected_control_sha)
        if created.returncode != 0:
            self._tmp.cleanup()
            raise ControlError(created.stderr.strip() or "cannot create control worktree")
        self.control_root = self.worktree / CONTROL_DIR
        self._closed = False

    def __enter__(self) -> "ControlTransaction":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        _run_git(self.store.repo, "worktree", "remove", "--force", str(self.worktree))
        self._tmp.cleanup()
        self._closed = True

    def _changed_paths(self) -> list[str]:
        tracked = _run_git(self.worktree, "diff", "--name-only", "HEAD")
        untracked = _run_git(self.worktree, "ls-files", "--others", "--exclude-standard")
        return sorted(set(
            line.strip() for output in (tracked.stdout, untracked.stdout)
            for line in output.splitlines() if line.strip()))

    def _raise_publish_conflict(self, commit: str) -> None:
        self.store.current_sha(refresh=True)
        changed = _run_git(
            self.worktree, "diff", "--name-only", self.expected_control_sha, commit,
            "--", f"{CONTROL_DIR}/claims").stdout.splitlines()
        snapshot = self.store.snapshot(refresh=False)
        for path in changed:
            leaf_id = Path(path).stem
            claim = snapshot["claims_by_leaf"].get(leaf_id)
            if claim and claim.get("status") == "active":
                raise ClaimConflict(
                    leaf_id, str(claim.get("owner")), str(claim.get("feature_id")),
                    str(claim.get("feature_branch")))
        current = self.store.current_sha(refresh=False)
        raise ConcurrentControlUpdate(
            f"control-tip-changed: expected={self.expected_control_sha} current={current}")

    def commit_and_publish(self, message: str) -> dict[str, Any]:
        paths = self._changed_paths()
        outside = [path for path in paths if not path.startswith(f"{CONTROL_DIR}/")]
        if outside:
            raise SchemaError(f"control transaction contains business paths: {outside}")
        import control  # Domain lint is loaded lazily to avoid an import cycle.
        problems = control.lint(self.control_root)
        if problems:
            raise SchemaError("control lint failed: " + "; ".join(problems))
        staged = _run_git(self.worktree, "add", "--", CONTROL_DIR)
        if staged.returncode != 0:
            raise ControlError(staged.stderr.strip() or "cannot stage control records")
        staged_paths = _run_git(self.worktree, "diff", "--cached", "--name-only").stdout.splitlines()
        if any(not path.startswith(f"{CONTROL_DIR}/") for path in staged_paths):
            raise SchemaError("staged paths escaped the control directory")
        if not staged_paths:
            return {"pushed": False, "control_sha": self.expected_control_sha,
                    "mode": self.store.mode}
        commit = _run_git(
            self.worktree, "-c", "user.name=sdlc-control", "-c",
            "user.email=sdlc-control@local", "commit", "-m", message)
        if commit.returncode != 0:
            raise ControlError(commit.stderr.strip() or "control commit failed")
        commit_sha = _run_git(self.worktree, "rev-parse", "HEAD", check=True).stdout.strip()
        if self.store.mode == "shared-control":
            publish = _run_git(
                self.worktree, "push", self.store.remote,
                f"{commit_sha}:refs/heads/{self.store.branch}")
        else:
            publish = _run_git(
                self.worktree, "update-ref", self.store.ref, commit_sha,
                self.expected_control_sha)
        if publish.returncode != 0:
            self._raise_publish_conflict(commit_sha)
        return {"pushed": True, "control_sha": commit_sha,
                "previous_sha": self.expected_control_sha, "mode": self.store.mode}
