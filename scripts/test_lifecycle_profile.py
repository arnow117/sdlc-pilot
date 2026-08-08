#!/usr/bin/env python3
"""Contract tests for project-scoped lifecycle default and migration selection."""
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

import lifecycle_profile  # noqa: E402


class LifecycleProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_clean_repository_defaults_to_dual_and_initialization_persists_it(self) -> None:
        before = lifecycle_profile.status(self.repo)
        self.assertEqual(before["resolution"], "new-project-default")
        self.assertEqual(before["mode"], lifecycle_profile.DUAL_MODE)
        self.assertEqual(before["artifacts"], [])

        initialized = lifecycle_profile.initialize(self.repo)
        self.assertEqual(initialized["resolution"], "configured")
        self.assertEqual(initialized["mode"], lifecycle_profile.DUAL_MODE)
        self.assertEqual(initialized["selection"], "new-project-default-v1")
        self.assertEqual(json.loads((self.repo / ".sdlc/lifecycle.json").read_text(encoding="utf-8")), {
            "mode": lifecycle_profile.DUAL_MODE,
            "profile_format": lifecycle_profile.PROFILE_FORMAT,
            "selection": "new-project-default-v1",
        })

    def test_legacy_artifacts_require_explicit_selection_and_are_never_reclassified(self) -> None:
        (self.repo / ".sdlc").mkdir()
        (self.repo / ".sdlc/STATE.md").write_text("legacy state\n", encoding="utf-8")
        before = lifecycle_profile.status(self.repo)
        self.assertEqual(before["resolution"], "migration-required")
        self.assertEqual(before["artifacts"], ["legacy-state"])

        with self.assertRaisesRegex(lifecycle_profile.LifecycleProfileError, "cannot-initialize:migration-required"):
            lifecycle_profile.initialize(self.repo)
        with self.assertRaisesRegex(
            lifecycle_profile.LifecycleProfileError, "dual-migration-requires-existing-artifact-confirmation",
        ):
            lifecycle_profile.migrate(lifecycle_profile.DUAL_MODE, repo=self.repo)

        migrated = lifecycle_profile.migrate(lifecycle_profile.LEGACY_MODE, repo=self.repo)
        self.assertEqual(migrated["mode"], lifecycle_profile.LEGACY_MODE)
        self.assertTrue((self.repo / ".sdlc/STATE.md").is_file())
        self.assertEqual((self.repo / ".sdlc/STATE.md").read_text(encoding="utf-8"), "legacy state\n")

    def test_dual_selection_over_existing_artifacts_requires_confirmation_but_never_converts_them(self) -> None:
        (self.repo / ".sdlc-control/dual-lifecycle").mkdir(parents=True)
        ledger = self.repo / ".sdlc-control/dual-lifecycle/ledger.json"
        ledger.write_text('{"historical":true}\n', encoding="utf-8")

        result = lifecycle_profile.migrate(
            lifecycle_profile.DUAL_MODE, repo=self.repo, allow_existing_artifacts=True,
        )
        self.assertEqual(result["resolution"], "configured")
        self.assertEqual(result["selection"], "explicit-migration-v1")
        self.assertEqual(ledger.read_text(encoding="utf-8"), '{"historical":true}\n')

    def test_preview_and_mixed_artifacts_do_not_imply_a_runtime(self) -> None:
        (self.repo / ".sdlc/preview/run-1").mkdir(parents=True)
        (self.repo / ".sdlc/plan.md").write_text("legacy\n", encoding="utf-8")
        result = lifecycle_profile.status(self.repo)
        self.assertEqual(result["resolution"], "migration-required")
        self.assertEqual(result["mode"], None)
        self.assertEqual(result["artifacts"], ["legacy-plan", "preview"])

    def test_profile_or_unknown_sdlc_content_prevents_new_project_default(self) -> None:
        (self.repo / ".sdlc").mkdir()
        (self.repo / ".sdlc/PROFILE.md").write_text("known project\n", encoding="utf-8")
        self.assertEqual(lifecycle_profile.status(self.repo)["artifacts"], ["legacy-profile"])

        (self.repo / ".sdlc/PROFILE.md").unlink()
        (self.repo / ".sdlc/foreign-tool-state.json").write_text("{}\n", encoding="utf-8")
        result = lifecycle_profile.status(self.repo)
        self.assertEqual(result["resolution"], "migration-required")
        self.assertEqual(result["artifacts"], ["unclassified-sdlc-artifact"])

    def test_profile_write_rechecks_artifacts_before_committing_selection(self) -> None:
        (self.repo / ".sdlc").mkdir()
        (self.repo / ".sdlc/STATE.md").write_text("appeared during selection\n", encoding="utf-8")
        with self.assertRaisesRegex(lifecycle_profile.LifecycleProfileError, "artifacts-changed-during-selection"):
            lifecycle_profile._write_profile(  # type: ignore[attr-defined]
                lifecycle_profile._repo_root(self.repo),  # type: ignore[attr-defined]
                {
                    "profile_format": lifecycle_profile.PROFILE_FORMAT,
                    "selection": "new-project-default-v1",
                    "mode": lifecycle_profile.DUAL_MODE,
                },
                expected_artifacts=[],
            )
        self.assertFalse((self.repo / ".sdlc/lifecycle.json").exists())

    def test_invalid_or_symlinked_profile_fails_closed(self) -> None:
        (self.repo / ".sdlc").mkdir()
        profile = self.repo / ".sdlc/lifecycle.json"
        profile.write_text('{"mode":"dual-lifecycle-v1"}\n', encoding="utf-8")
        with self.assertRaisesRegex(lifecycle_profile.LifecycleProfileError, "invalid-profile-fields"):
            lifecycle_profile.status(self.repo)

        profile.unlink()
        target = self.repo / "elsewhere.json"
        target.write_text("{}\n", encoding="utf-8")
        profile.symlink_to(target)
        with self.assertRaisesRegex(lifecycle_profile.LifecycleProfileError, "profile-cannot-be-symlink"):
            lifecycle_profile.status(self.repo)

    def test_cli_status_and_migration_have_stable_machine_output(self) -> None:
        command = [sys.executable, str(HERE / "lifecycle_profile.py"), "--repo", str(self.repo)]
        initial = subprocess.run([*command, "status"], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(initial.stdout)["resolution"], "new-project-default")
        migrated = subprocess.run(
            [*command, "migrate", "--mode", lifecycle_profile.LEGACY_MODE],
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(migrated.stdout)["mode"], lifecycle_profile.LEGACY_MODE)
        rejected = subprocess.run([*command, "init"], capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("cannot-initialize:configured", rejected.stderr)

    def test_all_public_write_skills_declare_the_common_profile_precondition(self) -> None:
        skills = [
            "sdlc",
            "sdlc-product-design",
            "sdlc-software-delivery",
            "sdlc-onboard",
            "sdlc-backlog",
            "sdlc-spec",
            "sdlc-plan",
            "sdlc-build",
            "sdlc-validate",
            "sdlc-review",
            "sdlc-ship",
        ]
        reference = ROOT / "skills/sdlc/references/lifecycle-profile.md"
        self.assertTrue(reference.is_file())
        self.assertIn("migration-required", reference.read_text(encoding="utf-8"))
        for skill in skills:
            with self.subTest(skill=skill):
                body = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("lifecycle-profile.md", body)
                self.assertIn("migration-required", body)


if __name__ == "__main__":
    unittest.main()
