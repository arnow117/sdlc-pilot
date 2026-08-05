#!/usr/bin/env python3
"""Deterministic evaluator used only to test live harness aggregation."""
from __future__ import annotations

import json
import sys


def main() -> int:
    request = json.load(sys.stdin)
    run = request["run"]
    runs = run["request"]["planned_runs"]
    result = {
        "scores": {
            "lifecycle_method_fit": 5,
            "contract_semantic_sufficiency": 5,
            "role_evidence": 5,
            "context_efficiency": 5,
        },
        "passed": True,
        "critical_failures": [],
        "notes": [],
        "execution": {
            "provider": "fixture", "model": "fake-skill-evaluator", "model_version": "v1",
            "temperature": 0, "max_tokens": 0,
            "tool_versions": {"fake_skill_evaluator": "v1"},
            "evaluator_model": "fake-skill-evaluator", "evaluator_version": "v1",
            "variant_runs": runs,
        },
    }
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
