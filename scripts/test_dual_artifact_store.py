#!/usr/bin/env python3
"""Tests for canonical bundle and execution/release receipt artifacts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import contract_bundle
import dual_artifact_store
import evidence_runner


PRODUCT_REF = "a" * 64
PRODUCT_APPROVAL_REF = "b" * 64
ENGINEERING_REF = "c" * 64
ENGINEERING_APPROVAL_REF = "d" * 64
PLAN_REF = "e" * 64
TESTED_SHA = "f" * 64
RELEASE_CODE_SHA = "7" * 64
GIT_SHA = "a" * 40
TIME = "2026-08-05T10:00:00+08:00"


def current_tuple() -> dict[str, object]:
    return {
        "contract_generation": 3,
        "product_contract_ref": PRODUCT_REF,
        "product_contract_approval_ref": PRODUCT_APPROVAL_REF,
        "engineering_spec_ref": ENGINEERING_REF,
        "engineering_spec_approval_ref": ENGINEERING_APPROVAL_REF,
        "delivery_plan_ref": PLAN_REF,
    }


def trace_refs() -> list[str]:
    return [
        f"PC:{PRODUCT_REF}#SCN-001",
        f"ES:{ENGINEERING_REF}#TEST-001",
    ]


def product_bundle(components: dict[str, object]) -> dict[str, object]:
    return contract_bundle.build_product_contract({
        "contract_kind": "feature",
        "leaf_id": "REQ-001",
        "source_request": "REQ-001",
        "components": components,
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


class BundleArtifactTest(unittest.TestCase):
    def test_text_and_binary_components_round_trip_as_canonical_json(self) -> None:
        components: dict[str, object] = {
            "z-binary.bin": b"\xff\x00\x80",
            "a-product.json": {"message": "你好", "retry": 3},
            "m-behavior.md": "# SCN-001\nworks\n",
        }
        bundle = product_bundle(components)
        artifact = dual_artifact_store.build_bundle_artifact(bundle, components)

        self.assertEqual(artifact["artifact_kind"], "product_contract")
        self.assertEqual(artifact["artifact_id"], bundle["product_contract_id"])
        stored = {item["path"]: item for item in artifact["components"]}  # type: ignore[index]
        self.assertEqual(stored["m-behavior.md"]["encoding"], "utf-8")
        self.assertEqual(stored["z-binary.bin"]["encoding"], "base64")
        self.assertEqual(
            [item["path"] for item in artifact["components"]],  # type: ignore[index]
            sorted(components),
        )
        encoded = dual_artifact_store.canonical_json_bytes(artifact)
        self.assertEqual(json.loads(encoded), artifact)
        self.assertEqual(
            dual_artifact_store.verify_bundle_artifact(artifact),
            bundle["product_contract_id"],
        )
        unpacked_bundle, unpacked_components = dual_artifact_store.unpack_bundle_artifact(artifact)
        self.assertEqual(unpacked_bundle, bundle)
        normalized, _ = contract_bundle.normalize_components(components)
        self.assertEqual(unpacked_components, normalized)

    def test_product_profile_and_engineering_bundle_types_are_supported(self) -> None:
        product_components = {"product.md": "OUT-001\nSCN-001\n"}
        product = product_bundle(product_components)
        profile_components = {"PROFILE.md": b"# profile\n"}
        profile = contract_bundle.snapshot_profile(
            profile_components["PROFILE.md"],
            feature_id="FEAT-001",
            source_sha=GIT_SHA,
            created_at=TIME,
        )
        engineering_components = {"engineering.md": "TEST-001\n"}
        engineering = contract_bundle.build_engineering_spec({
            "feature_id": "FEAT-001",
            "product_contract_approval_ref": PRODUCT_APPROVAL_REF,
            "specified_against_sha": GIT_SHA,
            "implements_product_ids": ["SCN-001"],
            "engineering_criterion_ids": ["TEST-001"],
            "target_surfaces": ["tests"],
            "components": engineering_components,
            "supersedes": None,
            "created_by": "architect",
            "created_at": TIME,
        }, product, profile)

        cases = (
            (product, product_components, "product_contract", product["product_contract_id"]),
            (profile, profile_components, "profile_snapshot", profile["profile_snapshot_id"]),
            (engineering, engineering_components, "engineering_spec", engineering["engineering_spec_id"]),
        )
        for bundle, components, kind, identity in cases:
            with self.subTest(kind=kind):
                artifact = dual_artifact_store.build_bundle_artifact(bundle, components)
                self.assertEqual(artifact["artifact_kind"], kind)
                self.assertEqual(dual_artifact_store.verify_bundle_artifact(artifact), identity)

    def test_unknown_fields_tampering_and_missing_components_are_rejected(self) -> None:
        components = {"product.md": "OUT-001\nSCN-001\n", "binary.bin": b"\xff"}
        bundle = product_bundle(components)
        unknown_bundle = dict(bundle, unexpected=True)
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "bundle-fields"):
            dual_artifact_store.build_bundle_artifact(unknown_bundle, components)

        artifact = dual_artifact_store.build_bundle_artifact(bundle, components)
        unknown_artifact = dict(artifact, unexpected=True)
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "artifact-fields"):
            dual_artifact_store.verify_bundle_artifact(unknown_artifact)

        missing = deepcopy(artifact)
        missing["components"].pop()  # type: ignore[union-attr]
        with self.assertRaises(dual_artifact_store.ArtifactStoreError):
            dual_artifact_store.verify_bundle_artifact(missing)

        tampered = deepcopy(artifact)
        text_component = next(item for item in tampered["components"] if item["encoding"] == "utf-8")  # type: ignore[index]
        text_component["content"] = "changed"
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "component-sha"):
            dual_artifact_store.verify_bundle_artifact(tampered)

        malformed_base64 = deepcopy(artifact)
        binary = next(item for item in malformed_base64["components"] if item["encoding"] == "base64")  # type: ignore[index]
        binary["content"] = "***"
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "base64"):
            dual_artifact_store.verify_bundle_artifact(malformed_base64)


class RunnerReceiptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.cwd = Path(self.tempdir.name)

    def run_command(self, source: str, *, timeout_seconds: float = 2.0) -> dict[str, object]:
        return evidence_runner.run_canonical(
            [sys.executable, "-c", source],
            cwd=self.cwd,
            timeout_seconds=timeout_seconds,
            policy_manifest_ref="1" * 64,
            context_manifest_ref="2" * 64,
            code_sha=TESTED_SHA,
            tool_version="python-test",
        )

    def test_preview_runner_record_cannot_create_a_canonical_receipt(self) -> None:
        preview = evidence_runner.run(
            [sys.executable, "-c", "print('preview')"],
            cwd=self.cwd,
            timeout_seconds=2.0,
            policy_manifest_ref="1" * 64,
            context_manifest_ref="2" * 64,
            code_sha=TESTED_SHA,
            tool_version="python-test",
        )
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "must-be-canonical"):
            dual_artifact_store.build_runner_receipt(
                preview,
                tested_sha=TESTED_SHA,
                feature_id="FEAT-001",
                task_id="TASK-001",
                current_tuple=current_tuple(),
                trace_refs=trace_refs(),
            )

    def verify(self, receipt: dict[str, object]) -> str:
        return dual_artifact_store.verify_runner_receipt(
            receipt,
            expected_tested_sha=TESTED_SHA,
            expected_feature_id="FEAT-001",
            expected_task_id="TASK-001",
            expected_current_tuple=current_tuple(),
            expected_trace_refs=trace_refs(),
        )

    def test_success_failure_and_timeout_are_derived_from_actual_runner_record(self) -> None:
        successful = dual_artifact_store.build_runner_receipt(
            self.run_command("print('ok')"),
            tested_sha=TESTED_SHA,
            feature_id="FEAT-001",
            task_id="TASK-001",
            current_tuple=current_tuple(),
            trace_refs=trace_refs(),
        )
        self.assertEqual(successful["command"][0], sys.executable)  # type: ignore[index]
        self.assertEqual(successful["exit_code"], 0)
        self.assertIs(successful["timed_out"], False)
        self.assertEqual(successful["result"], "pass")
        self.assertEqual(self.verify(successful), successful["receipt_id"])

        failed = dual_artifact_store.build_runner_receipt(
            self.run_command("raise SystemExit(7)"),
            tested_sha=TESTED_SHA,
            feature_id="FEAT-001",
            task_id="TASK-001",
            current_tuple=current_tuple(),
            trace_refs=trace_refs(),
        )
        self.assertEqual(failed["exit_code"], 7)
        self.assertEqual(failed["result"], "fail")

        timed_out = dual_artifact_store.build_runner_receipt(
            self.run_command("import time; time.sleep(10)", timeout_seconds=0.02),
            tested_sha=TESTED_SHA,
            feature_id="FEAT-001",
            task_id="TASK-001",
            current_tuple=current_tuple(),
            trace_refs=trace_refs(),
        )
        self.assertIs(timed_out["timed_out"], True)
        self.assertEqual(timed_out["result"], "fail")

    def test_self_report_hash_forgery_unknown_fields_and_wrong_tuple_fail(self) -> None:
        runner = self.run_command("print('ok')")
        self_reported = dict(runner, result="pass")
        with self.assertRaises(dual_artifact_store.ArtifactStoreError):
            dual_artifact_store.build_runner_receipt(
                self_reported,
                tested_sha=TESTED_SHA,
                feature_id="FEAT-001",
                task_id="TASK-001",
                current_tuple=current_tuple(),
                trace_refs=trace_refs(),
            )
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "tested-sha-runner-mismatch"):
            dual_artifact_store.build_runner_receipt(
                runner,
                tested_sha="0" * 64,
                feature_id="FEAT-001",
                task_id="TASK-001",
                current_tuple=current_tuple(),
                trace_refs=trace_refs(),
            )

        receipt = dual_artifact_store.build_runner_receipt(
            runner,
            tested_sha=TESTED_SHA,
            feature_id="FEAT-001",
            task_id="TASK-001",
            current_tuple=current_tuple(),
            trace_refs=trace_refs(),
        )
        forged = deepcopy(receipt)
        forged["exit_code"] = 9
        forged["receipt_id"] = hashlib.sha256(dual_artifact_store.canonical_json_bytes({
            key: value for key, value in forged.items() if key != "receipt_id"
        })).hexdigest()
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "runner-fact-mismatch"):
            self.verify(forged)

        unknown = dict(receipt, tests_passed=True)
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "runner-receipt-fields"):
            self.verify(unknown)

        stale = current_tuple()
        stale["contract_generation"] = 4
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "current-tuple-mismatch"):
            dual_artifact_store.verify_runner_receipt(
                receipt,
                expected_tested_sha=TESTED_SHA,
                expected_feature_id="FEAT-001",
                expected_task_id="TASK-001",
                expected_current_tuple=stale,
                expected_trace_refs=trace_refs(),
            )


class ReleaseReceiptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.cwd = Path(self.tempdir.name)

    def release_target(self) -> dict[str, str]:
        return {
            "environment": "production",
            "target_type": "container",
            "target_ref": "cluster/prod/api",
        }

    def release_artifact(self) -> dict[str, str]:
        return {
            "artifact_type": "oci-image",
            "artifact_ref": "registry.example/api@sha256:abc",
            "artifact_sha256": "3" * 64,
        }

    def run_release_command(
        self, source: str, *, timeout_seconds: float = 2.0,
    ) -> dict[str, object]:
        return evidence_runner.run_canonical(
            [sys.executable, "-c", source],
            cwd=self.cwd,
            timeout_seconds=timeout_seconds,
            policy_manifest_ref="4" * 64,
            context_manifest_ref="5" * 64,
            code_sha=RELEASE_CODE_SHA,
            tool_version="release-test",
        )

    def build(self, runner_record: dict[str, object]) -> dict[str, object]:
        return dual_artifact_store.build_release_receipt(
            runner_record,
            feature_id="FEAT-001",
            release_target=self.release_target(),
            actual_release_artifact=self.release_artifact(),
            release_sha=GIT_SHA,
            current_tuple=current_tuple(),
        )

    def verify(
        self,
        receipt: dict[str, object],
        *,
        runner_record_ref: str,
        tuple_value: dict[str, object] | None = None,
    ) -> str:
        return dual_artifact_store.verify_release_receipt(
            receipt,
            expected_runner_record_ref=runner_record_ref,
            expected_feature_id="FEAT-001",
            expected_release_target=self.release_target(),
            expected_actual_release_artifact=self.release_artifact(),
            expected_release_sha=GIT_SHA,
            expected_current_tuple=tuple_value or current_tuple(),
        )

    def test_release_receipt_binds_successful_canonical_runner_and_release_facts(self) -> None:
        runner = self.run_release_command("print('released')")
        try:
            receipt = self.build(runner)
        except TypeError as exc:
            self.fail(f"release builder must require a canonical runner record: {exc}")
        except dual_artifact_store.ArtifactStoreError as exc:
            self.fail(f"code and artifact identities must remain independent: {exc}")

        self.assertEqual(receipt["receipt_format"], "release-receipt-v2")
        self.assertEqual(receipt["runner_record_ref"], runner["evidence_id"])
        self.assertEqual(receipt["command"], runner["argv"])
        self.assertEqual(receipt["exit_code"], 0)
        self.assertIs(receipt["timed_out"], False)
        self.assertEqual(receipt["result"], "pass")
        self.assertEqual(receipt["tested_code_sha256"], RELEASE_CODE_SHA)
        self.assertNotEqual(receipt["tested_code_sha256"], self.release_artifact()["artifact_sha256"])
        self.assertEqual(receipt["release_sha"], GIT_SHA)
        self.assertEqual(receipt["actual_release_artifact"], self.release_artifact())
        self.assertEqual(
            self.verify(receipt, runner_record_ref=str(runner["evidence_id"])),
            receipt["receipt_id"],
        )

    def test_failed_timeout_and_preview_runner_are_rejected(self) -> None:
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "release-runner-not-successful"):
            self.build(self.run_release_command("raise SystemExit(9)"))

        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "release-runner-not-successful"):
            self.build(self.run_release_command("import time; time.sleep(10)", timeout_seconds=0.02))

        preview = evidence_runner.run(
            [sys.executable, "-c", "print('preview')"],
            cwd=self.cwd,
            timeout_seconds=2.0,
            policy_manifest_ref="4" * 64,
            context_manifest_ref="5" * 64,
            code_sha=RELEASE_CODE_SHA,
            tool_version="release-test",
        )
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "must-be-canonical"):
            self.build(preview)

    def test_release_receipt_rejects_unknown_fields_tampering_and_stale_tuple(self) -> None:
        runner = self.run_release_command("print('released')")
        bad_target = dict(self.release_target(), unexpected="x")
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "release-target-fields"):
            dual_artifact_store.build_release_receipt(
                runner,
                feature_id="FEAT-001",
                release_target=bad_target,
                actual_release_artifact=self.release_artifact(),
                release_sha=GIT_SHA,
                current_tuple=current_tuple(),
            )

        receipt = self.build(runner)
        unknown = dict(receipt, approved=True)
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "release-receipt-fields"):
            self.verify(unknown, runner_record_ref=str(runner["evidence_id"]))

        forged_facts = deepcopy(receipt)
        forged_facts["exit_code"] = 0 if runner["exit_code"] != 0 else 9
        forged_facts["receipt_id"] = hashlib.sha256(dual_artifact_store.canonical_json_bytes({
            key: value for key, value in forged_facts.items() if key != "receipt_id"
        })).hexdigest()
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "release-runner-fact-mismatch"):
            self.verify(forged_facts, runner_record_ref=str(runner["evidence_id"]))

        forged_code_sha = deepcopy(receipt)
        forged_code_sha["tested_code_sha256"] = "8" * 64
        forged_code_sha["receipt_id"] = hashlib.sha256(dual_artifact_store.canonical_json_bytes({
            key: value for key, value in forged_code_sha.items() if key != "receipt_id"
        })).hexdigest()
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "release-code-runner-mismatch"):
            self.verify(forged_code_sha, runner_record_ref=str(runner["evidence_id"]))

        tampered = deepcopy(receipt)
        tampered["actual_release_artifact"]["artifact_ref"] = "registry.example/api:other"  # type: ignore[index]
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "receipt-content-hash"):
            self.verify(tampered, runner_record_ref=str(runner["evidence_id"]))

        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "runner-record-ref-mismatch"):
            self.verify(receipt, runner_record_ref="0" * 64)

        stale = current_tuple()
        stale["delivery_plan_ref"] = "0" * 64
        with self.assertRaisesRegex(dual_artifact_store.ArtifactStoreError, "current-tuple-mismatch"):
            self.verify(
                receipt,
                runner_record_ref=str(runner["evidence_id"]),
                tuple_value=stale,
            )


if __name__ == "__main__":
    unittest.main()
