#!/usr/bin/env python3
"""CC Switch-backed, read-only Claude CLI adapter for live Skill evaluation.

The adapter is intentionally a runner, not an evaluator.  It accepts one JSON
run request on stdin, checks out the requested commit into a disposable
worktree, invokes the selected Claude-compatible provider with only read tools,
and emits the strict result envelope consumed by ``live_skill_eval.py``.
Provider secrets stay in the child process environment and are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Mapping, Sequence

import eval_skill_behavior as behavior_eval


DEFAULT_CC_SWITCH_DB = Path.home() / ".cc-switch" / "cc-switch.db"
RUNNER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["case_id", "route", "modules", "roles", "obligations", "artifacts", "actions", "transition"],
    "properties": {
        "case_id": {"type": "string"},
        "route": {"type": "array", "items": {"type": "string"}},
        "modules": {"type": "array", "items": {"type": "string"}},
        "roles": {"type": "array", "items": {"type": "string"}},
        "obligations": {"type": "array", "items": {"type": "string"}},
        "artifacts": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {"type": "string"}},
        "transition": {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision", "route"],
            "properties": {
                "decision": {"type": "string", "enum": ["route", "reject"]},
                "route": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


class ClaudeSkillRunnerError(RuntimeError):
    """The provider configuration, source checkout, or structured response is invalid."""


def _canonical_bytes(value: object) -> bytes:
    return behavior_eval.canonical_bytes(value)


def _strict_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaudeSkillRunnerError(f"invalid-{label}-json") from exc
    if not isinstance(value, dict):
        raise ClaudeSkillRunnerError(f"invalid-{label}-object")
    return value


def _provider_environment(database: Path, provider_name: str) -> dict[str, str]:
    """Load one Claude-compatible CC Switch provider without exposing values."""
    if not isinstance(provider_name, str) or not provider_name:
        raise ClaudeSkillRunnerError("invalid-provider-name")
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        row = connection.execute(
            "SELECT app_type, settings_config FROM providers WHERE name = ?", (provider_name,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ClaudeSkillRunnerError("cannot-read-cc-switch-provider") from exc
    finally:
        if "connection" in locals():
            connection.close()
    if row is None or row[0] != "claude":
        raise ClaudeSkillRunnerError("unknown-or-incompatible-cc-switch-provider")
    try:
        settings = json.loads(row[1])
        env = settings["env"]
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ClaudeSkillRunnerError("invalid-cc-switch-provider-settings") from exc
    if not isinstance(env, dict):
        raise ClaudeSkillRunnerError("invalid-cc-switch-provider-environment")
    selected = {
        key: value for key, value in env.items()
        if isinstance(key, str) and key.startswith("ANTHROPIC_") and isinstance(value, str) and value
    }
    if not selected.get("ANTHROPIC_AUTH_TOKEN") or not selected.get("ANTHROPIC_BASE_URL"):
        raise ClaudeSkillRunnerError("cc-switch-provider-missing-claude-credentials")
    return selected


def _resolve_model(provider_environment: Mapping[str, str], requested_model: str) -> str:
    """Use CC Switch's configured provider model unless an override is explicit."""
    if not isinstance(requested_model, str) or not requested_model:
        raise ClaudeSkillRunnerError("invalid-model")
    if requested_model != "configured":
        return requested_model
    for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"):
        model = provider_environment.get(key)
        if isinstance(model, str) and model:
            return model
    raise ClaudeSkillRunnerError("cc-switch-provider-missing-model")


def _prompt(request: Mapping[str, object]) -> str:
    invocation = request.get("invocation")
    if not isinstance(invocation, Mapping):
        raise ClaudeSkillRunnerError("missing-explicit-invocation-contract")
    return "\n".join([
        "You are a read-only SDLC Skill behavior evaluation runner.",
        "Use only Read, Glob, and Grep. Do not invoke shell commands, edit files, create artifacts, or infer authority.",
        "Inspect the checked-out repository and follow the invocation contract below exactly.",
        "For candidate runs, dual lifecycle authority is explicit. For baseline runs, preserve legacy routing.",
        "Report only selected IDs and actual required/artifact kinds. Do not claim tests, approvals, reviews, or security completion.",
        "Return only the required JSON object, without a Markdown code fence.",
        "Invocation contract:",
        _canonical_bytes(invocation).decode("utf-8").strip(),
    ])


def _build_command(*, model: str, max_budget_usd: float, prompt: str) -> list[str]:
    return [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--max-budget-usd", str(max_budget_usd),
        "--tools", "Read,Glob,Grep",
        "--permission-mode", "dontAsk",
        "--no-session-persistence",
    ]


