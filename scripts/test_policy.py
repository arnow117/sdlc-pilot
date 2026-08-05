#!/usr/bin/env python3
"""Contract tests for the deterministic SDLC Policy compiler."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPOSITORY_ROOT = HERE.parent

import policy_compiler  # noqa: E402


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


class Fixture:
    def __init__(self, *, reordered: bool = False) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.policy_root = self.root / "policy"
        self.skill_root = self.root / "skills"
        self.policy_root.mkdir()
        (self.skill_root / "playbooks").mkdir(parents=True)
        self.product = self.skill_root / "playbooks" / "product.md"
        self.delivery = self.skill_root / "playbooks" / "delivery.md"
        self.product.write_text(
            "# Product\n\n<!-- obligation:obl.product.discover -->\n\n"
            "<!-- obligation:obl.product.behavior -->\n",
            encoding="utf-8",
        )
        self.delivery.write_text(
            "# Delivery\n\n<!-- obligation:obl.delivery.spec -->\n",
            encoding="utf-8",
        )
        self.write_documents(reordered=reordered)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def playbook(self, path: Path) -> dict[str, str]:
        return {
            "path": path.relative_to(self.skill_root).as_posix(),
            "anchor": "# " + ("Product" if path == self.product else "Delivery"),
            "sha256": sha256(path.read_bytes()),
        }

    def module(self, module_id: str, lifecycle: str, operations: list[str], rule: str,
               priority: int, path: Path, depends_on: list[str] | None = None) -> dict[str, object]:
        return {
            "id": module_id,
            "lifecycles": [lifecycle],
            "operations": operations,
            "selector_rule_ids": [rule],
            "depends_on": depends_on or [],
            "playbook": self.playbook(path),
            "max_bytes": 4096,
            "fallback": {"kind": "needs_classification"},
        }

    @staticmethod
    def rule(rule_id: str, target_id: str, group: str, priority: int) -> dict[str, object]:
        return {
            "id": rule_id,
            "kind": "selector",
            "target": {"kind": "module", "id": target_id},
            "resolution_group": group,
            "priority": priority,
            "when": {"op": "always"},
        }

    @staticmethod
    def obligation(obligation_id: str, role_id: str, module_id: str, rule_id: str,
                   anchor: str, *, required: bool) -> dict[str, object]:
        return {
            "id": obligation_id,
            "role_id": role_id,
            "responsibility": "responsible",
            "participation": "required" if required else "conditional",
            "required_when_rule_id": rule_id,
            "min_actors": 1,
            "max_actors": 1,
            "independence_constraint_ids": [],
            "playbook_ref": {"module_id": module_id, "anchor": anchor},
            "completion_assertion_ids": ["assert.semantic"],
            "skip_policy": {
                "mode": "forbidden" if required else "selector_false_or_typed_override",
                "allowed_when_rule_id": None if required else rule_id,
                "override_policy": "none" if required else "typed-override-v1",
            },
        }

    def phase(self, phase_id: str, lifecycle: str, stage: str, module_ids: list[str],
              obligation: dict[str, object], input_kind: str, output_kind: str,
              target_phase_id: str | None, *, compatibility_adapter: str | None = None) -> dict[str, object]:
        return {
            "id": phase_id,
            "lifecycle": lifecycle,
            "stage": stage,
            "entry_predicate_rule_ids": [obligation["required_when_rule_id"]],
            "input_contracts": [{"id": f"in.{phase_id}", "kind": input_kind, "state": "current"}],
            "method_module_ids": module_ids,
            "output_contracts": [{"id": f"out.{phase_id}", "kind": output_kind, "scope": "preview"}],
            "completion_assertions": [
                {"id": "assert.semantic", "kind": "semantic", "source": "typed_attestation", "evidence_type": "attestation"},
            ],
            "semantic_attestation_types": ["semantic-v1"],
            "obligations": [obligation],
            "transition_intent": {
                "kind": "advance" if target_phase_id else "complete",
                "target_phase_id": target_phase_id,
                "scope": "preview",
            },
            "rollback_intent": None,
            "compatibility_adapter": compatibility_adapter,
        }

    def write_documents(self, *, reordered: bool = False) -> None:
        modules = [
            self.module("mod.product.core", "product-design", ["discover"], "rule.product.core", 10, self.product),
            self.module("mod.product.behavior", "product-design", ["behavior-design"], "rule.product.behavior", 20, self.product, ["mod.product.core"]),
            self.module("mod.delivery.spec", "software-delivery", ["engineering-spec"], "rule.delivery.spec", 30, self.delivery),
        ]
        rules = [
            self.rule("rule.product.core", "mod.product.core", "product-core", 10),
            self.rule("rule.product.behavior", "mod.product.behavior", "product-behavior", 10),
            self.rule("rule.delivery.spec", "mod.delivery.spec", "delivery-spec", 10),
        ]
        discover = self.obligation(
            "obl.product.discover", "role.product-owner", "mod.product.core", "rule.product.core",
            "<!-- obligation:obl.product.discover -->", required=True)
        behavior = self.obligation(
            "obl.product.behavior", "role.qa", "mod.product.behavior", "rule.product.behavior",
            "<!-- obligation:obl.product.behavior -->", required=False)
        delivery = self.obligation(
            "obl.delivery.spec", "role.architect", "mod.delivery.spec", "rule.delivery.spec",
            "<!-- obligation:obl.delivery.spec -->", required=True)
        phases = [
            self.phase("phase.product.discover", "product-design", "discover", ["mod.product.core"], discover, "Request", "ProductDefinition", "phase.product.behavior"),
            self.phase("phase.product.behavior", "product-design", "behavior-design", ["mod.product.core", "mod.product.behavior"], behavior, "ProductDefinition", "ProductContractDraft", None),
            self.phase("phase.delivery.spec", "software-delivery", "engineering-spec", ["mod.delivery.spec"], delivery, "ProductContract", "EngineeringSpec", None),
        ]
        roles = [
            {"id": "role.product-owner", "responsibility_types": ["accountable", "responsible"], "eligibility_rule_ids": ["rule.product.core"], "independence_constraints": []},
            {"id": "role.qa", "responsibility_types": ["responsible", "reviewer"], "eligibility_rule_ids": ["rule.product.behavior"], "independence_constraints": []},
            {"id": "role.architect", "responsibility_types": ["responsible"], "eligibility_rule_ids": ["rule.delivery.spec"], "independence_constraints": []},
        ]
        if reordered:
            modules.reverse()
            rules.reverse()
            phases.reverse()
            roles.reverse()
            for phase in phases:
                phase["method_module_ids"] = list(reversed(phase["method_module_ids"]))
        write_json(self.policy_root / "modules.json", {
            "schema_version": "sdlc-policy-modules-v1",
            "policy": {
                "policy_format": "sdlc-policy-v1",
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
            },
            "rules": rules,
            "modules": modules,
        })
        write_json(self.policy_root / "phases.json", {"schema_version": "sdlc-policy-phases-v1", "phases": phases})
        write_json(self.policy_root / "roles.json", {"schema_version": "sdlc-policy-roles-v1", "roles": roles})

    def read(self, name: str) -> dict[str, object]:
        return json.loads((self.policy_root / name).read_text(encoding="utf-8"))

    def write(self, name: str, value: object) -> None:
        write_json(self.policy_root / name, value)


class PolicyCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    def compile(self, **kwargs: object) -> dict[str, object]:
        return policy_compiler.compile_policy(self.fixture.policy_root, self.fixture.skill_root, "1.0.0", **kwargs)

    def test_canonical_projection_ignores_json_and_set_order(self) -> None:
        first = self.compile()
        reordered = Fixture(reordered=True)
        self.addCleanup(reordered.close)
        second = policy_compiler.compile_policy(reordered.policy_root, reordered.skill_root, "1.0.0")

        self.assertEqual(first["policy_manifest_id"], second["policy_manifest_id"])
        self.assertEqual(policy_compiler.canonical_bytes(first), policy_compiler.canonical_bytes(second))
        self.assertEqual([entry["path"] for entry in first["dependency_closure"]], sorted(entry["path"] for entry in first["dependency_closure"]))
        for phase in first["phases"]:
            self.assertEqual(phase["phase_contract_ref"], f"{first['policy_manifest_id']}#{phase['id']}")

    def test_hash_boundary_catches_raw_playbook_changes_but_not_json_formatting(self) -> None:
        first = self.compile()
        modules = self.fixture.read("modules.json")
        self.fixture.write("modules.json", modules)
        self.assertEqual(first["policy_manifest_id"], self.compile()["policy_manifest_id"])

        self.fixture.product.write_text(
            "# Product changed\n\n<!-- obligation:obl.product.discover -->\n\n<!-- obligation:obl.product.behavior -->\n",
            encoding="utf-8",
        )
        modules = self.fixture.read("modules.json")
        for module in modules["modules"]:
            if module["playbook"]["path"] == "playbooks/product.md":
                module["playbook"]["sha256"] = sha256(self.fixture.product.read_bytes())
        self.fixture.write("modules.json", modules)
        self.assertNotEqual(first["policy_manifest_id"], self.compile()["policy_manifest_id"])

    def test_rejects_duplicate_json_key_unknown_selector_and_bad_priority(self) -> None:
        (self.fixture.policy_root / "roles.json").write_text(
            '{"schema_version":"sdlc-policy-roles-v1","schema_version":"sdlc-policy-roles-v1","roles":[]}\n',
            encoding="utf-8",
        )
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        modules = self.fixture.read("modules.json")
        modules["rules"][0]["when"] = {"op": "shell", "command": "true"}
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        modules = self.fixture.read("modules.json")
        modules["rules"][1]["resolution_group"] = "product-core"
        modules["rules"][1]["priority"] = 10
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

    def test_rejects_reference_cycle_escape_and_engine_or_migration_mismatch(self) -> None:
        modules = self.fixture.read("modules.json")
        modules["modules"][0]["depends_on"] = ["mod.product.behavior"]
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        outside = self.fixture.root / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        (self.fixture.skill_root / "playbooks" / "escape.md").symlink_to(outside)
        modules = self.fixture.read("modules.json")
        modules["modules"][0]["playbook"] = {
            "path": "playbooks/escape.md", "anchor": "# Product", "sha256": sha256(outside.read_bytes()),
        }
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        modules = self.fixture.read("modules.json")
        modules["policy"]["engine_api"] = {"min_inclusive": "1.0.0", "max_exclusive": "1.0.0"}
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        modules = self.fixture.read("modules.json")
        modules["policy"]["migration_version"] = "unknown"
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

    def test_preview_contract_and_legacy_bridge_cannot_escape_preview_scope(self) -> None:
        phases = self.fixture.read("phases.json")
        phases["phases"][0]["transition_intent"]["scope"] = "canonical"
        self.fixture.write("phases.json", phases)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        phases = self.fixture.read("phases.json")
        phases["phases"][0]["output_contracts"][0]["scope"] = "canonical"
        self.fixture.write("phases.json", phases)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

        self.fixture.write_documents()
        modules = self.fixture.read("modules.json")
        modules["policy"]["activation"]["control_mutations"] = True
        self.fixture.write("modules.json", modules)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

    def test_legacy_composite_is_only_preview_legacy_plan_bridge(self) -> None:
        modules = self.fixture.read("modules.json")
        delivery_module = next(module for module in modules["modules"] if module["id"] == "mod.delivery.spec")
        delivery_module["lifecycles"].append("compatibility")
        self.fixture.write("modules.json", modules)
        phases = self.fixture.read("phases.json")
        bridge_obligation = self.fixture.obligation(
            "obl.compat.legacy-composite", "role.architect", "mod.delivery.spec", "rule.delivery.spec",
            "# Delivery", required=True)
        bridge = self.fixture.phase(
            "phase.compat.legacy-composite-v1", "compatibility", "legacy-composite-v1",
            ["mod.delivery.spec"], bridge_obligation, "LegacySpec", "LegacyPlan", None,
            compatibility_adapter="legacy-composite-v1")
        bridge["input_contracts"] = [
            {"id": "in.legacy.spec", "kind": "LegacySpec", "state": "approved"},
            {"id": "in.legacy.approval", "kind": "LegacyApprovalObservation", "state": "observed"},
        ]
        bridge["output_contracts"] = [{"id": "out.legacy.plan", "kind": "LegacyPlan", "scope": "preview"}]
        phases["phases"].append(bridge)
        self.fixture.write("phases.json", phases)
        self.compile()

        bridge["output_contracts"][0]["kind"] = "EngineeringSpec"
        self.fixture.write("phases.json", phases)
        with self.assertRaises(policy_compiler.PolicyError):
            self.compile()

    def test_cli_compile_and_check(self) -> None:
        output = self.fixture.root / "manifest.json"
        command = [sys.executable, str(HERE / "policy_compiler.py")]
        subprocess.run(
            [*command, "compile", "--policy-root", str(self.fixture.policy_root), "--skill-root", str(self.fixture.skill_root),
             "--engine-version", "1.0.0", "--out", str(output)], check=True, capture_output=True, text=True)
        subprocess.run(
            [*command, "check", "--policy-root", str(self.fixture.policy_root), "--skill-root", str(self.fixture.skill_root),
             "--engine-version", "1.0.0"], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["policy_manifest_id"], self.compile()["policy_manifest_id"])

    def test_production_policy_covers_both_lifecycles_and_the_single_legacy_bridge(self) -> None:
        manifest = policy_compiler.compile_policy(
            REPOSITORY_ROOT / "skills" / "sdlc" / "references" / "policies",
            REPOSITORY_ROOT / "skills",
            "1.0.0",
        )
        product = [phase for phase in manifest["phases"] if phase["lifecycle"] == "product-design"]
        delivery = [phase for phase in manifest["phases"] if phase["lifecycle"] == "software-delivery"]
        compatibility = [phase for phase in manifest["phases"] if phase["lifecycle"] == "compatibility"]
        self.assertEqual(len(product), 7)
        self.assertEqual(len(delivery), 6)
        self.assertEqual(len(compatibility), 1)
        bridge = compatibility[0]
        self.assertEqual(bridge["compatibility_adapter"], "legacy-composite-v1")
        self.assertEqual({(item["kind"], item["state"]) for item in bridge["input_contracts"]}, {
            ("LegacySpec", "approved"), ("LegacyApprovalObservation", "observed"),
        })
        self.assertEqual(
            {(item["kind"], item["scope"]) for item in bridge["output_contracts"]},
            {("LegacyPlan", "preview")},
        )
        self.assertTrue(all(
            output["scope"] == "preview" and phase["transition_intent"]["scope"] == "preview"
            for phase in manifest["phases"] for output in phase["output_contracts"]
        ))
        policy_roles = {role["id"] for role in manifest["roles"]}
        obligation_roles = {
            obligation["role_id"] for phase in manifest["phases"] for obligation in phase["obligations"]
        }
        self.assertEqual(policy_roles, obligation_roles)


if __name__ == "__main__":
    unittest.main()
