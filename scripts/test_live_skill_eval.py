#!/usr/bin/env python3
"""Tests for the provider-neutral repeated behavior-evaluation harness."""
from __future__ import annotations

import os
import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import live_skill_eval  # noqa: E402


RUNNER = f"{sys.executable} {HERE / 'fixtures' / 'fake_skill_runner.py'}"
JUDGE = f"{sys.executable} {HERE / 'fixtures' / 'fake_skill_evaluator.py'}"


class LiveSkillEvaluationTest(unittest.TestCase):
    def calibration(self) -> Path:
        report = self.temp / "evaluator-calibration.json"
        report.write_text(json.dumps({
            "calibration_format": "sdlc-skill-evaluator-calibration-v1",
            "evaluator": {
                "provider": "fixture", "model": "fake-skill-evaluator", "model_version": "v1", "evaluator_version": "v1",
            },
            "double_human_review_count": 20,
            "pass_fail_agreement": 0.85,
            "review_record_refs": [f"human-review:{index:02d}" for index in range(20)],
        }), encoding="utf-8")
        return report

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.temp = Path(self.tempdir.name)

    def test_mechanical_runner_writes_repeatable_full_trace(self) -> None:
        report = live_skill_eval.evaluate_live(
            ROOT,
            dataset_path="evals/dual-lifecycle-skill-v1.jsonl",
            baseline_path="evals/baselines/legacy-0.19.2.json",
            runner_cmd=RUNNER,
            evaluator_cmd=None,
            runs=5,
            mechanical_only=True,
            timeout_seconds=10,
        )
        self.assertEqual(report["summary"]["verdict"], "PASS")
        self.assertEqual(len(report["records"]), 120)
        self.assertEqual(report["summary"]["mechanical"]["rate"], 1.0)
        self.assertTrue(all(record["record_id"] for record in report["records"]))
        candidate = next(record for record in report["records"] if record["variant"] == "candidate")
        baseline = next(record for record in report["records"] if record["variant"] == "baseline")
        self.assertEqual(candidate["request"]["invocation"]["authority"], "dual-lifecycle-v1")
        self.assertEqual(baseline["request"]["invocation"]["authority"], "legacy")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report.json"
            live_skill_eval.write_report(output, report)
            self.assertEqual(output.read_bytes(), live_skill_eval._canonical_bytes(report))

    def test_semantic_runner_enforces_full_threshold_set(self) -> None:
        report = live_skill_eval.evaluate_live(
            ROOT,
            dataset_path="evals/dual-lifecycle-skill-v1.jsonl",
            baseline_path="evals/baselines/legacy-0.19.2.json",
            runner_cmd=RUNNER,
            evaluator_cmd=JUDGE,
            runs=1,
            mechanical_only=False,
            timeout_seconds=10,
            calibration_path=self.calibration(),
        )
        self.assertEqual(report["summary"]["verdict"], "PASS")
        self.assertEqual(report["summary"]["semantic"]["weighted_score"], 5.0)

    def test_semantic_evaluation_refuses_an_uncalibrated_judge(self) -> None:
        with self.assertRaisesRegex(live_skill_eval.LiveEvaluationError, "evaluator-calibration-required"):
            live_skill_eval.evaluate_live(
                ROOT,
                dataset_path="evals/dual-lifecycle-skill-v1.jsonl",
                baseline_path="evals/baselines/legacy-0.19.2.json",
                runner_cmd=RUNNER,
                evaluator_cmd=JUDGE,
                runs=1,
                mechanical_only=False,
                timeout_seconds=10,
            )

    def test_semantic_evaluation_refuses_a_calibration_for_a_different_judge(self) -> None:
        calibration = self.calibration()
        value = json.loads(calibration.read_text(encoding="utf-8"))
        value["evaluator"]["model"] = "different-evaluator"
        calibration.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(live_skill_eval.LiveEvaluationError, "calibration-identity-mismatch"):
            live_skill_eval.evaluate_live(
                ROOT,
                dataset_path="evals/dual-lifecycle-skill-v1.jsonl",
                baseline_path="evals/baselines/legacy-0.19.2.json",
                runner_cmd=RUNNER,
                evaluator_cmd=JUDGE,
                runs=1,
                mechanical_only=False,
                timeout_seconds=10,
                calibration_path=calibration,
            )

    def test_forbidden_completion_fails_mechanical_verdict(self) -> None:
        old = os.environ.get("FAKE_SKILL_RUNNER_FORGE")
        os.environ["FAKE_SKILL_RUNNER_FORGE"] = "1"
        self.addCleanup(
            lambda: os.environ.pop("FAKE_SKILL_RUNNER_FORGE", None)
            if old is None else os.environ.__setitem__("FAKE_SKILL_RUNNER_FORGE", old)
        )
        report = live_skill_eval.evaluate_live(
            ROOT,
            dataset_path="evals/dual-lifecycle-skill-v1.jsonl",
            baseline_path="evals/baselines/legacy-0.19.2.json",
            runner_cmd=RUNNER,
            evaluator_cmd=None,
            runs=1,
            mechanical_only=True,
            timeout_seconds=10,
        )
        self.assertEqual(report["summary"]["verdict"], "FAIL")
        self.assertIn("mechanical-assertion-failed", report["summary"]["reasons"])


if __name__ == "__main__":
    unittest.main()
