#!/usr/bin/env python3
"""Behavior checks for the offline Codex Security dependency probe."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "skills" / "sdlc" / "scripts" / "check_security_dependency.py"
SECRET_SENTINEL = "example-secret-never-print-624"


class DependencyProbeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bin_dir = Path(self.directory.name) / "bin"
        self.bin_dir.mkdir()
        self.marker = Path(self.directory.name) / "candidate-executed"

    def make_candidate(self, name):
        suffix = ".cmd" if os.name == "nt" else ""
        candidate = self.bin_dir / (name + suffix)
        if os.name == "nt":
            candidate.write_text(f"@echo ran > {self.marker}\n", encoding="utf-8")
        else:
            candidate.write_text(f"#!/bin/sh\ntouch '{self.marker}'\n", encoding="utf-8")
            candidate.chmod(0o755)
        return candidate

    def run_probe(self):
        environment = os.environ.copy()
        environment["PATH"] = str(self.bin_dir)
        environment["OPENAI_API_KEY"] = SECRET_SENTINEL
        environment["CODEX_API_KEY"] = SECRET_SENTINEL
        result = subprocess.run(
            [sys.executable, str(PROBE)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(SECRET_SENTINEL, result.stdout + result.stderr)
        self.assertFalse(self.marker.exists(), "probe executed a PATH candidate")
        report = json.loads(result.stdout)
        self.assertNotIn("强烈", report["recommendation"])
        return report

    def test_missing_cli_suggests_install_without_claiming_auth(self):
        report = self.run_probe()
        self.assertEqual(report["cli"]["state"], "not_found")
        self.assertIn("安装", report["recommendation"])
        self.assertEqual(report["plugin"], "not_checked")
        self.assertEqual(report["authentication"], "not_checked")
        self.assertEqual(report["scan"], "not_run")

    def test_long_name_is_only_a_candidate_and_is_not_executed(self):
        candidate = self.make_candidate("codex-security")
        self.make_candidate("node")
        self.make_candidate("npm")
        report = self.run_probe()
        self.assertEqual(report["cli"]["state"], "long_name_found")
        self.assertEqual(Path(report["cli"]["long_name"]), candidate)
        self.assertTrue(report["prerequisites"]["node_on_path"])
        self.assertTrue(report["prerequisites"]["npm_on_path"])
        self.assertEqual(report["version"], "not_checked")
        self.assertEqual(report["authentication"], "not_checked")
        self.assertIn("未检查", report["recommendation"])

    def test_short_name_alone_is_ambiguous(self):
        candidate = self.make_candidate("cs")
        report = self.run_probe()
        self.assertEqual(report["cli"]["state"], "short_name_ambiguous")
        self.assertEqual(Path(report["cli"]["short_name"]), candidate)
        self.assertIn("核实", report["recommendation"])


if __name__ == "__main__":
    unittest.main()
