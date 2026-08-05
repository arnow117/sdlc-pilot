#!/usr/bin/env python3
"""Contract tests for the preview-only Obligation Engine."""
from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import obligation_engine  # noqa: E402
import context_resolver  # noqa: E402
import policy_compiler  # noqa: E402


def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _cas_worker(head_path: str, expected: str, manifest: dict[str, object], queue: object) -> None:
    """Run one contender in a separate process for the expected-head contract."""
    assert hasattr(queue, "put")
    try:
        head = obligation_engine.update_head(head_path, expected=expected, manifest=manifest)
    except Exception as exc:  # pragma: no cover - result is asserted by parent process
        queue.put(("error", type(exc).__name__, str(exc)))
    else:  # pragma: no cover - result is asserted by parent process
        queue.put(("ok", head["head_ref"]))


class Fixture:
    policy_id = "f" * 64
    phase_id = "phase.product.behavior"
    approval_phase_id = "phase.product.approval"
    run_id = "run.preview.001"

    def __init__(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo_root = self.root / "repo"
        (self.repo_root / ".sdlc").mkdir(parents=True)
        (self.repo_root / ".sdlc" / "STATE.md").write_text(
            "stage: legacy-plan\nstatus: in-progress\n", encoding="utf-8")
        (self.repo_root / ".sdlc-control").mkdir()
        (self.repo_root / ".sdlc-control" / "snapshot.md").write_text("legacy-control\n", encoding="utf-8")
        self.policy = self._policy()

    def close(self) -> None:
        self.tempdir.cleanup()

    def _obligation(
        self,
        obligation_id: str,
        role_id: str,
        responsibility: str,
        participation: str,
        rule_id: str,
        assertion_ids: list[str],
        *,
        constraint_ids: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "id": obligation_id,
            "role_id": role_id,
            "responsibility": responsibility,
            "participation": participation,
            "required_when_rule_id": rule_id,
            "min_actors": 1,
            "max_actors": 1,
            "independence_constraint_ids": constraint_ids or [],
            "playbook_ref": {"module_id": "mod.preview", "anchor": f"`{obligation_id}`"},
            "completion_assertion_ids": assertion_ids,
            "skip_policy": (
                {"mode": "forbidden", "allowed_when_rule_id": None, "override_policy": "none"}
                if participation == "required"
                else {
                    "mode": "selector_false_or_typed_override",
                    "allowed_when_rule_id": rule_id,
                    "override_policy": "typed-override-v1",
                }
            ),
        }

    def _phase(self, phase_id: str, stage: str, obligations: list[dict[str, object]]) -> dict[str, object]:
        return {
            "id": phase_id,
            "lifecycle": "product-design",
            "stage": stage,
            "phase_contract_ref": f"{self.policy_id}#{phase_id}",
            "completion_assertions": [
                {"id": "assert.structure", "kind": "mechanical", "source": "runner", "evidence_type": "report"},
                {"id": "assert.semantic", "kind": "semantic", "source": "typed_attestation", "evidence_type": "sufficient"},
            ],
            "semantic_attestation_types": ["product-sufficient-v1"],
            "obligations": obligations,
            "compatibility_adapter": None,
        }

    def _policy(self) -> dict[str, object]:
        behavior = self._phase(
            self.phase_id,
            "behavior-design",
            [
                self._obligation(
                    "obl.required", "role.owner", "responsible", "required", "rule.required", ["assert.semantic"]),
                self._obligation(
                    "obl.conditional", "role.reviewer", "reviewer", "conditional", "rule.conditional", ["assert.structure"],
                    constraint_ids=["constraint.reviewer.distinct-owner"]),
                self._obligation(
                    "obl.new-required", "role.owner", "responsible", "conditional", "rule.new-required", ["assert.semantic"]),
            ],
        )
        approval = self._phase(
            self.approval_phase_id,
            "product-approval",
            [
                self._obligation(
                    "obl.approval", "role.owner", "approver", "required", "rule.approval", ["assert.semantic"]),
            ],
        )
        return {
            "schema_version": "sdlc-policy-manifest-v1",
            "policy_manifest_id": self.policy_id,
            "activation": {
                "scope": "preview",
                "control_mutations": False,
                "output_scope": "preview",
            },
            "roles": [
                {
                    "id": "role.owner",
                    "independence_constraints": [],
                },
                {
                    "id": "role.reviewer",
                    "independence_constraints": [
                        {
                            "id": "constraint.reviewer.distinct-owner",
                            "mode": "distinct_actor",
                            "against_role_ids": ["role.owner"],
                        }
                    ],
                },
            ],
            "phases": [behavior, approval],
        }

    def context(
        self,
        *,
        phase_id: str | None = None,
        selected: list[str] | None = None,
        skipped: list[dict[str, object]] | None = None,
        diff_head: str = "b" * 40,
        needs_classification: bool = False,
    ) -> dict[str, object]:
        selected = selected if selected is not None else ["obl.required", "obl.conditional"]
        skipped = skipped if skipped is not None else [
            {"id": "obl.new-required", "selector_proof": {"rule_id": "rule.new-required", "result": "false"}},
        ]
        phase_id = phase_id or self.phase_id
        context_input = {
            "policy_manifest_id": self.policy_id,
            "phase_contract_ref": f"{self.policy_id}#{phase_id}",
            "selected": selected,
            "skipped": skipped,
            "diff_head": diff_head,
            "needs_classification": needs_classification,
        }
        return {
            "schema_version": "sdlc-context-manifest-v1",
            "scope": "preview",
            "activation": {"scope": "preview", "control_mutations": False},
            "context_manifest_id": _sha256(context_input),
            "context_input_sha256": _sha256({"input": context_input}),
            "policy_manifest_id": self.policy_id,
            "phase_contract_ref": f"{self.policy_id}#{phase_id}",
            "lifecycle_run_id": self.run_id,
            "lifecycle": "product-design",
            "operation": "product-approval" if phase_id == self.approval_phase_id else "behavior-design",
            "contracts": {"product_contract_ref": "PC:preview"},
            "profile": {"sha256": "1" * 64},
            "diff": {
                "scope": "legacy",
                "base_sha": "a" * 40,
                "head_sha": diff_head,
                "dirty": False,
                "staged": False,
                "untracked": False,
            },
            "selected_obligation_ids": selected,
            "skipped_obligations": skipped,
            "classification_requests": [],
            "needs_classification": needs_classification,
        }

    @staticmethod
    def roles() -> dict[str, list[str]]:
        return {
            "actor.owner": ["role.owner"],
            "actor.reviewer": ["role.reviewer"],
        }

    def attestation(self, manifest: dict[str, object], obligation_id: str, actor: str) -> dict[str, object]:
        item = next(item for item in manifest["obligations"] if item["obligation_id"] == obligation_id)
        return {
            "schema_version": "sdlc-typed-attestation-v1",
            "scope": "preview",
            "subject_ref": "preview:artifact:001",
            "obligation_id": obligation_id,
            "role": item["role"],
            "actor": actor,
            "verdict": "pass",
            "attestation_type": "product-sufficient-v1",
            "evidence_refs": ["evidence:preview:001"],
            "rationale_ref": "rationale:preview:001",
            "policy_manifest_ref": manifest["policy_manifest_ref"],
            "context_manifest_ref": manifest["context_manifest_ref"],
            "created_at": "2026-08-05T00:00:00Z",
        }

    def override(self, manifest: dict[str, object], obligation_id: str, actor: str) -> dict[str, object]:
        item = next(item for item in manifest["obligations"] if item["obligation_id"] == obligation_id)
        return {
            "schema_version": "sdlc-typed-override-v1",
            "scope": "preview",
            "override_kind": "conditional_skip",
            "obligation_id": obligation_id,
            "role": item["role"],
            "actor": actor,
            "rule_id": item["selection_rule_id"],
            "policy_manifest_ref": manifest["policy_manifest_ref"],
            "context_manifest_ref": manifest["context_manifest_ref"],
            "reason_ref": "reason:preview:001",
            "replacement_evidence_refs": ["evidence:replacement:001"],
            "expires_at": "2026-08-06T00:00:00Z",
            "authorization_ref": "audit:configured:001",
        }


class ObligationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    @staticmethod
    def item(manifest: dict[str, object], obligation_id: str) -> dict[str, object]:
        return next(item for item in manifest["obligations"] if item["obligation_id"] == obligation_id)

    def test_initial_manifest_has_three_explicit_states_and_is_content_addressed(self) -> None:
        manifest = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)

        self.assertEqual(manifest["scope"], "preview")
        self.assertEqual(self.item(manifest, "obl.required")["status"], "selected")
        self.assertEqual(self.item(manifest, "obl.conditional")["status"], "selected")
        skipped = self.item(manifest, "obl.new-required")
        self.assertEqual(skipped["status"], "explicitly_skipped")
        self.assertFalse(skipped["active"])
        self.assertEqual(skipped["selector_proof"], {"rule_id": "rule.new-required", "result": "false"})
        self.assertEqual(len(manifest["obligation_manifest_id"]), 64)
        obligation_engine.validate_manifest(manifest)

    def test_context_cannot_turn_a_required_obligation_into_selector_skip(self) -> None:
        context = self.fixture.context(
            selected=["obl.conditional"],
            skipped=[
                {"id": "obl.required", "selector_proof": {"rule_id": "rule.required", "result": "false"}},
                {"id": "obl.new-required", "selector_proof": {"rule_id": "rule.new-required", "result": "false"}},
            ],
        )
        with self.assertRaisesRegex(obligation_engine.ObligationError, "invalid-selector-skip:obl.required"):
            obligation_engine.create_obligation_manifest(context, self.fixture.policy)

    def test_completion_requires_typed_attestation_and_trusted_actor_role_binding(self) -> None:
        manifest = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        attestation = self.fixture.attestation(manifest, "obl.required", "actor.owner")
        completed = obligation_engine.complete_obligation(
            manifest,
            "obl.required",
            actor="actor.owner",
            actor_role_bindings=self.fixture.roles(),
            evidence_refs=["evidence:preview:001"],
            attestation=attestation,
        )

        item = self.item(completed, "obl.required")
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["completed_by"], "actor.owner")
        self.assertEqual(item["attestation"]["actor"], "actor.owner")

        wrong_actor = self.fixture.attestation(manifest, "obl.required", "actor.reviewer")
        with self.assertRaisesRegex(obligation_engine.ObligationError, "actor-role-mismatch"):
            obligation_engine.complete_obligation(
                manifest,
                "obl.required",
                actor="actor.reviewer",
                actor_role_bindings=self.fixture.roles(),
                evidence_refs=["evidence:preview:001"],
                attestation=wrong_actor,
            )

        self_report = copy.deepcopy(attestation)
        self_report["approved"] = True
        with self.assertRaisesRegex(obligation_engine.ObligationError, "self-reported-fact:approved"):
            obligation_engine.complete_obligation(
                manifest,
                "obl.required",
                actor="actor.owner",
                actor_role_bindings=self.fixture.roles(),
                evidence_refs=["evidence:preview:001"],
                attestation=self_report,
            )

    def test_conditional_override_is_typed_and_required_skip_is_rejected(self) -> None:
        manifest = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        override = self.fixture.override(manifest, "obl.conditional", "actor.reviewer")
        skipped = obligation_engine.apply_override(
            manifest,
            "obl.conditional",
            override=override,
            actor_role_bindings=self.fixture.roles(),
            now="2026-08-05T00:00:00Z",
        )
        item = self.item(skipped, "obl.conditional")
        self.assertEqual(item["status"], "explicitly_skipped")
        self.assertEqual(item["skip_reason"], "typed_override")
        self.assertEqual(item["override"]["authorization_ref"], "audit:configured:001")

        with self.assertRaisesRegex(obligation_engine.ObligationError, "required-obligation-cannot-skip"):
            obligation_engine.apply_override(
                manifest,
                "obl.required",
                override=self.fixture.override(manifest, "obl.required", "actor.owner"),
                actor_role_bindings=self.fixture.roles(),
                now="2026-08-05T00:00:00Z",
            )

        invalid = copy.deepcopy(override)
        invalid["override_kind"] = "approval_authenticity"
        with self.assertRaisesRegex(obligation_engine.ObligationError, "non-overridable-invariant"):
            obligation_engine.apply_override(
                manifest,
                "obl.conditional",
                override=invalid,
                actor_role_bindings=self.fixture.roles(),
                now="2026-08-05T00:00:00Z",
            )

    def test_independence_constraint_rejects_one_actor_covering_owner_and_reviewer(self) -> None:
        manifest = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        bindings = self.fixture.roles()
        bindings["actor.dual"] = ["role.owner", "role.reviewer"]
        completed_owner = obligation_engine.complete_obligation(
            manifest,
            "obl.required",
            actor="actor.dual",
            actor_role_bindings=bindings,
            evidence_refs=["evidence:preview:001"],
            attestation=self.fixture.attestation(manifest, "obl.required", "actor.dual"),
        )

        with self.assertRaisesRegex(obligation_engine.ObligationError, "independence-violation"):
            obligation_engine.complete_obligation(
                completed_owner,
                "obl.conditional",
                actor="actor.dual",
                actor_role_bindings=bindings,
                evidence_refs=["evidence:preview:review"],
            )

    def test_readiness_is_diagnostic_only_and_expired_override_is_rejected(self) -> None:
        manifest = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        completed = obligation_engine.complete_obligation(
            manifest,
            "obl.required",
            actor="actor.owner",
            actor_role_bindings=self.fixture.roles(),
            evidence_refs=["evidence:preview:001"],
            attestation=self.fixture.attestation(manifest, "obl.required", "actor.owner"),
        )
        overridden = obligation_engine.apply_override(
            completed,
            "obl.conditional",
            override=self.fixture.override(completed, "obl.conditional", "actor.reviewer"),
            actor_role_bindings=self.fixture.roles(),
            now="2026-08-05T00:00:00Z",
        )

        readiness = obligation_engine.require_transition_ready(overridden, now="2026-08-05T00:00:00Z")
        self.assertEqual(readiness["scope"], "preview")
        self.assertEqual(readiness["readiness"], "diagnostic-only")
        with self.assertRaisesRegex(obligation_engine.ObligationError, "expired-override:obl.conditional"):
            obligation_engine.require_transition_ready(overridden, now="2026-08-07T00:00:00Z")

    def test_reconcile_merges_new_work_without_deleting_history_and_resets_stale_completion(self) -> None:
        current = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        current = obligation_engine.complete_obligation(
            current,
            "obl.required",
            actor="actor.owner",
            actor_role_bindings=self.fixture.roles(),
            evidence_refs=["evidence:preview:001"],
            attestation=self.fixture.attestation(current, "obl.required", "actor.owner"),
        )
        new_context = self.fixture.context(
            selected=["obl.required", "obl.new-required"],
            skipped=[
                {"id": "obl.conditional", "selector_proof": {"rule_id": "rule.conditional", "result": "false"}},
            ],
            diff_head="c" * 40,
        )
        reconciled = obligation_engine.reconcile(current, new_context, freshness=obligation_engine.STALE)

        self.assertEqual(reconciled["previous_ref"], current["obligation_manifest_id"])
        self.assertEqual(self.item(reconciled, "obl.required")["status"], "selected")
        self.assertEqual(self.item(reconciled, "obl.new-required")["status"], "selected")
        old_conditional = self.item(reconciled, "obl.conditional")
        self.assertFalse(old_conditional["active"])
        self.assertEqual(old_conditional["superseded_by_context_ref"], new_context["context_manifest_id"])
        self.assertEqual(
            sorted(item["obligation_id"] for item in reconciled["obligations"]),
            ["obl.conditional", "obl.new-required", "obl.required"],
        )

    def test_preview_head_uses_expected_hash_cas_and_never_mutates_legacy_state_or_control(self) -> None:
        state_before = (self.fixture.repo_root / ".sdlc" / "STATE.md").read_bytes()
        control_before = (self.fixture.repo_root / ".sdlc-control" / "snapshot.md").read_bytes()
        initial = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        head_path = obligation_engine.preview_head_path(self.fixture.repo_root, self.fixture.run_id)
        head = obligation_engine.update_head(head_path, expected=None, manifest=initial)
        next_one = obligation_engine.record_legacy_approval_observation(
            initial,
            {"kind": "legacy_approval_observation", "scope": "preview", "legacy_spec_sha256": "2" * 64},
        )
        with self.assertRaisesRegex(obligation_engine.ObligationConflict, "expected-head-mismatch"):
            obligation_engine.update_head(head_path, expected="wrong", manifest=next_one)
        updated = obligation_engine.update_head(head_path, expected=head["head_ref"], manifest=next_one)
        self.assertEqual(updated["head_ref"], next_one["obligation_manifest_id"])
        self.assertEqual(obligation_engine.read_head(head_path)["head_ref"], next_one["obligation_manifest_id"])
        self.assertEqual((self.fixture.repo_root / ".sdlc" / "STATE.md").read_bytes(), state_before)
        self.assertEqual((self.fixture.repo_root / ".sdlc-control" / "snapshot.md").read_bytes(), control_before)
        with self.assertRaisesRegex(obligation_engine.ObligationError, "invalid-preview-head-path"):
            obligation_engine.update_head(
                self.fixture.repo_root / ".sdlc-control" / "HEAD.json",
                expected=next_one["obligation_manifest_id"],
                manifest=next_one,
            )

    def test_two_processes_contending_for_one_expected_head_have_exactly_one_success(self) -> None:
        initial = obligation_engine.create_obligation_manifest(self.fixture.context(), self.fixture.policy)
        head_path = obligation_engine.preview_head_path(self.fixture.repo_root, self.fixture.run_id)
        obligation_engine.update_head(head_path, expected=None, manifest=initial)
        left = obligation_engine.record_legacy_approval_observation(
            initial,
            {"kind": "legacy_approval_observation", "scope": "preview", "legacy_spec_sha256": "3" * 64},
        )
        right = obligation_engine.record_legacy_approval_observation(
            initial,
            {"kind": "legacy_approval_observation", "scope": "preview", "legacy_spec_sha256": "4" * 64},
        )
        context = multiprocessing.get_context("fork")
        queue = context.Queue()
        processes = [
            context.Process(target=_cas_worker, args=(str(head_path), initial["obligation_manifest_id"], candidate, queue))
            for candidate in (left, right)
        ]
        for process in processes:
            process.start()
        results = [queue.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(sum(result[0] == "error" for result in results), 1)

    def test_legacy_approval_observation_never_completes_dual_approval(self) -> None:
        context = self.fixture.context(
            phase_id=self.fixture.approval_phase_id,
            selected=["obl.approval"],
            skipped=[],
        )
        manifest = obligation_engine.create_obligation_manifest(context, self.fixture.policy)
        observed = obligation_engine.record_legacy_approval_observation(
            manifest,
            {"kind": "legacy_approval_observation", "scope": "preview", "legacy_spec_sha256": "5" * 64},
        )
        self.assertEqual(len(observed["legacy_approval_observations"]), 1)
        with self.assertRaisesRegex(obligation_engine.ObligationError, "preview-approval-cannot-complete:obl.approval"):
            obligation_engine.complete_obligation(
                observed,
                "obl.approval",
                actor="actor.owner",
                actor_role_bindings=self.fixture.roles(),
                evidence_refs=["evidence:preview:approval"],
                attestation=self.fixture.attestation(observed, "obl.approval", "actor.owner"),
            )

    def test_real_policy_compiler_and_context_resolver_output_are_accepted(self) -> None:
        project_root = HERE.parent
        policy = policy_compiler.compile_policy(
            project_root / "skills/sdlc/references/policies",
            project_root / "skills",
            "1.0.0",
        )
        request = {
            "scope": "preview",
            "command": "sdlc-product-design-preview",
            "lifecycle_run_id": "run.real.policy.001",
            "phase_id": "phase.product.discover",
            "lifecycle": "product-design",
            "operation": "discover",
            "work_type": "feature",
            "authority_mode": "legacy",
            "identity": {"requirement_id": "REQ-001"},
            "contracts": {"request_ref": "REQ-001"},
            "profile": {"sha256": "1" * 64},
            "diff": {
                "scope": "legacy",
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "dirty": False,
                "staged": False,
                "untracked": False,
            },
            "intent_flags": {},
            "runtime_event": {"type": "preview-request"},
            "engine_version": "1.0.0",
            "modes": ["bdd"],
            "selector_attestation_refs": [],
        }
        context = context_resolver.resolve_context(request, policy, project_root, project_root / "skills")
        manifest = obligation_engine.create_obligation_manifest(context, policy)

        self.assertEqual(context["selected_obligation_ids"], ["obl.product.discover.problem-frame"])
        self.assertEqual(
            [(item["obligation_id"], item["status"]) for item in manifest["obligations"]],
            [
                ("obl.product.discover.preservation", "explicitly_skipped"),
                ("obl.product.discover.problem-frame", "selected"),
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
