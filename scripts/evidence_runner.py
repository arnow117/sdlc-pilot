#!/usr/bin/env python3
"""Preview-safe argv-only runner for mechanically derived Evidence facts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
from typing import Mapping, Sequence


_SHA256_LENGTH = 64
_FORBIDDEN_SELF_REPORTS = frozenset({
    "tests_passed", "approved", "review_complete", "security_complete", "result", "passed",
})


class EvidenceError(ValueError):
    """A caller attempted an unsafe run or an unsupported evidence claim."""


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH:
        raise EvidenceError(f"invalid-{label}")
    try:
        int(value, 16)
    except ValueError as exc:
        raise EvidenceError(f"invalid-{label}") from exc
    return value


def _validate_argv(argv: Sequence[str]) -> list[str]:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence) or not argv:
        raise EvidenceError("argv-must-be-a-nonempty-sequence")
    normalized: list[str] = []
    for index, value in enumerate(argv):
        if not isinstance(value, str) or not value or "\x00" in value:
            raise EvidenceError(f"invalid-argv-{index}")
        normalized.append(value)
    return normalized


def _output_summary(value: bytes, limit: int) -> dict[str, object]:
    truncated = len(value) > limit
    sample = value[:limit]
    try:
        preview = sample.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        preview = sample.decode("utf-8", errors="replace")
        encoding = "binary"
    return {
        "sha256": _sha256(value),
        "bytes": len(value),
        "truncated": truncated,
        "encoding": encoding,
        "preview": preview,
    }


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        process.kill()


def _run(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    timeout_seconds: float = 60.0,
    policy_manifest_ref: str,
    context_manifest_ref: str,
    code_sha: str,
    tool_version: str = "unspecified",
    cwd_identity: str | None = None,
    max_output_bytes: int = 65_536,
    scope: str,
) -> dict[str, object]:
    """Run one argv vector without a shell and derive immutable runner facts."""
    command = _validate_argv(argv)
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise EvidenceError("invalid-timeout-seconds")
    if not isinstance(max_output_bytes, int) or isinstance(max_output_bytes, bool) or max_output_bytes < 0:
        raise EvidenceError("invalid-max-output-bytes")
    if scope not in {"preview", "canonical"}:
        raise EvidenceError("invalid-evidence-runner-scope")
    policy_manifest_ref = _require_sha(policy_manifest_ref, "policy-manifest-ref")
    context_manifest_ref = _require_sha(context_manifest_ref, "context-manifest-ref")
    code_sha = _require_sha(code_sha, "code-sha")
    if not isinstance(tool_version, str) or not tool_version:
        raise EvidenceError("invalid-tool-version")
    try:
        resolved_cwd = Path(cwd).resolve(strict=True)
    except OSError as exc:
        raise EvidenceError("invalid-cwd") from exc
    if not resolved_cwd.is_dir():
        raise EvidenceError("cwd-is-not-a-directory")
    if cwd_identity is None:
        cwd_identity = _sha256(str(resolved_cwd).encode("utf-8"))
    else:
        cwd_identity = _require_sha(cwd_identity, "cwd-identity")

    timed_out = False
    try:
        process = subprocess.Popen(
            command,
            cwd=str(resolved_cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        raise EvidenceError(f"cannot-start-command:{command[0]}") from exc
    try:
        stdout, stderr = process.communicate(timeout=float(timeout_seconds))
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_group(process)
        stdout, stderr = process.communicate()
    exit_code = process.returncode
    if exit_code is None:
        raise EvidenceError("runner-did-not-produce-exit-code")
    stdout_summary = _output_summary(stdout, max_output_bytes)
    stderr_summary = _output_summary(stderr, max_output_bytes)
    preimage = {
        "schema_version": f"{scope}-runner-evidence-v1",
        "scope": scope,
        "argv": command,
        "cwd_identity": cwd_identity,
        "timeout_seconds": float(timeout_seconds),
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout": {key: stdout_summary[key] for key in ("sha256", "bytes", "truncated", "encoding")},
        "stderr": {key: stderr_summary[key] for key in ("sha256", "bytes", "truncated", "encoding")},
        "tool_version": tool_version,
        "code_sha": code_sha,
        "policy_manifest_ref": policy_manifest_ref,
        "context_manifest_ref": context_manifest_ref,
    }
    evidence_id = _sha256(canonical_bytes(preimage))
    return {
        **preimage,
        "evidence_id": evidence_id,
        "stdout": stdout_summary,
        "stderr": stderr_summary,
    }


def run(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    timeout_seconds: float = 60.0,
    policy_manifest_ref: str,
    context_manifest_ref: str,
    code_sha: str,
    tool_version: str = "unspecified",
    cwd_identity: str | None = None,
    max_output_bytes: int = 65_536,
    scope: str = "preview",
) -> dict[str, object]:
    """Run preview-only diagnostics without accidentally creating canonical evidence.

    The public preview function intentionally keeps the Phase 1 boundary: a
    caller cannot flip ``scope`` to canonical.  Canonical ledger code must use
    :func:`run_canonical`, making that privilege boundary visible in both code
    review and tests.
    """
    if scope != "preview":
        raise EvidenceError("phase1-evidence-must-have-preview-scope")
    return _run(
        argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        policy_manifest_ref=policy_manifest_ref,
        context_manifest_ref=context_manifest_ref,
        code_sha=code_sha,
        tool_version=tool_version,
        cwd_identity=cwd_identity,
        max_output_bytes=max_output_bytes,
        scope="preview",
    )


def run_canonical(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    timeout_seconds: float = 60.0,
    policy_manifest_ref: str,
    context_manifest_ref: str,
    code_sha: str,
    tool_version: str = "unspecified",
    cwd_identity: str | None = None,
    max_output_bytes: int = 65_536,
) -> dict[str, object]:
    """Run a canonical evidence command for the ledger authority adapter.

    This function reports only observed process facts.  It does not decide a
    Task transition, construct lifecycle evidence, or accept a caller-supplied
    pass/fail value; those responsibilities remain with the dual ledger and
    reducer respectively.
    """
    return _run(
        argv,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        policy_manifest_ref=policy_manifest_ref,
        context_manifest_ref=context_manifest_ref,
        code_sha=code_sha,
        tool_version=tool_version,
        cwd_identity=cwd_identity,
        max_output_bytes=max_output_bytes,
        scope="canonical",
    )


def derive_mechanical_facts(record: Mapping[str, object]) -> dict[str, object]:
    """Derive facts from a runner record; never accept a caller's completion assertion."""
    if not isinstance(record, Mapping):
        raise EvidenceError("invalid-runner-record")
    forbidden = sorted(_FORBIDDEN_SELF_REPORTS & set(record))
    if forbidden:
        raise EvidenceError("self-reported-mechanical-fact:" + ",".join(forbidden))
    required = frozenset({
        "schema_version", "scope", "evidence_id", "exit_code", "timed_out", "code_sha",
        "policy_manifest_ref", "context_manifest_ref", "stdout", "stderr",
    })
    missing = required - set(record)
    if missing:
        raise EvidenceError("missing-runner-record-fields:" + ",".join(sorted(missing)))
    scope = record["scope"]
    if scope not in {"preview", "canonical"} or record["schema_version"] != f"{scope}-runner-evidence-v1":
        raise EvidenceError("unsupported-runner-record-scope")
    evidence_id = _require_sha(record["evidence_id"], "evidence-id")
    code_sha = _require_sha(record["code_sha"], "code-sha")
    policy_ref = _require_sha(record["policy_manifest_ref"], "policy-manifest-ref")
    context_ref = _require_sha(record["context_manifest_ref"], "context-manifest-ref")
    if not isinstance(record["exit_code"], int) or isinstance(record["exit_code"], bool):
        raise EvidenceError("invalid-runner-exit-code")
    if not isinstance(record["timed_out"], bool):
        raise EvidenceError("invalid-runner-timeout")
    return {
        "scope": scope,
        "evidence_id": evidence_id,
        "runner_exit_code": record["exit_code"],
        "runner_timed_out": record["timed_out"],
        "runner_succeeded": record["exit_code"] == 0 and not record["timed_out"],
        "code_sha": code_sha,
        "policy_manifest_ref": policy_ref,
        "context_manifest_ref": context_ref,
    }
