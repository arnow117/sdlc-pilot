#!/usr/bin/env python3
"""Focused tests for the canonical dual-lifecycle authority configuration."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import dual_authority


def _valid_config() -> dict[str, object]:
    return {
        "authority_format": "dual-lifecycle-authority-v1",
        "authority_mode": "local-serial",
        "principal": {
            "authority_mode": "local-serial",
            "principal_ref": "principal:architecture-owner",
            "roles": ["architect", "quality-reviewer"],
            "authn_method": "configured-file",
            "authn_assurance": "configured-audit",
        },
        "policies": [
            {
                "policy_id": "product-contract-approval-v1",
                "allowed_roles": ["product-owner"],
                "min_authn_assurance": "configured-audit",
                "subject_type": "product_contract",
                "scope": "product",
            },
            {
                "policy_id": "engineering-spec-approval-v1",
                "allowed_roles": ["architect"],
                "min_authn_assurance": "configured-audit",
                "subject_type": "engineering_spec",
                "scope": "feature",
            },
        ],
        "change_request_policy": {
            "allowed_roles": ["architect"],
            "min_authn_assurance": "configured-audit",
        },
    }


def _parse(value: dict[str, object]) -> dual_authority.AuthorityConfig:
    return dual_authority.parse_config_bytes(json.dumps(value).encode("utf-8"))


def _engineering_subject() -> dict[str, str]:
    fingerprint = "a" * 64
    return {
        "subject_type": "engineering_spec",
        "scope": "feature",
        "subject_id": fingerprint,
        "subject_ref": fingerprint,
        "subject_revision": fingerprint,
        "subject_sha256": fingerprint,
    }


class DualAuthorityConfigTests(unittest.TestCase):
    def test_parse_load_resolve_and_select_a_configured_policy(self) -> None:
        config = _parse(_valid_config())

        self.assertEqual(config.authority_mode, "local-serial")
        self.assertEqual(
            dual_authority.resolve_configured_principal(config).principal_ref,
            "principal:architecture-owner",
        )
        policy = dual_authority.select_policy(
            config, subject_type="engineering_spec", scope="feature"
        )
        self.assertEqual(policy.policy_id, "engineering-spec-approval-v1")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authority.json"
            path.write_bytes(json.dumps(_valid_config()).encode("utf-8"))
            loaded = dual_authority.load_config(path)
        self.assertEqual(loaded, config)

    def test_builds_an_approval_from_only_the_configured_principal_and_policy(self) -> None:
        record = dual_authority.build_configured_approval(
            _parse(_valid_config()),
            subject=_engineering_subject(),
            decision="approve",
            previous_approval_ref=None,
            decision_intent_ref="intent:engineering-approval",
            decided_at="2026-08-05T12:00:00Z",
        )

        self.assertEqual(record["principal_ref"], "principal:architecture-owner")
        self.assertEqual(record["principal_role"], "architect")
        self.assertEqual(record["authorization_policy_ref"], "engineering-spec-approval-v1")
        self.assertEqual(record["subject_type"], "engineering_spec")

    def test_change_request_authorization_covers_accept_reject_and_cancel(self) -> None:
        config = _parse(_valid_config())

        for action in ("accept", "reject", "cancel"):
            self.assertEqual(
                dual_authority.authorize_change_request(config, action=action), "architect"
            )

        with self.assertRaises(dual_authority.AuthorityConfigError):
            dual_authority.authorize_change_request(config, action="approve")

        unauthorized = _valid_config()
        unauthorized["change_request_policy"] = {
            "allowed_roles": ["product-owner"],
            "min_authn_assurance": "configured-audit",
        }
        with self.assertRaises(dual_authority.AuthorityConfigError):
            dual_authority.authorize_change_request(_parse(unauthorized), action="accept")

    def test_rejects_caller_identity_and_policy_injection(self) -> None:
        config = _parse(_valid_config())
        common = {
            "subject": _engineering_subject(),
            "decision": "approve",
            "previous_approval_ref": None,
            "decision_intent_ref": "intent:engineering-approval",
            "decided_at": "2026-08-05T12:00:00Z",
        }

        for forged in (
            {"principal_ref": "principal:forged"},
            {"roles": ["product-owner"]},
            {"principal_role": "product-owner"},
            {"authorization_policy": {"policy_id": "forged"}},
            {"policy_id": "forged"},
            {"change_request_policy": {"allowed_roles": ["product-owner"]}},
        ):
            with self.subTest(forged=forged), self.assertRaises(
                dual_authority.AuthorityConfigError
            ):
                dual_authority.build_configured_approval(
                    config, caller_payload=forged, **common
                )

        with self.assertRaises(dual_authority.AuthorityConfigError):
            dual_authority.select_policy(
                config,
                subject_type="engineering_spec",
                scope="feature",
                caller_payload={"policy_id": "forged"},
            )

    def test_rejects_unknown_duplicate_and_empty_config_fields(self) -> None:
        unknown = _valid_config()
        unknown["unexpected"] = True
        with self.assertRaises(dual_authority.AuthorityConfigError):
            _parse(unknown)

        empty = _valid_config()
        empty["principal"] = copy.deepcopy(empty["principal"])
        empty["principal"]["principal_ref"] = ""
        with self.assertRaises(dual_authority.AuthorityConfigError):
            _parse(empty)

        duplicate_policy_id = _valid_config()
        duplicate_policy_id["policies"] = copy.deepcopy(duplicate_policy_id["policies"])
        duplicate_policy_id["policies"][1]["policy_id"] = duplicate_policy_id["policies"][0][
            "policy_id"
        ]
        with self.assertRaises(dual_authority.AuthorityConfigError):
            _parse(duplicate_policy_id)

        duplicate_target = _valid_config()
        duplicate_target["policies"] = copy.deepcopy(duplicate_target["policies"])
        duplicate_target["policies"][1]["subject_type"] = duplicate_target["policies"][0][
            "subject_type"
        ]
        duplicate_target["policies"][1]["scope"] = duplicate_target["policies"][0]["scope"]
        with self.assertRaises(dual_authority.AuthorityConfigError):
            _parse(duplicate_target)

        duplicate_key_payload = b'''{
          "authority_format":"dual-lifecycle-authority-v1",
          "authority_format":"dual-lifecycle-authority-v1"
        }'''
        with self.assertRaises(dual_authority.AuthorityConfigError):
            dual_authority.parse_config_bytes(duplicate_key_payload)

    def test_rejects_missing_or_ambiguous_policy_selection(self) -> None:
        config = _parse(_valid_config())
        with self.assertRaises(dual_authority.AuthorityConfigError):
            dual_authority.select_policy(
                config, subject_type="engineering_spec", scope="product"
            )


if __name__ == "__main__":
    unittest.main()
