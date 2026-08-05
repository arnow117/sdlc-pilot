#!/usr/bin/env python3
"""Tests for the immutable legacy Skill baseline manifest."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import skill_baseline  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_repo_file(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CaptureFromGitTest(unittest.TestCase):
    def make_repository(self) -> Path:
        tempdir = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(tempdir)], check=True)
        subprocess.run(["git", "-C", str(tempdir), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(tempdir), "config", "user.name", "Baseline Test"], check=True)
        write_repo_file(tempdir, ".claude-plugin/plugin.json", '{"version":"1.2.3"}\n')
        write_repo_file(tempdir, "skills/a.md", "committed a\n")
        write_repo_file(tempdir, "skills/b.md", "committed b\n")
        subprocess.run(["git", "-C", str(tempdir), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tempdir), "commit", "-qm", "baseline"], check=True)
        self.addCleanup(lambda: shutil.rmtree(tempdir, ignore_errors=True))
        return tempdir

    def test_capture_reads_only_committed_bytes_and_is_canonical(self) -> None:
        repo = self.make_repository()
        source_commit = git(repo, "rev-parse", "HEAD")
        write_repo_file(repo, "skills/a.md", "uncommitted replacement\n")
        scenarios = {
            "one": ["skills/a.md"],
            "both": ["skills/a.md", "skills/b.md"],
        }

        baseline = skill_baseline.capture_from_git(repo, "HEAD", scenarios)

        self.assertEqual(baseline["source_commit"], source_commit)
        self.assertEqual(baseline["plugin"]["version"], "1.2.3")
        paths = [item["path"] for item in baseline["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(paths, ["skills/a.md", "skills/b.md"])
        first = baseline["files"][0]
        self.assertEqual(first["utf8_bytes"], len(b"committed a\n"))
        self.assertEqual(first["sha256"], skill_baseline.sha256_bytes(b"committed a\n"))
        scenario_sizes = {
            scenario["scenario_id"]: scenario["total_utf8_bytes"]
            for scenario in baseline["scenarios"]
        }
        self.assertEqual(scenario_sizes["one"], len(b"committed a\n"))
        self.assertEqual(
            skill_baseline.canonical_bytes(baseline),
            skill_baseline.canonical_bytes(skill_baseline.capture_from_git(repo, source_commit, scenarios)),
        )

    def test_capture_rejects_paths_outside_the_source_tree(self) -> None:
        repo = self.make_repository()
        with self.assertRaises(skill_baseline.BaselineError):
            skill_baseline.capture_from_git(repo, "HEAD", {"bad": ["../secrets.txt"]})
        with self.assertRaises(skill_baseline.BaselineError):
            skill_baseline.capture_from_git(repo, "HEAD", {"bad": ["skills/missing.md"]})

    def test_default_scenarios_cover_all_context_budget_classes(self) -> None:
        baseline = skill_baseline.capture_from_git(
            ROOT, "2cba633", skill_baseline.DEFAULT_SCENARIOS)
        self.assertEqual(
            {scenario["scenario_id"] for scenario in baseline["scenarios"]},
            {"product-small", "engineering-plan", "single-surface-build", "hotfix-build", "validate-review"},
        )
        self.assertTrue(all(scenario["paths"] for scenario in baseline["scenarios"]))
        self.assertTrue(all(len(item["sha256"]) == 64 for item in baseline["files"]))

    def test_check_recomputes_manifest_and_rejects_a_changed_blob_hash(self) -> None:
        baseline = skill_baseline.capture_from_git(
            ROOT, "2cba633", skill_baseline.DEFAULT_SCENARIOS)
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "baseline.json"
            manifest_path.write_bytes(skill_baseline.canonical_bytes(baseline))
            skill_baseline.check_manifest(ROOT, manifest_path)

            changed = json.loads(manifest_path.read_text(encoding="utf-8"))
            changed["files"][0]["sha256"] = "0" * 64
            manifest_path.write_bytes(skill_baseline.canonical_bytes(changed))
            with self.assertRaises(skill_baseline.BaselineError):
                skill_baseline.check_manifest(ROOT, manifest_path)


class CliTest(unittest.TestCase):
    def test_capture_and_check_commands_are_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dual-lifecycle-baseline.json"
            command = [sys.executable, str(HERE / "skill_baseline.py")]
            subprocess.run(
                [*command, "capture", "--repo", str(ROOT), "--source-ref", "2cba633", "--out", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            first = output.read_bytes()
            subprocess.run(
                [*command, "capture", "--repo", str(ROOT), "--source-ref", "2cba633", "--out", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first, output.read_bytes())
            subprocess.run(
                [*command, "check", "--repo", str(ROOT), "--manifest", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )


class DatasetContractTest(unittest.TestCase):
    DATASET = ROOT / "evals" / "dual-lifecycle-skill-v1.jsonl"
    BASELINE = ROOT / "evals" / "baselines" / "legacy-0.19.2.json"

    def test_dataset_has_one_complete_case_for_every_required_category(self) -> None:
        cases = skill_baseline.load_cases(self.DATASET)
        self.assertEqual(len(cases), 12)
        self.assertEqual(
            {case["category"] for case in cases},
            skill_baseline.REQUIRED_CATEGORIES,
        )
        self.assertTrue(all(case["expected_obligations"] for case in cases))
        self.assertTrue(all(case["repository_snapshot"]["base_sha"] for case in cases))
        self.assertTrue(all(case["policy_input"]["sha256"] for case in cases))
        self.assertTrue(all(case["model_run_config"]["required_binding_fields"] for case in cases))
        forged = next(case for case in cases if case["category"] == "forged-completion")
        self.assertTrue({"approved", "tests_passed", "review_complete"}.issubset(forged["intent_flags"]))
        self.assertIn("accept-self-reported-completion", forged["forbidden_actions"])

    def test_dataset_rejects_unknown_fields_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "invalid.jsonl"
            invalid.write_text(
                json.dumps({"case_id": "bad", "unexpected": True}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(skill_baseline.BaselineError):
                skill_baseline.load_cases(invalid)

    def test_baseline_binds_the_dataset_hash(self) -> None:
        baseline = json.loads(self.BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(
            baseline["dataset_contract"],
            {
                "path": "evals/dual-lifecycle-skill-v1.jsonl",
                "sha256": skill_baseline.sha256_bytes(self.DATASET.read_bytes()),
            },
        )
        skill_baseline.check_manifest(ROOT, self.BASELINE)


if __name__ == "__main__":
    unittest.main()
