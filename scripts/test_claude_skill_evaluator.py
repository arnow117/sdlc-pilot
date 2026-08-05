#!/usr/bin/env python3
"""Read-only contract tests for the CC Switch semantic evaluator adapter."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import claude_skill_evaluator  # noqa: E402


class ClaudeSkillEvaluatorTest(unittest.TestCase):
    def request(self) -> dict[str, object]:
        return {"run": {"request": {"planned_runs": 5}}}

    def test_command_has_an_explicit_no_tool_boundary(self) -> None:
        command = claude_skill_evaluator._build_command(
            model="sonnet", max_budget_usd=0.10, prompt="judge",
        )
        self.assertEqual(command[0:2], ["claude", "-p"])
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertNotIn("--plugin-dir", command)
        self.assertIn("--max-budget-usd", command)

    def test_output_and_run_count_are_strict(self) -> None:
        output = claude_skill_evaluator._structured_output({
            "structured_output": {
                "scores": {
                    "lifecycle_method_fit": 5,
                    "contract_semantic_sufficiency": 3,
                    "role_evidence": 5,
                    "context_efficiency": 3,
                },
                "passed": True,
                "critical_failures": [],
                "notes": ["bound to recorded evidence"],
            },
        })
        self.assertEqual(output["scores"]["lifecycle_method_fit"], 5)
        self.assertEqual(claude_skill_evaluator._planned_runs(self.request()), 5)
        with self.assertRaisesRegex(claude_skill_evaluator.ClaudeSkillEvaluatorError, "planned-runs"):
            claude_skill_evaluator._planned_runs({"run": {"request": {"planned_runs": 0}}})
        with self.assertRaisesRegex(claude_skill_evaluator.ClaudeSkillEvaluatorError, "scores"):
            claude_skill_evaluator._structured_output({
                "structured_output": {
                    "scores": {"lifecycle_method_fit": 2},
                    "passed": True,
                    "critical_failures": [],
                    "notes": [],
                },
            })


if __name__ == "__main__":
    unittest.main()
