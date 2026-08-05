#!/usr/bin/env python3
"""Contract tests for argv-only preview Evidence collection."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import evidence_runner


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


class EvidenceRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.cwd = Path(self.tempdir.name)

    def run_evidence(self, argv: list[str], **kwargs: object) -> dict[str, object]:
        return evidence_runner.run(
            argv,
            cwd=self.cwd,
            policy_manifest_ref=SHA_A,
            context_manifest_ref=SHA_B,
            code_sha=SHA_C,
            **kwargs,
        )

    def test_success_facts_are_derived_from_runner_output(self) -> None:
        record = self.run_evidence([sys.executable, "-c", "print('ok')"])
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["scope"], "preview")
        self.assertEqual(record["stdout"]["encoding"], "utf-8")  # type: ignore[index]
        facts = evidence_runner.derive_mechanical_facts(record)
        self.assertTrue(facts["runner_succeeded"])

    def test_failure_timeout_truncation_and_binary_output(self) -> None:
        failed = self.run_evidence([sys.executable, "-c", "import sys; sys.exit(3)"])
        self.assertEqual(failed["exit_code"], 3)
        timed_out = self.run_evidence([sys.executable, "-c", "import time; time.sleep(5)"], timeout_seconds=0.05)
        self.assertTrue(timed_out["timed_out"])
        binary = self.run_evidence(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff' * 64)"],
            max_output_bytes=8,
        )
        self.assertTrue(binary["stdout"]["truncated"])  # type: ignore[index]
        self.assertEqual(binary["stdout"]["encoding"], "binary")  # type: ignore[index]

    def test_argv_does_not_invoke_a_shell_and_identity_is_deterministic(self) -> None:
        literal = "safe; touch should-not-exist"
        argv = [sys.executable, "-c", "import sys; print(sys.argv[1])", literal]
        first = self.run_evidence(argv)
        second = self.run_evidence(argv)
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertIn(literal, first["stdout"]["preview"])  # type: ignore[index]
        self.assertFalse((self.cwd / "should-not-exist").exists())

    def test_canonical_runner_is_an_explicit_separate_authority_api(self) -> None:
        record = evidence_runner.run_canonical(
            [sys.executable, "-c", "print('canonical')"],
            cwd=self.cwd,
            policy_manifest_ref=SHA_A,
            context_manifest_ref=SHA_B,
            code_sha=SHA_C,
        )
        self.assertEqual(record["scope"], "canonical")
        self.assertEqual(record["schema_version"], "canonical-runner-evidence-v1")
        self.assertTrue(evidence_runner.derive_mechanical_facts(record)["runner_succeeded"])

    def test_self_report_and_non_preview_scope_are_rejected(self) -> None:
        with self.assertRaises(evidence_runner.EvidenceError):
            self.run_evidence([sys.executable, "-c", "print('x')"], scope="canonical")
        with self.assertRaises(evidence_runner.EvidenceError):
            evidence_runner.derive_mechanical_facts({"tests_passed": True})


if __name__ == "__main__":
    unittest.main()
