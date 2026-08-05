#!/usr/bin/env python3
"""Operational end-to-end tests for the public dual-lifecycle ledger API."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import contract_bundle
import dual_ledger
import plan_compiler


TIME = "2026-08-05T10:00:00+08:00"
PRODUCT_COMPONENTS = {"product.md": "OUT", "behaviors.md": "SCN"}
PROFILE_COMPONENTS = {"PROFILE.md": "# profile\n"}
ENGINEERING_COMPONENTS = {"technical.md": "API"}
RELEASE_BYTES = b"release-v1\n"


def authority_config() -> dict[str, object]:
    """Return a strict local authority configuration with split responsibilities."""
    return {
        "authority_format": "dual-lifecycle-authority-v1",
        "authority_mode": "local-serial",
        "principal": {
            "authority_mode": "local-serial",
            "principal_ref": "principal:configured-owner",
            "roles": ["product-owner", "architect"],
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
            {
                "policy_id": "feature-review-v1",
                "allowed_roles": ["architect"],
                "min_authn_assurance": "configured-audit",
                "subject_type": "feature_review",
                "scope": "feature",
            },
        ],
        "change_request_policy": {
            "allowed_roles": ["architect"],
            "min_authn_assurance": "configured-audit",
        },
    }


class DualLifecycleOperationalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.observations = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temporary.name)
        self.observation_root = Path(self.observations.name)

        (self.repo_root / "src").mkdir()
        (self.repo_root / ".sdlc").mkdir()
        (self.repo_root / "dist").mkdir()
        (self.repo_root / "src" / "api.py").write_text(
            "def ready():\n    return True\n", encoding="utf-8",
        )
        (self.repo_root / ".sdlc" / "PROFILE.md").write_text(
            "# profile\n", encoding="utf-8",
        )
        (self.repo_root / "dist" / "release.bin").write_bytes(RELEASE_BYTES)

        self._git("init", "--quiet")
        self._git("config", "user.email", "operational@example.test")
        self._git("config", "user.name", "Operational Test")
        self._git("add", "src/api.py", ".sdlc/PROFILE.md", "dist/release.bin")
        self._git("commit", "--quiet", "-m", "operational fixture")
        self.git_sha = self._git("rev-parse", "HEAD", capture=True).strip()
        self.ledger = dual_ledger.DualLifecycleLedger(self.repo_root)

    def tearDown(self) -> None:
        self.observations.cleanup()
        self.temporary.cleanup()

    def _git(self, *arguments: str, capture: bool = False) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repo_root), *arguments],
            check=True,
            capture_output=capture,
            text=True,
        )
        return completed.stdout if capture else ""

    def apply_current(
        self, intent: dict[str, object], key: str,
    ) -> dual_ledger.ApplyResult:
        return self.ledger.apply(
            intent=intent,
            expected_snapshot_sha256=self.ledger.status().snapshot_sha256,
            idempotency_key=key,
            timestamp=TIME,
        )

    def write_authority(self) -> None:
        self.ledger.namespace_path.mkdir(parents=True, exist_ok=True)
        self.ledger.authority_path.write_bytes(
            json.dumps(
                authority_config(), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
        )

    def product_contract(self) -> dict[str, object]:
        return contract_bundle.build_product_contract({
            "contract_kind": "feature",
            "leaf_id": "REQ-001",
            "source_request": "REQ-001",
            "components": PRODUCT_COMPONENTS,
            "outcome_ids": ["OUT-001"],
            "behavior_ids": ["SCN-001"],
            "behavior_kinds": {"SCN-001": "new_behavior"},
            "domain_rule_ids": [],
            "experience_ids": [],
            "nfr_ids": [],
            "eval_ids": [],
            "intent_flags": {},
            "supersedes": None,
            "created_by": "product-owner",
            "created_at": TIME,
        })

    def profile_snapshot(self) -> dict[str, object]:
        return contract_bundle.snapshot_profile(
            b"# profile\n",
            feature_id="FEAT-001",
            source_sha=self.git_sha,
            created_at=TIME,
        )

    def engineering_spec(
        self,
        product: dict[str, object],
        product_approval_ref: str,
        profile: dict[str, object],
    ) -> dict[str, object]:
        return contract_bundle.build_engineering_spec({
            "feature_id": "FEAT-001",
            "product_contract_approval_ref": product_approval_ref,
            "specified_against_sha": self.git_sha,
            "implements_product_ids": ["SCN-001"],
            "engineering_criterion_ids": ["API-001"],
            "target_surfaces": ["server"],
            "components": ENGINEERING_COMPONENTS,
            "supersedes": None,
            "created_by": "architect",
            "created_at": TIME,
        }, product, profile)

    def delivery_plan(
        self,
        product: dict[str, object],
        engineering: dict[str, object],
        engineering_approval: dict[str, object],
        *,
        task_argv: list[str],
    ) -> dict[str, object]:
        effective_approval = {
            **engineering_approval,
            "head_ref": engineering_approval["approval_id"],
            "head_decision": "approve",
        }
        return plan_compiler.compile_delivery_plan(
            {**engineering, "contract_generation": 0},
            effective_approval,
            [{
                "id": "TASK-001",
                "title": "Implement API",
                "depends_on": [],
                "write_set": ["src/api.py"],
                "mutual_exclusion_with": [],
                "interface_owner": None,
                "interface_consumes": [],
                "execution_mode": "tdd",
                "evidence_strategy": {
                    "kind": "tdd",
                    "argv": task_argv,
                },
                "trace_refs": [
                    f"PC:{product['product_contract_id']}#SCN-001",
                    f"ES:{engineering['engineering_spec_id']}#API-001",
                ],
            }],
        )

    def current_fence(self) -> dict[str, object]:
        return self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"]

    def execution_request(
        self, source: str, *, fence: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "operation": "execute_task_evidence",
            "feature_id": "FEAT-001",
            "task_id": "TASK-001",
            "fence": fence if fence is not None else self.current_fence(),
            "argv": [sys.executable, "-c", source],
            "cwd": ".",
            "timeout_seconds": 5.0,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "tool_version": "operational-task-runner",
            "at": TIME,
        }

    def publish_request(
        self, source: str, *, fence: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "operation": "publish_feature",
            "feature_id": "FEAT-001",
            "fence": fence if fence is not None else self.current_fence(),
            "release_target": {
                "environment": "production",
                "target_type": "local-artifact",
                "target_ref": "dist/release.bin",
            },
            "actual_release_artifact": {
                "artifact_type": "binary",
                "artifact_ref": "dist/release.bin",
            },
            "artifact_path": "dist/release.bin",
            "argv": [sys.executable, "-c", source],
            "cwd": ".",
            "timeout_seconds": 5.0,
            "policy_manifest_ref": "3" * 64,
            "context_manifest_ref": "4" * 64,
            "tool_version": "operational-release-runner",
            "at": TIME,
        }

    def review_request(self, *, fence: dict[str, object] | None = None) -> dict[str, object]:
        projection = self.ledger.feature_projection(feature_id="FEAT-001")
        return {
            "operation": "submit_feature_review",
            "feature_id": "FEAT-001",
            "fence": fence if fence is not None else projection["current_fence"],
            "decision": "approve",
            "evidence_refs": list(projection["review_evidence_refs"]),
            "rationale_ref": "6" * 64,
            "policy_manifest_ref": "7" * 64,
            "context_manifest_ref": "8" * 64,
            "at": TIME,
        }

    def prepare_active_task(self, *, task_argv: list[str] | None = None) -> dict[str, dict[str, object]]:
        """Create immutable product/delivery artifacts through public apply calls."""
        task_argv = list(task_argv or [sys.executable, "-c", "print('ok')"])
        self.ledger.apply(
            intent={
                "operation": "create_product_definition",
                "leaf_id": "REQ-001",
                "source_request": "REQ-001",
                "owner": "product-owner",
                "at": TIME,
            },
            expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
            idempotency_key="create-definition",
            timestamp=TIME,
        )
        self.apply_current({
            "operation": "start_product_definition",
            "leaf_id": "REQ-001",
            "at": TIME,
        }, "start-definition")

        product = self.product_contract()
        self.apply_current({
            "operation": "submit_product_contract",
            "leaf_id": "REQ-001",
            "contract": product,
            "components": PRODUCT_COMPONENTS,
            "at": TIME,
        }, "submit-product")

        self.write_authority()
        product_request = {
            "operation": "request_approval",
            "subject_type": "product_contract",
            "subject_id": product["product_contract_id"],
            "decision": "approve",
            "decision_intent_ref": "approval:product:operational",
            "at": TIME,
        }
        product_result = self.apply_current(product_request, "approve-product")
        self.assertEqual(product_result.event["requested_intent"], product_request)
        product_canonical = product_result.event["intent"]
        self.assertEqual(product_canonical["operation"], "apply_approval")
        product_approval = product_canonical["approval_record"]
        self.assertEqual(product_approval["principal_ref"], "principal:configured-owner")
        self.assertEqual(product_approval["principal_role"], "product-owner")
        self.assertEqual(
            product_approval["authorization_policy_ref"],
            "product-contract-approval-v1",
        )
        self.assertNotIn("principal_ref", product_request)
        self.assertNotIn("authorization_policy", product_request)

        self.apply_current({
            "operation": "adopt_product_contract",
            "leaf_id": "REQ-001",
            "product_contract_ref": product["product_contract_id"],
            "product_contract_approval_ref": product_approval["approval_id"],
            "at": TIME,
        }, "adopt-product")
        self.apply_current({
            "operation": "claim_feature",
            "leaf_id": "REQ-001",
            "feature_id": "FEAT-001",
            "claimed_base_sha": self.git_sha,
            "expected_product_contract_ref": product["product_contract_id"],
            "expected_product_approval_ref": product_approval["approval_id"],
            "at": TIME,
        }, "claim-feature")

        profile = self.profile_snapshot()
        self.apply_current({
            "operation": "register_profile_snapshot",
            "profile_snapshot": profile,
            "components": PROFILE_COMPONENTS,
        }, "register-profile")

        engineering = self.engineering_spec(
            product, str(product_approval["approval_id"]), profile,
        )
        self.apply_current({
            "operation": "register_engineering_spec",
            "engineering_spec": engineering,
            "components": ENGINEERING_COMPONENTS,
        }, "register-engineering")
        engineering_request = {
            "operation": "request_approval",
            "subject_type": "engineering_spec",
            "subject_id": engineering["engineering_spec_id"],
            "decision": "approve",
            "decision_intent_ref": "approval:engineering:operational",
            "at": TIME,
        }
        engineering_result = self.apply_current(
            engineering_request, "approve-engineering",
        )
        self.assertEqual(engineering_result.event["requested_intent"], engineering_request)
        engineering_canonical = engineering_result.event["intent"]
        self.assertEqual(engineering_canonical["operation"], "apply_approval")
        engineering_approval = engineering_canonical["approval_record"]
        self.assertEqual(
            engineering_approval["principal_ref"], "principal:configured-owner",
        )
        self.assertEqual(engineering_approval["principal_role"], "architect")
        self.assertEqual(
            engineering_approval["authorization_policy_ref"],
            "engineering-spec-approval-v1",
        )

        self.apply_current({
            "operation": "adopt_engineering_spec",
            "feature_id": "FEAT-001",
            "engineering_spec_ref": engineering["engineering_spec_id"],
            "engineering_spec_approval_ref": engineering_approval["approval_id"],
            "expected_generation": 0,
            "at": TIME,
        }, "adopt-engineering")
        plan = self.delivery_plan(product, engineering, engineering_approval, task_argv=task_argv)
        self.apply_current({
            "operation": "activate_delivery_plan",
            "feature_id": "FEAT-001",
            "delivery_plan": plan,
            "expected_generation": 0,
            "at": TIME,
        }, "activate-plan")
        for action in ("claim", "start"):
            self.apply_current({
                "operation": "transition_task",
                "feature_id": "FEAT-001",
                "task_id": "TASK-001",
                "action": action,
                "fence": self.current_fence(),
                "at": TIME,
            }, f"task-{action}")

        return {
            "product": product,
            "product_approval": product_approval,
            "profile": profile,
            "engineering": engineering,
            "engineering_approval": engineering_approval,
            "plan": plan,
        }

    def test_operational_public_flow_is_replayable_and_product_isolated(self) -> None:
        execution_marker = self.observation_root / "task-command-ran-once"
        successful_source = (
            "from pathlib import Path; "
            f"p=Path({str(execution_marker)!r}); "
            "assert not p.exists(); p.write_text('once', encoding='utf-8')"
        )
        artifacts = self.prepare_active_task(
            task_argv=[sys.executable, "-c", successful_source],
        )
        self.assertEqual(len(self.ledger.snapshot()["bundle_artifacts"]), 3)

        stale_fence = copy.deepcopy(self.current_fence())
        stale_fence["contract_generation"] += 1
        stale_marker = self.observation_root / "stale-command-ran"
        stale_source = (
            "from pathlib import Path; "
            f"Path({str(stale_marker)!r}).write_text('ran', encoding='utf-8')"
        )
        before_stale = self.ledger.status()
        with self.assertRaisesRegex(
            dual_ledger.LedgerTransitionError, "stale-contract-fence",
        ):
            self.ledger.apply(
                intent=self.execution_request(stale_source, fence=stale_fence),
                expected_snapshot_sha256=before_stale.snapshot_sha256,
                idempotency_key="stale-execution",
                timestamp=TIME,
            )
        after_stale = self.ledger.status()
        self.assertEqual(after_stale.snapshot_sha256, before_stale.snapshot_sha256)
        self.assertEqual(after_stale.event_count, before_stale.event_count)
        self.assertFalse(stale_marker.exists())

        execution_request = self.execution_request(successful_source)
        execution_expected = self.ledger.status().snapshot_sha256
        executed = self.ledger.apply(
            intent=execution_request,
            expected_snapshot_sha256=execution_expected,
            idempotency_key="successful-execution",
            timestamp=TIME,
        )
        self.assertTrue(execution_marker.exists())
        events_after_execution = self.ledger.status().event_count
        execution_retry = self.ledger.apply(
            intent=execution_request,
            expected_snapshot_sha256=execution_expected,
            idempotency_key="successful-execution",
            timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(execution_retry.idempotent)
        self.assertEqual(execution_retry.event, executed.event)
        self.assertEqual(execution_retry.next_snapshot_sha256, executed.next_snapshot_sha256)
        self.assertEqual(self.ledger.status().event_count, events_after_execution)
        self.assertEqual(execution_marker.read_text(encoding="utf-8"), "once")
        changed_execution = copy.deepcopy(execution_request)
        changed_execution["timeout_seconds"] = 4.0
        with self.assertRaisesRegex(
            dual_ledger.LedgerConflictError, "idempotency-key-intent-mismatch",
        ):
            self.ledger.apply(
                intent=changed_execution,
                expected_snapshot_sha256=executed.next_snapshot_sha256,
                idempotency_key="successful-execution",
                timestamp=TIME,
            )

        for key, intent in (
            ("verify-task", {
                "operation": "transition_task",
                "feature_id": "FEAT-001",
                "task_id": "TASK-001",
                "action": "verify",
                "fence": self.current_fence(),
                "at": TIME,
            }),
            ("validate-feature", {
                "operation": "validate_feature",
                "feature_id": "FEAT-001",
                "fence": self.current_fence(),
                "at": TIME,
            }),
            ("review-feature", self.review_request()),
        ):
            self.apply_current(intent, key)

        publish_marker = self.observation_root / "publish-command-ran-once"
        publish_source = (
            "from pathlib import Path; "
            f"assert Path('dist/release.bin').read_bytes() == {RELEASE_BYTES!r}; "
            f"p=Path({str(publish_marker)!r}); "
            "assert not p.exists(); p.write_text('once', encoding='utf-8')"
        )
        publish_request = self.publish_request(publish_source)
        publish_expected = self.ledger.status().snapshot_sha256
        published = self.ledger.apply(
            intent=publish_request,
            expected_snapshot_sha256=publish_expected,
            idempotency_key="publish-feature",
            timestamp=TIME,
        )
        self.assertTrue(publish_marker.exists())
        events_after_publish = self.ledger.status().event_count
        publish_retry = self.ledger.apply(
            intent=publish_request,
            expected_snapshot_sha256=publish_expected,
            idempotency_key="publish-feature",
            timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(publish_retry.idempotent)
        self.assertEqual(publish_retry.event, published.event)
        self.assertEqual(publish_retry.next_snapshot_sha256, published.next_snapshot_sha256)
        self.assertEqual(self.ledger.status().event_count, events_after_publish)
        self.assertEqual(publish_marker.read_text(encoding="utf-8"), "once")

        snapshot = self.ledger.snapshot()
        feature = snapshot["features"]["FEAT-001"]
        claim = snapshot["claims"]["REQ-001"]
        task = next(iter(snapshot["tasks"].values()))
        self.assertEqual(feature["status"], "shipped")
        self.assertEqual(feature["validation_status"], "passed")
        self.assertEqual(feature["review_status"], "approved")
        self.assertEqual(claim["status"], "released")
        self.assertEqual(task["status"], "verified")
        self.assertEqual(claim["release_evidence_ref"], feature["release_evidence_ref"])

        bundle_kinds = {
            artifact["artifact_kind"]
            for artifact in snapshot["bundle_artifacts"].values()
        }
        self.assertEqual(
            bundle_kinds,
            {"product_contract", "profile_snapshot", "engineering_spec"},
        )
        self.assertEqual(
            set(snapshot["bundle_artifacts"]),
            {
                artifacts["product"]["product_contract_id"],
                artifacts["profile"]["profile_snapshot_id"],
                artifacts["engineering"]["engineering_spec_id"],
            },
        )
        runner_results = sorted(
            receipt["result"] for receipt in snapshot["runner_receipts"].values()
        )
        self.assertEqual(runner_results, ["pass"])
        self.assertEqual(
            sorted(evidence["result"] for evidence in snapshot["evidence"].values()),
            ["pass"],
        )

        release_ref = feature["release_evidence_ref"]
        release_receipt = snapshot["release_receipts"][release_ref]
        artifact_sha256 = hashlib.sha256(RELEASE_BYTES).hexdigest()
        self.assertEqual(release_receipt["receipt_format"], "release-receipt-v2")
        self.assertEqual(release_receipt["result"], "pass")
        self.assertEqual(release_receipt["release_sha"], self.git_sha)
        self.assertEqual(
            release_receipt["actual_release_artifact"],
            {
                "artifact_type": "binary",
                "artifact_ref": "dist/release.bin",
                "artifact_sha256": artifact_sha256,
            },
        )
        self.assertEqual(
            release_receipt["tested_code_sha256"],
            release_receipt["runner_record"]["code_sha"],
        )
        self.assertNotEqual(release_receipt["tested_code_sha256"], artifact_sha256)
        self.assertFalse(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.replay_snapshot(), snapshot)

        product_projection = self.ledger.product_projection(leaf_id="REQ-001")
        self.assertEqual(
            set(product_projection),
            {
                "leaf_id",
                "definition_status",
                "product_contract_ref",
                "product_contract_approval_ref",
                "features",
            },
        )
        self.assertEqual(len(product_projection["features"]), 1)
        projected_feature = product_projection["features"][0]
        self.assertEqual(projected_feature["status"], "shipped")
        self.assertEqual(projected_feature["delivery_state"], "shipped")
        self.assertEqual(projected_feature["task_counts"], {"verified": 1})
        self.assertEqual(
            set(projected_feature),
            {
                "feature_id",
                "status",
                "contract_generation",
                "delivery_state",
                "validation_status",
                "review_status",
                "task_counts",
                "active_change_request_refs",
            },
        )
        serialized_projection = json.dumps(product_projection, sort_keys=True)
        for internal_field in (
            "engineering_spec_ref",
            "engineering_spec_approval_ref",
            "delivery_plan_ref",
            "bundle_artifacts",
            "runner_receipts",
            "release_receipts",
            "actual_release_artifact",
        ):
            self.assertNotIn(internal_field, serialized_projection)
        product_projection["features"][0]["status"] = "tampered"
        self.assertEqual(
            self.ledger.product_projection(leaf_id="REQ-001")["features"][0]["status"],
            "shipped",
        )

    def test_internal_operations_and_caller_claimed_facts_are_rejected(self) -> None:
        def assert_absent_rejection(
            intent: dict[str, object], key: str, pattern: str,
        ) -> None:
            before = self.ledger.status()
            self.assertFalse(before.initialized)
            with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, pattern):
                self.ledger.apply(
                    intent=intent,
                    expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
                    idempotency_key=key,
                    timestamp=TIME,
                )
            after = self.ledger.status()
            self.assertFalse(after.initialized)
            self.assertEqual(after.snapshot_sha256, before.snapshot_sha256)
            self.assertEqual(after.event_count, 0)

        for operation in ("apply_approval", "record_evidence", "review_feature", "ship_feature"):
            assert_absent_rejection(
                {"operation": operation},
                f"raw-{operation}",
                f"raw-internal-operation-is-not-public:{operation}",
            )

        fake_fence = {
            "contract_generation": 0,
            "product_contract_ref": "a" * 64,
            "product_contract_approval_ref": "b" * 64,
            "engineering_spec_ref": "c" * 64,
            "engineering_spec_approval_ref": "d" * 64,
            "delivery_plan_ref": "e" * 64,
        }
        execute_request = {
            "operation": "execute_task_evidence",
            "feature_id": "FEAT-001",
            "task_id": "TASK-001",
            "fence": fake_fence,
            "argv": [sys.executable, "-c", "print('not run')"],
            "cwd": ".",
            "timeout_seconds": 1.0,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "tool_version": "forged-runner",
            "at": TIME,
        }
        assert_absent_rejection(
            {**execute_request, "result": "pass"},
            "caller-result",
            "invalid-execute-task-evidence-fields",
        )
        assert_absent_rejection(
            {**execute_request, "code_sha": "f" * 64},
            "caller-code-sha",
            "invalid-execute-task-evidence-fields",
        )

        publish_request = {
            "operation": "publish_feature",
            "feature_id": "FEAT-001",
            "fence": fake_fence,
            "release_target": {
                "environment": "production",
                "target_type": "local-artifact",
                "target_ref": "dist/release.bin",
            },
            "actual_release_artifact": {
                "artifact_type": "binary",
                "artifact_ref": "dist/release.bin",
            },
            "artifact_path": "dist/release.bin",
            "argv": [sys.executable, "-c", "print('not run')"],
            "cwd": ".",
            "timeout_seconds": 1.0,
            "policy_manifest_ref": "3" * 64,
            "context_manifest_ref": "4" * 64,
            "tool_version": "forged-publisher",
            "at": TIME,
        }
        assert_absent_rejection(
            {**publish_request, "release_sha": self.git_sha},
            "caller-release-sha",
            "invalid-publish-feature-fields",
        )
        forged_artifact_request = copy.deepcopy(publish_request)
        forged_artifact_request["actual_release_artifact"]["artifact_sha256"] = "f" * 64
        assert_absent_rejection(
            forged_artifact_request,
            "caller-artifact-sha",
            "invalid-actual-release-artifact-fields",
        )


if __name__ == "__main__":
    unittest.main()
