#!/usr/bin/env python3
"""Contract tests for the offline dual-lifecycle skill behavior evaluator."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import eval_skill_behavior  # noqa: E402


DATASET = ROOT / "evals" / "dual-lifecycle-skill-v1.jsonl"
BASELINE = ROOT / "evals" / "baselines" / "legacy-0.19.2.json"


class FixtureEvaluationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.temp = Path(self.tempdir.name)

    def candidate_fixture(self) -> dict[str, object]:
        cases, dataset_bytes = eval_skill_behavior.load_dataset(DATASET)
        policy_bindings = sorted(
            {
                (str(case["policy_input"]["policy_id"]), str(case["policy_input"]["sha256"]))
                for case in cases
            }
        )
        outputs: list[dict[str, object]] = []
        for case in cases:
            route = list(case["expected_route"])
            outputs.append({
                "case_id": case["case_id"],
                "route": route,
                "modules": list(case["expected_modules"]),
                "roles": list(case["expected_roles"]),
                "obligations": list(case["expected_obligations"]),
                "artifacts": list(case["required_artifacts"]),
                "actions": [],
                "transition": {
                    "decision": "reject" if route == ["reject-transition"] else "route",
                    "route": route,
                },
            })
        source_config = dict(cases[0]["model_run_config"])
        return {
            "fixture_format": eval_skill_behavior.FIXTURE_FORMAT,
            "mode": "fixture",
            "dataset_contract": {
                "path": "evals/dual-lifecycle-skill-v1.jsonl",
                "sha256": eval_skill_behavior.sha256_bytes(dataset_bytes),
            },
            "baseline_contract": {
                "path": "evals/baselines/legacy-0.19.2.json",
                "sha256": eval_skill_behavior.sha256_bytes(BASELINE.read_bytes()),
            },
            "policy_bindings": [
                {"policy_id": policy_id, "sha256": digest}
                for policy_id, digest in policy_bindings
            ],
            "run_config": {
                "source_model_run_config": source_config,
                "execution": {
                    "provider": "fixture",
                    "model": "none",
                    "model_version": "none",
                    "temperature": 0,
                    "max_tokens": 0,
                    "tool_versions": {"eval_skill_behavior": "v1"},
                    "evaluator_model": "deterministic-fixture",
                    "evaluator_version": "v1",
                    "variant_runs": 0,
                },
            },
            "outputs": outputs,
        }

    def write_fixture(self, value: dict[str, object]) -> Path:
        path = self.temp / "candidate.json"
        path.write_bytes(eval_skill_behavior.canonical_bytes(value))
        return path

    def evaluate(self, fixture: Path) -> dict[str, object]:
        return eval_skill_behavior.evaluate_fixture(
            ROOT,
            dataset_path=DATASET,
            baseline_path=BASELINE,
            fixture_path=fixture,
        )

    def test_fixture_mode_is_deterministic_and_covers_every_assertion_kind(self) -> None:
        fixture = self.write_fixture(self.candidate_fixture())
        first = self.evaluate(fixture)
        second = self.evaluate(fixture)

        self.assertEqual(first, second)
        self.assertEqual(first["mode"], "fixture")
        self.assertEqual(first["summary"], {"case_count": 12, "failed": 0, "passed": 12, "verdict": "PASS"})
        self.assertEqual(first["run_id"], eval_skill_behavior.report_id(first))
        assertion_names = {
            assertion["name"]
            for result in first["cases"]
            for assertion in result["assertions"]
        }
        self.assertEqual(
            assertion_names,
            {"actions", "artifacts", "modules", "obligations", "roles", "route", "transition"},
        )

    def test_candidate_mismatches_and_forbidden_actions_are_reported_without_stopping_other_cases(self) -> None:
        candidate = self.candidate_fixture()
        outputs = candidate["outputs"]
        self.assertIsInstance(outputs, list)
        outputs[0]["actions"] = ["treat-unknown-as-false"]
        outputs[1]["modules"] = ["product-core"]
        report = self.evaluate(self.write_fixture(candidate))

        self.assertEqual(report["summary"], {"case_count": 12, "failed": 2, "passed": 10, "verdict": "FAIL"})
        first = report["cases"][0]
        second = report["cases"][1]
        self.assertEqual(first["verdict"], "FAIL")
        self.assertEqual(second["verdict"], "FAIL")
        first_actions = next(assertion for assertion in first["assertions"] if assertion["name"] == "actions")
        self.assertEqual(first_actions["violations"], ["treat-unknown-as-false"])
        second_modules = next(assertion for assertion in second["assertions"] if assertion["name"] == "modules")
        self.assertEqual(second_modules["missing"], ["behavior-bdd", "engineering-spec", "implementation-tdd", "planning"])

    def test_route_obligation_artifact_and_transition_assertions_fail_independently(self) -> None:
        changes: dict[str, object] = {
            "route": ["unexpected-route"],
            "obligations": ["unexpected-obligation"],
            "artifacts": ["UnexpectedArtifact"],
            "transition": {"decision": "reject", "route": ["sdlc-product-design", "discover", "behavior-design"]},
        }
        for field, replacement in changes.items():
            with self.subTest(field=field):
                candidate = json.loads(json.dumps(self.candidate_fixture()))
                candidate["outputs"][0][field] = replacement
                report = self.evaluate(self.write_fixture(candidate))
                assertion = next(
                    item for item in report["cases"][0]["assertions"] if item["name"] == field
                )
                self.assertFalse(assertion["passed"])
                self.assertEqual(report["summary"]["failed"], 1)

    def test_live_output_keeps_empty_selections_for_mechanical_scoring(self) -> None:
        output = eval_skill_behavior._normalize_live_output({
            "case_id": "live-empty", "route": [], "modules": [], "roles": [], "obligations": [],
            "artifacts": [], "actions": [], "transition": {"decision": "route", "route": []},
        })
        self.assertEqual(output["modules"], [])
        with self.assertRaisesRegex(eval_skill_behavior.EvaluationError, "invalid-fixture-output-route"):
            eval_skill_behavior._normalize_output(output)

    def test_live_output_deduplicates_repeated_selected_identifiers(self) -> None:
        raw = {
            "case_id": "hotfix",
            "route": ["sdlc-product-design", "patch-contract", "patch-contract"],
            "modules": ["patch-contract", "patch-contract"],
            "roles": ["server-dev", "server-dev"],
            "obligations": ["delivery.hotfix.reproduction", "delivery.hotfix.reproduction"],
            "artifacts": ["PatchContract", "PatchContract"],
            "actions": [],
            "transition": {"decision": "route", "route": ["patch-contract", "patch-contract"]},
        }
        output = eval_skill_behavior._normalize_live_output(raw)
        self.assertEqual(output["route"], ["sdlc-product-design", "patch-contract"])
        self.assertEqual(output["transition"]["route"], ["patch-contract"])
        with self.assertRaisesRegex(eval_skill_behavior.EvaluationError, "duplicate-fixture-output-route"):
            eval_skill_behavior._normalize_output(raw)

    def test_contract_drift_and_remote_execution_are_refused(self) -> None:
        bad_hash = self.candidate_fixture()
        bad_hash["dataset_contract"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(eval_skill_behavior.EvaluationError, "dataset-contract-hash-mismatch"):
            self.evaluate(self.write_fixture(bad_hash))

        remote = self.candidate_fixture()
        remote["run_config"]["execution"]["provider"] = "remote-provider"
        with self.assertRaisesRegex(eval_skill_behavior.EvaluationError, "remote-model-mode-is-not-supported"):
            self.evaluate(self.write_fixture(remote))

    def test_cli_writes_a_canonical_content_addressed_report_and_refuses_model_mode(self) -> None:
        fixture = self.write_fixture(self.candidate_fixture())
        output = self.temp / "report.json"
        command = [
            sys.executable,
            str(HERE / "eval_skill_behavior.py"),
            "--repo", str(ROOT),
            "--dataset", "evals/dual-lifecycle-skill-v1.jsonl",
            "--baseline", "evals/baselines/legacy-0.19.2.json",
            "--fixture", str(fixture),
            "--out", str(output),
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(output.read_bytes(), eval_skill_behavior.canonical_bytes(report))
        self.assertEqual(json.loads(completed.stdout), report)
        self.assertEqual(report["run_id"], eval_skill_behavior.report_id(report))

        refused = subprocess.run([*command, "--mode", "model"], capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("remote-model-mode-is-not-supported", refused.stderr)

    def test_cli_live_mode_uses_the_explicit_harness_contract(self) -> None:
        output = self.temp / "live-report.json"
        runner = f"{sys.executable} {HERE / 'fixtures' / 'fake_skill_runner.py'}"
        command = [
            sys.executable,
            str(HERE / "eval_skill_behavior.py"),
            "--repo", str(ROOT),
            "--dataset", "evals/dual-lifecycle-skill-v1.jsonl",
            "--baseline", "evals/baselines/legacy-0.19.2.json",
            "--mode", "live",
            "--runner-cmd", runner,
            "--runs", "1",
            "--mechanical-only",
            "--out", str(output),
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["report_format"], "sdlc-skill-behavior-live-report-v1")
        self.assertEqual(report["summary"]["verdict"], "PASS")
        self.assertEqual(json.loads(completed.stdout)["run_id"], report["run_id"])

    def test_cli_live_failure_writes_secret_free_content_addressed_evidence(self) -> None:
        failure = self.temp / "live-failure.json"
        runner = (
            f'{sys.executable} -c "import sys; '
            "print('ERROR: claude-runner-failed:model:2', file=sys.stderr); raise SystemExit(2)\""
        )
        completed = subprocess.run([
            sys.executable, str(HERE / "eval_skill_behavior.py"),
            "--repo", str(ROOT), "--mode", "live", "--runner-cmd", runner,
            "--runs", "1", "--mechanical-only", "--out", str(self.temp / "unused.json"),
            "--failure-out", str(failure),
        ], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        report = json.loads(failure.read_text(encoding="utf-8"))
        self.assertEqual(report["report_format"], "sdlc-skill-behavior-failure-v1")
        self.assertEqual(report["error"], "runner-failed:2:claude-runner-failed:model:2")
        self.assertEqual(report["run_id"], eval_skill_behavior.sha256_bytes(
            eval_skill_behavior.canonical_bytes({key: value for key, value in report.items() if key != "run_id"})
        ))


if __name__ == "__main__":
    unittest.main()
