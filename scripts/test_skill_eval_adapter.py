#!/usr/bin/env python3
"""Contract tests for the explicit behavior-evaluation invocation adapter."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import eval_skill_behavior  # noqa: E402
import context_resolver  # noqa: E402
import policy_compiler  # noqa: E402
import skill_eval_adapter  # noqa: E402


class SkillEvaluationAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases, _ = eval_skill_behavior.load_dataset(ROOT / "evals/dual-lifecycle-skill-v1.jsonl")

    def test_candidate_cases_are_explicitly_dual_and_use_canonical_selector_names(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                invocation = skill_eval_adapter.build_invocation(case, variant="candidate")
                self.assertEqual(invocation["authority"], "dual-lifecycle-v1")
                self.assertTrue(invocation["explicit_authority_required"])
                self.assertNotEqual(invocation["steps"][0]["skill"], "sdlc")
        complex_case = next(case for case in self.cases if case["case_id"] == "complex-domain")
        ai_case = next(case for case in self.cases if case["case_id"] == "ai-output")
        self.assertTrue(skill_eval_adapter.build_invocation(complex_case, variant="candidate")["intent_flags"]["domain_model_needed"])
        self.assertTrue(skill_eval_adapter.build_invocation(complex_case, variant="candidate")["intent_flags"]["domain_rule"])
        self.assertTrue(skill_eval_adapter.build_invocation(ai_case, variant="candidate")["intent_flags"]["ai_output"])

    def test_candidate_expectations_are_static_canonical_policy_contracts(self) -> None:
        modules = {item["id"] for item in json.loads(
            (ROOT / "skills/sdlc/references/policies/modules.json").read_text(encoding="utf-8"))["modules"]}
        roles = {item["id"] for item in json.loads(
            (ROOT / "skills/sdlc/references/policies/roles.json").read_text(encoding="utf-8"))["roles"]}
        phases = json.loads((ROOT / "skills/sdlc/references/policies/phases.json").read_text(encoding="utf-8"))["phases"]
        obligations = {item["id"] for phase in phases for item in phase["obligations"]}
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                expected = skill_eval_adapter.expected_case(case, variant="candidate")
                invocation = skill_eval_adapter.build_invocation(case, variant="candidate")
                self.assertEqual(
                    expected["expected_route"],
                    [f"{step['skill']}:{step['phase']}" for step in invocation["steps"]],
                )
                self.assertTrue(set(expected["expected_modules"]).issubset(modules))
                self.assertTrue(set(expected["expected_roles"]).issubset(roles))
                self.assertTrue(set(expected["expected_obligations"]).issubset(obligations))
                output = skill_eval_adapter.expected_output(case, variant="candidate")
                self.assertEqual(output["transition"], expected["expected_transition"])

    def test_explicit_false_flags_keep_irrelevant_context_out_of_candidate_contract(self) -> None:
        small = next(case for case in self.cases if case["case_id"] == "small-feature")
        flags = skill_eval_adapter.build_invocation(small, variant="candidate")["intent_flags"]
        self.assertFalse(flags["domain_rule"])
        self.assertFalse(flags["security_sensitive"])
        expected = skill_eval_adapter.expected_case(small, variant="candidate")
        self.assertNotIn("mod.delivery.tactical-ddd", expected["expected_modules"])
        self.assertNotIn("mod.delivery.security", expected["expected_modules"])

    def test_explicit_false_flags_reduce_the_resolved_engineering_context(self) -> None:
        small = next(case for case in self.cases if case["case_id"] == "small-feature")
        policy = policy_compiler.compile_policy(
            ROOT / "skills/sdlc/references/policies", ROOT / "skills", "1.0.0",
        )
        context = context_resolver.resolve_context({
            "scope": "preview",
            "command": "skill-eval",
            "lifecycle_run_id": "eval.small.001",
            "phase_id": "phase.delivery.engineering-spec",
            "lifecycle": "software-delivery",
            "operation": "engineering-spec",
            "work_type": "feature",
            "authority_mode": "legacy",
            "identity": {"requirement_id": "REQ-001"},
            "contracts": {},
            "profile": {"sha256": "1" * 64},
            "diff": {
                "scope": "legacy", "base_sha": "a" * 40, "head_sha": "b" * 40,
                "dirty": False, "staged": False, "untracked": False,
            },
            "intent_flags": skill_eval_adapter.build_invocation(small, variant="candidate")["intent_flags"],
            "runtime_event": {"type": "skill-evaluation"},
            "engine_version": "1.0.0",
            "modes": [],
            "selector_attestation_refs": [],
        }, policy, ROOT, ROOT / "skills")
        self.assertEqual(
            [module["id"] for module in context["selected_modules"]],
            ["mod.delivery.core-sdd", "mod.delivery.engineering-spec"],
        )
        self.assertFalse(context["needs_classification"])

    def test_high_risk_and_blocking_scenarios_have_required_canonical_guards(self) -> None:
        reliability = next(case for case in self.cases if case["case_id"] == "reliability-security")
        ai = next(case for case in self.cases if case["case_id"] == "ai-output")
        gap = next(case for case in self.cases if case["case_id"] == "implementation-spec-gap")
        hotfix = next(case for case in self.cases if case["case_id"] == "hotfix")
        self.assertIn("obl.delivery.security.review", skill_eval_adapter.expected_case(
            reliability, variant="candidate")["expected_obligations"])
        self.assertIn("obl.delivery.eval-harness.bench", skill_eval_adapter.expected_case(
            ai, variant="candidate")["expected_obligations"])
        self.assertEqual(skill_eval_adapter.expected_case(
            gap, variant="candidate")["expected_transition"]["decision"], "reject")
        self.assertIn("sdlc-software-delivery:plan", skill_eval_adapter.expected_case(
            hotfix, variant="candidate")["expected_route"])

    def test_baseline_is_bound_to_legacy_and_unknown_case_is_rejected(self) -> None:
        baseline = skill_eval_adapter.build_invocation(self.cases[0], variant="baseline")
        self.assertEqual(baseline["authority"], "legacy")
        self.assertEqual(baseline["steps"], [{"skill": "sdlc", "phase": "legacy", "operation": "legacy-route"}])
        with self.assertRaisesRegex(skill_eval_adapter.SkillEvaluationAdapterError, "unsupported-evaluation-case"):
            skill_eval_adapter.build_invocation({"case_id": "unknown", "request": "x", "intent_flags": {"x": True}}, variant="candidate")


if __name__ == "__main__":
    unittest.main()
