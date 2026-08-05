#!/usr/bin/env python3
"""Deterministic contract tests for the durable dual-lifecycle local ledger."""
from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import contract_bundle
import dual_ledger
import plan_compiler


TIME = "2026-08-05T10:00:00+08:00"
SCRIPT = Path(__file__).with_name("dual_ledger.py")


def create_definition_intent(leaf_id: str = "REQ-001") -> dict[str, object]:
    return {
        "operation": "create_product_definition",
        "leaf_id": leaf_id,
        "source_request": leaf_id,
        "owner": "product-owner",
        "at": TIME,
    }


def authority_config(
    *, roles: list[str] | None = None, change_request_roles: list[str] | None = None,
) -> dict[str, object]:
    return {
        "authority_format": "dual-lifecycle-authority-v1",
        "authority_mode": "local-serial",
        "principal": {
            "authority_mode": "local-serial",
            "principal_ref": "principal:configured-owner",
            "roles": roles or ["product-owner", "architect"],
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
            "allowed_roles": change_request_roles or ["architect"],
            "min_authn_assurance": "configured-audit",
        },
    }


def product_contract() -> dict[str, object]:
    return contract_bundle.build_product_contract({
        "contract_kind": "feature",
        "leaf_id": "REQ-001",
        "source_request": "REQ-001",
        "components": {"product.md": "OUT", "behaviors.md": "SCN"},
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


def profile_snapshot(*, source_sha: str) -> dict[str, object]:
    return contract_bundle.snapshot_profile(
        b"# profile\n", feature_id="FEAT-001", source_sha=source_sha, created_at=TIME,
    )


def engineering_spec(
    product: dict[str, object], product_approval_ref: str, profile: dict[str, object], *, source_sha: str,
) -> dict[str, object]:
    return contract_bundle.build_engineering_spec({
        "feature_id": "FEAT-001",
        "product_contract_approval_ref": product_approval_ref,
        "specified_against_sha": source_sha,
        "implements_product_ids": ["SCN-001"],
        "engineering_criterion_ids": ["API-001"],
        "target_surfaces": ["server"],
        "components": {"technical.md": "API"},
        "supersedes": None,
        "created_by": "architect",
        "created_at": TIME,
    }, product, profile)


def delivery_plan(
    product: dict[str, object], engineering: dict[str, object], effective_approval: dict[str, object], *,
    evidence_argv: list[str],
) -> dict[str, object]:
    return plan_compiler.compile_delivery_plan(
        dict(engineering, contract_generation=0),
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
            "evidence_strategy": {"kind": "tdd", "argv": evidence_argv},
            "trace_refs": [
                f"PC:{product['product_contract_id']}#SCN-001",
                f"ES:{engineering['engineering_spec_id']}#API-001",
            ],
        }],
    )


def _concurrent_apply_worker(
    repo_root: str, leaf_id: str, idempotency_key: str, start: multiprocessing.synchronize.Event,
    output: multiprocessing.queues.Queue,
) -> None:
    """Top-level target so macOS's spawn multiprocessing context can import it."""
    start.wait(10)
    try:
        result = dual_ledger.DualLifecycleLedger(repo_root).apply(
            intent=create_definition_intent(leaf_id),
            expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
            idempotency_key=idempotency_key,
            timestamp=TIME,
        )
        output.put(("ok", result.next_snapshot_sha256))
    except Exception as exc:  # The parent asserts the exact one-winner shape.
        output.put(("error", type(exc).__name__, str(exc)))


class DualLifecycleLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.observations = tempfile.TemporaryDirectory()
        self.repo_root = self.temporary.name
        subprocess.run(["git", "init", "--quiet", self.repo_root], check=True)
        subprocess.run(["git", "-C", self.repo_root, "config", "user.email", "ledger@example.test"], check=True)
        subprocess.run(["git", "-C", self.repo_root, "config", "user.name", "Ledger Test"], check=True)
        Path(self.repo_root, "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", self.repo_root, "add", "README.md"], check=True)
        subprocess.run(["git", "-C", self.repo_root, "commit", "--quiet", "-m", "fixture"], check=True)
        self.git_sha = subprocess.run(
            ["git", "-C", self.repo_root, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.ledger = dual_ledger.DualLifecycleLedger(self.repo_root)
        self.planned_argv = [sys.executable, "-c", "print('ok')"]

    def tearDown(self) -> None:
        self.observations.cleanup()
        self.temporary.cleanup()

    def apply_initial(self, *, key: str = "request-1") -> dual_ledger.ApplyResult:
        return self.ledger.apply(
            intent=create_definition_intent(),
            expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
            idempotency_key=key,
            timestamp=TIME,
        )

    def write_authority(self, config: dict[str, object] | None = None) -> None:
        self.ledger.namespace_path.mkdir(parents=True, exist_ok=True)
        self.ledger.authority_path.write_bytes(
            json.dumps(config or authority_config()).encode("utf-8")
        )

    def apply_current(self, intent: dict[str, object], key: str) -> dual_ledger.ApplyResult:
        return self.ledger.apply(
            intent=intent,
            expected_snapshot_sha256=self.ledger.status().snapshot_sha256,
            idempotency_key=key,
            timestamp=TIME,
        )

    def prepare_active_feature(self, *, evidence_argv: list[str] | None = None) -> None:
        """Build a real approved Feature/Task through the public ledger path."""
        self.planned_argv = list(evidence_argv or [sys.executable, "-c", "print('ok')"])
        self.apply_current(create_definition_intent(), "setup-definition")
        self.apply_current(
            {"operation": "start_product_definition", "leaf_id": "REQ-001", "at": TIME},
            "setup-start-definition",
        )
        product = product_contract()
        self.apply_current({
            "operation": "submit_product_contract",
            "leaf_id": "REQ-001",
            "contract": product,
            "components": {"product.md": "OUT", "behaviors.md": "SCN"},
            "at": TIME,
        }, "setup-submit-product")
        self.write_authority()
        product_approved = self.apply_current({
            "operation": "request_approval",
            "subject_type": "product_contract",
            "subject_id": product["product_contract_id"],
            "decision": "approve",
            "decision_intent_ref": "approval:product:setup",
            "at": TIME,
        }, "setup-approve-product")
        product_approval = product_approved.event["intent"]["approval_record"]  # type: ignore[index]
        self.apply_current({
            "operation": "adopt_product_contract",
            "leaf_id": "REQ-001",
            "product_contract_ref": product["product_contract_id"],
            "product_contract_approval_ref": product_approval["approval_id"],
            "at": TIME,
        }, "setup-adopt-product")
        self.apply_current({
            "operation": "claim_feature",
            "leaf_id": "REQ-001",
            "feature_id": "FEAT-001",
            "claimed_base_sha": self.git_sha,
            "expected_product_contract_ref": product["product_contract_id"],
            "expected_product_approval_ref": product_approval["approval_id"],
            "at": TIME,
        }, "setup-claim-feature")
        profile = profile_snapshot(source_sha=self.git_sha)
        self.apply_current({
            "operation": "register_profile_snapshot",
            "profile_snapshot": profile,
            "components": {"PROFILE.md": "# profile\n"},
        }, "setup-register-profile")
        engineering = engineering_spec(
            product, str(product_approval["approval_id"]), profile, source_sha=self.git_sha,
        )
        self.apply_current({
            "operation": "register_engineering_spec",
            "engineering_spec": engineering,
            "components": {"technical.md": "API"},
        }, "setup-register-engineering")
        engineering_approved = self.apply_current({
            "operation": "request_approval",
            "subject_type": "engineering_spec",
            "subject_id": engineering["engineering_spec_id"],
            "decision": "approve",
            "decision_intent_ref": "approval:engineering:setup",
            "at": TIME,
        }, "setup-approve-engineering")
        engineering_approval = engineering_approved.event["intent"]["approval_record"]  # type: ignore[index]
        self.apply_current({
            "operation": "adopt_engineering_spec",
            "feature_id": "FEAT-001",
            "engineering_spec_ref": engineering["engineering_spec_id"],
            "engineering_spec_approval_ref": engineering_approval["approval_id"],
            "expected_generation": 0,
            "at": TIME,
        }, "setup-adopt-engineering")
        effective_approval = {
            **engineering_approval,
            "head_ref": engineering_approval["approval_id"],
            "head_decision": "approve",
        }
        self.apply_current({
            "operation": "activate_delivery_plan",
            "feature_id": "FEAT-001",
            "delivery_plan": delivery_plan(
                product, engineering, effective_approval, evidence_argv=self.planned_argv,
            ),
            "expected_generation": 0,
            "at": TIME,
        }, "setup-activate-plan")
        for action in ("claim", "start"):
            self.apply_current({
                "operation": "transition_task",
                "feature_id": "FEAT-001",
                "task_id": "TASK-001",
                "action": action,
                "fence": self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"],
                "at": TIME,
            }, f"setup-task-{action}")

    def execution_request(self, *, argv: list[str] | None = None, timeout: float = 0.25) -> dict[str, object]:
        return {
            "operation": "execute_task_evidence",
            "feature_id": "FEAT-001",
            "task_id": "TASK-001",
            "fence": self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"],
            "argv": list(argv or self.planned_argv),
            "cwd": ".",
            "timeout_seconds": timeout,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "tool_version": "ledger-test-runner",
            "at": TIME,
        }

    def review_request(self, *, decision: str = "approve", fence: dict[str, object] | None = None) -> dict[str, object]:
        projection = self.ledger.feature_projection(feature_id="FEAT-001")
        return {
            "operation": "submit_feature_review",
            "feature_id": "FEAT-001",
            "fence": fence if fence is not None else projection["current_fence"],
            "decision": decision,
            "evidence_refs": list(projection["review_evidence_refs"]),
            "rationale_ref": "4" * 64,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "at": TIME,
        }

    def register_product_contract(self, *, key: str = "register-product") -> tuple[dual_ledger.ApplyResult, dict[str, object]]:
        contract = product_contract()
        result = self.ledger.apply(
            intent={
                "operation": "register_product_contract",
                "contract": contract,
                "components": {"product.md": "OUT", "behaviors.md": "SCN"},
            },
            expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
            idempotency_key=key, timestamp=TIME,
        )
        return result, contract

    def test_initial_apply_persists_canonical_snapshot_and_bound_event(self) -> None:
        before = self.ledger.status()
        self.assertFalse(before.initialized)
        self.assertEqual(before.snapshot_sha256, dual_ledger.ABSENT_SNAPSHOT_SHA256)

        applied = self.apply_initial()

        self.assertFalse(applied.idempotent)
        self.assertEqual(applied.previous_snapshot_sha256, dual_ledger.ABSENT_SNAPSHOT_SHA256)
        self.assertEqual(applied.next_snapshot_sha256, applied.current_snapshot_sha256)
        self.assertEqual(applied.event["idempotency_key"], "request-1")
        self.assertEqual(applied.event["requested_intent"], create_definition_intent())
        self.assertEqual(applied.event["requested_intent_sha256"], applied.requested_intent_sha256)
        self.assertEqual(applied.event["intent"], create_definition_intent())
        self.assertEqual(applied.event["intent_sha256"], applied.intent_sha256)
        self.assertEqual(applied.requested_intent_sha256, applied.intent_sha256)
        self.assertEqual(applied.event["previous_snapshot_sha256"], dual_ledger.ABSENT_SNAPSHOT_SHA256)
        self.assertEqual(applied.event["next_snapshot_sha256"], applied.next_snapshot_sha256)
        self.assertEqual(applied.event["timestamp"], TIME)

        status = self.ledger.status()
        self.assertTrue(status.initialized)
        self.assertEqual(status.snapshot_sha256, applied.next_snapshot_sha256)
        self.assertEqual(status.event_count, 1)
        self.assertEqual(status.snapshot["product_definitions"]["REQ-001"]["draft_status"], "idle")  # type: ignore[index]
        raw = self.ledger.ledger_path.read_bytes()
        parsed = dual_ledger.parse_strict_json_bytes(raw, label="ledger", require_canonical=True)
        self.assertEqual(raw, dual_ledger.canonical_json_bytes(parsed))

    def test_cas_requires_exact_current_snapshot_and_absence_is_initial_only(self) -> None:
        initial = self.apply_initial()
        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "stale-snapshot-cas"):
            self.ledger.apply(
                intent={"operation": "start_product_definition", "leaf_id": "REQ-001", "at": TIME},
                expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
                idempotency_key="request-2", timestamp=TIME,
            )
        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "stale-snapshot-cas"):
            self.ledger.apply(
                intent={"operation": "start_product_definition", "leaf_id": "REQ-001", "at": TIME},
                expected_snapshot_sha256="a" * 64,
                idempotency_key="request-3", timestamp=TIME,
            )
        advanced = self.ledger.apply(
            intent={"operation": "start_product_definition", "leaf_id": "REQ-001", "at": TIME},
            expected_snapshot_sha256=initial.next_snapshot_sha256,
            idempotency_key="request-4", timestamp=TIME,
        )
        self.assertNotEqual(advanced.next_snapshot_sha256, initial.next_snapshot_sha256)
        self.assertEqual(self.ledger.status().event_count, 2)

    def test_idempotency_retry_after_later_event_returns_its_original_snapshot(self) -> None:
        first = self.apply_initial(key="stable-request")
        later = self.ledger.apply(
            intent={"operation": "start_product_definition", "leaf_id": "REQ-001", "at": TIME},
            expected_snapshot_sha256=first.next_snapshot_sha256,
            idempotency_key="later-request", timestamp=TIME,
        )
        replay = self.ledger.apply(
            intent=create_definition_intent(),
            # Retrying a lost response intentionally reuses the original CAS
            # value; the existing event is returned without another reduction.
            expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
            idempotency_key="stable-request", timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(replay.idempotent)
        self.assertEqual(replay.next_snapshot_sha256, first.next_snapshot_sha256)
        self.assertEqual(replay.current_snapshot_sha256, first.current_snapshot_sha256)
        self.assertEqual(replay.event, first.event)
        self.assertEqual(replay.event_count, 1)
        self.assertEqual(replay.snapshot, first.snapshot)
        self.assertEqual(replay.snapshot["product_definitions"]["REQ-001"]["draft_status"], "idle")  # type: ignore[index]
        self.assertEqual(self.ledger.status().snapshot_sha256, later.next_snapshot_sha256)
        self.assertEqual(self.ledger.status().snapshot["product_definitions"]["REQ-001"]["draft_status"], "shaping")  # type: ignore[index]
        self.assertEqual(self.ledger.status().event_count, 2)
        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "idempotency-key-intent-mismatch"):
            self.ledger.apply(
                intent=create_definition_intent("REQ-002"),
                expected_snapshot_sha256=later.next_snapshot_sha256,
                idempotency_key="stable-request", timestamp=TIME,
            )

    def test_replay_reconstructs_events_and_rejects_corrupt_snapshot_cache(self) -> None:
        initial = self.apply_initial()
        self.ledger.apply(
            intent={"operation": "start_product_definition", "leaf_id": "REQ-001", "at": TIME},
            expected_snapshot_sha256=initial.next_snapshot_sha256,
            idempotency_key="request-2", timestamp=TIME,
        )
        self.assertEqual(self.ledger.replay_snapshot(), self.ledger.snapshot())

        wrapper = dual_ledger.parse_strict_json_bytes(
            self.ledger.ledger_path.read_bytes(), label="ledger", require_canonical=True,
        )
        self.assertIsInstance(wrapper, dict)
        wrapper["snapshot"]["product_definitions"]["REQ-001"]["draft_status"] = "idle"  # type: ignore[index]
        wrapper["snapshot_sha256"] = dual_ledger.snapshot_sha256(wrapper["snapshot"])  # type: ignore[index]
        self.ledger.ledger_path.write_bytes(dual_ledger.canonical_json_bytes(wrapper))

        with self.assertRaisesRegex(dual_ledger.LedgerIntegrityError, "ledger-replay-final-snapshot-mismatch"):
            self.ledger.status()
        with self.assertRaisesRegex(dual_ledger.LedgerIntegrityError, "ledger-replay-final-snapshot-mismatch"):
            self.ledger.replay_snapshot()

    def test_strict_parser_rejects_duplicate_keys_and_noncanonical_ledger_bytes(self) -> None:
        with self.assertRaisesRegex(dual_ledger.LedgerParseError, "duplicate-json-key"):
            dual_ledger.parse_strict_json_bytes(b'{"a":1,"a":2}', label="intent")
        self.apply_initial()
        self.ledger.ledger_path.write_bytes(self.ledger.ledger_path.read_bytes().rstrip(b"\n") + b" \n")
        with self.assertRaisesRegex(dual_ledger.LedgerParseError, "non-canonical-ledger-json"):
            self.ledger.status()

    def test_concurrent_initial_cas_has_exactly_one_winner(self) -> None:
        context = multiprocessing.get_context("spawn")
        start = context.Event()
        output = context.Queue()
        workers = [
            context.Process(
                target=_concurrent_apply_worker,
                args=(self.repo_root, "REQ-A", "concurrent-a", start, output),
            ),
            context.Process(
                target=_concurrent_apply_worker,
                args=(self.repo_root, "REQ-B", "concurrent-b", start, output),
            ),
        ]
        for worker in workers:
            worker.start()
        start.set()
        for worker in workers:
            worker.join(15)
            self.assertEqual(worker.exitcode, 0)
        outcomes = [output.get(timeout=5) for _ in workers]
        successes = [outcome for outcome in outcomes if outcome[0] == "ok"]
        failures = [outcome for outcome in outcomes if outcome[0] == "error"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][1], "LedgerConflictError")
        self.assertIn("stale-snapshot-cas", failures[0][2])
        self.assertEqual(self.ledger.status().event_count, 1)

    def test_request_approval_persists_public_and_config_derived_replay_intents(self) -> None:
        registered, contract = self.register_product_contract()
        self.write_authority()
        request = {
            "operation": "request_approval",
            "subject_type": "product_contract",
            "subject_id": contract["product_contract_id"],
            "decision": "approve",
            "decision_intent_ref": "approval:product:one",
            "at": TIME,
        }
        approved = self.ledger.apply(
            intent=request, expected_snapshot_sha256=registered.next_snapshot_sha256,
            idempotency_key="request-product-approval", timestamp=TIME,
        )
        canonical = approved.event["intent"]
        self.assertEqual(approved.event["requested_intent"], request)
        self.assertEqual(approved.event["requested_intent_sha256"], approved.requested_intent_sha256)
        self.assertEqual(canonical["operation"], "apply_approval")  # type: ignore[index]
        self.assertEqual(canonical["at"], TIME)  # type: ignore[index]
        record = canonical["approval_record"]  # type: ignore[index]
        self.assertEqual(record["principal_ref"], "principal:configured-owner")  # type: ignore[index]
        self.assertEqual(record["principal_role"], "product-owner")  # type: ignore[index]
        self.assertEqual(record["previous_approval_ref"], None)  # type: ignore[index]
        self.assertEqual(canonical["authorization_policy"]["policy_id"], "product-contract-approval-v1")  # type: ignore[index]
        self.assertNotEqual(approved.requested_intent_sha256, approved.intent_sha256)

        revoke_request = {
            **request,
            "decision": "revoke",
            "decision_intent_ref": "approval:product:two",
        }
        revoked = self.ledger.apply(
            intent=revoke_request, expected_snapshot_sha256=approved.next_snapshot_sha256,
            idempotency_key="request-product-revoke", timestamp=TIME,
        )
        revoke_record = revoked.event["intent"]["approval_record"]  # type: ignore[index]
        self.assertEqual(revoke_record["previous_approval_ref"], record["approval_id"])  # type: ignore[index]

        # A retry must compare the public request and return the original event
        # without reading a changed future authority configuration.
        changed = authority_config(roles=["architect"], change_request_roles=["architect"])
        self.write_authority(changed)
        retry = self.ledger.apply(
            intent=request, expected_snapshot_sha256=registered.next_snapshot_sha256,
            idempotency_key="request-product-approval", timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(retry.idempotent)
        self.assertEqual(retry.event, approved.event)
        self.assertEqual(retry.snapshot, approved.snapshot)
        self.assertEqual(self.ledger.replay_snapshot(), self.ledger.snapshot())
        # Omitted and explicit-empty resolve lists produce the same reducer
        # effect, but are distinct public requests and may not reuse a key.
        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "idempotency-key-intent-mismatch"):
            self.ledger.apply(
                intent={**request, "resolves_change_requests": []},
                expected_snapshot_sha256=registered.next_snapshot_sha256,
                idempotency_key="request-product-approval", timestamp=TIME,
            )

    def test_public_authority_requests_reject_injection_and_unsafe_authority_files(self) -> None:
        registered, contract = self.register_product_contract()
        request = {
            "operation": "request_approval",
            "subject_type": "product_contract",
            "subject_id": contract["product_contract_id"],
            "decision": "approve",
            "decision_intent_ref": "approval:product:one",
            "at": TIME,
        }
        with self.assertRaisesRegex(dual_ledger.LedgerAuthorityError, "authority-config-missing"):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=registered.next_snapshot_sha256,
                idempotency_key="missing-authority", timestamp=TIME,
            )
        forged_predecessor = {**request, "previous_approval_ref": "a" * 64}
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "public-request-cannot-supply"):
            self.ledger.apply(
                intent=forged_predecessor, expected_snapshot_sha256=registered.next_snapshot_sha256,
                idempotency_key="forged-predecessor", timestamp=TIME,
            )
        forged_principal = {**request, "principal_ref": "principal:forged"}
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "public-request-cannot-supply"):
            self.ledger.apply(
                intent=forged_principal, expected_snapshot_sha256=registered.next_snapshot_sha256,
                idempotency_key="forged-principal", timestamp=TIME,
            )

        self.ledger.namespace_path.mkdir(parents=True, exist_ok=True)
        self.ledger.authority_path.mkdir()
        with self.assertRaisesRegex(dual_ledger.LedgerAuthorityError, "regular-file"):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=registered.next_snapshot_sha256,
                idempotency_key="directory-authority", timestamp=TIME,
            )
        self.ledger.authority_path.rmdir()
        target = Path(self.repo_root) / "authority-target.json"
        target.write_bytes(json.dumps(authority_config()).encode("utf-8"))
        self.ledger.authority_path.symlink_to(target)
        with self.assertRaisesRegex(dual_ledger.LedgerAuthorityError, "cannot-be-symlink"):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=registered.next_snapshot_sha256,
                idempotency_key="symlink-authority", timestamp=TIME,
            )

    def test_public_apply_rejects_raw_internal_operations_and_decision_actor_injection(self) -> None:
        for operation in (
            "apply_approval", "accept_change_request", "reject_change_request", "cancel_change_request",
            "record_evidence", "review_feature", "ship_feature",
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(
                dual_ledger.LedgerTransitionError, "raw-internal-operation-is-not-public",
            ):
                self.ledger.apply(
                    intent={"operation": operation},
                    expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
                    idempotency_key=f"raw-{operation}", timestamp=TIME,
                )
        self.ledger.status()  # Establish the namespace without an authority read.
        self.write_authority()
        forged_actor = {
            "operation": "decide_change_request",
            "change_request_id": "CR-001",
            "decision": "accept",
            "actor": "forged",
            "at": TIME,
        }
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "invalid-decide-change-request-fields"):
            self.ledger.apply(
                intent=forged_actor, expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
                idempotency_key="forged-change-actor", timestamp=TIME,
            )

        denied = authority_config(roles=["architect"], change_request_roles=["product-owner"])
        self.write_authority(copy.deepcopy(denied))
        with self.assertRaisesRegex(dual_ledger.LedgerAuthorityError, "authority-request-rejected"):
            self.ledger.apply(
                intent={
                    "operation": "decide_change_request",
                    "change_request_id": "CR-002",
                    "decision": "reject",
                    "at": TIME,
                },
                expected_snapshot_sha256=dual_ledger.ABSENT_SNAPSHOT_SHA256,
                idempotency_key="denied-change-decision", timestamp=TIME,
            )
        self.write_authority()
        public_decision = {
            "operation": "decide_change_request",
            "change_request_id": "CR-001",
            "decision": "accept",
            "at": TIME,
        }
        # The real reducer correctly rejects an unknown CR.  Exercise only the
        # public-to-canonical transport step here, without persisting a fake CR.
        with self.ledger._locked(exclusive=True):
            canonical = self.ledger._canonicalize_requested_intent_locked(
                public_decision, dual_ledger.lifecycle_reducer.empty_snapshot(),
            )
        self.assertEqual(canonical["operation"], "accept_change_request")
        self.assertEqual(canonical["accepted_by"], "architect")

    def test_execute_task_evidence_runs_canonical_argv_once_and_replays_fractional_timeout(self) -> None:
        marker = Path(self.observations.name, "execution-count.txt")
        argv = ["/usr/bin/touch", str(marker)]
        self.prepare_active_feature(evidence_argv=argv)
        request = self.execution_request(argv=argv, timeout=0.02)
        expected = self.ledger.status().snapshot_sha256
        applied = self.ledger.apply(
            intent=request, expected_snapshot_sha256=expected,
            idempotency_key="canonical-execution", timestamp=TIME,
        )
        self.assertFalse(applied.idempotent)
        canonical = applied.event["intent"]
        self.assertEqual(canonical["operation"], "record_evidence")  # type: ignore[index]
        self.assertEqual(canonical["tested_sha"], canonical["runner_record"]["code_sha"])  # type: ignore[index]
        self.assertEqual(canonical["runner_record"]["timeout_seconds"], 0.02)  # type: ignore[index]
        self.assertTrue(marker.exists())
        self.assertFalse(self.ledger.execution_journal_path.exists())
        self.assertEqual(len(applied.snapshot["runner_receipts"]), 1)  # type: ignore[arg-type]
        evidence = next(iter(applied.snapshot["evidence"].values()))  # type: ignore[union-attr]
        self.assertEqual(evidence["result"], "pass")

        retry = self.ledger.apply(
            intent=request, expected_snapshot_sha256=expected,
            idempotency_key="canonical-execution", timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(retry.idempotent)
        self.assertEqual(retry.event, applied.event)
        self.assertTrue(marker.exists())
        self.assertEqual(self.ledger.replay_snapshot(), self.ledger.snapshot())
        self.assertTrue(marker.exists())

        for field, value in (
            ("result", "pass"), ("receipt", {}), ("tested_sha", "f" * 64), ("code_sha", "f" * 64),
        ):
            with self.subTest(forbidden=field), self.assertRaisesRegex(
                dual_ledger.LedgerTransitionError, "invalid-execute-task-evidence-fields",
            ):
                self.ledger.apply(
                    intent={**request, field: value},
                    expected_snapshot_sha256=applied.next_snapshot_sha256,
                    idempotency_key=f"forged-{field}", timestamp=TIME,
                )
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "shell-argv-not-allowed"):
            self.ledger.apply(
                intent={**request, "argv": ["/bin/sh", "-c", "echo forged"]},
                expected_snapshot_sha256=applied.next_snapshot_sha256,
                idempotency_key="shell-command", timestamp=TIME,
            )

        escape = Path(self.repo_root, "escape")
        escape.symlink_to(Path(self.repo_root).parent, target_is_directory=True)
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "symlink-cwd-is-not-allowed"):
            self.ledger.apply(
                intent={**request, "cwd": "escape"},
                expected_snapshot_sha256=applied.next_snapshot_sha256,
                idempotency_key="escaped-cwd", timestamp=TIME,
            )
        self.assertTrue(marker.exists())

    def test_failed_task_runner_is_durable_observed_evidence_and_clears_journal(self) -> None:
        argv = [sys.executable, "-c", "raise SystemExit(7)"]
        self.prepare_active_feature(evidence_argv=argv)
        request = self.execution_request(argv=argv, timeout=0.02)
        applied = self.ledger.apply(
            intent=request,
            expected_snapshot_sha256=self.ledger.status().snapshot_sha256,
            idempotency_key="failed-task-runner", timestamp=TIME,
        )
        evidence = next(iter(applied.snapshot["evidence"].values()))  # type: ignore[union-attr]
        self.assertEqual(evidence["result"], "fail")
        self.assertFalse(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.replay_snapshot(), self.ledger.snapshot())

    def test_task_evidence_requires_the_plan_declared_command_before_execution(self) -> None:
        self.prepare_active_feature()
        marker = Path(self.observations.name, "forged-command-ran")
        request = self.execution_request(argv=["/usr/bin/touch", str(marker)], timeout=0.25)
        before = self.ledger.status()
        with self.assertRaisesRegex(
            dual_ledger.LedgerTransitionError, "evidence-command-does-not-match-delivery-plan",
        ):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=before.snapshot_sha256,
                idempotency_key="forged-task-command", timestamp=TIME,
            )
        self.assertFalse(marker.exists())
        self.assertFalse(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.status().snapshot_sha256, before.snapshot_sha256)

    def test_worktree_mutation_during_task_execution_is_not_recorded(self) -> None:
        argv = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('README.md').write_text('mutated\\n', encoding='utf-8')",
        ]
        self.prepare_active_feature(evidence_argv=argv)
        before = self.ledger.status()
        with self.assertRaisesRegex(
            dual_ledger.LedgerTransitionError, "worktree-code-changed-during-canonical-execution",
        ):
            self.ledger.apply(
                intent=self.execution_request(argv=argv, timeout=0.25),
                expected_snapshot_sha256=before.snapshot_sha256,
                idempotency_key="mutated-task-worktree", timestamp=TIME,
            )
        self.assertTrue(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.status().snapshot_sha256, before.snapshot_sha256)
        self.assertEqual(self.ledger.snapshot()["runner_receipts"], {})

    def test_crash_window_journal_blocks_same_and_unrelated_writes_without_rerun(self) -> None:
        marker = Path(self.observations.name, "crash-count.txt")
        argv = ["/usr/bin/touch", str(marker)]
        self.prepare_active_feature(evidence_argv=argv)
        request = self.execution_request(argv=argv, timeout=0.02)
        expected = self.ledger.status().snapshot_sha256
        with mock.patch.object(self.ledger, "_write_locked", side_effect=dual_ledger.LedgerError("simulated-crash")):
            with self.assertRaisesRegex(dual_ledger.LedgerError, "simulated-crash"):
                self.ledger.apply(
                    intent=request, expected_snapshot_sha256=expected,
                    idempotency_key="crash-window", timestamp=TIME,
                )
        self.assertTrue(marker.exists())
        journal = dual_ledger.parse_strict_json_bytes(
            self.ledger.execution_journal_path.read_bytes(), label="execution-journal", require_canonical=True,
        )
        self.assertEqual(journal["idempotency_key"], "crash-window")  # type: ignore[index]
        self.assertEqual(journal["requested_intent_sha256"], dual_ledger.sha256_json(request))  # type: ignore[index]

        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "execution-recovery-required-for-idempotency-key"):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=expected,
                idempotency_key="crash-window", timestamp=TIME,
            )
        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "another-execution-recovery-required"):
            self.ledger.apply(
                intent={"operation": "transition_task", "feature_id": "FEAT-001", "task_id": "TASK-001",
                        "action": "block", "fence": request["fence"], "at": TIME},
                expected_snapshot_sha256=expected,
                idempotency_key="unrelated-write", timestamp=TIME,
            )
        self.assertTrue(marker.exists())

    def test_same_key_retry_cleans_journal_after_a_durable_event_without_rerunning(self) -> None:
        marker = Path(self.observations.name, "post-commit-cleanup-count.txt")
        argv = ["/usr/bin/touch", str(marker)]
        self.prepare_active_feature(evidence_argv=argv)
        request = self.execution_request(argv=argv, timeout=0.02)
        expected = self.ledger.status().snapshot_sha256
        events_before = self.ledger.status().event_count
        with mock.patch.object(
            self.ledger,
            "_clear_execution_journal_locked",
            side_effect=dual_ledger.LedgerError("simulated-post-commit-crash"),
        ):
            with self.assertRaisesRegex(dual_ledger.LedgerError, "simulated-post-commit-crash"):
                self.ledger.apply(
                    intent=request, expected_snapshot_sha256=expected,
                    idempotency_key="post-commit-cleanup", timestamp=TIME,
                )
        self.assertTrue(marker.exists())
        self.assertTrue(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.status().event_count, events_before + 1)

        retry = self.ledger.apply(
            intent=request, expected_snapshot_sha256=expected,
            idempotency_key="post-commit-cleanup", timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(retry.idempotent)
        self.assertFalse(self.ledger.execution_journal_path.exists())
        self.assertTrue(marker.exists())
        self.assertEqual(self.ledger.status().event_count, events_before + 1)

    def test_public_review_requires_the_current_passing_evidence_refs(self) -> None:
        self.prepare_active_feature()
        self.ledger.apply(
            intent=self.execution_request(timeout=0.02),
            expected_snapshot_sha256=self.ledger.status().snapshot_sha256,
            idempotency_key="review-evidence-prepare", timestamp=TIME,
        )
        fence = self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"]
        self.apply_current({
            "operation": "transition_task", "feature_id": "FEAT-001", "task_id": "TASK-001",
            "action": "verify", "fence": fence, "at": TIME,
        }, "review-evidence-verify")
        fence = self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"]
        self.apply_current({
            "operation": "validate_feature", "feature_id": "FEAT-001", "fence": fence, "at": TIME,
        }, "review-evidence-validate")
        bad_request = {**self.review_request(), "evidence_refs": ["f" * 64]}
        before = self.ledger.status()
        with self.assertRaisesRegex(
            dual_ledger.LedgerTransitionError, "review-evidence-does-not-match-current-feature-evidence",
        ):
            self.ledger.apply(
                intent=bad_request, expected_snapshot_sha256=before.snapshot_sha256,
                idempotency_key="review-wrong-evidence", timestamp=TIME,
            )
        self.assertEqual(self.ledger.status().snapshot_sha256, before.snapshot_sha256)
        self.assertEqual(self.ledger.snapshot()["review_attestations"], {})

    def prepare_feature_for_release(self) -> None:
        evidence = self.ledger.apply(
            intent=self.execution_request(timeout=0.02),
            expected_snapshot_sha256=self.ledger.status().snapshot_sha256,
            idempotency_key="release-prepare-evidence", timestamp=TIME,
        )
        fence = self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"]
        self.apply_current({
            "operation": "transition_task", "feature_id": "FEAT-001", "task_id": "TASK-001",
            "action": "verify", "fence": fence, "at": TIME,
        }, "release-prepare-verify")
        fence = self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"]
        self.apply_current({
            "operation": "validate_feature", "feature_id": "FEAT-001", "fence": fence, "at": TIME,
        }, "release-prepare-validate")
        fence = self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"]
        self.apply_current({
            **self.review_request(fence=fence),
        }, "release-prepare-review")
        self.assertEqual(evidence.snapshot["features"]["FEAT-001"]["status"], "active")  # type: ignore[index]

    def test_publish_feature_derives_artifact_hash_and_release_receipt_without_rerun(self) -> None:
        self.prepare_active_feature()
        self.prepare_feature_for_release()
        artifact = Path(self.repo_root, "dist", "release.bin")
        artifact.parent.mkdir()
        artifact.write_bytes(b"release-bytes")
        marker = Path(self.observations.name, "publish-count.txt")
        request = {
            "operation": "publish_feature",
            "feature_id": "FEAT-001",
            "fence": self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"],
            "release_target": {
                "environment": "production", "target_type": "container", "target_ref": "cluster/prod/api",
            },
            "actual_release_artifact": {"artifact_type": "oci-image", "artifact_ref": "registry.example/api:1"},
            "artifact_path": "dist/release.bin",
            "argv": ["/usr/bin/touch", str(marker)],
            "cwd": ".",
            "timeout_seconds": 0.02,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "tool_version": "ledger-test-publisher",
            "at": TIME,
        }
        expected = self.ledger.status().snapshot_sha256
        published = self.ledger.apply(
            intent=request, expected_snapshot_sha256=expected,
            idempotency_key="publish-feature", timestamp=TIME,
        )
        self.assertEqual(published.snapshot["features"]["FEAT-001"]["status"], "shipped")  # type: ignore[index]
        self.assertFalse(self.ledger.execution_journal_path.exists())
        receipt = next(iter(published.snapshot["release_receipts"].values()))  # type: ignore[union-attr]
        self.assertEqual(receipt["actual_release_artifact"]["artifact_sha256"], hashlib.sha256(b"release-bytes").hexdigest())
        self.assertEqual(receipt["tested_code_sha256"], receipt["runner_record"]["code_sha"])
        self.assertTrue(marker.exists())
        retry = self.ledger.apply(
            intent=request, expected_snapshot_sha256=expected,
            idempotency_key="publish-feature", timestamp="2026-08-06T10:00:00+08:00",
        )
        self.assertTrue(retry.idempotent)
        self.assertTrue(marker.exists())
        self.assertEqual(self.ledger.replay_snapshot(), self.ledger.snapshot())
        with self.assertRaisesRegex(dual_ledger.LedgerIntegrityError, "canonical-runner-cwd-mismatch"):
            dual_ledger._validate_requested_to_replay_pair(  # type: ignore[attr-defined]
                {**request, "artifact_path": "README.md"}, published.event["intent"],
            )

        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "invalid-publish-feature-fields"):
            self.ledger.apply(
                intent={**request, "release_sha": self.git_sha},
                expected_snapshot_sha256=published.next_snapshot_sha256,
                idempotency_key="forged-release-sha", timestamp=TIME,
            )
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "invalid-actual-release-artifact-fields"):
            self.ledger.apply(
                intent={
                    **request,
                    "actual_release_artifact": {
                        **request["actual_release_artifact"], "artifact_sha256": "f" * 64,
                    },
                },
                expected_snapshot_sha256=published.next_snapshot_sha256,
                idempotency_key="forged-artifact-sha", timestamp=TIME,
            )

    def test_failed_publish_keeps_recovery_journal_and_does_not_ship(self) -> None:
        self.prepare_active_feature()
        self.prepare_feature_for_release()
        artifact = Path(self.repo_root, "dist", "release.bin")
        artifact.parent.mkdir()
        artifact.write_bytes(b"release-bytes")
        request = {
            "operation": "publish_feature",
            "feature_id": "FEAT-001",
            "fence": self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"],
            "release_target": {
                "environment": "production", "target_type": "container", "target_ref": "cluster/prod/api",
            },
            "actual_release_artifact": {"artifact_type": "oci-image", "artifact_ref": "registry.example/api:1"},
            "artifact_path": "dist/release.bin",
            "argv": [sys.executable, "-c", "raise SystemExit(7)"],
            "cwd": ".",
            "timeout_seconds": 0.02,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "tool_version": "ledger-test-publisher",
            "at": TIME,
        }
        expected = self.ledger.status().snapshot_sha256
        with self.assertRaisesRegex(dual_ledger.LedgerTransitionError, "release-runner-not-successful"):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=expected,
                idempotency_key="failed-publish", timestamp=TIME,
            )
        self.assertTrue(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.snapshot()["features"]["FEAT-001"]["status"], "validated")  # type: ignore[index]
        with self.assertRaisesRegex(dual_ledger.LedgerConflictError, "execution-recovery-required-for-idempotency-key"):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=expected,
                idempotency_key="failed-publish", timestamp=TIME,
            )

    def test_worktree_mutation_during_publish_is_not_recorded(self) -> None:
        self.prepare_active_feature()
        self.prepare_feature_for_release()
        artifact = Path(self.repo_root, "dist", "release.bin")
        artifact.parent.mkdir()
        artifact.write_bytes(b"release-bytes")
        request = {
            "operation": "publish_feature",
            "feature_id": "FEAT-001",
            "fence": self.ledger.feature_projection(feature_id="FEAT-001")["current_fence"],
            "release_target": {
                "environment": "production", "target_type": "container", "target_ref": "cluster/prod/api",
            },
            "actual_release_artifact": {"artifact_type": "oci-image", "artifact_ref": "registry.example/api:1"},
            "artifact_path": "dist/release.bin",
            "argv": [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('README.md').write_text('mutated\\n', encoding='utf-8')",
            ],
            "cwd": ".",
            "timeout_seconds": 0.25,
            "policy_manifest_ref": "1" * 64,
            "context_manifest_ref": "2" * 64,
            "tool_version": "ledger-test-publisher",
            "at": TIME,
        }
        before = self.ledger.status()
        with self.assertRaisesRegex(
            dual_ledger.LedgerTransitionError, "worktree-code-changed-during-canonical-execution",
        ):
            self.ledger.apply(
                intent=request, expected_snapshot_sha256=before.snapshot_sha256,
                idempotency_key="mutated-publish-worktree", timestamp=TIME,
            )
        self.assertTrue(self.ledger.execution_journal_path.exists())
        self.assertEqual(self.ledger.status().snapshot_sha256, before.snapshot_sha256)
        self.assertEqual(self.ledger.snapshot()["release_receipts"], {})

    def test_cli_supports_status_apply_and_product_projection(self) -> None:
        status = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", self.repo_root, "status"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertFalse(json.loads(status.stdout)["initialized"])
        applied = subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo", self.repo_root, "apply",
                "--expected-sha", dual_ledger.ABSENT_SNAPSHOT_SHA256,
                "--idempotency-key", "cli-request", "--intent-json", json.dumps(create_definition_intent()),
                "--timestamp", TIME,
            ],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        current_sha = json.loads(applied.stdout)["next_snapshot_sha256"]
        self.assertEqual(current_sha, self.ledger.status().snapshot_sha256)
        projection = subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo", self.repo_root,
                "product-projection", "--leaf-id", "REQ-001",
            ],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(projection.returncode, 0, projection.stderr)
        self.assertEqual(json.loads(projection.stdout)["leaf_id"], "REQ-001")


if __name__ == "__main__":
    unittest.main()