def _safe_failure_class(stderr: bytes, stdout: bytes = b"") -> str:
    """Classify a CLI failure without retaining provider endpoints or secrets.

    Claude CLI reports some runtime failures as a JSON result on stdout rather
    than stderr.  Inspect only its bounded diagnostic fields in memory and
    return a fixed category; callers never receive the provider text itself.
    """
    diagnostics = [stderr.decode("utf-8", errors="replace")]
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result = None
    if isinstance(result, dict):
        subtype = result.get("subtype")
        if isinstance(subtype, str):
            diagnostics.append(subtype)
        errors = result.get("errors")
        if isinstance(errors, list):
            diagnostics.extend(item for item in errors if isinstance(item, str))
    text = "\n".join(diagnostics).lower()
    if any(token in text for token in ("model_not_found", "model not found", "invalid model", "unknown model")):
        return "model"
    if any(token in text for token in ("401", "403", "authentication", "unauthorized", "api key")):
        return "authentication"
    if any(token in text for token in ("plugin", "marketplace", "manifest")):
        return "plugin"
    if any(token in text for token in ("unknown tool", "invalid tool", "--tools")):
        return "tool-config"
    if any(token in text for token in ("permission-mode", "permission mode")):
        return "permission-mode"
    if any(token in text for token in ("connection", "connect", "timeout", "econn", "network")):
        return "provider-connection"
    if "error_during_execution" in text:
        return "client-execution"
    return "opaque"


def _structured_output(value: Mapping[str, object]) -> dict[str, object]:
    raw = value.get("structured_output")
    if raw is None:
        raw = value.get("result")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeSkillRunnerError("claude-result-is-not-structured-json") from exc
    if not isinstance(raw, dict):
        raise ClaudeSkillRunnerError("claude-missing-structured-output")
    try:
        return behavior_eval._normalize_output(raw)
    except behavior_eval.EvaluationError as exc:
        raise ClaudeSkillRunnerError(f"invalid-structured-skill-output:{exc}") from exc


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise ClaudeSkillRunnerError("git-source-checkout-failed")
    return completed.stdout.strip()


def run_once(
    request: Mapping[str, object], *, repo: Path, provider_name: str, model: str,
    max_budget_usd: float, database: Path, timeout_seconds: int,
    evaluator_model: str, evaluator_version: str,
) -> dict[str, object]:
    source_ref = request.get("source_ref")
    if not isinstance(source_ref, str) or not source_ref:
        raise ClaudeSkillRunnerError("invalid-source-ref")
    source_commit = _git(repo, "rev-parse", "--verify", f"{source_ref}^{{commit}}")
    provider_environment = _provider_environment(database, provider_name)
    selected_model = _resolve_model(provider_environment, model)
    environment = os.environ.copy()
    environment.update(provider_environment)
    temporary = Path(tempfile.mkdtemp(prefix="sdlc-skill-eval-"))
    worktree = temporary / "source"
    started = time.monotonic()
    try:
        _git(repo, "worktree", "add", "--detach", str(worktree), source_commit)
        command = _build_command(model=selected_model, max_budget_usd=max_budget_usd, prompt=_prompt(request))
        command.extend(["--plugin-dir", str(worktree)])
        completed = subprocess.run(
            command,
            cwd=worktree,
            env=environment,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0:
            raise ClaudeSkillRunnerError(
                f"claude-runner-failed:{_safe_failure_class(completed.stderr, completed.stdout)}:{completed.returncode}")
        response = _strict_object(completed.stdout, "claude-result")
        output = _structured_output(response)
        total_cost = response.get("total_cost_usd", 0)
        cost = float(total_cost) if isinstance(total_cost, (int, float)) and total_cost >= 0 else 0.0
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "output": output,
            "tool_events": [{"tool": "claude", "mode": "read-only", "duration_ms": duration_ms}],
            "manifests": {
                "source_commit": source_commit,
                "invocation": request["invocation"],
                "response_type": response.get("type", "unknown"),
            },
            "cost": {"usd": cost},
            "execution": {
                "provider": provider_name,
                "model": selected_model,
                "model_version": str(response.get("model", selected_model)),
                "temperature": "provider-default",
                "max_tokens": "provider-default",
                "tool_versions": {"claude": _claude_version()},
                "evaluator_model": evaluator_model,
                "evaluator_version": evaluator_version,
                "variant_runs": request.get("planned_runs"),
            },
        }
    except subprocess.TimeoutExpired as exc:
        raise ClaudeSkillRunnerError("claude-runner-timeout") from exc
    finally:
        if worktree.exists():
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
                           check=False, capture_output=True)
        shutil.rmtree(temporary, ignore_errors=True)


def _claude_version() -> str:
    completed = subprocess.run(["claude", "--version"], check=False, capture_output=True, text=True)
    return completed.stdout.strip() if completed.returncode == 0 and completed.stdout.strip() else "unknown"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--provider", default="Zhipu GLM")
    parser.add_argument("--model", default="configured", help="CC Switch model or 'configured' (default)")
    parser.add_argument("--max-budget-usd", type=float, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--cc-switch-db", default=str(DEFAULT_CC_SWITCH_DB))
    parser.add_argument("--evaluator-model", default="unconfigured")
    parser.add_argument("--evaluator-version", default="unconfigured")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        request = _strict_object(sys.stdin.buffer.read(), "runner-input")
        if args.max_budget_usd <= 0 or args.timeout_seconds <= 0:
            raise ClaudeSkillRunnerError("invalid-runner-budget-or-timeout")
        result = run_once(
            request,
            repo=Path(args.repo).resolve(),
            provider_name=args.provider,
            model=args.model,
            max_budget_usd=args.max_budget_usd,
            database=Path(args.cc_switch_db),
            timeout_seconds=args.timeout_seconds,
            evaluator_model=args.evaluator_model,
            evaluator_version=args.evaluator_version,
        )
    except ClaudeSkillRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
