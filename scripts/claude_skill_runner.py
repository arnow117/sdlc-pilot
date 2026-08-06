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
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Mapping, Sequence

import eval_skill_behavior as behavior_eval


DEFAULT_CC_SWITCH_DB = Path.home() / ".cc-switch" / "cc-switch.db"
MAX_AGENT_TURNS = 2
MAX_CONTEXT_PACK_BYTES = 64 * 1024
MAX_SKILL_SOURCE_CHARS = 6_000
_POLICY_ROOT = Path("skills/sdlc/references/policies")
_POLICY_PHASE_PREFIXES = {
    "sdlc-product-design": "phase.product.",
    "sdlc-software-delivery": "phase.delivery.",
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


def _read_policy_document(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaudeSkillRunnerError(f"cannot-read-evaluation-policy-{label}") from exc
    if not isinstance(value, dict):
        raise ClaudeSkillRunnerError(f"invalid-evaluation-policy-{label}")
    return value


def _evaluation_policy_surface(checkout: Path, invocation: Mapping[str, object]) -> str | None:
    """Return the bounded policy data a selected dual-lifecycle step actually needs.

    The live evaluator asks the provider for executable IDs, not prose labels.
    A normal runtime resolves those IDs through the policy documents; providing
    only SKILL.md made that contract impossible for the read-only runner to
    satisfy.  This surface contains the selected phase contracts and their
    possible module/role/obligation inputs, never the case's expected output.
    """
    raw_steps = invocation.get("steps")
    if not isinstance(raw_steps, list):
        raise ClaudeSkillRunnerError("missing-invocation-steps")
    phase_requests: list[dict[str, str]] = []
    for item in raw_steps:
        if not isinstance(item, Mapping):
            raise ClaudeSkillRunnerError("invalid-invocation-step")
        skill = item.get("skill")
        phase = item.get("phase")
        prefix = _POLICY_PHASE_PREFIXES.get(skill) if isinstance(skill, str) else None
        if prefix is None:
            continue
        if not isinstance(phase, str) or not phase:
            continue
        phase_requests.append({"skill": skill, "phase": phase, "phase_id": f"{prefix}{phase}"})
    if not phase_requests:
        return None

    root = checkout / _POLICY_ROOT
    modules_document = _read_policy_document(root / "modules.json", "modules")
    phases_document = _read_policy_document(root / "phases.json", "phases")
    roles_document = _read_policy_document(root / "roles.json", "roles")
    raw_modules = modules_document.get("modules")
    raw_rules = modules_document.get("rules")
    raw_phases = phases_document.get("phases")
    raw_roles = roles_document.get("roles")
    if not all(isinstance(value, list) for value in (raw_modules, raw_rules, raw_phases, raw_roles)):
        raise ClaudeSkillRunnerError("invalid-evaluation-policy-collections")
    modules = {item.get("id"): item for item in raw_modules if isinstance(item, dict) and isinstance(item.get("id"), str)}
    phases = {item.get("id"): item for item in raw_phases if isinstance(item, dict) and isinstance(item.get("id"), str)}
    roles = {item.get("id"): item for item in raw_roles if isinstance(item, dict) and isinstance(item.get("id"), str)}
    rules = {item.get("id"): item for item in raw_rules if isinstance(item, dict) and isinstance(item.get("id"), str)}

    selected_phases: list[dict[str, object]] = []
    for request in phase_requests:
        phase = phases.get(request["phase_id"])
        if phase is None:
            raise ClaudeSkillRunnerError(f"unknown-evaluation-policy-phase:{request['phase_id']}")
        selected_phases.append(phase)

    module_ids: set[str] = set()
    role_ids: set[str] = set()
    rule_ids: set[str] = set()
    for phase in selected_phases:
        for rule_id in phase.get("entry_predicate_rule_ids", []):
            if isinstance(rule_id, str):
                rule_ids.add(rule_id)
        for module_id in phase.get("method_module_ids", []):
            if isinstance(module_id, str):
                module_ids.add(module_id)
        obligations = phase.get("obligations", [])
        if not isinstance(obligations, list):
            raise ClaudeSkillRunnerError("invalid-evaluation-policy-obligations")
        for obligation in obligations:
            if not isinstance(obligation, dict):
                raise ClaudeSkillRunnerError("invalid-evaluation-policy-obligation")
            role_id = obligation.get("role_id")
            rule_id = obligation.get("required_when_rule_id")
            playbook_ref = obligation.get("playbook_ref")
            if isinstance(role_id, str):
                role_ids.add(role_id)
            if isinstance(rule_id, str):
                rule_ids.add(rule_id)
            if isinstance(playbook_ref, dict) and isinstance(playbook_ref.get("module_id"), str):
                module_ids.add(playbook_ref["module_id"])

    pending = list(module_ids)
    while pending:
        module_id = pending.pop()
        module = modules.get(module_id)
        if module is None:
            raise ClaudeSkillRunnerError(f"unknown-evaluation-policy-module:{module_id}")
        for rule_id in module.get("selector_rule_ids", []):
            if isinstance(rule_id, str):
                rule_ids.add(rule_id)
        for dependency_id in module.get("depends_on", []):
            if isinstance(dependency_id, str) and dependency_id not in module_ids:
                module_ids.add(dependency_id)
                pending.append(dependency_id)

    for role_id in role_ids:
        role = roles.get(role_id)
        if role is None:
            raise ClaudeSkillRunnerError(f"unknown-evaluation-policy-role:{role_id}")
        for rule_id in role.get("eligibility_rule_ids", []):
            if isinstance(rule_id, str):
                rule_ids.add(rule_id)

    missing_rules = sorted(rule_ids.difference(rules))
    if missing_rules:
        raise ClaudeSkillRunnerError(f"unknown-evaluation-policy-rule:{missing_rules[0]}")
    surface = {
        "surface_format": "sdlc-skill-evaluation-policy-surface-v1",
        "route_format": "<skill>:<phase>",
        "steps": phase_requests,
        "phases": sorted(selected_phases, key=lambda item: str(item["id"])),
        "modules": [modules[module_id] for module_id in sorted(module_ids)],
        "roles": [roles[role_id] for role_id in sorted(role_ids)],
        "rules": [rules[rule_id] for rule_id in sorted(rule_ids)],
    }
    return json.dumps(surface, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _context_pack(checkout: Path, request: Mapping[str, object]) -> str:
    """Read the selected Skill source locally so the provider need not use tools."""
    invocation = request.get("invocation")
    if not isinstance(invocation, Mapping):
        raise ClaudeSkillRunnerError("missing-explicit-invocation-contract")
    steps = invocation.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ClaudeSkillRunnerError("missing-invocation-steps")
    names: list[str] = []
    for step in steps:
        skill = step.get("skill") if isinstance(step, Mapping) else None
        if not isinstance(skill, str) or not skill or not skill.replace("-", "").isalnum():
            raise ClaudeSkillRunnerError("invalid-invocation-skill")
        if skill not in names:
            names.append(skill)
    parts: list[str] = []
    total = 0
    for skill in names:
        source = checkout / "skills" / skill / "SKILL.md"
        try:
            payload = source.read_bytes()
        except OSError as exc:
            raise ClaudeSkillRunnerError("missing-invocation-skill-source") from exc
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ClaudeSkillRunnerError("invalid-invocation-skill-source") from exc
        truncated = len(text) > MAX_SKILL_SOURCE_CHARS
        excerpt = text[:MAX_SKILL_SOURCE_CHARS].rstrip()
        if truncated:
            excerpt += "\n\n[Source excerpt truncated locally for the bounded evaluation context.]"
        total += len(excerpt.encode("utf-8"))
        if total > MAX_CONTEXT_PACK_BYTES:
            raise ClaudeSkillRunnerError("skill-context-pack-too-large")
        parts.extend((f"### skills/{skill}/SKILL.md", excerpt))
    policy_surface = _evaluation_policy_surface(checkout, invocation)
    if policy_surface is not None:
        total += len(policy_surface.encode("utf-8"))
        if total > MAX_CONTEXT_PACK_BYTES:
            raise ClaudeSkillRunnerError("skill-context-pack-too-large")
        parts.extend(("### SDLC evaluation policy surface (canonical IDs)", policy_surface))
    return "\n\n".join(parts)


def _prompt(request: Mapping[str, object], context_pack: str) -> str:
    invocation = request.get("invocation")
    if not isinstance(invocation, Mapping):
        raise ClaudeSkillRunnerError("missing-explicit-invocation-contract")
    return "\n".join([
        "You are a read-only SDLC Skill behavior evaluation runner.",
        "Do not invoke any tool. Do not rely on globally installed Skills or infer authority.",
        "The context pack below is the selected source for this invocation.",
        "Read only the source files necessary to answer this invocation; then return the JSON response immediately.",
        "For candidate runs, dual lifecycle authority is explicit. For baseline runs, preserve legacy routing.",
        "Report only selected IDs and actual required/artifact kinds. Do not claim tests, approvals, reviews, or security completion.",
        "When the policy surface is present, select only its exact canonical module, role, obligation, and artifact IDs; never invent aliases.",
        "For every selected module, include its full transitive depends_on closure. For every selected obligation, include its role_id when its selector is true.",
        "Each route and transition.route item must use the exact `<skill>:<phase>` format from the invocation steps; do not append operation names. Top-level route is always the selected invocation sequence, including a rejected transition; only transition.route is empty for decision reject.",
        "For operation change-request, the selected behavior-design step produces BehaviorContractPreview and the delivery step requires ChangeRequest; reject the transition with an empty transition.route. For reject-transition, include the selected release-candidate route, its module dependency closure, and its required role and obligation; reject with an empty transition.route. Caller-declared approval, tests, or review never count as evidence, so require ApprovalHead, ReviewRecord, and RunnerEvidence.",
        "For every operation other than change-request or reject-transition, transition.decision must be route and transition.route must equal top-level route. A request to plan or implement work is not rejected merely because it does not yet contain completion evidence.",
        "For migrate-preview-policy, require PreviewPolicyMigration, ContextManifest, and ObligationManifest. For sdlc-onboard, use the canonical artifact name ProfileSnapshot.",
        "Return only a JSON object with exactly these top-level keys: case_id, route, modules, roles, obligations, artifacts, actions, transition.",
        "Do not add reasoning, notes, explanations, confidence, metadata, or any other key. actions must be an empty array because no tool may run.",
        "transition must contain exactly decision ('route' or 'reject') and route. Do not use a Markdown code fence.",
        "case_id is a string. route, modules, roles, obligations, artifacts, actions, and transition.route are arrays of strings, never a comma-separated string or object.",
        "The required JSON shape is: {\"case_id\":\"...\",\"route\":[\"...\"],\"modules\":[\"...\"],\"roles\":[\"...\"],\"obligations\":[\"...\"],\"artifacts\":[\"...\"],\"actions\":[],\"transition\":{\"decision\":\"route\",\"route\":[\"...\"]}}.",
        "Context pack:",
        context_pack,
        "Invocation contract:",
        _canonical_bytes(invocation).decode("utf-8").strip(),
    ])


def _build_command(*, model: str, max_budget_usd: float, prompt: str) -> list[str]:
    return [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--safe-mode",
        "--model", model,
        "--max-budget-usd", str(max_budget_usd),
        "--effort", "low",
        "--max-turns", str(MAX_AGENT_TURNS),
        "--tools", "Read,Glob,Grep",
        "--disallowed-tools", "Read,Glob,Grep",
        "--permission-mode", "dontAsk",
        "--no-session-persistence",
    ]


def _run_claude(command: Sequence[str], *, cwd: Path, environment: Mapping[str, str],
                timeout_seconds: int) -> subprocess.CompletedProcess[bytes]:
    """Run Claude in its own process group so an expired call cannot strand children."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise ClaudeSkillRunnerError("claude-runner-timeout") from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


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
    if any(token in text for token in ("max budget", "budget", "cost limit", "spend limit")):
        return "budget"
    if any(token in text for token in ("context length", "context window", "prompt too long", "input is too long")):
        return "context-length"
    if any(token in text for token in ("max turns", "turn limit", "max_turns")):
        return "turn-limit"
    if any(token in text for token in ("plugin", "marketplace", "manifest")):
        return "plugin"
    if any(token in text for token in ("tool use", "tool_use", "tool call")):
        return "tool-execution"
    if any(token in text for token in ("unknown tool", "invalid tool", "--tools")):
        return "tool-config"
    if any(token in text for token in ("permission-mode", "permission mode")):
        return "permission-mode"
    if any(token in text for token in ("connection", "connect", "timeout", "econn", "network")):
        return "provider-connection"
    if "error_during_execution" in text:
        return "client-execution"
    if isinstance(result, dict) and result.get("is_error") is True:
        return "claude-error-result"
    if stdout:
        return "claude-non-json-output"
    if stderr:
        return "claude-cli-stderr"
    return "claude-empty-failure"


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
        return behavior_eval._normalize_live_output(raw)
    except behavior_eval.EvaluationError as exc:
        raise ClaudeSkillRunnerError(f"invalid-structured-skill-output:{exc}") from exc


def _invalid_live_output(request: Mapping[str, object]) -> dict[str, object]:
    """Represent an unparseable provider response as a scoreable model failure.

    A provider/runner outage invalidates a run; a model response that violates
    the requested JSON protocol is observed behavior.  Return a neutral,
    mechanically failing output for the latter so the batch can continue.
    """
    case = request.get("case")
    case_id = case.get("case_id") if isinstance(case, Mapping) else None
    if not isinstance(case_id, str) or not case_id:
        raise ClaudeSkillRunnerError("missing-case-id-for-invalid-live-output")
    return {
        "case_id": case_id,
        "route": [],
        "modules": [],
        "roles": [],
        "obligations": [],
        "artifacts": [],
        "actions": [],
        "transition": {"decision": "reject", "route": []},
    }


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
        context_pack = _context_pack(worktree, request)
        command = _build_command(
            model=selected_model, max_budget_usd=max_budget_usd,
            prompt=_prompt(request, context_pack),
        )
        completed = _run_claude(
            command, cwd=worktree, environment=environment, timeout_seconds=timeout_seconds,
        )
        if completed.returncode != 0:
            raise ClaudeSkillRunnerError(
                f"claude-runner-failed:{_safe_failure_class(completed.stderr, completed.stdout)}:{completed.returncode}")
        response_type = "invalid"
        output_validity = "invalid-structured-output"
        total_cost: object = 0
        try:
            response = _strict_object(completed.stdout, "claude-result")
            output = _structured_output(response)
            total_cost = response.get("total_cost_usd", 0)
            response_type = str(response.get("type", "unknown"))
            output_validity = "valid"
        except ClaudeSkillRunnerError:
            output = _invalid_live_output(request)
        cost = float(total_cost) if isinstance(total_cost, (int, float)) and total_cost >= 0 else 0.0
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "output": output,
            "tool_events": [{"tool": "claude", "mode": "read-only", "duration_ms": duration_ms}],
            "manifests": {
                "source_commit": source_commit,
                "invocation": request["invocation"],
                "response_type": response_type,
                "output_validity": output_validity,
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
