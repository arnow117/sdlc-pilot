#!/usr/bin/env python3
"""Tests for exact historical legacy-runbook loading."""
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

import legacy_runbook  # noqa: E402


class LegacyRunbookTest(unittest.TestCase):
    def test_manifest_has_a_complete_pinned_legacy_surface(self) -> None:
        manifest = legacy_runbook.load_manifest(ROOT)
        self.assertEqual(manifest["schema_version"], legacy_runbook.SCHEMA_VERSION)
        self.assertEqual(manifest["version"], "0.19.2")
        self.assertEqual(
            set(manifest["runbooks"]),
            {"driver", "spec", "plan", "build", "validate", "review"},
        )
        self.assertEqual(len(manifest["source_commit"]), 40)

    def test_loader_reads_historical_not_worktree_bytes_and_verifies_each_digest(self) -> None:
        for stage in ("driver", "spec", "plan", "build", "validate", "review"):
            with self.subTest(stage=stage):
                payload = legacy_runbook.load_runbook(stage, ROOT)
                self.assertTrue(payload.startswith(b"---\n"))
                self.assertIn(b"control-plane.md", payload)
        report = legacy_runbook.verify(ROOT)
        self.assertEqual(
            report["runbook_sha256"]["spec"],
            legacy_runbook.sha256_bytes(legacy_runbook.load_runbook("spec", ROOT)),
        )
        self.assertEqual(len(report["report_sha256"]), 64)

    def test_manifest_rejects_unsafe_or_incomplete_data(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            target = root / legacy_runbook.MANIFEST_RELATIVE_PATH
            target.parent.mkdir(parents=True)
            target.write_text(
                json.dumps(
                    {
                        "schema_version": legacy_runbook.SCHEMA_VERSION,
                        "version": "0.19.2",
                        "source_commit": "0" * 40,
                        "runbooks": {
                            stage: {
                                "path": "../unsafe.md",
                                "sha256": "0" * 64,
                                "utf8_bytes": 1,
                            }
                            for stage in ("driver", "spec", "plan", "build", "validate", "review")
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(legacy_runbook.LegacyRunbookError, "unsafe-legacy-runbook-path"):
                legacy_runbook.load_manifest(root)

    def test_missing_historical_object_fails_closed(self) -> None:
        tempdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tempdir, ignore_errors=True))
        subprocess.run(["git", "init", "-q", str(tempdir)], check=True)
        manifest = (ROOT / legacy_runbook.MANIFEST_RELATIVE_PATH).read_bytes()
        target = tempdir / legacy_runbook.MANIFEST_RELATIVE_PATH
        target.parent.mkdir(parents=True)
        target.write_bytes(manifest)
        with self.assertRaisesRegex(legacy_runbook.LegacyRunbookError, "legacy-runbook-git-object-unavailable"):
            legacy_runbook.load_runbook("spec", tempdir)

    def test_cli_show_and_verify_are_deterministic(self) -> None:
        command = [sys.executable, str(HERE / "legacy_runbook.py"), "--repo-root", str(ROOT)]
        shown = subprocess.run(
            [*command, "show", "--stage", "plan"],
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(shown, legacy_runbook.load_runbook("plan", ROOT))
        verified = subprocess.run(
            [*command, "verify"],
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(json.loads(verified), legacy_runbook.verify(ROOT))


if __name__ == "__main__":
    unittest.main()
