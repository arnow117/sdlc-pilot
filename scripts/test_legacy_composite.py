#!/usr/bin/env python3
"""Tests for the isolated Phase 1 legacy-composite preview renderer."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import legacy_composite  # noqa: E402
import policy_compiler  # noqa: E402


class LegacyCompositeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = policy_compiler.compile_policy(
            REPOSITORY_ROOT / "skills" / "sdlc" / "references" / "policies",
            REPOSITORY_ROOT / "skills",
            "1.0.0",
        )
        cls.policy_ref = str(cls.manifest["policy_manifest_id"])
        bridge = next(
            phase for phase in cls.manifest["phases"]
            if phase["id"] == legacy_composite.PHASE_ID
        )
        cls.phase_ref = str(bridge["phase_contract_ref"])
        cls.spec_bytes = b"# Existing Legacy Spec\n\n- behavior remains legacy\n"
        cls.observation = {
            "kind": "legacy_approval_observation",
            "scope": "preview",
            "legacy_spec_sha256": hashlib.sha256(cls.spec_bytes).hexdigest(),
        }

    def render(self, **overrides: object) -> str:
        arguments: dict[str, object] = {
            "legacy_spec_bytes": self.spec_bytes,
            "legacy_approval_observation": self.observation,
            "policy_manifest": self.manifest,
            "policy_manifest_ref": self.policy_ref,
            "phase_contract_ref": self.phase_ref,
            "lifecycle_run_id": "legacy.composite.001",
        }
        arguments.update(overrides)
        return legacy_composite.render_legacy_composite_preview(**arguments)  # type: ignore[arg-type]

    def test_render_is_deterministic_preview_only_legacy_plan(self) -> None:
        rendered = self.render()
        self.assertEqual(rendered, self.render())
        self.assertIn("artifact_kind: LegacyPlan\n", rendered)
        self.assertIn("scope: preview\n", rendered)
        self.assertIn("plan_format: shadow-delivery-plan-v1\n", rendered)
        self.assertIn("adapter: legacy-composite-v1\n", rendered)
        self.assertIn(f"renderer_version: {legacy_composite.RENDERER_VERSION}\n", rendered)
        self.assertIn(f"policy_manifest_ref: {self.policy_ref}\n", rendered)
        self.assertIn(f"phase_contract_ref: {self.phase_ref}\n", rendered)
        self.assertIn(f"legacy_spec_sha256: {self.observation['legacy_spec_sha256']}\n", rendered)
        observation_sha = legacy_composite.sha256_bytes(legacy_composite.canonical_bytes(self.observation))
        self.assertIn(f"legacy_approval_observation_sha256: {observation_sha}\n", rendered)
        self.assertNotIn("artifact_kind: EngineeringSpec", rendered)
        self.assertNotIn("record_type: Approval", rendered)
        self.assertNotIn("record_type: Control", rendered)

    def test_observation_is_exact_preview_observation_bound_to_spec_bytes(self) -> None:
        cases = [
            ({**self.observation, "scope": "canonical"}, "invalid-legacy-approval-observation-scope"),
            ({**self.observation, "kind": "approval"}, "invalid-legacy-approval-observation-kind"),
            ({**self.observation, "legacy_spec_sha256": "0" * 64}, "spec-sha256-mismatch"),
            ({**self.observation, "extra": True}, "invalid-legacy-approval-observation-keys"),
        ]
        for observation, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(legacy_composite.LegacyCompositeError, message):
                    self.render(legacy_approval_observation=observation)

    def test_renderer_requires_the_exact_compatibility_phase_and_policy_reference(self) -> None:
        delivery_phase = next(
            phase for phase in self.manifest["phases"]
            if phase["id"] == "phase.delivery.plan"
        )
        with self.assertRaisesRegex(legacy_composite.LegacyCompositeError, "not-legacy-composite-phase"):
            self.render(phase_contract_ref=delivery_phase["phase_contract_ref"])
        with self.assertRaisesRegex(legacy_composite.LegacyCompositeError, "policy-manifest-ref-mismatch"):
            self.render(policy_manifest_ref="0" * 64)
        broken = deepcopy(self.manifest)
        bridge = next(phase for phase in broken["phases"] if phase["id"] == legacy_composite.PHASE_ID)
        bridge["compatibility_adapter"] = "unexpected-adapter"
        with self.assertRaisesRegex(legacy_composite.LegacyCompositeError, "invalid-legacy-composite-phase"):
            self.render(policy_manifest=broken)

    def test_writer_has_one_preview_target_and_never_overwrites_legacy_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repository = Path(tempdir)
            legacy_plan = repository / ".sdlc" / "plan.md"
            legacy_plan.parent.mkdir(parents=True)
            legacy_plan.write_text("legacy plan must remain\n", encoding="utf-8")
            destination = legacy_composite.write_legacy_composite_preview(
                repository,
                legacy_spec_bytes=self.spec_bytes,
                legacy_approval_observation=self.observation,
                policy_manifest=self.manifest,
                policy_manifest_ref=self.policy_ref,
                phase_contract_ref=self.phase_ref,
                lifecycle_run_id="legacy.composite.001",
            )
            self.assertEqual(
                destination.resolve(),
                (repository / ".sdlc" / "preview" / "legacy.composite.001" / "plan.shadow.md").resolve(),
            )
            self.assertEqual(destination.read_text(encoding="utf-8"), self.render())
            self.assertEqual(legacy_plan.read_text(encoding="utf-8"), "legacy plan must remain\n")
            with self.assertRaisesRegex(legacy_composite.LegacyCompositeError, "preview-artifact-already-exists"):
                legacy_composite.write_legacy_composite_preview(
                    repository,
                    legacy_spec_bytes=self.spec_bytes,
                    legacy_approval_observation=self.observation,
                    policy_manifest=self.manifest,
                    policy_manifest_ref=self.policy_ref,
                    phase_contract_ref=self.phase_ref,
                    lifecycle_run_id="legacy.composite.001",
                )
            self.assertEqual(legacy_plan.read_text(encoding="utf-8"), "legacy plan must remain\n")

    def test_run_id_cannot_escape_preview_namespace(self) -> None:
        for run_id in ("", "../legacy", "legacy/composite", ".."):
            with self.subTest(run_id=run_id):
                with self.assertRaisesRegex(legacy_composite.LegacyCompositeError, "invalid-lifecycle-run-id"):
                    self.render(lifecycle_run_id=run_id)


if __name__ == "__main__":
    unittest.main()
