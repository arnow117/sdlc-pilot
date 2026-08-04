#!/usr/bin/env python3
"""Focused request intake and decomposition contract tests."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import control  # noqa: E402
import control_store  # noqa: E402


def requirement(leaf_id: str, *, request_id: str, body: object) -> dict:
    return {
        "id": leaf_id,
        "title": f"Requirement {leaf_id}",
        "domain_path": "order/checkout",
        "cross_link": [],
        "old_system_ref": "planner/request.md",
        "new_domain_path": "order/checkout",
        "status": "captured",
        "priority": "P0",
        "depends_on": [],
        "risk_level": "high",
        "source_request": request_id,
        "updated": "2026-08-04",
        "body": body,
    }


class RequirementBodyTest(unittest.TestCase):
    def test_intake_persists_multiline_body_outside_frontmatter(self):
        body = "## Requirement\nKeep the acceptance evidence.\n\n- observable result"
        with tempfile.TemporaryDirectory() as root:
            control.intake(
                root,
                request={"request_id": "req-1", "title": "Raw", "body": "raw input"},
                leaves=[requirement("order.checkout.a", request_id="req-1", body=body)],
                at="2026-08-04T10:00:00+08:00",
            )
            path = Path(root, "requirements", "order", "checkout", "order.checkout.a.md")
            text = path.read_text(encoding="utf-8")
            record = control_store.read_record(path)
            self.assertNotIn("\nbody:", text)
            self.assertEqual(record["_body"], body)

    def test_decompose_request_persists_multiline_body(self):
        body = "## Acceptance\nThe child is independently verifiable."
        with tempfile.TemporaryDirectory() as root:
            control.capture_request(
                root,
                request={"request_id": "req-1", "title": "Raw", "body": "raw input"},
                at="2026-08-04T10:00:00+08:00",
            )
            result = control.decompose_request(
                root,
                request_id="req-1",
                leaves=[requirement("order.checkout.a", request_id="req-1", body=body)],
                at="2026-08-04T10:01:00+08:00",
            )
            self.assertEqual(result["leaf_ids"], ["order.checkout.a"])
            snapshot = control.load_control_snapshot(root)
            self.assertEqual(snapshot["requirements_by_id"]["order.checkout.a"]["_body"], body)

    def test_intake_rejects_non_string_body_before_writing_request(self):
        for value in ({"heading": "Acceptance"}, ["acceptance"], None, 1):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(control_store.SchemaError, "body must be a string"):
                    control.intake(
                        root,
                        request={"request_id": "req-1", "title": "Raw", "body": "raw input"},
                        leaves=[requirement("order.checkout.a", request_id="req-1", body=value)],
                        at="2026-08-04T10:00:00+08:00",
                    )
                self.assertFalse(Path(root, "requests", "req-1.md").exists())

    def test_decompose_request_rejects_non_string_body_without_writing_leaf(self):
        for value in ({"heading": "Acceptance"}, ["acceptance"], None, 1):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as root:
                control.capture_request(
                    root,
                    request={"request_id": "req-1", "title": "Raw", "body": "raw input"},
                    at="2026-08-04T10:00:00+08:00",
                )
                with self.assertRaisesRegex(control_store.SchemaError, "body must be a string"):
                    control.decompose_request(
                        root,
                        request_id="req-1",
                        leaves=[requirement("order.checkout.a", request_id="req-1", body=value)],
                        at="2026-08-04T10:01:00+08:00",
                    )
                path = Path(
                    root, "requirements", "order", "checkout", "order.checkout.a.md")
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
