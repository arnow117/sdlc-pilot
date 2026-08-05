#!/usr/bin/env python3
"""Contract tests for the Phase 1 preview-only context resolver."""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import context_resolver  # noqa: E402


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Fixture:
    def __init__(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo_root = self.root / "repo"
        self.skill_root = self.root / "skills"
        (self.repo_root / ".sdlc").mkdir(parents=True)
        (self.skill_root / "playbooks").mkdir(parents=True)
        self.state = self.repo_root / ".sdlc" / "STATE.md"
        self.state.write_text("stage: legacy-plan\n", encoding="utf-8")
        self.core = self.skill_root / "playbooks" / "core.md"
        self.behavior = self.skill_root / "playbooks" / "behavior.md"
        self.core.write_text("# Core\n\n<!-- obligation:core -->\n", encoding="utf-8")
        self.behavior.write_text("# Behavior\n\n<!-- obligation:behavior -->\n", encoding="utf-8")
        self.manifest = self._manifest()

    def close(self) -> None:
        self.tempdir.cleanup()

    def request(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "scope": "preview",
            "command": "sdlc-product-design-preview",
            "lifecycle_run_id": "run.product.001",
            "phase_id": "phase.product.behavior",
            "lifecycle": "product-design",
            "operation": "behavior-design",
            "work_type": "product-change",
            "authority_mode": "legacy",
            "identity": {"requirement_id": "REQ-001"},
            "contracts": {"product_contract_ref": "PC:placeholder"},
            "profile": {"sha256": "1" * 64},
            "diff": {
                "scope": "legacy",
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "dirty": False,
                "staged": False,
                "untracked": False,
            },
            "intent_flags": {"requires_behavior": True},
            "runtime_event": {"type": "preview-request"},
            "engine_version": "1.0.0",
            "modes": ["ddd", "bdd"],
            "selector_attestation_refs": [],
            "byte_budget": 4096,
        }
        value.update(overrides)
        return value

    def resolve(self, **overrides: object) -> dict[str, object]:
        return context_resolver.resolve_context(
            self.request(**overrides), self.manifest, self.repo_root, self.skill_root)

    def _module(self, module_id: str, path: Path, rules: list[str], depends_on: list[str]) -> dict[str, object]:
        return {
            "id": module_id,
            "lifecycles": ["product-design"],
            "operations": ["behavior-design"],
            "selector_rule_ids": rules,
            "depends_on": depends_on,
            "playbook": {
                "path": path.relative_to(self.skill_root).as_posix(),
                "anchor": "# Core" if path == self.core else "# Behavior",
                "sha256": sha256(path.read_bytes()),
            },
            "max_bytes": 4096,
            "fallback": {"kind": "needs_classification"},
        }

    @staticmethod
    def _rule(rule_id: str, target_id: str, selector: dict[str, object], priority: int) -> dict[str, object]:
        return {
            "id": rule_id,
            "kind": "selector",
            "target": {"kind": "module", "id": target_id},
            "resolution_group": rule_id,
            "priority": priority,
            "when": selector,
        }

    def _manifest(self) -> dict[str, object]:
        manifest_id = "f" * 64
        rules = [
            self._rule("rule.module.core", "mod.core", {"op": "always"}, 10),
            self._rule(
                "rule.module.behavior", "mod.behavior",
                {"op": "eq", "field": "intent_flags.requires_behavior", "value": True}, 20),
            self._rule("rule.phase.behavior", "phase.product.behavior", {"op": "always"}, 30),
            self._rule(
                "rule.obligation.behavior", "obl.behavior",
                {"op": "eq", "field": "intent_flags.requires_behavior", "value": True}, 40),
        ]
        return {
            "schema_version": "sdlc-policy-manifest-v1",
            "policy_format": "sdlc-policy-v1",
            "policy_manifest_id": manifest_id,
            "engine_api": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
            "migration_version": "phase1-preview-v1",
            "activation": {
                "scope": "preview",
                "explicit_invocation_only": True,
                "control_mutations": False,
                "output_scope": "preview",
                "unknown_selector": "needs_classification",
                "legacy_projection": "legacy-route-projection-v1",
                "legacy_bridge": "legacy-composite-v1",
            },
            "rules": rules,
            "modules": [
                self._module("mod.core", self.core, ["rule.module.core"], []),
                self._module("mod.behavior", self.behavior, ["rule.module.behavior"], ["mod.core"]),
            ],
            "roles": [
                {
                    "id": "role.product-owner",
                    "responsibility_types": ["responsible"],
                    "eligibility_rule_ids": ["rule.module.core"],
                    "independence_constraints": [],
                },
            ],
            "phases": [
                {
                    "id": "phase.product.behavior",
                    "lifecycle": "product-design",
                    "stage": "behavior-design",
                    "phase_contract_ref": f"{manifest_id}#phase.product.behavior",
                    "entry_predicate_rule_ids": ["rule.phase.behavior"],
                    "method_module_ids": ["mod.behavior"],
                    "output_contracts": [
                        {"id": "out.product.behavior", "kind": "ProductContractDraft", "scope": "preview"},
                    ],
                    "transition_intent": {"kind": "complete", "target_phase_id": None, "scope": "preview"},
                    "obligations": [
                        {
                            "id": "obl.behavior",
                            "role_id": "role.product-owner",
                            "responsibility": "responsible",
                            "participation": "conditional",
                            "required_when_rule_id": "rule.obligation.behavior",
                            "min_actors": 1,
                            "max_actors": 1,
                            "independence_constraint_ids": [],
                            "playbook_ref": {"module_id": "mod.behavior", "anchor": "<!-- obligation:behavior -->"},
                            "completion_assertion_ids": ["assert.behavior"],
                            "skip_policy": {
                                "mode": "selector_false_or_typed_override",
                                "allowed_when_rule_id": "rule.obligation.behavior",
                                "override_policy": "typed-override-v1",
                            },
                        }
                    ],
                }
            ],
            "dependency_closure": [
                {
                    "path": self.core.relative_to(self.skill_root).as_posix(),
                    "sha256": sha256(self.core.read_bytes()),
                    "utf8_bytes": len(self.core.read_bytes()),
                },
                {
                    "path": self.behavior.relative_to(self.skill_root).as_posix(),
                    "sha256": sha256(self.behavior.read_bytes()),
                    "utf8_bytes": len(self.behavior.read_bytes()),
                },
            ],
        }


class ContextResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    def test_same_explicit_input_has_identical_preview_manifest(self) -> None:
        first = self.fixture.resolve()
        second = self.fixture.resolve()

        self.assertEqual(first, second)
        self.assertEqual(first["scope"], "preview")
        self.assertEqual(first["phase_contract_ref"], "f" * 64 + "#phase.product.behavior")
        self.assertEqual(first["selected_modules"], [
            {
                "id": "mod.behavior",
                "path": "playbooks/behavior.md",
                "sha256": sha256(self.fixture.behavior.read_bytes()),
                "bytes": len(self.fixture.behavior.read_bytes()),
                "reason": {
                    "dependency_of": [],
                    "matched_rule_ids": ["rule.module.behavior"],
                    "required_by_obligation_ids": ["obl.behavior"],
                    "unknown_rule_ids": [],
                },
            },
            {
                "id": "mod.core",
                "path": "playbooks/core.md",
                "sha256": sha256(self.fixture.core.read_bytes()),
                "bytes": len(self.fixture.core.read_bytes()),
                "reason": {
                    "dependency_of": ["mod.behavior"],
                    "matched_rule_ids": ["rule.module.core"],
                    "required_by_obligation_ids": [],
                    "unknown_rule_ids": [],
                },
            },
        ])
        self.assertEqual(first["roles"], ["role.product-owner"])
        self.assertEqual(first["modes"], ["bdd", "ddd"])
        self.assertEqual(first["warnings"], [])
        self.assertEqual(len(first["context_manifest_id"]), 64)
        self.assertLessEqual(first["total_bytes"], 4096)

    def test_unknown_selector_is_not_silently_skipped(self) -> None:
        result = self.fixture.resolve(intent_flags={})

        self.assertTrue(result["needs_classification"])
        self.assertEqual(result["warnings"], ["needs_classification"])
        self.assertIn("obl.behavior", result["selected_obligation_ids"])
        self.assertEqual(result["skipped_obligations"], [])
        self.assertEqual(
            [(item["target_kind"], item["target_id"], item["rule_id"]) for item in result["classification_requests"]],
            [
                ("module", "mod.behavior", "rule.module.behavior"),
                ("obligation", "obl.behavior", "rule.obligation.behavior"),
            ],
        )

    def test_required_obligation_cannot_be_silently_skipped_when_its_selector_is_false(self) -> None:
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest["phases"][0]["obligations"][0]["participation"] = "required"
        manifest["phases"][0]["obligations"][0]["skip_policy"] = {
            "mode": "forbidden", "allowed_when_rule_id": None, "override_policy": "none",
        }
        with self.assertRaisesRegex(context_resolver.ContextError, "required-obligation-selector-false:obl.behavior"):
            context_resolver.resolve_context(
                self.fixture.request(intent_flags={"requires_behavior": False}),
                manifest,
                self.fixture.repo_root,
                self.fixture.skill_root,
            )

    def test_symlink_escape_is_rejected_before_module_body_read(self) -> None:
        outside = self.fixture.root / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        escape = self.fixture.skill_root / "playbooks" / "escape.md"
        escape.symlink_to(outside)
        manifest = copy.deepcopy(self.fixture.manifest)
        module = next(item for item in manifest["modules"] if item["id"] == "mod.behavior")
        module["playbook"] = {"path": "playbooks/escape.md", "anchor": "# Behavior", "sha256": sha256(outside.read_bytes())}
        closure = next(item for item in manifest["dependency_closure"] if item["path"] == "playbooks/behavior.md")
        closure["path"] = "playbooks/escape.md"
        closure["sha256"] = sha256(outside.read_bytes())
        closure["utf8_bytes"] = len(outside.read_bytes())

        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("body-read")):
            with self.assertRaisesRegex(context_resolver.ContextError, "module-path-escapes-skill-root"):
                context_resolver.resolve_context(self.fixture.request(), manifest, self.fixture.repo_root, self.fixture.skill_root)

    def test_byte_cap_is_rejected_before_module_body_read(self) -> None:
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("body-read")):
            with self.assertRaisesRegex(context_resolver.ContextError, "context-byte-budget-exceeded"):
                self.fixture.resolve(byte_budget=1)

    def test_default_budget_is_part_of_the_canonical_context_input(self) -> None:
        request = self.fixture.request()
        request.pop("byte_budget")
        result = context_resolver.resolve_context(
            request, self.fixture.manifest, self.fixture.repo_root, self.fixture.skill_root)

        self.assertEqual(result["byte_budget"], context_resolver.DEFAULT_BYTE_BUDGET)
        self.assertNotEqual(result["context_input_sha256"], self.fixture.resolve()["context_input_sha256"])

    def test_preview_boundary_never_mutates_legacy_state(self) -> None:
        before = self.fixture.state.read_bytes()
        result = self.fixture.resolve(authority_mode="shared-control")
        self.assertEqual(self.fixture.state.read_bytes(), before)
        self.assertEqual(result["scope"], "preview")
        self.assertFalse(result["activation"]["control_mutations"])

        canonical_manifest = copy.deepcopy(self.fixture.manifest)
        canonical_manifest["activation"]["control_mutations"] = True
        with self.assertRaisesRegex(context_resolver.ContextError, "preview-policy-required"):
            context_resolver.resolve_context(self.fixture.request(), canonical_manifest, self.fixture.repo_root, self.fixture.skill_root)

        canonical_phase_manifest = copy.deepcopy(self.fixture.manifest)
        canonical_phase_manifest["phases"][0]["output_contracts"][0]["scope"] = "canonical"
        with self.assertRaisesRegex(context_resolver.ContextError, "non-preview-phase-output"):
            context_resolver.resolve_context(
                self.fixture.request(), canonical_phase_manifest, self.fixture.repo_root, self.fixture.skill_root)

    def test_hash_mismatch_is_rejected_after_safe_preflight(self) -> None:
        manifest = copy.deepcopy(self.fixture.manifest)
        module = next(item for item in manifest["modules"] if item["id"] == "mod.behavior")
        module["playbook"]["sha256"] = "0" * 64
        closure = next(item for item in manifest["dependency_closure"] if item["path"] == "playbooks/behavior.md")
        closure["sha256"] = "0" * 64

        with self.assertRaisesRegex(context_resolver.ContextError, "module-hash-mismatch:mod.behavior"):
            context_resolver.resolve_context(self.fixture.request(), manifest, self.fixture.repo_root, self.fixture.skill_root)


if __name__ == "__main__":
    unittest.main()
