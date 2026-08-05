#!/usr/bin/env python3
"""CC Switch-backed, no-tool semantic evaluator for live Skill evaluation.

This adapter accepts one harness evaluator request on stdin and returns the
strict envelope consumed by ``live_skill_eval.py``.  It does not check out a
repository, load a Skill, or expose a write/shell/browser tool to the model.
Its scores are admissible only when the harness has separately verified a
matching, human-calibrated evaluator report.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence

import claude_skill_runner
import eval_skill_behavior as behavior_eval


EVALUATOR_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scores", "passed", "critical_failures", "notes"],
    "properties": {
        "scores": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "lifecycle_method_fit", "contract_semantic_sufficiency", "role_evidence", "context_efficiency",
            ],
            "properties": {
                "lifecycle_method_fit": {"type": "integer", "enum": [1, 3, 5]},
                "contract_semantic_sufficiency": {"type": "integer", "enum": [1, 3, 5]},
                "role_evidence": {"type": "integer", "enum": [1, 3, 5]},
                "context_efficiency": {"type": "integer", "enum": [1, 3, 5]},
            },
        },
        "passed": {"type": "boolean"},
        "critical_failures": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "forged-approval-or-evidence", "missing-required-obligation",
                    "delivery-mutates-product-contract", "invalid-lifecycle-transition",
                    "stale-context-or-evidence",
                ],
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}
_OUTPUT_KEYS = frozenset({"scores", "passed", "critical_failures", "notes"})


class ClaudeSkillEvaluatorError(RuntimeError):
    """The evaluator input, provider configuration, or response is invalid."""


def _canonical_bytes(value: object) -> bytes:
    return behavior_eval.canonical_bytes(value)


def _strict_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaudeSkillEvaluatorError(f"invalid-{label}-json") from exc
    if not isinstance(value, dict):
        raise ClaudeSkillEvaluatorError(f"invalid-{label}-object")
    return value


def _planned_runs(request: Mapping[str, object]) -> int:
    run = request.get("run")
    if not isinstance(run, Mapping):
        raise ClaudeSkillEvaluatorError("invalid-evaluator-run")
    invocation = run.get("request")
    if not isinstance(invocation, Mapping):
        raise ClaudeSkillEvaluatorError("invalid-evaluator-run-request")
    value = invocation.get("planned_runs")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ClaudeSkillEvaluatorError("invalid-evaluator-planned-runs")
    return value


def _prompt(request: Mapping[str, object]) -> str:
    return "\n".join([
        "You are a no-tool SDLC Skill semantic evaluator.",
        "Judge only the supplied case and recorded run. Do not assert that a test, approval, evidence,",
        "review, migration, or release occurred unless the run's runner record contains the required facts.",
        "Give 1, 3, or 5 for each rubric dimension. Flag a listed critical failure whenever applicable.",
        "Return only the required JSON object; notes must be brief and evidence-based.",
        "Evaluation input:",
        _canonical_bytes(request).decode("utf-8").strip(),
    ])


def _build_command(*, model: str, max_budget_usd: float, prompt: str) -> list[str]:
    return [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--json-schema", json.dumps(EVALUATOR_OUTPUT_SCHEMA, ensure_ascii=False, separators=(",", ":")),
        "--model", model,
        "--max-budget-usd", str(max_budget_usd),
        "--tools", "",
        "--permission-mode", "dontAsk",
        "--no-session-persistence",
    ]


def _structured_output(value: Mapping[str, object]) -> dict[str, object]:
    raw = value.get("structured_output")
    if raw is None:
        raw = value.get("result")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeSkillEvaluatorError("claude-result-is-not-structured-json") from exc
    if not isinstance(raw, dict) or set(raw) != _OUTPUT_KEYS:
        raise ClaudeSkillEvaluatorError("invalid-structured-evaluator-output")
    scores = raw["scores"]
    if not isinstance(scores, dict) or set(scores) != {
        "lifecycle_method_fit", "contract_semantic_sufficiency", "role_evidence", "context_efficiency",
    } or any(value not in {1, 3, 5} for value in scores.values()):
        raise ClaudeSkillEvaluatorError("invalid-structured-evaluator-scores")
    if not isinstance(raw["passed"], bool):
        raise ClaudeSkillEvaluatorError("invalid-structured-evaluator-passed")
    critical = raw["critical_failures"]
    notes = raw["notes"]
    if (not isinstance(critical, list) or len(set(critical)) != len(critical)
            or any(not isinstance(item, str) or not item for item in critical)
            or not isinstance(notes, list) or any(not isinstance(item, str) or not item for item in notes)):
        raise ClaudeSkillEvaluatorError("invalid-structured-evaluator-notes")
    return {
        "scores": {key: scores[key] for key in sorted(scores)},
        "passed": raw["passed"],
        "critical_failures": sorted(critical),
        "notes": list(notes),
    }


def run_once(
    request: Mapping[str, object], *, provider_name: str, model: str, max_budget_usd: float,
    database: Path, timeout_seconds: int, evaluator_version: str,
) -> dict[str, object]:
    """Run one semantic judgment with no filesystem or repository capability."""
    planned_runs = _planned_runs(request)
    environment = os.environ.copy()
    try:
        provider_environment = claude_skill_runner._provider_environment(database, provider_name)
        selected_model = claude_skill_runner._resolve_model(provider_environment, model)
        environment.update(provider_environment)
    except claude_skill_runner.ClaudeSkillRunnerError as exc:
        raise ClaudeSkillEvaluatorError(str(exc)) from exc
    command = _build_command(model=selected_model, max_budget_usd=max_budget_usd, prompt=_prompt(request))
    try:
        completed = subprocess.run(
            command,
            env=environment,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeSkillEvaluatorError("claude-evaluator-timeout") from exc
    if completed.returncode != 0:
        # stderr could contain a provider endpoint; preserve neither it nor
        # credentials in a durable report.
        raise ClaudeSkillEvaluatorError(f"claude-evaluator-failed:{completed.returncode}")
    response = _strict_object(completed.stdout, "claude-result")
    output = _structured_output(response)
    return {
        **output,
        "execution": {
            "provider": provider_name,
            "model": selected_model,
            "model_version": str(response.get("model", selected_model)),
            "temperature": "provider-default",
            "max_tokens": "provider-default",
            "tool_versions": {"claude": claude_skill_runner._claude_version(), "tools": "none"},
            "evaluator_model": selected_model,
            "evaluator_version": evaluator_version,
            "variant_runs": planned_runs,
        },
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="Zhipu GLM")
    parser.add_argument("--model", default="configured", help="CC Switch model or 'configured' (default)")
    parser.add_argument("--max-budget-usd", type=float, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--cc-switch-db", default=str(claude_skill_runner.DEFAULT_CC_SWITCH_DB))
    parser.add_argument("--evaluator-version", default="unconfigured")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        request = _strict_object(sys.stdin.buffer.read(), "evaluator-input")
        if args.max_budget_usd <= 0 or args.timeout_seconds <= 0:
            raise ClaudeSkillEvaluatorError("invalid-evaluator-budget-or-timeout")
        result = run_once(
            request,
            provider_name=args.provider,
            model=args.model,
            max_budget_usd=args.max_budget_usd,
            database=Path(args.cc_switch_db),
            timeout_seconds=args.timeout_seconds,
            evaluator_version=args.evaluator_version,
        )
    except ClaudeSkillEvaluatorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
