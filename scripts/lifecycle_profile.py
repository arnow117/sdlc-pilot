#!/usr/bin/env python3
"""Resolve and persist the SDLC lifecycle selected for one target repository.

The profile is deliberately small and versioned.  It is the only source for a
project's lifecycle choice once an SDLC artifact exists: legacy state, preview
output, or a dual ledger must never cause the router to guess a different
runtime.  A repository with no SDLC artifacts is the sole defaultable case and
starts with the canonical dual lifecycle.

This module does not convert records or initialize a ledger.  ``migrate`` only
records the user's selection, keeping old and new state separate and auditable.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Mapping, Sequence


PROFILE_FORMAT = "sdlc-lifecycle-profile-v1"
STATUS_FORMAT = "sdlc-lifecycle-profile-status-v1"
LEGACY_MODE = "legacy-0.19.2"
DUAL_MODE = "dual-lifecycle-v1"
MODES = frozenset({LEGACY_MODE, DUAL_MODE})

_PROFILE_FIELDS = frozenset({"profile_format", "selection", "mode"})
_PROFILE_SELECTIONS = frozenset({"new-project-default-v1", "explicit-migration-v1"})
_LOCK_FILENAME = "lifecycle.lock"
_ARTIFACT_PATHS = (
    ("legacy-profile", ".sdlc/PROFILE.md"),
    ("legacy-state", ".sdlc/STATE.md"),
    ("legacy-task", ".sdlc/TASK.md"),
    ("legacy-spec", ".sdlc/spec.md"),
    ("legacy-plan", ".sdlc/plan.md"),
    ("legacy-requirements", ".sdlc/requirements"),
    ("legacy-validate", ".sdlc/validate"),
    ("legacy-review", ".sdlc/review"),
    ("legacy-ship", ".sdlc/ship"),
    ("legacy-archive", ".sdlc/archive"),
    ("legacy-evolution", ".sdlc/EVOLUTION.md"),
    ("preview", ".sdlc/preview"),
    ("legacy-control", ".sdlc-control"),
    ("dual-ledger", ".sdlc-control/dual-lifecycle/ledger.json"),
)


class LifecycleProfileError(RuntimeError):
    """The target repository's lifecycle choice is missing or unsafe."""


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleProfileError("duplicate-profile-field")
        result[key] = value
    return result


def _repo_root(repo: str | os.PathLike[str]) -> Path:
    source = Path(repo)
    if source.is_symlink():
        raise LifecycleProfileError("repository-root-cannot-be-symlink")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise LifecycleProfileError("repository-root-not-found") from exc
    if not resolved.is_dir():
        raise LifecycleProfileError("repository-root-not-directory")
    return resolved


def _checked_directory(path: Path, *, create: bool) -> Path:
    try:
        if path.exists():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise LifecycleProfileError(f"unsafe-profile-directory:{path.name}")
        elif create:
            path.mkdir(mode=0o755)
        else:
            raise LifecycleProfileError(f"profile-directory-not-found:{path.name}")
        resolved = path.resolve(strict=True)
    except LifecycleProfileError:
        raise
    except OSError as exc:
        raise LifecycleProfileError(f"cannot-create-profile-directory:{path.name}") from exc
    if not resolved.is_dir() or resolved != path:
        raise LifecycleProfileError(f"unsafe-profile-directory:{path.name}")
    return resolved


def _profile_path(root: Path, *, create_parent: bool) -> Path:
    directory = root / ".sdlc"
    if directory.is_symlink():
        raise LifecycleProfileError("unsafe-profile-directory:.sdlc")
    if not directory.exists() and not create_parent:
        return directory / "lifecycle.json"
    directory = _checked_directory(directory, create=create_parent)
    candidate = directory / "lifecycle.json"
    if candidate.is_symlink():
        raise LifecycleProfileError("profile-cannot-be-symlink")
    return candidate


def _directory_fd(path: Path) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LifecycleProfileError("cannot-open-profile-directory") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise LifecycleProfileError("unsafe-profile-directory:.sdlc")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


