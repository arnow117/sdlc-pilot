#!/usr/bin/env python3
"""State-machine tests for the pure dual-lifecycle reducer."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest

import approval
import contract_bundle
import dual_artifact_store
import evidence_runner
import lifecycle_reducer as lifecycle
import plan_compiler
import review_attestation


GIT_A = "a" * 40
GIT_B = "b" * 40
TESTED_SHA = "f" * 64
TIME = "2026-08-05T10:00:00+08:00"

PRODUCT_POLICY = {
    "policy_id": "product-policy-v1",
    "allowed_roles": ["product-owner"],
    "min_authn_assurance": "configured-audit",
    "subject_type": "product_contract",
    "scope": "product",
}
ENGINEERING_POLICY = {
    "policy_id": "engineering-policy-v1",
    "allowed_roles": ["architect"],
    "min_authn_assurance": "configured-audit",
    "subject_type": "engineering_spec",
    "scope": "feature",
}
REVIEW_POLICY = {
    "policy_id": "feature-review-v1",
    "allowed_roles": ["architect"],
    "min_authn_assurance": "configured-audit",
    "subject_type": "feature_review",
    "scope": "feature",
}


def product_components() -> dict[str, object]:
    return {"product.md": "OUT", "behaviors.md": "SCN"}


def profile_components() -> dict[str, object]:
    return {"PROFILE.md": b"# profile\n"}


def engineering_components(*, replacement: bool = False) -> dict[str, object]:
    return {"technical.md": "API replacement" if replacement else "API"}


def product_contract(*, kind: str = "feature", supersedes: object = None) -> dict[str, object]:
    behavior_kind = "reproduction" if kind == "patch" else "new_behavior"
    return contract_bundle.build_product_contract({
        "contract_kind": kind,
        "leaf_id": "REQ-001",
        "source_request": "REQ-001",
        "components": product_components(),
        "outcome_ids": ["OUT-001"],
        "behavior_ids": ["SCN-001"],
        "behavior_kinds": {"SCN-001": behavior_kind},
        "domain_rule_ids": [],
        "experience_ids": [],
        "nfr_ids": [],
        "eval_ids": [],
        "intent_flags": {},
        "supersedes": supersedes,
        "created_by": "product-owner",
        "created_at": TIME,
    })


def principal(role: str) -> approval.Principal:
    return approval.resolve_principal(
        authority_mode="local-serial",
        authority_config={
            "authority_mode": "local-serial",
            "principal_ref": f"principal:{role}",
            "roles": [role],
            "authn_method": "configured-file",
            "authn_assurance": "configured-audit",
        },
    )


def feature_review_attestation(
    state: dict[str, object], *, decision: str = "approve", evidence_refs: list[str] | None = None,
) -> dict[str, object]:
    feature = state["features"]["FEAT-001"]  # type: ignore[index]
    if evidence_refs is None:
        evidence_refs = sorted({
            evidence_id
            for task in state["tasks"].values()  # type: ignore[index,union-attr]
            if task["feature_id"] == "FEAT-001"
            and task["delivery_plan_ref"] == feature["delivery_plan_ref"]
            and task["contract_generation"] == feature["contract_generation"]
            for evidence_id in task["evidence_refs"]
            if state["evidence"][evidence_id]["result"] == "pass"  # type: ignore[index]
        })
    return review_attestation.build_review_attestation(
        feature_id="FEAT-001",
        decision=decision,
        current_tuple=lifecycle.current_fence(state, feature_id="FEAT-001"),
        reviewer=principal("architect"),
        authorization_policy=approval.parse_authorization_policy(REVIEW_POLICY),
        evidence_refs=evidence_refs,
        rationale_ref="b" * 64,
        policy_manifest_ref="c" * 64,
        context_manifest_ref="d" * 64,
        reviewed_at=TIME,
    )


def approve(
    state: dict[str, object], *, subject_type: str, subject_id: str, policy: dict[str, object], role: str,
) -> tuple[dict[str, object], dict[str, object]]:
    parsed = approval.parse_authorization_policy(policy)
    record = approval.build_approval(
        subject=lifecycle.approval_subject(subject_type, subject_id),
        decision="approve",
        previous_approval_ref=None,
        authorization_policy=parsed,
        principal=principal(role),
        decision_intent_ref=f"intent:{subject_type}",
        decided_at=TIME,
    )
    return lifecycle.apply_approval(
        state, approval_record=record, authorization_policy=policy, at=TIME,
    ), record


def revoke(
    state: dict[str, object], *, subject_type: str, subject_id: str, previous: str,
    policy: dict[str, object], role: str,
) -> tuple[dict[str, object], dict[str, object]]:
    parsed = approval.parse_authorization_policy(policy)
    record = approval.build_approval(
        subject=lifecycle.approval_subject(subject_type, subject_id),
        decision="revoke",
        previous_approval_ref=previous,
        authorization_policy=parsed,
        principal=principal(role),
        decision_intent_ref=f"revoke:{subject_type}",
        decided_at=TIME,
    )
    return lifecycle.apply_approval(
        state, approval_record=record, authorization_policy=policy, at=TIME,
    ), record


def approved_product_state(*, kind: str = "feature") -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    state = lifecycle.empty_snapshot()
    state = lifecycle.create_product_definition(
        state, leaf_id="REQ-001", source_request="REQ-001", owner="product-owner", at=TIME,
    )
    state = lifecycle.start_product_definition(state, leaf_id="REQ-001", at=TIME)
    product = product_contract(kind=kind)
    state = lifecycle.submit_product_contract(
        state, leaf_id="REQ-001", contract=product, components=product_components(), at=TIME,
    )
    state, product_approval = approve(
        state,
        subject_type="product_contract",
        subject_id=str(product["product_contract_id"]),
        policy=PRODUCT_POLICY,
        role="product-owner",
    )
    state = lifecycle.adopt_product_contract(
        state,
        leaf_id="REQ-001",
        product_contract_ref=str(product["product_contract_id"]),
        product_contract_approval_ref=str(product_approval["approval_id"]),
        at=TIME,
    )
    return state, product, product_approval


def claimed_state() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    state, product, product_approval = approved_product_state()
    state = lifecycle.claim_feature(
        state,
        leaf_id="REQ-001",
        feature_id="FEAT-001",
        claimed_base_sha=GIT_A,
        expected_product_contract_ref=str(product["product_contract_id"]),
        expected_product_approval_ref=str(product_approval["approval_id"]),
        at=TIME,
    )
    return state, product, product_approval


def engineering_artifacts(
    product: dict[str, object], product_approval: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    profile = contract_bundle.snapshot_profile(
        profile_components()["PROFILE.md"], feature_id="FEAT-001", source_sha=GIT_A, created_at=TIME,
    )
    engineering = contract_bundle.build_engineering_spec({
        "feature_id": "FEAT-001",
        "product_contract_approval_ref": product_approval["approval_id"],
        "specified_against_sha": GIT_A,
        "implements_product_ids": ["SCN-001"],
        "engineering_criterion_ids": ["API-001"],
        "target_surfaces": ["server"],
        "components": engineering_components(),
        "supersedes": None,
        "created_by": "architect",
        "created_at": TIME,
    }, product, profile)
    return profile, engineering


def replacement_engineering_artifacts(
    product: dict[str, object], product_approval: dict[str, object], previous: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    profile = contract_bundle.snapshot_profile(
        profile_components()["PROFILE.md"], feature_id="FEAT-001", source_sha=GIT_A, created_at=TIME,
    )
    engineering = contract_bundle.build_engineering_spec({
        "feature_id": "FEAT-001",
        "product_contract_approval_ref": product_approval["approval_id"],
        "specified_against_sha": GIT_A,
        "implements_product_ids": ["SCN-001"],
        "engineering_criterion_ids": ["API-002"],
        "target_surfaces": ["server"],
        "components": engineering_components(replacement=True),
        "supersedes": {"ref": previous["engineering_spec_id"], "feature_id": "FEAT-001"},
        "created_by": "architect",
        "created_at": TIME,
    }, product, profile)
    return profile, engineering


def plan_tasks(product: dict[str, object], engineering: dict[str, object]) -> list[dict[str, object]]:
    return [{
        "id": "TASK-001",
        "title": "Implement API",
        "depends_on": [],
        "write_set": ["src/api.py"],
        "mutual_exclusion_with": [],
        "interface_owner": None,
        "interface_consumes": [],
        "execution_mode": "tdd",
        "evidence_strategy": {"kind": "tdd", "argv": ["python3", "-m", "pytest"]},
        "trace_refs": [
            f"PC:{product['product_contract_id']}#SCN-001",
            f"ES:{engineering['engineering_spec_id']}#API-001",
        ],
    }]


def approved_engineering_state(
) -> tuple[
    dict[str, object], dict[str, object], dict[str, object], dict[str, object],
    dict[str, object], dict[str, object],
]:
    state, product, product_approval = claimed_state()
    profile, engineering = engineering_artifacts(product, product_approval)
    state = lifecycle.register_profile_snapshot(
        state, profile_snapshot=profile, components=profile_components(),
    )
    state = lifecycle.register_engineering_spec(
        state, engineering_spec=engineering, components=engineering_components(),
    )
    state, engineering_approval = approve(
        state,
        subject_type="engineering_spec",
        subject_id=str(engineering["engineering_spec_id"]),
        policy=ENGINEERING_POLICY,
        role="architect",
    )
    state = lifecycle.adopt_engineering_spec(
        state,
        feature_id="FEAT-001",
        engineering_spec_ref=str(engineering["engineering_spec_id"]),
        engineering_spec_approval_ref=str(engineering_approval["approval_id"]),
        expected_generation=0,
        at=TIME,
    )
    effective = dict(engineering_approval, head_ref=engineering_approval["approval_id"], head_decision="approve")
    return state, product, product_approval, engineering, engineering_approval, effective


def active_delivery_state() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    state, product, product_approval, engineering, engineering_approval, effective = approved_engineering_state()
    # Generation is a Feature binding, not part of the immutable engineering bundle hash.
    plan = plan_compiler.compile_delivery_plan(
        dict(engineering, contract_generation=0), effective, plan_tasks(product, engineering),
    )
    state = lifecycle.activate_delivery_plan(
        state,
        feature_id="FEAT-001",
        delivery_plan=plan,
        expected_generation=0,
        at=TIME,
    )
    return state, product, product_approval, engineering, engineering_approval


def rehash_plan(plan: dict[str, object]) -> None:
    digest = hashlib.sha256(plan_compiler.canonical_bytes(plan_compiler._plan_preimage(plan))).hexdigest()
    plan["delivery_plan_id"] = digest
    plan["bundle_sha256"] = digest


def runner_record(*, passed: bool = True, tested_sha: str = TESTED_SHA) -> dict[str, object]:
    source = "print('ok')" if passed else "raise SystemExit(7)"
    return evidence_runner.run_canonical(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parent,
        timeout_seconds=2.0,
        policy_manifest_ref="1" * 64,
        context_manifest_ref="2" * 64,
        code_sha=tested_sha,
        tool_version="python-test",
    )


def record_task_evidence(
    state: dict[str, object], *, passed: bool = True,
    tested_sha: str = TESTED_SHA, fence: dict[str, object] | None = None,
) -> dict[str, object]:
    return lifecycle.record_evidence(
        state,
        runner_record=runner_record(passed=passed, tested_sha=tested_sha),
        tested_sha=tested_sha,
        feature_id="FEAT-001",
        task_id="TASK-001",
        fence=fence or lifecycle.current_fence(state, feature_id="FEAT-001"),
        at=TIME,
    )


def release_target() -> dict[str, str]:
    return {
        "environment": "production",
        "target_type": "container",
        "target_ref": "cluster/prod/api",
    }


def release_artifact() -> dict[str, str]:
    return {
        "artifact_type": "oci-image",
        "artifact_ref": "registry.example/api@sha256:abc",
        "artifact_sha256": "9" * 64,
    }


def release_receipt_for(
    state: dict[str, object], *, feature_id: str = "FEAT-001",
    tuple_value: dict[str, object] | None = None,
) -> dict[str, object]:
    return dual_artifact_store.build_release_receipt(
        runner_record(tested_sha=str(release_artifact()["artifact_sha256"])),
        feature_id=feature_id,
        release_target=release_target(),
        actual_release_artifact=release_artifact(),
        release_sha=GIT_A,
        current_tuple=tuple_value or lifecycle.current_fence(state, feature_id=feature_id),
    )


def reviewed_delivery_state() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    state, product, product_approval, engineering, engineering_approval = active_delivery_state()
    state = lifecycle.transition_task(
        state,
        feature_id="FEAT-001",
        task_id="TASK-001",
        action="claim",
        fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
        at=TIME,
    )
    state = lifecycle.transition_task(
        state,
        feature_id="FEAT-001",
        task_id="TASK-001",
        action="start",
        fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
        at=TIME,
    )
    state = record_task_evidence(state)
    state = lifecycle.transition_task(
        state,
        feature_id="FEAT-001",
        task_id="TASK-001",
        action="verify",
        fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
        at=TIME,
    )
    state = lifecycle.validate_feature(
        state, feature_id="FEAT-001", fence=lifecycle.current_fence(state, feature_id="FEAT-001"), at=TIME,
    )
    state = lifecycle.review_feature(
        state,
        feature_id="FEAT-001",
        fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
        attestation=feature_review_attestation(state),
        at=TIME,
    )
    return state, product, product_approval, engineering, engineering_approval


class LifecycleReducerTest(unittest.TestCase):
    def test_serializable_dispatcher_routes_to_the_same_pure_reducer(self) -> None:
        state = lifecycle.reduce(lifecycle.empty_snapshot(), {
            "operation": "create_product_definition",
            "leaf_id": "REQ-001",
            "source_request": "REQ-001",
            "owner": "product-owner",
            "at": TIME,
        })
        self.assertEqual(state["product_definitions"]["REQ-001"]["draft_status"], "idle")  # type: ignore[index]
        with self.assertRaisesRegex(lifecycle.ReducerError, "unknown-lifecycle-operation"):
            lifecycle.reduce(state, {"operation": "erase_everything"})

    def test_snapshot_declares_all_immutable_artifact_and_receipt_collections(self) -> None:
        state = lifecycle.empty_snapshot()
        self.assertEqual(state["bundle_artifacts"], {})
        self.assertEqual(state["runner_receipts"], {})
        self.assertEqual(state["review_attestations"], {})
        self.assertEqual(state["release_receipts"], {})
        lifecycle.validate_snapshot(state)

    def test_bundle_registration_requires_components_and_is_atomic_on_forgery(self) -> None:
        state = lifecycle.empty_snapshot()
        product = product_contract()
        profile = contract_bundle.snapshot_profile(
            profile_components()["PROFILE.md"], feature_id="FEAT-001", source_sha=GIT_A, created_at=TIME,
        )
        engineering = contract_bundle.build_engineering_spec({
            "feature_id": "FEAT-001",
            "product_contract_approval_ref": "a" * 64,
            "specified_against_sha": GIT_A,
            "implements_product_ids": ["SCN-001"],
            "engineering_criterion_ids": ["API-001"],
            "target_surfaces": ["server"],
            "components": engineering_components(),
            "supersedes": None,
            "created_by": "architect",
            "created_at": TIME,
        }, product, profile)
        cases = (
            lambda: lifecycle.register_product_contract(state, contract=product),
            lambda: lifecycle.register_profile_snapshot(state, profile_snapshot=profile),
            lambda: lifecycle.register_engineering_spec(state, engineering_spec=engineering),
        )
        for operation in cases:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(lifecycle.ReducerError, "components-required"):
                    operation()
        self.assertEqual(state, lifecycle.empty_snapshot())

        shaping = lifecycle.create_product_definition(
            state, leaf_id="REQ-001", source_request="REQ-001", owner="product-owner", at=TIME,
        )
        shaping = lifecycle.start_product_definition(shaping, leaf_id="REQ-001", at=TIME)
        before = deepcopy(shaping)
        with self.assertRaisesRegex(lifecycle.ReducerError, "components-required"):
            lifecycle.submit_product_contract(shaping, leaf_id="REQ-001", contract=product, at=TIME)
        with self.assertRaises(lifecycle.ReducerError):
            lifecycle.submit_product_contract(
                shaping,
                leaf_id="REQ-001",
                contract=product,
                components={"product.md": "forged", "behaviors.md": "SCN"},
                at=TIME,
            )
        self.assertEqual(shaping, before)

        registered = lifecycle.reduce(state, {
            "operation": "register_product_contract",
            "contract": product,
            "components": product_components(),
        })
        identity = product["product_contract_id"]
        self.assertEqual(registered["product_contracts"][identity], product)  # type: ignore[index]
        self.assertEqual(registered["bundle_artifacts"][identity]["artifact_id"], identity)  # type: ignore[index]

    def test_bundle_artifacts_are_persisted_and_reverified_by_readiness_and_adoption(self) -> None:
        state, product, _, engineering, _, _ = approved_engineering_state()
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        expected = {
            str(product["product_contract_id"]): state["product_contracts"][product["product_contract_id"]],  # type: ignore[index]
            str(feature["profile_ref"]): state["profile_snapshots"][feature["profile_ref"]],  # type: ignore[index]
            str(engineering["engineering_spec_id"]): state["engineering_specs"][engineering["engineering_spec_id"]],  # type: ignore[index]
        }
        for identity, bundle in expected.items():
            with self.subTest(identity=identity):
                artifact = state["bundle_artifacts"][identity]  # type: ignore[index]
                self.assertEqual(dual_artifact_store.verify_bundle_artifact(artifact), identity)
                unpacked, _ = dual_artifact_store.unpack_bundle_artifact(artifact)
                self.assertEqual(unpacked, bundle)

        missing = deepcopy(state)
        del missing["bundle_artifacts"][product["product_contract_id"]]  # type: ignore[index]
        readiness = lifecycle.product_readiness(missing, leaf_id="REQ-001")
        self.assertFalse(readiness["ready"])
        self.assertIn("missing-product-contract-bundle-artifact", readiness["reasons"])

        mismatched = deepcopy(state)
        mismatched["product_contracts"][product["product_contract_id"]]["created_at"] = "changed"  # type: ignore[index]
        readiness = lifecycle.product_readiness(mismatched, leaf_id="REQ-001")
        self.assertFalse(readiness["ready"])
        self.assertIn("product-contract-bundle-artifact-mismatch", readiness["reasons"])

        pending = lifecycle.empty_snapshot()
        pending = lifecycle.create_product_definition(
            pending, leaf_id="REQ-001", source_request="REQ-001", owner="product-owner", at=TIME,
        )
        pending = lifecycle.start_product_definition(pending, leaf_id="REQ-001", at=TIME)
        pending = lifecycle.submit_product_contract(
            pending, leaf_id="REQ-001", contract=product,
            components=product_components(), at=TIME,
        )
        pending, pending_approval = approve(
            pending,
            subject_type="product_contract",
            subject_id=str(product["product_contract_id"]),
            policy=PRODUCT_POLICY,
            role="product-owner",
        )
        del pending["bundle_artifacts"][product["product_contract_id"]]  # type: ignore[index]
        with self.assertRaisesRegex(lifecycle.ReducerError, "missing-product-contract-bundle-artifact"):
            lifecycle.adopt_product_contract(
                pending,
                leaf_id="REQ-001",
                product_contract_ref=str(product["product_contract_id"]),
                product_contract_approval_ref=str(pending_approval["approval_id"]),
                at=TIME,
            )

        claimed, claimed_product, claimed_approval = claimed_state()
        profile, candidate = engineering_artifacts(claimed_product, claimed_approval)
        claimed = lifecycle.register_profile_snapshot(
            claimed, profile_snapshot=profile, components=profile_components(),
        )
        claimed = lifecycle.register_engineering_spec(
            claimed, engineering_spec=candidate, components=engineering_components(),
        )
        claimed, candidate_approval = approve(
            claimed,
            subject_type="engineering_spec",
            subject_id=str(candidate["engineering_spec_id"]),
            policy=ENGINEERING_POLICY,
            role="architect",
        )
        cases = (
            (candidate["engineering_spec_id"], "missing-engineering-spec-bundle-artifact"),
            (profile["profile_snapshot_id"], "missing-profile-snapshot-bundle-artifact"),
        )
        for artifact_ref, error in cases:
            with self.subTest(missing_artifact=artifact_ref):
                missing_adoption_artifact = deepcopy(claimed)
                del missing_adoption_artifact["bundle_artifacts"][artifact_ref]  # type: ignore[index]
                with self.assertRaisesRegex(lifecycle.ReducerError, error):
                    lifecycle.adopt_engineering_spec(
                        missing_adoption_artifact,
                        feature_id="FEAT-001",
                        engineering_spec_ref=str(candidate["engineering_spec_id"]),
                        engineering_spec_approval_ref=str(candidate_approval["approval_id"]),
                        expected_generation=0,
                        at=TIME,
                    )

    def test_claim_pins_effective_product_tuple_and_rejects_stale_claim_fence(self) -> None:
        state, product, product_approval = approved_product_state()
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "claim-fence"):
            lifecycle.claim_feature(
                state,
                leaf_id="REQ-001",
                feature_id="FEAT-001",
                claimed_base_sha=GIT_A,
                expected_product_contract_ref="a" * 64,
                at=TIME,
            )
        self.assertEqual(state, before)
        claimed = lifecycle.claim_feature(
            state,
            leaf_id="REQ-001",
            feature_id="FEAT-001",
            claimed_base_sha=GIT_A,
            expected_product_contract_ref=str(product["product_contract_id"]),
            expected_product_approval_ref=str(product_approval["approval_id"]),
            at=TIME,
        )
        feature = claimed["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(feature["product_contract_ref"], product["product_contract_id"])
        self.assertEqual(feature["product_contract_approval_ref"], product_approval["approval_id"])
        self.assertEqual(feature["contract_generation"], 0)

    def test_activation_checks_current_tuple_and_creates_complete_task_set_atomically(self) -> None:
        state, _, _, engineering, _ = active_delivery_state()
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(feature["delivery_plan_ref"], next(iter(state["delivery_plans"])))  # type: ignore[index]
        tasks = list(state["tasks"].values())  # type: ignore[index,union-attr]
        self.assertEqual([task["task_id"] for task in tasks], ["TASK-001"])
        self.assertEqual(tasks[0]["status"], "ready")
        self.assertEqual(tasks[0]["engineering_spec_ref"], engineering["engineering_spec_id"])
        self.assertEqual(tasks[0]["contract_generation"], 0)
        self.assertEqual(tasks[0]["evidence_strategy"], {
            "kind": "tdd", "argv": ["python3", "-m", "pytest"], "cwd": ".",
        })

    def test_activation_rejects_an_execution_strategy_without_a_canonical_runner(self) -> None:
        state, product, _, engineering, _, effective = approved_engineering_state()
        tasks = plan_tasks(product, engineering)
        tasks[0].update({
            "execution_mode": "static-check",
            "evidence_strategy": {"kind": "static-check", "check_ref": "ruff"},
        })
        plan = plan_compiler.compile_delivery_plan(
            dict(engineering, contract_generation=0), effective, tasks,
        )
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "canonical-execution-strategy-not-supported"):
            lifecycle.activate_delivery_plan(
                state,
                feature_id="FEAT-001",
                delivery_plan=plan,
                expected_generation=0,
                at=TIME,
            )
        self.assertEqual(state, before)

    def test_activation_rejects_hand_hashed_empty_plan_against_current_spec_and_approval(self) -> None:
        state, product, _, engineering, _, effective = approved_engineering_state()
        valid = plan_compiler.compile_delivery_plan(
            dict(engineering, contract_generation=0), effective, plan_tasks(product, engineering),
        )
        empty = deepcopy(valid)
        empty["tasks"] = []
        empty["interfaces"] = []
        rehash_plan(empty)
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "invalid-task-definitions"):
            lifecycle.activate_delivery_plan(
                state,
                feature_id="FEAT-001",
                delivery_plan=empty,
                expected_generation=0,
                at=TIME,
            )
        self.assertEqual(state, before)

    def test_open_change_request_requires_exact_current_scope_subject(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        current = {
            "product": feature["product_contract_ref"],
            "engineering": feature["engineering_spec_ref"],
            "delivery": feature["delivery_plan_ref"],
        }
        for scope, subject_ref in current.items():
            with self.subTest(scope=scope):
                opened = lifecycle.open_change_request(
                    state,
                    change_request_id=f"CR-{scope.upper()}",
                    feature_id="FEAT-001",
                    scope=scope,
                    subject_ref=str(subject_ref),
                    blocking=True,
                    reported_by="qa",
                    at=TIME,
                )
                self.assertEqual(opened["change_requests"][f"CR-{scope.upper()}"]["subject_ref"], subject_ref)  # type: ignore[index]
                with self.assertRaisesRegex(lifecycle.ReducerError, "change-request-subject-mismatch"):
                    lifecycle.open_change_request(
                        state,
                        change_request_id=f"CR-{scope.upper()}-WRONG",
                        feature_id="FEAT-001",
                        scope=scope,
                        subject_ref="f" * 64,
                        blocking=True,
                        reported_by="qa",
                        at=TIME,
                    )

        claimed, _, _ = claimed_state()
        with self.assertRaisesRegex(lifecycle.ReducerError, "change-request-current-subject-missing:engineering"):
            lifecycle.open_change_request(
                claimed,
                change_request_id="CR-NO-ENGINEERING",
                feature_id="FEAT-001",
                scope="engineering",
                subject_ref="f" * 64,
                blocking=True,
                reported_by="qa",
                at=TIME,
            )

    def test_reject_and_cancel_resolve_change_requests_and_release_blocking_delivery(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        plan_ref = state["features"]["FEAT-001"]["delivery_plan_ref"]  # type: ignore[index]
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-REJECT",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(plan_ref),
            blocking=True,
            reported_by="qa",
            at=TIME,
        )
        state = lifecycle.accept_change_request(
            state, change_request_id="CR-REJECT", accepted_by="architect", at=TIME,
        )
        state = lifecycle.reject_change_request(state, change_request_id="CR-REJECT", at=TIME)
        rejected = state["change_requests"]["CR-REJECT"]  # type: ignore[index]
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(rejected["status"], "rejected")
        self.assertIsNone(rejected["accepted_by"])
        self.assertIsNone(rejected["accepted_at"])
        self.assertNotIn("CR-REJECT", feature["active_change_request_refs"])
        self.assertIn("CR-REJECT", feature["resolved_change_request_refs"])
        state = lifecycle.transition_task(
            state,
            feature_id="FEAT-001",
            task_id="TASK-001",
            action="claim",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            at=TIME,
        )
        self.assertEqual(next(iter(state["tasks"].values()))["status"], "claimed")  # type: ignore[index,union-attr]

        fresh, _, _, _, _ = active_delivery_state()
        fresh_plan_ref = fresh["features"]["FEAT-001"]["delivery_plan_ref"]  # type: ignore[index]
        fresh = lifecycle.open_change_request(
            fresh,
            change_request_id="CR-CANCEL",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(fresh_plan_ref),
            blocking=True,
            reported_by="qa",
            at=TIME,
        )
        fresh = lifecycle.reduce(fresh, {
            "operation": "cancel_change_request", "change_request_id": "CR-CANCEL", "at": TIME,
        })
        self.assertEqual(fresh["change_requests"]["CR-CANCEL"]["status"], "cancelled")  # type: ignore[index]
        self.assertIn("CR-CANCEL", fresh["features"]["FEAT-001"]["resolved_change_request_refs"])  # type: ignore[index]

    def test_failed_evidence_is_historical_but_cannot_advance_or_verify_task(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        fence = lifecycle.current_fence(state, feature_id="FEAT-001")
        state = lifecycle.transition_task(
            state, feature_id="FEAT-001", task_id="TASK-001", action="claim", fence=fence, at=TIME,
        )
        state = lifecycle.transition_task(
            state,
            feature_id="FEAT-001",
            task_id="TASK-001",
            action="start",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            at=TIME,
        )
        state = record_task_evidence(state, passed=False)
        task = next(iter(state["tasks"].values()))  # type: ignore[index,union-attr]
        self.assertEqual(task["status"], "in_progress")
        failed_evidence = next(iter(state["evidence"].values()))  # type: ignore[index,union-attr]
        self.assertEqual(failed_evidence["evidence_format"], "execution-evidence-v2")
        self.assertEqual(failed_evidence["result"], "fail")
        failed_receipt_ref = failed_evidence["runner_receipt_ref"]
        self.assertIn(failed_receipt_ref, state["runner_receipts"])  # type: ignore[operator]
        state = lifecycle.transition_task(
            state,
            feature_id="FEAT-001",
            task_id="TASK-001",
            action="submit",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            at=TIME,
        )
        with self.assertRaisesRegex(lifecycle.ReducerError, "requires-current-passing-evidence"):
            lifecycle.transition_task(
                state,
                feature_id="FEAT-001",
                task_id="TASK-001",
                action="verify",
                fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                at=TIME,
            )
        state = record_task_evidence(state)
        state = lifecycle.transition_task(
            state,
            feature_id="FEAT-001",
            task_id="TASK-001",
            action="verify",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            at=TIME,
        )
        self.assertEqual(next(iter(state["tasks"].values()))["status"], "verified")  # type: ignore[index,union-attr]

    def test_product_definition_adoption_only_updates_future_claims_and_feature_adoption_requires_cr(self) -> None:
        state, product, _, _, _ = active_delivery_state()
        fence = lifecycle.current_fence(state, feature_id="FEAT-001")
        state = lifecycle.transition_task(
            state, feature_id="FEAT-001", task_id="TASK-001", action="claim", fence=fence, at=TIME,
        )
        state = lifecycle.transition_task(
            state, feature_id="FEAT-001", task_id="TASK-001", action="start",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"), at=TIME,
        )
        state = record_task_evidence(state)
        historical_evidence_refs = set(state["evidence"])  # type: ignore[arg-type]
        before_feature = deepcopy(state["features"]["FEAT-001"])  # type: ignore[index]

        replacement = product_contract(
            kind="patch",
            supersedes={"ref": product["product_contract_id"], "leaf_id": "REQ-001"},
        )
        state = lifecycle.start_product_definition(state, leaf_id="REQ-001", at=TIME)
        state = lifecycle.submit_product_contract(
            state,
            leaf_id="REQ-001",
            contract=replacement,
            components=product_components(),
            at=TIME,
        )
        state, replacement_approval = approve(
            state,
            subject_type="product_contract",
            subject_id=str(replacement["product_contract_id"]),
            policy=PRODUCT_POLICY,
            role="product-owner",
        )
        state = lifecycle.adopt_product_contract(
            state,
            leaf_id="REQ-001",
            product_contract_ref=str(replacement["product_contract_id"]),
            product_contract_approval_ref=str(replacement_approval["approval_id"]),
            at=TIME,
        )
        # ProductDefinition's new tuple becomes the source for future claims;
        # an already claimed Feature stays pinned until its own CR is applied.
        self.assertEqual(state["product_definitions"]["REQ-001"]["current_contract_ref"], replacement["product_contract_id"])  # type: ignore[index]
        self.assertEqual(state["features"]["FEAT-001"], before_feature)  # type: ignore[index]

        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-PRODUCT-001",
            feature_id="FEAT-001",
            scope="product",
            subject_ref=str(product["product_contract_id"]),
            blocking=True,
            reported_by="product-owner",
            at=TIME,
        )
        with self.assertRaisesRegex(lifecycle.ReducerError, "must-be-accepted"):
            lifecycle.adopt_feature_product_contract(
                state,
                feature_id="FEAT-001",
                change_request_id="CR-PRODUCT-001",
                product_contract_ref=str(replacement["product_contract_id"]),
                product_contract_approval_ref=str(replacement_approval["approval_id"]),
                expected_generation=0,
                at=TIME,
            )
        state = lifecycle.accept_change_request(
            state, change_request_id="CR-PRODUCT-001", accepted_by="product-owner", at=TIME,
        )
        with self.assertRaisesRegex(lifecycle.ReducerError, "stale-contract-generation"):
            lifecycle.adopt_feature_product_contract(
                state,
                feature_id="FEAT-001",
                change_request_id="CR-PRODUCT-001",
                product_contract_ref=str(replacement["product_contract_id"]),
                product_contract_approval_ref=str(replacement_approval["approval_id"]),
                expected_generation=1,
                at=TIME,
            )
        with self.assertRaisesRegex(lifecycle.ReducerError, "requires-feature-product-contract-adoption"):
            lifecycle.apply_change_request(
                state,
                change_request_id="CR-PRODUCT-001",
                resolution={
                    "resolution_kind": "delivery-invalidation-v1",
                    "resolution_ref": "f" * 64,
                    "semantics": "invalidate-delivery-plan",
                },
                expected_generation=0,
                at=TIME,
            )
        state = lifecycle.adopt_feature_product_contract(
            state,
            feature_id="FEAT-001",
            change_request_id="CR-PRODUCT-001",
            product_contract_ref=str(replacement["product_contract_id"]),
            product_contract_approval_ref=str(replacement_approval["approval_id"]),
            expected_generation=0,
            at=TIME,
        )
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(feature["status"], "active")
        self.assertEqual(feature["contract_generation"], 1)
        self.assertEqual(feature["product_contract_ref"], replacement["product_contract_id"])
        self.assertIsNone(feature["engineering_spec_ref"])
        self.assertIsNone(feature["delivery_plan_ref"])
        self.assertTrue(historical_evidence_refs.issubset(state["evidence"]))  # type: ignore[arg-type]
        self.assertEqual(next(iter(state["tasks"].values()))["status"], "superseded")  # type: ignore[index,union-attr]
        change_request = state["change_requests"]["CR-PRODUCT-001"]  # type: ignore[index]
        self.assertEqual(change_request["status"], "applied")
        self.assertEqual(change_request["resolution"]["product_contract_ref"], replacement["product_contract_id"])

    def test_stale_task_and_evidence_writes_are_rejected_after_invalidation(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        stale_fence = lifecycle.current_fence(state, feature_id="FEAT-001")
        state = lifecycle.invalidate_feature(state, feature_id="FEAT-001", reason="test-change", at=TIME)
        with self.assertRaisesRegex(lifecycle.ReducerError, "stale-contract-fence"):
            lifecycle.transition_task(
                state, feature_id="FEAT-001", task_id="TASK-001", action="claim", fence=stale_fence, at=TIME,
            )
        with self.assertRaisesRegex(lifecycle.ReducerError, "stale-contract-fence"):
            record_task_evidence(state, fence=stale_fence)

    def test_delivery_projection_is_read_only_and_hides_engineering_artifacts(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        before = deepcopy(state)
        projection = lifecycle.project_delivery_status(state, leaf_id="REQ-001")
        self.assertNotIn("engineering_spec_ref", projection["features"][0])
        self.assertEqual(projection["features"][0]["delivery_state"], "in_progress")
        projection["features"][0]["task_counts"]["ready"] = 999
        self.assertEqual(state, before)

    def test_feature_projection_is_minimal_sorted_and_deeply_detached(self) -> None:
        state, _, _, _, _ = reviewed_delivery_state()
        plan_ref = state["features"]["FEAT-001"]["delivery_plan_ref"]  # type: ignore[index]
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-RESOLVED",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(plan_ref),
            blocking=False,
            reported_by="qa",
            at=TIME,
        )
        state = lifecycle.cancel_change_request(state, change_request_id="CR-RESOLVED", at=TIME)
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-ACTIVE",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(plan_ref),
            blocking=False,
            reported_by="qa",
            at=TIME,
        )
        second = deepcopy(next(iter(state["tasks"].values())))  # type: ignore[index,union-attr]
        second.update({
            "task_instance_id": "0" * 64,
            "task_id": "TASK-000",
            "status": "ready",
            "depends_on": [],
            "trace_refs": [],
            "evidence_refs": [],
        })
        state["tasks"]["0" * 64] = second  # type: ignore[index]
        before = deepcopy(state)

        projection = lifecycle.project_feature_status(state, feature_id="FEAT-001")

        self.assertEqual(set(projection), {
            "feature_id", "leaf_id", "work_type", "status", "validation_status", "review_status",
            "review_attestation_ref", "review_evidence_refs",
            "current_fence", "active_change_request_refs", "resolved_change_request_refs",
            "release_evidence_ref", "tasks",
        })
        self.assertEqual(projection["current_fence"], lifecycle.current_fence(state, feature_id="FEAT-001"))
        self.assertEqual(projection["active_change_request_refs"], ["CR-ACTIVE"])
        self.assertEqual(projection["resolved_change_request_refs"], ["CR-RESOLVED"])
        self.assertEqual([task["task_id"] for task in projection["tasks"]], ["TASK-000", "TASK-001"])
        self.assertEqual(projection["review_evidence_refs"], projection["tasks"][1]["evidence_refs"])
        for task in projection["tasks"]:
            self.assertEqual(
                set(task),
                {"task_id", "status", "depends_on", "execution_mode", "evidence_strategy", "trace_refs", "evidence_refs"},
            )
        for forbidden in (
            "product_contracts", "profile_snapshots", "engineering_specs", "delivery_plans",
            "bundle_artifacts", "runner_receipts", "release_receipts",
        ):
            self.assertNotIn(forbidden, projection)

        projection["current_fence"]["delivery_plan_ref"] = "0" * 64
        projection["active_change_request_refs"].append("CR-MUTATED")
        projection["tasks"][0]["trace_refs"].append("PC:mutated")
        self.assertEqual(state, before)

    def test_feature_projection_rejects_missing_feature_without_mutation(self) -> None:
        state = lifecycle.empty_snapshot()
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "unknown-feature"):
            lifecycle.project_feature_status(state, feature_id="FEAT-MISSING")
        self.assertEqual(state, before)

    def test_hotfix_requires_approved_patch_contract(self) -> None:
        state, _, _ = approved_product_state(kind="feature")
        readiness = lifecycle.product_readiness(state, leaf_id="REQ-001", work_type="hotfix")
        self.assertFalse(readiness["ready"])
        self.assertIn("hotfix-requires-approved-patch-contract", readiness["reasons"])
        with self.assertRaisesRegex(lifecycle.ReducerError, "hotfix-requires-approved-patch-contract"):
            lifecycle.claim_feature(
                state, leaf_id="REQ-001", feature_id="FEAT-HOTFIX", claimed_base_sha=GIT_A,
                work_type="hotfix", at=TIME,
            )
        patch_state, _, _ = approved_product_state(kind="patch")
        claimed = lifecycle.claim_feature(
            patch_state, leaf_id="REQ-001", feature_id="FEAT-HOTFIX", claimed_base_sha=GIT_A,
            work_type="hotfix", at=TIME,
        )
        self.assertEqual(claimed["features"]["FEAT-HOTFIX"]["work_type"], "hotfix")  # type: ignore[index]

    def test_change_request_requires_typed_resolution_and_delivery_only_invalidation(self) -> None:
        state, _, _, engineering, _ = active_delivery_state()
        delivery_plan_ref = state["features"]["FEAT-001"]["delivery_plan_ref"]  # type: ignore[index]
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-001",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(delivery_plan_ref),
            blocking=True,
            reported_by="qa",
            at=TIME,
        )
        state = lifecycle.triage_change_request(state, change_request_id="CR-001", at=TIME)
        state = lifecycle.accept_change_request(state, change_request_id="CR-001", accepted_by="architect", at=TIME)
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "invalid-delivery-change-request-resolution-fields"):
            lifecycle.apply_change_request(
                state, change_request_id="CR-001", resolution={}, expected_generation=0, at=TIME,
            )
        self.assertEqual(state, before)
        state = lifecycle.apply_change_request(
            state,
            change_request_id="CR-001",
            resolution={
                "resolution_kind": "delivery-invalidation-v1",
                "resolution_ref": "f" * 64,
                "semantics": "invalidate-delivery-plan",
            },
            expected_generation=0,
            at=TIME,
        )
        self.assertEqual(state["features"]["FEAT-001"]["contract_generation"], 1)  # type: ignore[index]
        self.assertIsNone(state["features"]["FEAT-001"]["delivery_plan_ref"])  # type: ignore[index]
        self.assertEqual(state["features"]["FEAT-001"]["engineering_spec_ref"], engineering["engineering_spec_id"])  # type: ignore[index]
        change_request = state["change_requests"]["CR-001"]  # type: ignore[index]
        self.assertEqual(change_request["status"], "applied")
        self.assertEqual(change_request["resolution"]["semantics"], "invalidate-delivery-plan")
        tampered = deepcopy(state)
        tampered["change_requests"]["CR-001"]["resolution"] = {}  # type: ignore[index]
        with self.assertRaisesRegex(lifecycle.ReducerError, "invalid-delivery-change-request-resolution-fields"):
            lifecycle.apply_change_request(
                tampered,
                change_request_id="CR-001",
                resolution={
                    "resolution_kind": "delivery-invalidation-v1",
                    "resolution_ref": "f" * 64,
                    "semantics": "invalidate-delivery-plan",
                },
                expected_generation=1,
                at=TIME,
            )

    def test_engineering_change_request_adopts_the_explicit_replacement_tuple(self) -> None:
        state, product, product_approval, engineering, _ = active_delivery_state()
        profile, replacement = replacement_engineering_artifacts(product, product_approval, engineering)
        state = lifecycle.register_profile_snapshot(
            state, profile_snapshot=profile, components=profile_components(),
        )
        state = lifecycle.register_engineering_spec(
            state, engineering_spec=replacement, components=engineering_components(replacement=True),
        )
        state, replacement_approval = approve(
            state,
            subject_type="engineering_spec",
            subject_id=str(replacement["engineering_spec_id"]),
            policy=ENGINEERING_POLICY,
            role="architect",
        )
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-ENGINEERING-001",
            feature_id="FEAT-001",
            scope="engineering",
            subject_ref=str(engineering["engineering_spec_id"]),
            blocking=True,
            reported_by="architect",
            at=TIME,
        )
        state = lifecycle.accept_change_request(
            state, change_request_id="CR-ENGINEERING-001", accepted_by="architect", at=TIME,
        )
        state = lifecycle.apply_change_request(
            state,
            change_request_id="CR-ENGINEERING-001",
            resolution={
                "resolution_kind": "engineering-spec-replacement-v1",
                "engineering_spec_ref": replacement["engineering_spec_id"],
                "engineering_spec_approval_ref": replacement_approval["approval_id"],
                "semantics": "replace-engineering-spec",
            },
            expected_generation=0,
            at=TIME,
        )
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(feature["contract_generation"], 1)
        self.assertEqual(feature["engineering_spec_ref"], replacement["engineering_spec_id"])
        self.assertEqual(feature["engineering_spec_approval_ref"], replacement_approval["approval_id"])
        self.assertIsNone(feature["delivery_plan_ref"])
        change_request = state["change_requests"]["CR-ENGINEERING-001"]  # type: ignore[index]
        self.assertEqual(change_request["status"], "applied")
        self.assertEqual(change_request["resolution"]["engineering_spec_ref"], replacement["engineering_spec_id"])

    def test_open_blocking_change_request_stops_task_evidence_validation_and_review(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        delivery_plan_ref = state["features"]["FEAT-001"]["delivery_plan_ref"]  # type: ignore[index]
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-BLOCK-001",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(delivery_plan_ref),
            blocking=True,
            reported_by="qa",
            at=TIME,
        )
        fence = lifecycle.current_fence(state, feature_id="FEAT-001")
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "active-blocking-change-request"):
            lifecycle.transition_task(
                state, feature_id="FEAT-001", task_id="TASK-001", action="claim", fence=fence, at=TIME,
            )
        with self.assertRaisesRegex(lifecycle.ReducerError, "active-blocking-change-request"):
            record_task_evidence(state, fence=fence)
        with self.assertRaisesRegex(lifecycle.ReducerError, "active-blocking-change-request"):
            lifecycle.validate_feature(state, feature_id="FEAT-001", fence=fence, at=TIME)
        with self.assertRaisesRegex(lifecycle.ReducerError, "active-blocking-change-request"):
            lifecycle.review_feature(
                state, feature_id="FEAT-001", fence=fence,
                attestation=feature_review_attestation(state, evidence_refs=["a" * 64]), at=TIME,
            )
        self.assertEqual(state, before)

    def test_runner_receipt_is_derived_reverified_and_persisted_with_v2_evidence(self) -> None:
        state, _, _, _, _ = active_delivery_state()
        state = lifecycle.transition_task(
            state,
            feature_id="FEAT-001",
            task_id="TASK-001",
            action="claim",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            at=TIME,
        )
        state = lifecycle.transition_task(
            state,
            feature_id="FEAT-001",
            task_id="TASK-001",
            action="start",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            at=TIME,
        )
        forged = runner_record()
        forged["exit_code"] = 9
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "runner-evidence-hash-mismatch"):
            lifecycle.record_evidence(
                state,
                runner_record=forged,
                tested_sha=TESTED_SHA,
                feature_id="FEAT-001",
                task_id="TASK-001",
                fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                at=TIME,
            )
        self.assertEqual(state, before)

        accepted = record_task_evidence(state)
        evidence = next(iter(accepted["evidence"].values()))  # type: ignore[index,union-attr]
        receipt_ref = evidence["runner_receipt_ref"]
        receipt = accepted["runner_receipts"][receipt_ref]  # type: ignore[index]
        self.assertEqual(evidence["evidence_format"], "execution-evidence-v2")
        self.assertEqual(evidence["result"], "pass")
        self.assertEqual(evidence["tested_sha"], TESTED_SHA)
        self.assertEqual(receipt["receipt_id"], receipt_ref)
        self.assertEqual(receipt["runner_record"], runner_record())

        tampered = deepcopy(accepted)
        tampered["runner_receipts"][receipt_ref]["result"] = "fail"  # type: ignore[index]
        with self.assertRaisesRegex(lifecycle.ReducerError, "requires-current-passing-evidence"):
            lifecycle.transition_task(
                tampered,
                feature_id="FEAT-001",
                task_id="TASK-001",
                action="verify",
                fence=lifecycle.current_fence(tampered, feature_id="FEAT-001"),
                at=TIME,
            )

    def test_approval_revocation_invalidates_unshipped_delivery(self) -> None:
        state, _, _, engineering, engineering_approval = active_delivery_state()

        state, _ = revoke(
            state,
            subject_type="engineering_spec",
            subject_id=str(engineering["engineering_spec_id"]),
            previous=str(engineering_approval["approval_id"]),
            policy=ENGINEERING_POLICY,
            role="architect",
        )
        feature = state["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(feature["contract_generation"], 1)
        self.assertIsNone(feature["engineering_spec_ref"])
        self.assertIsNone(feature["delivery_plan_ref"])

    def test_approval_revocation_rejects_current_artifacts_referenced_by_shipped_feature(self) -> None:
        cases = (
            ("product_contract", PRODUCT_POLICY, "product-owner"),
            ("engineering_spec", ENGINEERING_POLICY, "architect"),
        )
        for subject_type, policy, role in cases:
            with self.subTest(subject_type=subject_type):
                state, product, product_approval, engineering, engineering_approval = reviewed_delivery_state()
                state = lifecycle.ship_feature(
                    state,
                    feature_id="FEAT-001",
                    fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                    release_receipt=release_receipt_for(state),
                    at=TIME,
                )
                if subject_type == "product_contract":
                    subject_id = str(product["product_contract_id"])
                    previous = str(product_approval["approval_id"])
                else:
                    subject_id = str(engineering["engineering_spec_id"])
                    previous = str(engineering_approval["approval_id"])
                before = deepcopy(state)
                with self.assertRaisesRegex(lifecycle.ReducerError, "cannot-revoke-approval-referenced-by-shipped-feature"):
                    revoke(
                        state,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        previous=previous,
                        policy=policy,
                        role=role,
                    )
                self.assertEqual(state, before)

    def test_ship_rejects_forged_or_stale_release_receipts_atomically(self) -> None:
        state, _, _, _, _ = reviewed_delivery_state()
        forged = release_receipt_for(state)
        forged["actual_release_artifact"]["artifact_ref"] = "registry.example/api:forged"  # type: ignore[index]
        before = deepcopy(state)
        with self.assertRaisesRegex(lifecycle.ReducerError, "receipt-content-hash-mismatch"):
            lifecycle.ship_feature(
                state,
                feature_id="FEAT-001",
                fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                release_receipt=forged,
                at=TIME,
            )
        self.assertEqual(state, before)

        stale_tuple = lifecycle.current_fence(state, feature_id="FEAT-001")
        stale_tuple["contract_generation"] = 1
        stale = release_receipt_for(state, tuple_value=stale_tuple)
        with self.assertRaisesRegex(lifecycle.ReducerError, "current-tuple-mismatch"):
            lifecycle.ship_feature(
                state,
                feature_id="FEAT-001",
                fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                release_receipt=stale,
                at=TIME,
            )
        self.assertEqual(state, before)

    def test_review_requires_the_current_feature_passing_evidence(self) -> None:
        state, _, _, _, _ = reviewed_delivery_state()
        before = deepcopy(state)
        with self.assertRaisesRegex(
            lifecycle.ReducerError, "review-evidence-does-not-match-current-feature-evidence",
        ):
            lifecycle.review_feature(
                state,
                feature_id="FEAT-001",
                fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                attestation=feature_review_attestation(state, evidence_refs=["a" * 64]),
                at=TIME,
            )
        self.assertEqual(state, before)

    def test_ship_feature_requires_current_validated_review_and_no_blocking_cr(self) -> None:
        active, _, _, _, _ = active_delivery_state()
        with self.assertRaisesRegex(lifecycle.ReducerError, "ship-requires-validated-feature"):
            lifecycle.ship_feature(
                active,
                feature_id="FEAT-001",
                fence=lifecycle.current_fence(active, feature_id="FEAT-001"),
                release_receipt=release_receipt_for(active),
                at=TIME,
            )

        state, _, _, engineering, _ = reviewed_delivery_state()
        delivery_plan_ref = state["features"]["FEAT-001"]["delivery_plan_ref"]  # type: ignore[index]
        state = lifecycle.open_change_request(
            state,
            change_request_id="CR-SHIP-BLOCK-001",
            feature_id="FEAT-001",
            scope="delivery",
            subject_ref=str(delivery_plan_ref),
            blocking=True,
            reported_by="qa",
            at=TIME,
        )
        with self.assertRaisesRegex(lifecycle.ReducerError, "blocking-change-request-prevents-release"):
            lifecycle.ship_feature(
                state,
                feature_id="FEAT-001",
                fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
                release_receipt=release_receipt_for(state),
                at=TIME,
            )

        state, _, _, engineering, _ = reviewed_delivery_state()
        state = lifecycle.register_requirement(state, leaf_id="REQ-001", status="ready")
        product_records_before = {
            "requirements": deepcopy(state["requirements"]),
            "product_definitions": deepcopy(state["product_definitions"]),
        }
        receipt = release_receipt_for(state)
        shipped = lifecycle.ship_feature(
            state,
            feature_id="FEAT-001",
            fence=lifecycle.current_fence(state, feature_id="FEAT-001"),
            release_receipt=receipt,
            at=TIME,
        )
        feature = shipped["features"]["FEAT-001"]  # type: ignore[index]
        self.assertEqual(feature["status"], "shipped")
        self.assertEqual(feature["release_evidence_ref"], receipt["receipt_id"])
        self.assertEqual(shipped["release_receipts"][receipt["receipt_id"]], receipt)  # type: ignore[index]
        self.assertEqual(shipped["claims"]["REQ-001"]["status"], "released")  # type: ignore[index]
        self.assertEqual(shipped["requirements"], product_records_before["requirements"])
        self.assertEqual(shipped["product_definitions"], product_records_before["product_definitions"])
        projection = lifecycle.project_delivery_status(shipped, leaf_id="REQ-001")
        self.assertEqual(projection["features"][0]["status"], "shipped")
        self.assertEqual(projection["features"][0]["delivery_state"], "shipped")
        self.assertNotIn("engineering_spec_ref", projection["features"][0])
        with self.assertRaisesRegex(lifecycle.ReducerError, "cannot-write-terminal-feature"):
            lifecycle.transition_task(
                shipped,
                feature_id="FEAT-001",
                task_id="TASK-001",
                action="claim",
                fence=lifecycle.current_fence(shipped, feature_id="FEAT-001"),
                at=TIME,
            )
        with self.assertRaisesRegex(lifecycle.ReducerError, "cannot-invalidate-terminal-feature"):
            lifecycle.invalidate_feature(shipped, feature_id="FEAT-001", reason="after-release", at=TIME)
        with self.assertRaisesRegex(lifecycle.ReducerError, "cannot-adopt-engineering-spec-for-terminal-feature"):
            lifecycle.adopt_engineering_spec(
                shipped,
                feature_id="FEAT-001",
                engineering_spec_ref=str(engineering["engineering_spec_id"]),
                engineering_spec_approval_ref=str(feature["engineering_spec_approval_ref"]),
                expected_generation=0,
                at=TIME,
            )


if __name__ == "__main__":
    unittest.main()
