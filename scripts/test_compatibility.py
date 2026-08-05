#!/usr/bin/env python3
"""Tests for the pure Phase 1 legacy parity comparator."""
from __future__ import annotations

from copy import deepcopy
import unittest

import compatibility


SHA_A = "a" * 64
SHA_B = "b" * 64


def snapshot() -> dict[str, object]:
    return {
        "entrypoint": "sdlc-plan",
        "route": {"skill": "sdlc-plan", "mode": "legacy"},
        "exit_status": 0,
        "artifacts": {".sdlc/plan.md": {"sha256": SHA_A, "schema": "legacy-plan-v1"}},
        "handoff": {"next": "sdlc-build", "task": "TASK-001"},
        "state": {"stage": "plan", "status": "in_progress", "next_action": "build"},
        "control_tree": {"features/FEAT-001.md": SHA_A},
        "legacy_approval_observation": {
            "kind": "legacy_approval_observation", "scope": "preview", "legacy_spec_sha256": SHA_B,
        },
    }


class CompatibilityTest(unittest.TestCase):
    def test_identical_snapshot_has_no_difference(self) -> None:
        report = compatibility.compare_legacy(snapshot(), snapshot())
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["unexpected_differences"], [])

    def test_control_change_is_unexpected_without_exact_exception(self) -> None:
        baseline = snapshot()
        candidate = deepcopy(baseline)
        candidate["control_tree"] = {"features/FEAT-001.md": SHA_B}
        report = compatibility.compare_legacy(baseline, candidate)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["unexpected_differences"][0]["path"], "control_tree.features/FEAT-001.md")

    def test_exact_exception_is_accepted_but_wildcard_is_not_supported(self) -> None:
        baseline = snapshot()
        candidate = deepcopy(baseline)
        candidate["state"]["next_action"] = "review"  # type: ignore[index]
        exception = {
            "id": "EXC-001",
            "entrypoint": "sdlc-plan",
            "path": "state.next_action",
            "baseline": "build",
            "candidate": "review",
            "reason": "named migration behavior",
            "owner": "release-engineer",
            "approval_ref": "ADR-0002",
        }
        report = compatibility.compare_legacy(baseline, candidate, [exception])
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["accepted_differences"][0]["exception_id"], "EXC-001")
        invalid = dict(exception)
        invalid["path"] = "*"
        self.assertEqual(compatibility.compare_legacy(baseline, candidate, [invalid])["verdict"], "FAIL")

    def test_required_fields_and_preview_observation_are_fail_closed(self) -> None:
        missing = snapshot()
        del missing["handoff"]
        with self.assertRaises(compatibility.CompatibilityError):
            compatibility.compare_legacy(missing, snapshot())
        unsafe = snapshot()
        unsafe["legacy_approval_observation"] = {"kind": "approval", "scope": "canonical", "legacy_spec_sha256": SHA_B}
        with self.assertRaises(compatibility.CompatibilityError):
            compatibility.compare_legacy(snapshot(), unsafe)

    def test_differences_are_stably_sorted(self) -> None:
        baseline = snapshot()
        candidate = deepcopy(baseline)
        candidate["exit_status"] = 1
        candidate["state"]["status"] = "blocked"  # type: ignore[index]
        paths = [item["path"] for item in compatibility.compare_legacy(baseline, candidate)["differences"]]
        self.assertEqual(paths, sorted(paths))


if __name__ == "__main__":
    unittest.main()