@contextmanager
def _selection_lock(root: Path):
    """Serialize profile selection and keep the profile directory FD pinned."""
    path = _profile_path(root, create_parent=True)
    directory_descriptor = _directory_fd(path.parent)
    descriptor = -1
    try:
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(_LOCK_FILENAME, flags, 0o600, dir_fd=directory_descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise LifecycleProfileError("lifecycle-lock-must-be-regular-file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except LifecycleProfileError:
        raise
    except OSError as exc:
        raise LifecycleProfileError("cannot-lock-lifecycle-selection") from exc
    finally:
        if descriptor >= 0:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        os.close(directory_descriptor)


def _parse_profile(payload: bytes) -> dict[str, str]:
    try:
        decoded = payload.decode("utf-8")
        source = json.loads(decoded, object_pairs_hook=_reject_duplicate_fields)
    except LifecycleProfileError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleProfileError("invalid-profile-json") from exc
    if not isinstance(source, dict) or set(source) != _PROFILE_FIELDS:
        raise LifecycleProfileError("invalid-profile-fields")
    profile_format = source.get("profile_format")
    selection = source.get("selection")
    mode = source.get("mode")
    if profile_format != PROFILE_FORMAT:
        raise LifecycleProfileError("unsupported-profile-format")
    if not isinstance(selection, str) or selection not in _PROFILE_SELECTIONS:
        raise LifecycleProfileError("invalid-profile-selection")
    if not isinstance(mode, str) or mode not in MODES:
        raise LifecycleProfileError("invalid-profile-mode")
    return {"profile_format": profile_format, "selection": selection, "mode": mode}


def _read_profile(root: Path) -> dict[str, str] | None:
    path = _profile_path(root, create_parent=False)
    if not path.parent.exists():
        return None
    directory_descriptor = _directory_fd(path.parent)
    try:
        try:
            info = os.stat(path.name, dir_fd=directory_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode):
            raise LifecycleProfileError("profile-cannot-be-symlink")
        if not stat.S_ISREG(info.st_mode):
            raise LifecycleProfileError("profile-must-be-regular-file")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path.name, flags, dir_fd=directory_descriptor)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise LifecycleProfileError("profile-must-be-regular-file")
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                payload = handle.read()
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
    except LifecycleProfileError:
        raise
    except OSError as exc:
        raise LifecycleProfileError("cannot-read-profile") from exc
    finally:
        os.close(directory_descriptor)
    return _parse_profile(payload)


def _artifacts(root: Path, *, ignored_sdlc_entries: frozenset[str] = frozenset()) -> list[str]:
    detected: list[str] = []
    for name, relative in _ARTIFACT_PATHS:
        if (root / relative).exists() or (root / relative).is_symlink():
            detected.append(name)
    sdlc = root / ".sdlc"
    recognized = {Path(relative).parts[1] for _, relative in _ARTIFACT_PATHS if relative.startswith(".sdlc/")}
    if sdlc.exists():
        try:
            allowed = recognized | {"lifecycle.json", _LOCK_FILENAME} | ignored_sdlc_entries
            unknown = any(entry.name not in allowed for entry in sdlc.iterdir())
        except OSError as exc:
            raise LifecycleProfileError("cannot-read-sdlc-artifacts") from exc
        if unknown:
            detected.append("unclassified-sdlc-artifact")
    return detected


def status(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    """Return the lifecycle router's deterministic decision without writing."""
    root = _repo_root(repo)
    profile = _read_profile(root)
    artifacts = _artifacts(root)
    base: dict[str, object] = {
        "status_format": STATUS_FORMAT,
        "profile_path": ".sdlc/lifecycle.json",
        "artifacts": artifacts,
    }
    if profile is not None:
        return {
            **base,
            "resolution": "configured",
            "mode": profile["mode"],
            "selection": profile["selection"],
        }
    if artifacts:
        return {**base, "resolution": "migration-required", "mode": None, "selection": None}
    return {
        **base,
        "resolution": "new-project-default",
        "mode": DUAL_MODE,
        "selection": "new-project-default-v1",
    }


def _write_profile(
    root: Path,
    profile: Mapping[str, str],
    *,
    expected_artifacts: Sequence[str],
) -> None:
    path = _profile_path(root, create_parent=True)
    payload = canonical_json_bytes(dict(profile))
    directory_descriptor = _directory_fd(path.parent)
    temporary_name: str | None = None
    try:
        try:
            os.stat(path.name, dir_fd=directory_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise LifecycleProfileError("profile-already-exists")
        descriptor = -1
        for _ in range(8):
            candidate = f".lifecycle.{secrets.token_hex(16)}.json"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(candidate, flags, 0o600, dir_fd=directory_descriptor)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor < 0 or temporary_name is None:
            raise LifecycleProfileError("cannot-create-profile-temporary")
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if _artifacts(root, ignored_sdlc_entries=frozenset({temporary_name})) != list(expected_artifacts):
            raise LifecycleProfileError("artifacts-changed-during-selection")
        try:
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise LifecycleProfileError("profile-already-exists") from exc
        try:
            os.fsync(directory_descriptor)
        except OSError as exc:
            raise LifecycleProfileError("cannot-sync-profile-directory") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
        os.close(directory_descriptor)


def initialize(repo: str | os.PathLike[str] = ".") -> dict[str, object]:
    """Persist the automatic dual default for a repository with no SDLC history."""
    root = _repo_root(repo)
    with _selection_lock(root):
        current = status(root)
        if current["resolution"] != "new-project-default":
            raise LifecycleProfileError(f"cannot-initialize:{current['resolution']}")
        _write_profile(root, {
            "profile_format": PROFILE_FORMAT,
            "selection": "new-project-default-v1",
            "mode": DUAL_MODE,
        }, expected_artifacts=[])
    return status(root)


def migrate(
    mode: str,
    *,
    repo: str | os.PathLike[str] = ".",
    allow_existing_artifacts: bool = False,
) -> dict[str, object]:
    """Persist an explicit lifecycle selection without transforming prior state."""
    if mode not in MODES:
        raise LifecycleProfileError("invalid-migration-mode")
    root = _repo_root(repo)
    with _selection_lock(root):
        current = status(root)
        if current["resolution"] == "configured":
            raise LifecycleProfileError("profile-already-configured")
        artifacts = current["artifacts"]
        assert isinstance(artifacts, list)
        if mode == DUAL_MODE and artifacts and not allow_existing_artifacts:
            raise LifecycleProfileError("dual-migration-requires-existing-artifact-confirmation")
        selection = (
            "new-project-default-v1"
            if current["resolution"] == "new-project-default" and mode == DUAL_MODE
            else "explicit-migration-v1"
        )
        _write_profile(root, {
            "profile_format": PROFILE_FORMAT,
            "selection": selection,
            "mode": mode,
        }, expected_artifacts=artifacts)
    return status(root)


def _emit(value: Mapping[str, object]) -> None:
    print(canonical_json_bytes(dict(value)).decode("utf-8"), end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="resolve a target repository's SDLC lifecycle profile")
    parser.add_argument("--repo", default=".", help="target repository root (default: current directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="read the configured lifecycle or report a required migration")
    commands.add_parser("init", help="persist the dual default for a repository with no SDLC artifacts")
    migrate_parser = commands.add_parser("migrate", help="persist an explicit lifecycle selection without converting state")
    migrate_parser.add_argument("--mode", required=True, choices=sorted(MODES))
    migrate_parser.add_argument(
        "--allow-existing-artifacts", action="store_true",
        help="required before selecting dual lifecycle where SDLC artifacts already exist",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = status(args.repo)
        elif args.command == "init":
            result = initialize(args.repo)
        else:
            result = migrate(
                args.mode, repo=args.repo, allow_existing_artifacts=bool(args.allow_existing_artifacts),
            )
    except LifecycleProfileError as exc:
        print(f"lifecycle-profile-error: {exc}", file=sys.stderr)
        return 2
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DUAL_MODE", "LEGACY_MODE", "LifecycleProfileError", "PROFILE_FORMAT", "STATUS_FORMAT", "initialize",
    "main", "migrate", "status",
]
