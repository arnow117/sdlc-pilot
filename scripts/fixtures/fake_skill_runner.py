#!/usr/bin/env python3
"""Deterministic provider-neutral runner used only by live harness tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import skill_eval_adapter  # noqa: E402


def main() -> int:
    request = json.load(sys.stdin)
    case = request["case"]
    output = skill_eval_adapter.expected_output(case, variant=request["variant"])
    if os.environ.get("FAKE_SKILL_RUNNER_FORGE") == "1" and case["case_id"] == "forged-completion":
        output["actions"] = ["accept-self-reported-completion"]
    result = {
        "output": output,
        "tool_events": [],
        "manifests": {"policy": case["policy_input"], "context": {"source_ref": request["source_ref"]}, "obligation": {}},
        "cost": {"usd": 0.0},
        "execution": {
            "provider": "fixture", "model": "fake-skill-runner", "model_version": "v1",
            "temperature": 0, "max_tokens": 0,
            "tool_versions": {"fake_skill_runner": "v1"},
            "evaluator_model": "fake-skill-evaluator", "evaluator_version": "v1",
            "variant_runs": request["planned_runs"],
        },
    }
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
