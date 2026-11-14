#!/usr/bin/env python3
"""Contract tests for the Git-tracked lightweight lifecycle state."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lifecycle_state  # noqa: E402
import test_support  # noqa: E402


class LifecycleFixture(unittest.TestCase):
    """Shared temporary-repository fixture for lifecycle contract tests."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        test_support.initialize_git_repo(self.repo, readme="test repository\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return test_support.git(self.repo, *args)

    def context(self, name: str, *, root: Path | None = None) -> str:
        target_root = self.repo if root is None else root
        relative = f".sdlc-v1/context/{name}.md"
        path = target_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
        return relative

    def commit_state(self, message: str = "update lifecycle state") -> None:
        self.git("add", ".sdlc-v1")
        self.git("commit", "-m", message)

    def initialize_state(self) -> None:
        lifecycle_state.initialize(self.repo, at="2026-08-10T00:00:00Z")

    def capture(self, requirement_id: str, *, priority: str = "P2") -> str:
        ref = self.context(f"product-{requirement_id}")
        lifecycle_state.capture_requirement(
            repo=self.repo,
            requirement_id=requirement_id,
            title=f"Requirement {requirement_id}",
            priority=priority,
            product_context_ref=ref,
            at="2026-08-10T00:01:00Z",
        )
        return ref

    def start(self, requirement_id: str, feature_id: str) -> str:
        ref = self.context(f"engineering-{feature_id}")
        lifecycle_state.start_feature(
            repo=self.repo,
            requirement_id=requirement_id,
            feature_id=feature_id,
            branch=f"feature/{feature_id}",
            engineering_context_ref=ref,
            at="2026-08-10T00:03:00Z",
        )
        return ref

    def update_requirement_timestamp(self, timestamp: str) -> None:
        state_path = self.repo / ".sdlc-v1/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-timestamp"]["updated_at"] = timestamp
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def prepare_requirement_timestamp_state(self) -> None:
        self.initialize_state()
        self.capture("REQ-timestamp")

    def complete_one_task(self, feature_id: str = "FEAT-one") -> None:
        lifecycle_state.add_task(
            repo=self.repo, feature_id=feature_id, task_id="TASK-one", title="Implement",
            at="2026-08-10T00:04:00Z",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id=feature_id, task_id="TASK-one", status="in_progress",
            at="2026-08-10T00:05:00Z",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id=feature_id, task_id="TASK-one", status="done",
            at="2026-08-10T00:06:00Z",
        )

    def prepare_branch_migration(
        self,
        *,
        requirement_id: str = "REQ-migrate",
        feature_id: str = "FEAT-migrate",
        branch: str = "feature/migrated",
    ) -> tuple[str, str, str]:
        self.initialize_state()
        self.capture(requirement_id)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id=requirement_id)
        engineering_ref = self.start(requirement_id, feature_id)
        self.git("checkout", "-b", branch)
        head = self.git("rev-parse", "HEAD").stdout.strip()
        return engineering_ref, head, f"feature/{feature_id}"

    def state_bytes(self, *, root: Path | None = None) -> bytes:
        target_root = self.repo if root is None else root
        return (target_root / ".sdlc-v1/state.json").read_bytes()

    def migration_arguments(
        self,
        *,
        feature_id: str = "FEAT-migrate",
        expected_branch: str = "feature/FEAT-migrate",
        branch: str = "feature/migrated",
        expected_head: str | None = None,
    ) -> dict[str, str | Path]:
        head = expected_head or self.git("rev-parse", "HEAD").stdout.strip()
        return {
            "repo": self.repo,
            "feature_id": feature_id,
            "expected_branch": expected_branch,
            "branch": branch,
            "expected_head": head,
            "reason": "continue implementation in the current checkout",
        }


class LifecycleStateTest(LifecycleFixture):
    """Contract tests for the pre-fingerprint lifecycle behaviors."""

    def test_state_load_preserves_supported_timezone_spellings(self) -> None:
        self.prepare_requirement_timestamp_state()

        for timestamp in (
            "2026-08-21T06:16:11+0800",
            "2026-08-21T06:16:11-0330",
            "2026-08-21T06:16:11Z",
            "2026-08-21T06:16:11+08:00",
        ):
            with self.subTest(timestamp=timestamp):
                self.update_requirement_timestamp(timestamp)

                loaded = lifecycle_state.load(self.repo)

                self.assertEqual(
                    loaded["requirements"]["REQ-timestamp"]["updated_at"],
                    timestamp,
                )

    def test_mutation_preserves_basic_timezone_offset(self) -> None:
        self.initialize_state()
        product_ref = self.context("product-REQ-basic-offset")
        timestamp = "2026-08-21T06:16:11-0330"

        captured = lifecycle_state.capture_requirement(
            repo=self.repo,
            requirement_id="REQ-basic-offset",
            title="Basic offset",
            priority="P2",
            product_context_ref=product_ref,
            at=timestamp,
        )

        self.assertEqual(captured["requirement"]["updated_at"], timestamp)
        loaded = lifecycle_state.load(self.repo)
        self.assertEqual(
            loaded["requirements"]["REQ-basic-offset"]["updated_at"],
            timestamp,
        )

    def test_state_load_rejects_naive_and_invalid_timezone_offsets(self) -> None:
        self.prepare_requirement_timestamp_state()

        for timestamp in (
            "2026-08-21T06:16:11",
            "2026-08-21T06:16:11+080",
            "2026-08-21T06:16:11+2400",
        ):
            with self.subTest(timestamp=timestamp):
                self.update_requirement_timestamp(timestamp)

                with self.assertRaisesRegex(
                    lifecycle_state.LifecycleStateError,
                    "invalid-requirement-updated-at",
                ):
                    lifecycle_state.load(self.repo)

    def test_state_updates_can_be_batched_before_a_git_handoff(self) -> None:
        self.initialize_state()
        product_ref = self.capture("REQ-001")
        lifecycle_state.mark_requirement_ready(
            repo=self.repo, requirement_id="REQ-001", at="2026-08-10T00:02:00Z",
        )
        before = lifecycle_state.status(self.repo)
        self.assertFalse(before["git"]["tracked"])
        self.assertEqual(lifecycle_state.load(self.repo)["requirements"]["REQ-001"]["status"], "ready")
        self.commit_state("share product handoff")
        after = lifecycle_state.status(self.repo)
        self.assertTrue(after["git"]["tracked"])
        self.assertEqual(after["state_version"], 3)
        self.assertTrue((self.repo / product_ref).is_file())

    def test_captured_requirement_can_be_revised_and_cancelled(self) -> None:
        self.initialize_state()
        self.capture("REQ-base")
        self.capture("REQ-change")
        revised = lifecycle_state.revise_requirement(
            repo=self.repo,
            requirement_id="REQ-change",
            title="Revised requirement",
            description="Narrowed delivery result",
            domain="platform",
            priority="P0",
            depends_on=["REQ-base"],
            at="2026-08-10T00:02:00Z",
        )
        self.assertEqual(revised["requirement"]["title"], "Revised requirement")
        self.assertEqual(revised["requirement"]["depends_on"], ["REQ-base"])
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "requirement-has-active-dependents:REQ-change",
        ):
            lifecycle_state.cancel_requirement(
                repo=self.repo, requirement_id="REQ-base", reason="superseded",
            )
        lifecycle_state.revise_requirement(
            repo=self.repo, requirement_id="REQ-change", depends_on=[],
        )
        cancelled = lifecycle_state.cancel_requirement(
            repo=self.repo,
            requirement_id="REQ-base",
            reason="superseded by a bounded requirement",
            at="2026-08-10T00:03:00Z",
        )
        self.assertEqual(cancelled["requirement"]["status"], "cancelled")
        self.assertEqual(cancelled["reason"], "superseded by a bounded requirement")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "requirement-not-cancellable"):
            lifecycle_state.cancel_requirement(
                repo=self.repo, requirement_id="REQ-base", reason="cancel twice",
            )

    def test_requirement_revision_rejects_invalid_or_started_changes(self) -> None:
        self.initialize_state()
        self.capture("REQ-one")
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "requirement-revision-has-no-changes",
        ):
            lifecycle_state.revise_requirement(repo=self.repo, requirement_id="REQ-one")
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "unknown-requirement-dependency:REQ-missing",
        ):
            lifecycle_state.revise_requirement(
                repo=self.repo, requirement_id="REQ-one", depends_on=["REQ-missing"],
            )
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-one")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "requirement-not-revisable"):
            lifecycle_state.revise_requirement(
                repo=self.repo, requirement_id="REQ-one", priority="P0",
            )

    def test_state_must_not_be_ignored_staged_or_unmerged(self) -> None:
        (self.repo / ".gitignore").write_text(".sdlc-v1/\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "ignore state")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "state-path-is-gitignored"):
            lifecycle_state.initialize(self.repo)

        self.git("rm", ".gitignore")
        self.git("commit", "-m", "allow state")
        self.initialize_state()
        self.capture("REQ-staged")
        self.git("add", ".sdlc-v1/state.json")
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "state-is-staged-commit-or-unstage-before-update",
        ):
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-staged")
        self.git("reset", "HEAD", ".sdlc-v1/state.json")
        self.commit_state("track state before conflict")

        blob = self.git("hash-object", "-w", ".sdlc-v1/state.json").stdout.strip()
        self.git("update-index", "--force-remove", "--", ".sdlc-v1/state.json")
        entries = "".join(
            f"100644 {blob} {stage}\t.sdlc-v1/state.json\n" for stage in (1, 2, 3)
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "update-index", "--index-info"],
            input=entries, text=True, check=True, capture_output=True,
        )
        self.assertTrue(lifecycle_state.status(self.repo)["git"]["unmerged"])
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "state-has-unmerged-index-entries"):
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-staged")

    def test_context_references_are_required_repo_local_markdown_files(self) -> None:
        self.initialize_state()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "product-context-not-found"):
            lifecycle_state.capture_requirement(
                repo=self.repo,
                requirement_id="REQ-missing",
                title="Missing",
                product_context_ref=".sdlc-v1/context/missing.md",
            )
        (self.repo / "outside.md").write_text("# Outside\n", encoding="utf-8")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "invalid-requirement-product-context-ref"):
            lifecycle_state.capture_requirement(
                repo=self.repo,
                requirement_id="REQ-outside",
                title="Outside",
                product_context_ref="outside.md",
            )
        context_dir = self.repo / ".sdlc-v1/context"
        context_dir.mkdir(parents=True, exist_ok=True)
        (context_dir / "linked.md").symlink_to(self.repo / "README.md")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "product-context-cannot-be-symlink"):
            lifecycle_state.capture_requirement(
                repo=self.repo,
                requirement_id="REQ-link",
                title="Link",
                product_context_ref=".sdlc-v1/context/linked.md",
            )
        self.capture("REQ-engineering")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-engineering")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "engineering-context-not-found"):
            lifecycle_state.start_feature(
                repo=self.repo,
                requirement_id="REQ-engineering",
                feature_id="FEAT-missing",
                branch="feature/missing",
                engineering_context_ref=".sdlc-v1/context/missing-engineering.md",
            )

    def test_historical_directories_are_ignored_but_copied_hooks_are_reported(self) -> None:
        (self.repo / ".sdlc").mkdir()
        (self.repo / ".sdlc/lifecycle.json").write_text("{}\n", encoding="utf-8")
        (self.repo / ".sdlc-control/dual-lifecycle").mkdir(parents=True)
        (self.repo / ".sdlc-control/dual-lifecycle/ledger.json").write_text("{}\n", encoding="utf-8")
        (self.repo / ".sdlc-v1").mkdir()
        (self.repo / ".sdlc-v1/ledger.json").write_text("{}\n", encoding="utf-8")
        self.initialize_state()
        self.assertTrue((self.repo / ".sdlc-v1/state.json").is_file())

        second = self.base / "hook-repo"
        second.mkdir()
        subprocess.run(["git", "-C", str(second), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(second), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(second), "config", "user.name", "SDLC tests"], check=True)
        (second / "README.md").write_text("hook test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(second), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(second), "commit", "-m", "initial"], check=True, capture_output=True)
        hook = second / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\n# sdlc-pilot pre-push\n", encoding="utf-8")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "unsupported-sdlc-hooks-installed:pre-push"):
            lifecycle_state.initialize(second)
        self.assertFalse((second / ".sdlc-v1/state.json").exists())

    def test_full_lifecycle_syncs_between_two_clones(self) -> None:
        remote = self.base / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "HEAD")
        branch = self.git("branch", "--show-current").stdout.strip()
        subprocess.run(
            ["git", "-C", str(remote), "symbolic-ref", "HEAD", f"refs/heads/{branch}"], check=True,
        )

        self.initialize_state()
        product_ref = self.capture("REQ-shared")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-shared")
        self.commit_state("hand off ready requirement")
        self.git("push")

        other = self.base / "other-clone"
        subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(other), "config", "user.email", "other@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(other), "config", "user.name", "Other machine"], check=True)
        self.assertEqual(lifecycle_state.readyqueue(other)[0]["product_context_ref"], product_ref)
        engineering_ref = self.context("engineering-shared", root=other)
        lifecycle_state.start_feature(
            repo=other,
            requirement_id="REQ-shared",
            feature_id="FEAT-shared",
            branch="feature/shared",
            engineering_context_ref=engineering_ref,
        )
        subprocess.run(["git", "-C", str(other), "add", ".sdlc-v1"], check=True)
        subprocess.run(
            ["git", "-C", str(other), "commit", "-m", "start shared feature"],
            check=True, capture_output=True,
        )
        subprocess.run(["git", "-C", str(other), "push"], check=True, capture_output=True)
        self.git("pull", "--ff-only")
        feature = lifecycle_state.feature_projection(repo=self.repo, feature_id="FEAT-shared")["feature"]
        self.assertEqual(feature["status"], "planned")
        self.assertEqual(feature["engineering_context_ref"], engineering_ref)

        lifecycle_state.add_task(
            repo=other, feature_id="FEAT-shared", task_id="TASK-shared", title="Implement",
        )
        lifecycle_state.set_task_status(
            repo=other, feature_id="FEAT-shared", task_id="TASK-shared", status="in_progress",
        )
        lifecycle_state.set_task_status(
            repo=other, feature_id="FEAT-shared", task_id="TASK-shared", status="done",
        )
        (other / "implementation.txt").write_text("shared implementation\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(other), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(other), "commit", "-m", "implement shared feature"],
            check=True, capture_output=True,
        )
        validation_commit = subprocess.run(
            ["git", "-C", str(other), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        lifecycle_state.record_validation(
            repo=other, feature_id="FEAT-shared", result="pass", command="test shared feature",
        )
        subprocess.run(["git", "-C", str(other), "add", ".sdlc-v1"], check=True)
        subprocess.run(
            ["git", "-C", str(other), "commit", "-m", "share validation result"],
            check=True, capture_output=True,
        )
        subprocess.run(["git", "-C", str(other), "push"], check=True, capture_output=True)

        self.git("pull", "--ff-only")
        lifecycle_state.record_review(
            repo=self.repo, feature_id="FEAT-shared", decision="approved", by="machine-a",
        )
        self.commit_state("share review result")
        self.git("push")

        subprocess.run(
            ["git", "-C", str(other), "pull", "--ff-only"], check=True, capture_output=True,
        )
        lifecycle_state.record_release(repo=other, feature_id="FEAT-shared")
        released = lifecycle_state.product_projection(
            repo=other, requirement_id="REQ-shared",
        )
        self.assertEqual(released["requirement"]["status"], "released")
        self.assertEqual(released["feature"]["release"]["commit"], validation_commit)

    def test_two_local_cli_writers_do_not_drop_each_others_update(self) -> None:
        self.initialize_state()
        first_ref = self.context("product-first")
        second_ref = self.context("product-second")
        command = [
            sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo), "capture-requirement",
        ]
        first = subprocess.Popen(
            [*command, "--id", "REQ-first", "--title", "First", "--product-context-ref", first_ref],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        second = subprocess.Popen(
            [*command, "--id", "REQ-second", "--title", "Second", "--product-context-ref", second_ref],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        first_out, first_error = first.communicate(timeout=10)
        second_out, second_error = second.communicate(timeout=10)
        self.assertEqual(first.returncode, 0, first_error or first_out)
        self.assertEqual(second.returncode, 0, second_error or second_out)
        self.assertEqual(sorted(lifecycle_state.load(self.repo)["requirements"]), ["REQ-first", "REQ-second"])

    def test_validation_requires_tracked_state_and_clean_implementation(self) -> None:
        self.initialize_state()
        self.capture("REQ-one")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-one")
        self.start("REQ-one", "FEAT-one")
        self.complete_one_task()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "state-must-be-git-tracked"):
            lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-one", result="pass")

        self.commit_state("ready for validation")
        (self.repo / "README.md").write_text("implementation changed\n", encoding="utf-8")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "require-clean-worktree"):
            lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-one", result="pass")
        self.git("add", "README.md")
        self.git("commit", "-m", "tested implementation")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-one", result="pass")
        (self.repo / "README.md").write_text("unvalidated change\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "unvalidated implementation")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "review-commit-does-not-match-validation"):
            lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-one", decision="approved")

    def test_product_to_release_allows_state_only_handoff_commits(self) -> None:
        self.initialize_state()
        self.capture("REQ-release", priority="P1")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-release")
        self.start("REQ-release", "FEAT-release")
        self.complete_one_task("FEAT-release")
        self.commit_state("ready for lifecycle checks")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        lifecycle_state.record_validation(
            repo=self.repo,
            feature_id="FEAT-release",
            result="pass",
            command="python -m unittest",
        )
        self.assertEqual(
            lifecycle_state.feature_projection(repo=self.repo, feature_id="FEAT-release")["feature"]["validation"]["commit"],
            head,
        )
        engineering_ref = lifecycle_state.feature_projection(
            repo=self.repo, feature_id="FEAT-release",
        )["feature"]["engineering_context_ref"]
        (self.repo / engineering_ref).write_text(
            "# engineering-FEAT-release\n\nValidation evidence: pass.\n",
            encoding="utf-8",
        )
        self.commit_state("share validation result")
        self.assertNotEqual(self.git("rev-parse", "HEAD").stdout.strip(), head)
        lifecycle_state.record_review(
            repo=self.repo, feature_id="FEAT-release", decision="approved", by="owner",
        )
        self.commit_state("share review result")
        lifecycle_state.record_release(
            repo=self.repo, feature_id="FEAT-release", commit=head,
        )
        product = lifecycle_state.product_projection(repo=self.repo, requirement_id="REQ-release")
        self.assertEqual(product["requirement"]["status"], "released")
        self.assertEqual(product["feature"]["release"]["commit"], head)

    def test_retract_release_restores_reviewed_state_without_rewriting_validation(self) -> None:
        self.initialize_state()
        self.capture("REQ-retract")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-retract")
        self.start("REQ-retract", "FEAT-retract")
        self.complete_one_task("FEAT-retract")
        self.commit_state("ready for release correction test")
        validation = lifecycle_state.record_validation(
            repo=self.repo, feature_id="FEAT-retract", result="pass", command="python -m unittest",
        )["feature"]["validation"]
        self.commit_state("record validation")
        lifecycle_state.record_review(
            repo=self.repo, feature_id="FEAT-retract", decision="approved", by="owner",
        )
        self.commit_state("record review")
        lifecycle_state.record_release(repo=self.repo, feature_id="FEAT-retract")

        result = lifecycle_state.retract_release(
            repo=self.repo,
            feature_id="FEAT-retract",
            reason="release was recorded after merge without deployment smoke",
            at="2026-08-10T00:10:00Z",
        )

        self.assertEqual(result["reason"], "release was recorded after merge without deployment smoke")
        self.assertEqual(result["feature"]["status"], "reviewed")
        self.assertEqual(result["feature"]["release"], {"status": "pending", "commit": None, "at": None})
        self.assertEqual(result["feature"]["validation"], validation)
        self.assertEqual(result["requirement"]["status"], "validated")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-not-released"):
            lifecycle_state.retract_release(
                repo=self.repo, feature_id="FEAT-retract", reason="duplicate correction",
            )

    def test_review_rejects_long_lived_context_change_after_validation(self) -> None:
        self.initialize_state()
        self.capture("REQ-context")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-context")
        self.start("REQ-context", "FEAT-context")
        self.complete_one_task("FEAT-context")
        self.commit_state("ready for long-lived context check")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-context", result="pass")
        (self.repo / "AGENTS.md").write_text("# Updated contributor guidance\n", encoding="utf-8")
        self.git("add", "AGENTS.md")
        self.git("commit", "-m", "docs: update long-lived guidance")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "review-commit-does-not-match-validation"):
            lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-context", decision="approved")

    def test_next_routes_the_full_single_feature_lifecycle(self) -> None:
        self.initialize_state()
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "intake")
        self.capture("REQ-next")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "spec")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-next")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "plan")
        self.start("REQ-next", "FEAT-next")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "plan")
        lifecycle_state.add_task(repo=self.repo, feature_id="FEAT-next", task_id="TASK-next", title="Next")
        lifecycle_state.add_task(repo=self.repo, feature_id="FEAT-next", task_id="TASK-dropped", title="Dropped")
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-next", task_id="TASK-dropped", status="cancelled",
        )
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "build")
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-next", task_id="TASK-next", status="blocked",
        )
        blocked = lifecycle_state.next_action(self.repo)
        self.assertEqual(blocked["stage"], "build")
        self.assertEqual(blocked["reason"], "blocked-tasks-require-work")
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-next", task_id="TASK-next", status="in_progress",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-next", task_id="TASK-next", status="done",
        )
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "validate")
        self.commit_state("validate next routing")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-next", result="pass")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "review")
        lifecycle_state.record_review(
            repo=self.repo, feature_id="FEAT-next", decision="changes_requested", by="reviewer",
        )
        requested = lifecycle_state.next_action(self.repo)
        self.assertEqual(requested["stage"], "build")
        self.assertEqual(requested["reason"], "review-requested-changes")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-next", result="pass")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-next", decision="approved")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "ship")
        lifecycle_state.record_release(repo=self.repo, feature_id="FEAT-next")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "done")

    def test_next_requires_explicit_selection_for_parallel_work(self) -> None:
        self.initialize_state()
        self.capture("REQ-low", priority="P2")
        self.capture("REQ-high", priority="P0")
        captured = lifecycle_state.next_action(self.repo)
        self.assertEqual(captured["stage"], "needs_selection")
        self.assertEqual(
            [candidate["requirement_id"] for candidate in captured["candidates"]],
            ["REQ-high", "REQ-low"],
        )
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-low")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-high")
        self.start("REQ-low", "FEAT-low")
        self.start("REQ-high", "FEAT-high")
        active = lifecycle_state.next_action(self.repo)
        self.assertEqual(active["stage"], "needs_selection")
        self.assertEqual(active["reason"], "multiple-active-features")
        self.assertEqual(
            [candidate["feature_id"] for candidate in active["candidates"]],
            ["FEAT-high", "FEAT-low"],
        )

    def test_cli_exposes_context_arguments_and_next(self) -> None:
        self.initialize_state()
        product_ref = self.context("product-cli")
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        captured = subprocess.run(
            [
                *command,
                "capture-requirement",
                "--id", "REQ-cli",
                "--title", "CLI requirement",
                "--product-context-ref", product_ref,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(captured.returncode, 0, captured.stderr)
        routed = subprocess.run([*command, "next"], capture_output=True, text=True)
        self.assertEqual(routed.returncode, 0, routed.stderr)
        self.assertEqual(json.loads(routed.stdout)["stage"], "spec")

    def test_set_task_status_cli_rejection_reports_semantic_details(self) -> None:
        self.initialize_state()
        self.capture("REQ-transition")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-transition")
        self.start("REQ-transition", "FEAT-transition")
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-transition",
            task_id="TASK-transition",
            title="Implement transition details",
        )
        before = self.state_bytes()
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        result = subprocess.run(
            [
                *command,
                "set-task-status",
                "--feature-id",
                "FEAT-transition",
                "--task-id",
                "TASK-transition",
                "--status",
                "done",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(lines[0], "lifecycle-state-error: invalid-task-transition:todo->done")
        self.assertTrue(lines[1].startswith("error-details: "))
        details = json.loads(lines[1].removeprefix("error-details: "))
        self.assertEqual(details["operation"], "set-task-status")
        self.assertEqual(details["feature_id"], "FEAT-transition")
        self.assertEqual(details["task_id"], "TASK-transition")
        self.assertEqual(details["current_status"], "todo")
        self.assertEqual(details["requested_status"], "done")
        self.assertEqual(details["allowed_next"], ["blocked", "cancelled", "in_progress"])
        self.assertFalse(details["state_changed"])
        self.assertIn("任务", details["message"])
        self.assertIn("无影响", details["effect"])
        self.assertEqual(self.state_bytes(), before)

    def test_task_reopen_resets_delivery_checks_and_routes_build(self) -> None:
        self.initialize_state()
        self.capture("REQ-reopen")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-reopen")
        self.start("REQ-reopen", "FEAT-reopen")
        self.complete_one_task("FEAT-reopen")
        self.commit_state("ready to validate reopened task")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-reopen", result="pass")
        lifecycle_state.record_review(
            repo=self.repo,
            feature_id="FEAT-reopen",
            decision="approved",
            by="reviewer",
        )
        before_rejection = self.state_bytes()
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        rejected = subprocess.run(
            [
                *command,
                "set-task-status",
                "--feature-id",
                "FEAT-reopen",
                "--task-id",
                "TASK-one",
                "--status",
                "in_progress",
            ],
            capture_output=True,
            text=True,
        )
        rejection_details = json.loads(rejected.stderr.splitlines()[1].removeprefix("error-details: "))
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("done 转为 todo", rejection_details["hint"])
        self.assertIn("validation", rejection_details["effect"])
        self.assertEqual(self.state_bytes(), before_rejection)

        lifecycle_state.set_task_status(
            repo=self.repo,
            feature_id="FEAT-reopen",
            task_id="TASK-one",
            status="todo",
        )

        feature = lifecycle_state.feature_projection(
            repo=self.repo,
            feature_id="FEAT-reopen",
        )["feature"]
        self.assertEqual(feature["status"], "in_progress")
        self.assertEqual(feature["validation"]["result"], "pending")
        self.assertEqual(feature["review"]["decision"], "pending")
        self.assertEqual(feature["release"]["status"], "pending")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "build")
        lifecycle_state.set_task_status(
            repo=self.repo,
            feature_id="FEAT-reopen",
            task_id="TASK-one",
            status="in_progress",
        )
        self.assertEqual(
            lifecycle_state.feature_projection(
                repo=self.repo,
                feature_id="FEAT-reopen",
            )["feature"]["tasks"]["TASK-one"]["status"],
            "in_progress",
        )

    def test_set_task_status_rejections_filter_available_transitions(self) -> None:
        self.initialize_state()
        self.capture("REQ-dependencies")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-dependencies")
        self.start("REQ-dependencies", "FEAT-dependencies")
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-dependencies",
            task_id="TASK-prerequisite",
            title="Finish prerequisite",
        )
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-dependencies",
            task_id="TASK-dependent",
            title="Run dependent work",
            depends_on=["TASK-prerequisite"],
        )
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        blocked = subprocess.run(
            [
                *command,
                "set-task-status",
                "--feature-id",
                "FEAT-dependencies",
                "--task-id",
                "TASK-dependent",
                "--status",
                "in_progress",
            ],
            capture_output=True,
            text=True,
        )
        blocked_details = json.loads(blocked.stderr.splitlines()[1].removeprefix("error-details: "))
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(blocked_details["allowed_next"], ["blocked", "cancelled"])
        self.assertEqual(blocked_details["unmet_dependencies"], ["TASK-prerequisite"])

        lifecycle_state.set_task_status(
            repo=self.repo,
            feature_id="FEAT-dependencies",
            task_id="TASK-dependent",
            status="cancelled",
        )
        cancelled = subprocess.run(
            [
                *command,
                "set-task-status",
                "--feature-id",
                "FEAT-dependencies",
                "--task-id",
                "TASK-dependent",
                "--status",
                "todo",
            ],
            capture_output=True,
            text=True,
        )
        cancelled_details = json.loads(cancelled.stderr.splitlines()[1].removeprefix("error-details: "))
        self.assertEqual(cancelled.returncode, 2)
        self.assertEqual(cancelled_details["current_status"], "cancelled")
        self.assertEqual(cancelled_details["allowed_next"], [])

    def test_closed_feature_rejection_has_no_available_task_transition(self) -> None:
        self.initialize_state()
        self.capture("REQ-closed")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-closed")
        self.start("REQ-closed", "FEAT-closed")
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-closed",
            task_id="TASK-closed",
            title="Closed feature task",
        )
        state = lifecycle_state.load(self.repo)
        state["features"]["FEAT-closed"]["status"] = "cancelled"
        state["requirements"]["REQ-closed"]["status"] = "cancelled"
        lifecycle_state.state_path(self.repo).write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        result = subprocess.run(
            [
                *command,
                "set-task-status",
                "--feature-id",
                "FEAT-closed",
                "--task-id",
                "TASK-closed",
                "--status",
                "in_progress",
            ],
            capture_output=True,
            text=True,
        )

        details = json.loads(result.stderr.splitlines()[1].removeprefix("error-details: "))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(details["current_status"], "todo")
        self.assertEqual(details["allowed_next"], [])
        self.assertEqual(details["feature_status"], "cancelled")
        self.assertFalse(details["state_changed"])
        self.assertNotIn("重开", details["hint"])
        self.assertNotIn("retract", details["hint"])

    def test_task_status_errors_do_not_change_other_command_output_or_api_code(self) -> None:
        self.initialize_state()
        self.capture("REQ-compatibility")
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        successful = subprocess.run([*command, "next"], capture_output=True, text=True)
        self.assertEqual(successful.returncode, 0, successful.stderr)
        self.assertEqual(successful.stderr, "")
        self.assertEqual(json.loads(successful.stdout)["stage"], "spec")

        rejected = subprocess.run(
            [*command, "product-projection", "--requirement-id", "REQ-missing"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, "")
        self.assertEqual(rejected.stderr, "lifecycle-state-error: requirement-not-found:REQ-missing\n")

        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-compatibility")
        self.start("REQ-compatibility", "FEAT-compatibility")
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-compatibility",
            task_id="TASK-compatibility",
            title="Compatibility",
        )
        with self.assertRaises(lifecycle_state.LifecycleStateError) as raised:
            lifecycle_state.set_task_status(
                repo=self.repo,
                feature_id="FEAT-compatibility",
                task_id="TASK-compatibility",
                status="done",
            )
        self.assertEqual(str(raised.exception), "invalid-task-transition:todo->done")

    def test_cli_accepts_the_documented_task_status_sequence(self) -> None:
        self.initialize_state()
        self.capture("REQ-cli-task")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-cli-task")
        self.start("REQ-cli-task", "FEAT-cli-task")
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-cli-task",
            task_id="TASK-cli-task",
            title="Run the documented sequence",
        )
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        for status in ("in_progress", "done"):
            result = subprocess.run(
                [
                    *command,
                    "set-task-status",
                    "--feature-id",
                    "FEAT-cli-task",
                    "--task-id",
                    "TASK-cli-task",
                    "--status",
                    status,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(result.stdout)["task"]["status"], status)

    def test_task_status_postreplace_failure_reports_unknown_state_change(self) -> None:
        self.initialize_state()
        self.capture("REQ-recovery")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-recovery")
        self.start("REQ-recovery", "FEAT-recovery")
        lifecycle_state.add_task(
            repo=self.repo,
            feature_id="FEAT-recovery",
            task_id="TASK-recovery",
            title="Recover after replacement",
        )
        before = self.state_bytes()
        argv = [
            "--repo",
            str(self.repo),
            "set-task-status",
            "--feature-id",
            "FEAT-recovery",
            "--task-id",
            "TASK-recovery",
            "--status",
            "in_progress",
        ]
        with (
            mock.patch.object(
                lifecycle_state,
                "_sync_directory",
                side_effect=lifecycle_state.LifecycleStateError("cannot-sync-state-directory"),
            ),
            mock.patch("sys.stderr", new_callable=io.StringIO) as captured_stderr,
        ):
            self.assertEqual(lifecycle_state.main(argv), 2)

        lines = captured_stderr.getvalue().splitlines()
        details = json.loads(lines[1].removeprefix("error-details: "))
        self.assertEqual(lines[0], "lifecycle-state-error: cannot-sync-state-directory")
        self.assertEqual(details["state_changed"], "unknown")
        self.assertIsNone(details["current_status"])
        self.assertIsNone(details["allowed_next"])
        self.assertIn("feature-projection", details["hint"])
        self.assertNotEqual(self.state_bytes(), before)
        self.assertEqual(
            lifecycle_state.load(self.repo)["features"]["FEAT-recovery"]["tasks"]["TASK-recovery"]["status"],
            "in_progress",
        )

    def test_migrate_feature_branch_updates_only_the_open_feature_registration(self) -> None:
        self.initialize_state()
        self.capture("REQ-migrate")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-migrate")
        engineering_ref = self.start("REQ-migrate", "FEAT-migrate")
        self.git("checkout", "-b", "feature/migrated")
        head = self.git("rev-parse", "HEAD").stdout.strip()

        before = lifecycle_state.load(self.repo)
        result = lifecycle_state.migrate_feature_branch(
            repo=self.repo,
            feature_id="FEAT-migrate",
            expected_branch="feature/FEAT-migrate",
            branch="feature/migrated",
            expected_head=head,
            reason="continue implementation in the current checkout",
            at="2026-10-07T00:00:00Z",
        )
        after = lifecycle_state.load(self.repo)

        self.assertEqual(result["operation"], "migrate-feature-branch")
        self.assertEqual(result["feature_id"], "FEAT-migrate")
        self.assertEqual(result["old_branch"], "feature/FEAT-migrate")
        self.assertEqual(result["new_branch"], "feature/migrated")
        self.assertEqual(result["head"], head)
        self.assertEqual(result["engineering_context_ref"], engineering_ref)
        self.assertEqual(after["features"]["FEAT-migrate"]["branch"], "feature/migrated")
        self.assertEqual(after["features"]["FEAT-migrate"]["updated_at"], "2026-10-07T00:00:00Z")
        self.assertEqual(after["requirements"], before["requirements"])
        self.assertEqual(after["features"]["FEAT-migrate"]["tasks"], before["features"]["FEAT-migrate"]["tasks"])
        self.assertEqual(
            after["features"]["FEAT-migrate"]["validation"],
            before["features"]["FEAT-migrate"]["validation"],
        )
        self.assertEqual(
            after["features"]["FEAT-migrate"]["review"],
            before["features"]["FEAT-migrate"]["review"],
        )
        self.assertEqual(
            after["features"]["FEAT-migrate"]["release"],
            before["features"]["FEAT-migrate"]["release"],
        )

    def test_migrate_feature_branch_preserves_delivery_evidence_and_other_records(self) -> None:
        self.initialize_state()
        self.capture("REQ-migrate")
        self.capture("REQ-other")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-migrate")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-other")
        self.start("REQ-migrate", "FEAT-migrate")
        self.start("REQ-other", "FEAT-other")
        lifecycle_state.add_task(
            repo=self.repo, feature_id="FEAT-migrate", task_id="TASK-blocked", title="Blocked work",
        )
        lifecycle_state.add_task(
            repo=self.repo, feature_id="FEAT-migrate", task_id="TASK-done", title="Completed work",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-migrate", task_id="TASK-blocked", status="blocked",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-migrate", task_id="TASK-done", status="in_progress",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-migrate", task_id="TASK-done", status="done",
        )
        self.git("checkout", "-b", "feature/migrated")
        head = self.git("rev-parse", "HEAD").stdout.strip()

        fixture = lifecycle_state.load(self.repo)
        target = fixture["features"]["FEAT-migrate"]
        target["validation"] = {
            "result": "fail", "command": "python -m unittest", "commit": head,
            "at": "2026-10-07T00:00:00Z",
        }
        target["review"] = {
            "decision": "approved", "by": "reviewer", "at": "2026-10-07T00:01:00Z",
        }
        lifecycle_state.state_path(self.repo).write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        before = lifecycle_state.load(self.repo)

        lifecycle_state.migrate_feature_branch(
            **self.migration_arguments(expected_head=head), at="2026-10-07T00:02:00Z",
        )
        after = lifecycle_state.load(self.repo)

        self.assertEqual(after["requirements"], before["requirements"])
        self.assertEqual(after["features"]["FEAT-other"], before["features"]["FEAT-other"])
        for field in ("id", "requirement_id", "status", "tasks", "engineering_context_ref", "validation", "review", "release", "created_at"):
            self.assertEqual(after["features"]["FEAT-migrate"][field], before["features"]["FEAT-migrate"][field])
        self.assertEqual(after["features"]["FEAT-migrate"]["branch"], "feature/migrated")
        self.assertEqual(after["features"]["FEAT-migrate"]["updated_at"], "2026-10-07T00:02:00Z")

    def test_migrate_feature_branch_rejects_closed_unknown_stale_and_repeated_requests(self) -> None:
        self.prepare_branch_migration()
        before = self.state_bytes()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-not-found:FEAT-unknown"):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(feature_id="FEAT-unknown"),
            )
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "feature-branch-does-not-match-expected:FEAT-migrate",
        ):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(expected_branch="feature/stale"),
            )
        self.git("branch", "feature/FEAT-migrate")
        self.git("checkout", "feature/FEAT-migrate")
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "feature-branch-migration-requires-new-branch",
        ):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(branch="feature/FEAT-migrate"),
            )
        self.git("checkout", "feature/migrated")
        self.assertEqual(self.state_bytes(), before)

        lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        after_success = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "feature-branch-does-not-match-expected:FEAT-migrate",
        ):
            lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(self.state_bytes(), after_success)

        closed = lifecycle_state.load(self.repo)
        closed["features"]["FEAT-migrate"]["status"] = "cancelled"
        closed["requirements"]["REQ-migrate"]["status"] = "cancelled"
        lifecycle_state.state_path(self.repo).write_text(
            json.dumps(closed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.git("checkout", "-b", "feature/next")
        closed_before = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "feature-not-open-for-branch-migration:FEAT-migrate",
        ):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(expected_branch="feature/migrated", branch="feature/next"),
            )
        self.assertEqual(self.state_bytes(), closed_before)

        released = lifecycle_state.load(self.repo)
        current_head = self.git("rev-parse", "HEAD").stdout.strip()
        released["features"]["FEAT-migrate"].update({
            "status": "released",
            "validation": {
                "result": "pass", "command": "python -m unittest", "commit": current_head,
                "at": "2026-10-07T00:03:00Z",
            },
            "review": {"decision": "approved", "by": "reviewer", "at": "2026-10-07T00:04:00Z"},
            "release": {"status": "released", "commit": current_head, "at": "2026-10-07T00:05:00Z"},
        })
        released["requirements"]["REQ-migrate"]["status"] = "released"
        lifecycle_state.state_path(self.repo).write_text(
            json.dumps(released, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        released_before = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "feature-not-open-for-branch-migration:FEAT-migrate",
        ):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(expected_branch="feature/migrated", branch="feature/next"),
            )
        self.assertEqual(self.state_bytes(), released_before)

    def test_migrate_feature_branch_rejects_unsafe_branch_identity_before_write(self) -> None:
        self.prepare_branch_migration()
        self.git("branch", "feature/not-current")
        before = self.state_bytes()
        for invalid_branch in ("invalid..branch", "@{-1}", "HEAD", "refs/heads/explicit"):
            with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "invalid-feature-branch"):
                lifecycle_state.migrate_feature_branch(
                    **self.migration_arguments(branch=invalid_branch),
                )
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "branch-migration-branch-not-current-checkout",
        ):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(branch="feature/not-current"),
            )
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "branch-migration-head-mismatch"):
            lifecycle_state.migrate_feature_branch(
                **self.migration_arguments(expected_head="0" * 40),
            )
        nested = self.repo / "nested"
        nested.mkdir()
        arguments = self.migration_arguments()
        arguments["repo"] = nested
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "branch-migration-repository-root-mismatch",
        ):
            lifecycle_state.migrate_feature_branch(**arguments)
        self.assertEqual(self.state_bytes(), before)

    def test_migrate_feature_branch_rejects_detached_and_unborn_checkouts_before_write(self) -> None:
        self.prepare_branch_migration()
        before = self.state_bytes()
        self.git("checkout", "--detach")
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "branch-migration-requires-attached-local-branch",
        ):
            lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(self.state_bytes(), before)

        unborn = self.base / "unborn"
        unborn.mkdir()
        subprocess.run(["git", "-C", str(unborn), "init"], check=True, capture_output=True, text=True)
        context = ".sdlc-v1/context/engineering-unborn.md"
        (unborn / context).parent.mkdir(parents=True)
        (unborn / context).write_text("# engineering\n", encoding="utf-8")
        lifecycle_state.initialize(unborn)
        lifecycle_state.capture_requirement(
            repo=unborn,
            requirement_id="REQ-unborn",
            title="Unborn repository",
            product_context_ref=context,
        )
        lifecycle_state.mark_requirement_ready(repo=unborn, requirement_id="REQ-unborn")
        lifecycle_state.start_feature(
            repo=unborn,
            requirement_id="REQ-unborn",
            feature_id="FEAT-unborn",
            branch="feature/FEAT-unborn",
            engineering_context_ref=context,
        )
        unborn_branch = subprocess.run(
            ["git", "-C", str(unborn), "symbolic-ref", "--short", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        unborn_before = (unborn / ".sdlc-v1/state.json").read_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "branch-migration-requires-head-commit",
        ):
            lifecycle_state.migrate_feature_branch(
                repo=unborn,
                feature_id="FEAT-unborn",
                expected_branch="feature/FEAT-unborn",
                branch=unborn_branch,
                expected_head="0" * 40,
                reason="unborn checkout is not migratable",
            )
        self.assertEqual((unborn / ".sdlc-v1/state.json").read_bytes(), unborn_before)

    def test_migrate_feature_branch_rejects_git_local_environment_before_write(self) -> None:
        self.prepare_branch_migration()
        arguments = self.migration_arguments()
        redirects = (
            ("GIT_INDEX_FILE", str(self.base / "other-index")),
            ("GIT_DIR", str(self.base / "other-git")),
            ("GIT_NAMESPACE", "other-namespace"),
            ("GIT_CONFIG_COUNT", "1"),
            ("GIT_CONFIG_KEY_0", "core.worktree"),
            ("GIT_CONFIG_VALUE_0", str(self.base / "other-worktree")),
        )
        for name, value in redirects:
            before = self.state_bytes()
            with mock.patch.dict(os.environ, {name: value}, clear=True):
                with self.assertRaisesRegex(
                    lifecycle_state.LifecycleStateError,
                    f"branch-migration-rejects-git-local-environment:{name}",
                ):
                    lifecycle_state.migrate_feature_branch(**arguments)
            self.assertEqual(self.state_bytes(), before)

        without_index_guard = lifecycle_state._GIT_LOCAL_ENVIRONMENT_VARIABLES - {"GIT_INDEX_FILE"}
        before_mutation_check = self.state_bytes()
        with mock.patch.object(lifecycle_state, "_GIT_LOCAL_ENVIRONMENT_VARIABLES", without_index_guard):
            with mock.patch.dict(
                os.environ,
                {"GIT_INDEX_FILE": str(self.base / "other-index")},
                clear=True,
            ):
                with mock.patch.object(
                    lifecycle_state,
                    "_repo_root",
                    side_effect=RuntimeError("index guard was bypassed"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "index guard was bypassed"):
                        lifecycle_state.migrate_feature_branch(**arguments)
        self.assertEqual(self.state_bytes(), before_mutation_check)

    def test_migrate_feature_branch_rejects_missing_context_staged_or_unmerged_state(self) -> None:
        self.prepare_branch_migration()
        valid_context = lifecycle_state.load(self.repo)
        missing_context = lifecycle_state.load(self.repo)
        missing_context["features"]["FEAT-migrate"]["engineering_context_ref"] = (
            ".sdlc-v1/context/missing.md"
        )
        lifecycle_state.state_path(self.repo).write_text(
            json.dumps(missing_context, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        before_missing = self.state_bytes()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "engineering-context-not-found"):
            lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(self.state_bytes(), before_missing)

        lifecycle_state.state_path(self.repo).write_text(
            json.dumps(valid_context, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        context_path = self.repo / ".sdlc-v1/context/engineering-FEAT-migrate.md"
        context_path.unlink()
        context_path.symlink_to(self.repo / "README.md")
        before_symlink = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "engineering-context-cannot-be-symlink",
        ):
            lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(self.state_bytes(), before_symlink)

    def test_migrate_feature_branch_rejects_staged_or_unmerged_state_before_write(self) -> None:
        self.prepare_branch_migration()
        self.git("add", ".sdlc-v1/state.json")
        before_staged = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "state-is-staged-commit-or-unstage-before-update",
        ):
            lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(self.state_bytes(), before_staged)

        self.git("read-tree", "HEAD")
        blob = self.git("hash-object", "-w", ".sdlc-v1/state.json").stdout.strip()
        entries = "".join(
            f"100644 {blob} {stage}\t.sdlc-v1/state.json\n" for stage in (1, 2, 3)
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "update-index", "--index-info"],
            input=entries, text=True, check=True, capture_output=True,
        )
        before_unmerged = self.state_bytes()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "state-has-unmerged-index-entries"):
            lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(self.state_bytes(), before_unmerged)

    def test_migrate_feature_branch_supports_a_linked_worktree(self) -> None:
        self.prepare_branch_migration()
        self.commit_state("share branch migration fixture")
        linked = self.base / "linked"
        self.git("worktree", "add", "-b", "feature/linked", str(linked))
        head = subprocess.run(
            ["git", "-C", str(linked), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

        result = lifecycle_state.migrate_feature_branch(
            repo=linked,
            feature_id="FEAT-migrate",
            expected_branch="feature/FEAT-migrate",
            branch="feature/linked",
            expected_head=head,
            reason="continue in the linked worktree",
        )

        self.assertEqual(result["repo_root"], str(linked.resolve()))
        self.assertEqual(result["new_branch"], "feature/linked")
        self.assertEqual(lifecycle_state.load(linked)["features"]["FEAT-migrate"]["branch"], "feature/linked")

    def test_migrate_feature_branch_rechecks_identity_inside_the_locked_operation(self) -> None:
        self.prepare_branch_migration()
        head = self.git("rev-parse", "HEAD").stdout.strip()
        identity = {"head": head, "repo_root": str(self.repo.resolve())}
        changed = {"head": "f" * 40, "repo_root": str(self.repo.resolve())}
        before = self.state_bytes()
        with mock.patch.object(
            lifecycle_state,
            "_current_branch_migration_identity",
            side_effect=[identity, identity, changed],
        ):
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError,
                "branch-migration-identity-changed-during-operation",
            ):
                lifecycle_state.migrate_feature_branch(**self.migration_arguments(expected_head=head))
        self.assertEqual(self.state_bytes(), before)

    def test_migrate_feature_branch_marks_postreplace_failures_as_recovery_cases(self) -> None:
        self.prepare_branch_migration()
        with mock.patch.object(lifecycle_state, "_sync_directory", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "cannot-write-state"):
                lifecycle_state.migrate_feature_branch(**self.migration_arguments())
        self.assertEqual(lifecycle_state.load(self.repo)["features"]["FEAT-migrate"]["branch"], "feature/migrated")

    def test_migrate_feature_branch_marks_output_failures_as_recovery_cases(self) -> None:
        self.prepare_branch_migration()
        arguments = self.migration_arguments()
        argv = [
            "--repo", str(self.repo), "migrate-feature-branch",
            "--feature-id", str(arguments["feature_id"]),
            "--expected-branch", str(arguments["expected_branch"]),
            "--branch", str(arguments["branch"]),
            "--expected-head", str(arguments["expected_head"]),
            "--reason", str(arguments["reason"]),
        ]
        with mock.patch.object(lifecycle_state, "_emit", side_effect=OSError("output failure")):
            with self.assertRaisesRegex(OSError, "output failure"):
                lifecycle_state.main(argv)
        self.assertEqual(lifecycle_state.load(self.repo)["features"]["FEAT-migrate"]["branch"], "feature/migrated")

    def test_migrate_feature_branch_cli_help_audit_and_two_writers(self) -> None:
        self.prepare_branch_migration()
        command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]
        help_result = subprocess.run(
            [*command, "migrate-feature-branch", "--help"], capture_output=True, text=True,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for option in ("--feature-id", "--expected-branch", "--branch", "--expected-head", "--reason", "--at"):
            self.assertIn(option, help_result.stdout)
        self.assertIn("not checkout code", help_result.stdout)
        self.assertIn("exact branch value currently stored", help_result.stdout)
        self.assertIn("already checked out", help_result.stdout)
        self.assertIn("full current commit ID", help_result.stdout)
        self.assertIn("pre-recorded migration decision", help_result.stdout)

        arguments = self.migration_arguments()
        migration_command = [
            *command,
            "migrate-feature-branch",
            "--feature-id", str(arguments["feature_id"]),
            "--expected-branch", str(arguments["expected_branch"]),
            "--branch", str(arguments["branch"]),
            "--expected-head", str(arguments["expected_head"]),
            "--reason", str(arguments["reason"]),
            "--at", "2026-10-07T00:00:00Z",
        ]
        first = subprocess.Popen(migration_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(migration_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        results = [process.communicate() + (process.returncode,) for process in (first, second)]
        return_codes = sorted(result[2] for result in results)
        self.assertEqual(return_codes, [0, 2])
        successful_output = next(stdout for stdout, _stderr, code in results if code == 0)
        audit = json.loads(successful_output)
        self.assertEqual(audit["operation"], "migrate-feature-branch")
        self.assertEqual(audit["old_branch"], "feature/FEAT-migrate")
        self.assertEqual(audit["new_branch"], "feature/migrated")
        self.assertEqual(audit["repo_root"], str(self.repo.resolve()))
        self.assertEqual(lifecycle_state.load(self.repo)["features"]["FEAT-migrate"]["branch"], "feature/migrated")

    def test_branch_migration_does_not_add_global_branch_rules_to_queries_or_delivery(self) -> None:
        self.initialize_state()
        self.capture("REQ-delivery")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-delivery")
        self.start("REQ-delivery", "FEAT-delivery")
        self.complete_one_task("FEAT-delivery")
        self.commit_state("ready for delivery checks")
        validated_head = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "--detach")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-delivery", result="pass")
        self.git("checkout", "-b", "release/FEAT-delivery")
        self.assertEqual(lifecycle_state.status(self.repo)["features"], 1)
        self.assertEqual(
            lifecycle_state.feature_projection(repo=self.repo, feature_id="FEAT-delivery")["feature"]["branch"],
            "feature/FEAT-delivery",
        )
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-delivery", decision="approved")
        self.git("checkout", "--detach")
        self.assertEqual(lifecycle_state.next_action(self.repo)["stage"], "ship")
        lifecycle_state.record_release(repo=self.repo, feature_id="FEAT-delivery", commit=validated_head)
        self.assertEqual(
            lifecycle_state.feature_projection(repo=self.repo, feature_id="FEAT-delivery")["feature"]["status"],
            "released",
        )

    def test_migration_to_a_different_implementation_cannot_bypass_approved_delivery(self) -> None:
        self.initialize_state()
        self.capture("REQ-protection")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-protection")
        self.start("REQ-protection", "FEAT-protection")
        self.complete_one_task("FEAT-protection")
        self.commit_state("ready for implementation protection")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-protection", result="pass")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-protection", decision="approved")
        self.git("checkout", "-b", "feature/migrated")
        (self.repo / "implementation.txt").write_text("different implementation\n", encoding="utf-8")
        self.git("add", "implementation.txt")
        self.git("commit", "-m", "implement different feature branch")
        different_head = self.git("rev-parse", "HEAD").stdout.strip()

        before_migration = lifecycle_state.feature_projection(
            repo=self.repo, feature_id="FEAT-protection",
        )["feature"]

        lifecycle_state.migrate_feature_branch(
            repo=self.repo,
            feature_id="FEAT-protection",
            expected_branch="feature/FEAT-protection",
            branch="feature/migrated",
            expected_head=different_head,
            reason="continue on the branch with the implementation",
        )
        after_migration = lifecycle_state.feature_projection(
            repo=self.repo, feature_id="FEAT-protection",
        )["feature"]
        for field in ("status", "tasks", "validation", "review", "release"):
            self.assertEqual(after_migration[field], before_migration[field])

        before_review = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "review-commit-does-not-match-validation",
        ):
            lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-protection", decision="approved")
        self.assertEqual(self.state_bytes(), before_review)

        before_release = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "release-commit-does-not-match-validation",
        ):
            lifecycle_state.record_release(repo=self.repo, feature_id="FEAT-protection")
        self.assertEqual(self.state_bytes(), before_release)


ACCEPTANCE_POINTS = ("spec_ready", "plan", "validation", "review")


class AcceptanceFingerprintTest(LifecycleFixture):
    """Behavior tests for the acceptance content fingerprint (REQ-SDLC-FINGERPRINT-001)."""

    def setUp(self) -> None:
        super().setUp()
        self.command = [sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(self.repo)]

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*self.command, *args], capture_output=True, text=True)

    def verify_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli("verify-acceptance", *args)

    def write_context(self, ref: str, content: str = "", *, raw: bytes | None = None) -> None:
        path = self.repo / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            path.write_bytes(raw)
        else:
            path.write_text(content, encoding="utf-8")

    def spec_document(
        self,
        *,
        updated_at: str = "2026-11-13T00:00:00Z",
        document_status: str = "captured",
        status_line: str = "- 文档状态：Requirement captured；正文定稿。",
        body_rule: str = "拒绝空值",
    ) -> str:
        return (
            "---\n"
            f"updated_at: {updated_at}\n"
            "status: draft\n"
            f"document_status: {document_status}\n"
            "owner: product-owner\n"
            "---\n"
            "# 产品规格\n"
            "\n"
            f"{status_line}\n"
            "\n"
            "## 验收条件\n"
            "\n"
            f"- 接受标准：{body_rule}\n"
        )

    def capture_documented(self, requirement_id: str, content: str) -> str:
        ref = f".sdlc-v1/context/product-{requirement_id}.md"
        self.write_context(ref, content)
        lifecycle_state.capture_requirement(
            repo=self.repo,
            requirement_id=requirement_id,
            title=f"Requirement {requirement_id}",
            product_context_ref=ref,
            at="2026-08-10T00:01:00Z",
        )
        return ref

    def deliver_through_validation(self, requirement_id: str, feature_id: str) -> tuple[str, str]:
        product_ref = self.capture(requirement_id)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id=requirement_id)
        engineering_ref = self.start(requirement_id, feature_id)
        self.complete_one_task(feature_id)
        self.commit_state("ready for delivery checks")
        lifecycle_state.record_validation(
            repo=self.repo, feature_id=feature_id, result="pass", command="python -m unittest",
        )
        return product_ref, engineering_ref

    def acceptance_of(self, requirement_id: str | None = None, feature_id: str | None = None) -> object:
        state = lifecycle_state.load(self.repo)
        if requirement_id is not None:
            return state["requirements"][requirement_id].get("acceptance")
        return state["features"][feature_id].get("acceptance")

    def assert_hex_digest(self, value: object) -> None:
        self.assertIsInstance(value, str)
        self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_spec_acceptance_binds_product_context_and_matches_initially(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-spec", self.spec_document())

        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-spec")
        result = self.run_cli("verify-acceptance", "--requirement-id", "REQ-spec")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["target_type"], "requirement")
        self.assertEqual(payload["target_id"], "REQ-spec")
        self.assertEqual(payload["result"], "match")
        self.assertEqual([point["point"] for point in payload["points"]], ["spec_ready"])
        entry = payload["points"][0]["files"][0]
        self.assertEqual(entry["path"], product_ref)
        self.assertEqual(entry["reason"], "match")
        self.assertEqual(entry["expected_digest"], entry["current_digest"])
        self.assert_hex_digest(entry["expected_digest"])

    def test_feature_default_points_bind_expected_reference_sets(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-points", "FEAT-points")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-points", decision="approved")

        result = self.run_cli("verify-acceptance", "--feature-id", "FEAT-points")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["target_type"], "feature")
        self.assertEqual(payload["result"], "match")
        self.assertEqual([point["point"] for point in payload["points"]], list(ACCEPTANCE_POINTS))
        file_counts = {point["point"]: len(point["files"]) for point in payload["points"]}
        self.assertEqual(file_counts, {"spec_ready": 1, "plan": 2, "validation": 2, "review": 2})
        plan_paths = {entry["path"] for entry in payload["points"][1]["files"]}
        self.assertEqual(plan_paths, {product_ref, engineering_ref})
        spec_paths = {entry["path"] for entry in payload["points"][0]["files"]}
        self.assertEqual(spec_paths, {product_ref})

    def test_unrelated_documents_do_not_affect_acceptance_results(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-unrelated", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-unrelated")
        other_ref = self.capture("REQ-other")
        (self.repo / "project.md").write_text("# project\n", encoding="utf-8")

        before = self.run_cli("verify-acceptance", "--requirement-id", "REQ-unrelated")
        self.write_context(other_ref, "# product-REQ-other changed\n")
        (self.repo / "project.md").write_text("# project changed\n", encoding="utf-8")
        after = self.run_cli("verify-acceptance", "--requirement-id", "REQ-unrelated")

        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(json.loads(before.stdout)["result"], "match")
        self.assertEqual(json.loads(after.stdout)["result"], "match")

    def test_content_drift_reports_stale_with_accurate_file_and_recovers(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-drift", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-drift")
        original = (self.repo / product_ref).read_bytes()

        self.write_context(product_ref, self.spec_document(body_rule="接受空值"))
        stale = self.verify_cli("--requirement-id", "REQ-drift")
        self.assertEqual(stale.returncode, 1, stale.stderr)
        payload = json.loads(stale.stdout)
        self.assertEqual(payload["result"], "stale")
        entry = payload["points"][0]["files"][0]
        self.assertEqual(entry["path"], product_ref)
        self.assertEqual(entry["reason"], "content-drift")
        self.assertNotEqual(entry["expected_digest"], entry["current_digest"])
        self.assert_hex_digest(entry["current_digest"])

        (self.repo / product_ref).write_bytes(original)
        recovered = self.verify_cli("--requirement-id", "REQ-drift")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(json.loads(recovered.stdout)["result"], "match")

    def test_deleted_bound_file_is_drift_not_error(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-deleted", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-deleted")
        (self.repo / product_ref).unlink()

        result = self.verify_cli("--requirement-id", "REQ-deleted")

        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"], "stale")
        entry = payload["points"][0]["files"][0]
        self.assertEqual(entry["reason"], "missing-file")
        self.assertIsNone(entry["current_digest"])
        self.assert_hex_digest(entry["expected_digest"])

    def test_reference_switch_is_observed_as_drift(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-switch", self.spec_document())
        other_ref = self.capture("REQ-switch-target")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-switch")
        state_path = lifecycle_state.state_path(self.repo)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-switch"]["product_context_ref"] = other_ref
        state_path.write_text(json.dumps(state), encoding="utf-8")

        result = self.verify_cli("--requirement-id", "REQ-switch")

        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"], "stale")
        reasons = {entry["path"]: entry["reason"] for entry in payload["points"][0]["files"]}
        self.assertEqual(reasons[other_ref], "ref-added")
        self.assertIn("ref-removed", reasons.values())

    def test_validation_and_review_points_record_only_on_pass_and_approved(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-record", "FEAT-record")
        self.assertIsNotNone(product_ref and engineering_ref)
        validated = self.verify_cli("--feature-id", "FEAT-record", "--point", "validation")
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(json.loads(validated.stdout)["points"][0]["result"], "match")

        lifecycle_state.record_review(
            repo=self.repo, feature_id="FEAT-record", decision="approved", by="owner",
        )
        approved = self.verify_cli("--feature-id", "FEAT-record", "--point", "review")
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertEqual(json.loads(approved.stdout)["points"][0]["result"], "match")

        # No fingerprint is produced by a failed validation or a rejection review.
        self.deliver_through_validation("REQ-negative", "FEAT-negative")
        lifecycle_state.record_review(
            repo=self.repo, feature_id="FEAT-negative", decision="changes_requested",
        )
        rejected = self.verify_cli("--feature-id", "FEAT-negative", "--point", "review")
        self.assertEqual(json.loads(rejected.stdout)["points"][0]["result"], "missing")
        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-negative", result="fail")
        failed = self.verify_cli("--feature-id", "FEAT-negative", "--point", "validation")
        self.assertEqual(failed.returncode, 0, failed.stderr)
        failed_payload = json.loads(failed.stdout)
        self.assertEqual(failed_payload["points"][0]["result"], "missing")
        self.assertEqual(failed_payload["points"][0]["files"], [])

    def test_metadata_line_exclusions_follow_the_documented_positions(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-normalize", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-normalize")

        def expect(payload_changes: dict, *, should_match: bool) -> None:
            self.write_context(product_ref, self.spec_document(**payload_changes))
            result = self.verify_cli("--requirement-id", "REQ-normalize")
            payload = json.loads(result.stdout)
            if should_match:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(payload["result"], "match", payload_changes)
            else:
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(payload["result"], "stale", payload_changes)

        expect({"updated_at": "2026-11-14T00:00:00Z"}, should_match=True)
        expect({"document_status": "ready"}, should_match=True)
        expect({"status_line": "- 文档状态：Requirement ready；正文定稿。"}, should_match=True)
        expect({"status_line": "**状态**：ready"}, should_match=True)
        expect({"updated_at": "2026-11-15T00:00:00Z", "document_status": "ready"}, should_match=True)
        expect({"body_rule": "接受空值"}, should_match=False)
        expect({"status_line": "owner: 改成别的键"}, should_match=False)

    def test_normalization_keeps_non_designated_metadata_and_structural_changes(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-keep", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-keep")

        # A same-named status line outside the designated region is content.
        drifted = self.spec_document().replace(
            "- 接受标准：拒绝空值\n",
            "- 接受标准：拒绝空值\n- 文档状态：混入正文的同名行\n",
        )
        self.write_context(product_ref, drifted)
        result = self.verify_cli("--requirement-id", "REQ-keep")
        self.assertEqual(json.loads(result.stdout)["result"], "stale")

        # Other frontmatter keys stay byte-sensitive.
        self.write_context(product_ref, self.spec_document().replace("owner: product-owner", "owner: someone-else"))
        self.assertEqual(json.loads(self.verify_cli("--requirement-id", "REQ-keep").stdout)["result"], "stale")

        # Line-ending changes on kept lines are drift.
        self.write_context(product_ref, self.spec_document().replace("- 接受标准：拒绝空值\n", "- 接受标准：拒绝空值\r\n"))
        self.assertEqual(json.loads(self.verify_cli("--requirement-id", "REQ-keep").stdout)["result"], "stale")
        self.write_context(product_ref, self.spec_document())

    def test_quoted_multiline_frontmatter_hides_no_metadata_like_lines(self) -> None:
        self.initialize_state()
        content = (
            "---\n"
            "title: \"产品规格第一行\n"
            "status: reject-empty\n"
            "第二行\"\n"
            "updated_at: 2026-11-13T00:00:00Z\n"
            "owner: product-owner\n"
            "---\n"
            "# 产品规格\n"
            "## 验收条件\n"
            "- 接受标准：拒绝空值\n"
        )
        product_ref = self.capture_documented("REQ-quoted", content)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-quoted")

        # The metadata-like line inside the quoted value is real content, not metadata.
        self.write_context(product_ref, content.replace("status: reject-empty", "status: accept-empty"))
        result = self.verify_cli("--requirement-id", "REQ-quoted")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "stale")

        # The designated top-level scalar after the quoted value is still excluded.
        self.write_context(product_ref, content.replace("2026-11-13", "2026-11-14"))
        recovered = self.verify_cli("--requirement-id", "REQ-quoted")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(json.loads(recovered.stdout)["result"], "match")

    def test_code_fence_examples_before_the_first_heading_stay_content(self) -> None:
        self.initialize_state()
        content = (
            "---\n"
            "updated_at: 2026-11-13T00:00:00Z\n"
            "status: draft\n"
            "document_status: captured\n"
            "owner: product-owner\n"
            "---\n"
            "```text\n"
            "# Example heading\n"
            "- 文档状态：示例（首标题前代码块内）\n"
            "```\n"
            "# 产品规格\n"
            "- 文档状态：Requirement captured；正文定稿。\n"
            "## 验收条件\n"
            "- 接受标准：拒绝空值\n"
        )
        product_ref = self.capture_documented("REQ-fence-head", content)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-fence-head")

        self.write_context(
            product_ref,
            content.replace("- 文档状态：示例（首标题前代码块内）", "- 文档状态：示例已修改"),
        )
        result = self.verify_cli("--requirement-id", "REQ-fence-head")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "stale")

        self.write_context(
            product_ref,
            content.replace(
                "- 文档状态：Requirement captured；正文定稿。", "- 文档状态：ready；正文定稿。",
            ),
        )
        recovered = self.verify_cli("--requirement-id", "REQ-fence-head")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(json.loads(recovered.stdout)["result"], "match")

    def test_code_fence_examples_inside_the_metadata_region_stay_content(self) -> None:
        self.initialize_state()
        content = (
            "---\n"
            "updated_at: 2026-11-13T00:00:00Z\n"
            "status: draft\n"
            "document_status: captured\n"
            "owner: product-owner\n"
            "---\n"
            "# 产品规格\n"
            "```text\n"
            "- 文档状态：示例（元数据区代码块内）\n"
            "```\n"
            "- 文档状态：Requirement captured；正文定稿。\n"
            "## 验收条件\n"
            "- 接受标准：拒绝空值\n"
        )
        product_ref = self.capture_documented("REQ-fence-region", content)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-fence-region")

        self.write_context(
            product_ref,
            content.replace("- 文档状态：示例（元数据区代码块内）", "- 文档状态：示例已修改"),
        )
        result = self.verify_cli("--requirement-id", "REQ-fence-region")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "stale")

        self.write_context(
            product_ref,
            content.replace(
                "- 文档状态：Requirement captured；正文定稿。", "- 文档状态：ready；正文定稿。",
            ),
        )
        recovered = self.verify_cli("--requirement-id", "REQ-fence-region")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(json.loads(recovered.stdout)["result"], "match")

    def test_plain_scalar_continuation_after_blank_line_is_content(self) -> None:
        self.initialize_state()
        content = (
            "---\nstatus: reject-empty\n\n  continuation\n"
            "updated_at: 2026-11-13\n---\n"
            "# Title\n- 文档状态：draft\n## Rules\nbody sentinel\n"
        )
        product_ref = self.capture_documented("REQ-blank-continuation", content)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-blank-continuation")

        for old, new in (("reject-empty", "accept-empty"), ("continuation", "changed")):
            with self.subTest(changed=old):
                self.write_context(product_ref, content.replace(old, new))
                result = self.verify_cli("--requirement-id", "REQ-blank-continuation")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(json.loads(result.stdout)["result"], "stale")

        expected = content.replace("updated_at: 2026-11-13\n", "").replace("- 文档状态：draft\n", "")
        self.assertEqual(lifecycle_state._normalize_context_v1(content), expected)

    def test_multiline_flow_nested_keys_are_content(self) -> None:
        self.initialize_state()
        content = (
            "---\nmeta: {\nquoted: \"} [ still quoted\",\n"
            "status: reject-empty\n}\nstatus: draft\n---\n"
            "# Title\n- 文档状态：draft\n## Rules\nbody sentinel\n"
        )
        product_ref = self.capture_documented("REQ-flow", content)
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-flow")

        for old, new, code, expected_result in (
            ("status: reject-empty", "status: accept-empty", 1, "stale"),
            ("status: draft", "status: ready", 0, "match"),
        ):
            with self.subTest(changed=old):
                self.write_context(product_ref, content.replace(old, new))
                result = self.verify_cli("--requirement-id", "REQ-flow")
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(json.loads(result.stdout)["result"], expected_result)

        expected = content.replace("status: draft\n", "").replace("- 文档状态：draft\n", "")
        self.assertEqual(lifecycle_state._normalize_context_v1(content), expected)

    def test_quoted_flow_keys_preserve_exact_normalized_content(self) -> None:
        for key in ('"meta:x"', '"meta#x"', '"meta\\\"#x"', "'meta''#x'"):
            for nested in ("reject-empty", "accept-empty"):
                with self.subTest(key=key, nested=nested):
                    content = (
                        f"---\n{key}: {{\nstatus: {nested}\n}}\nstatus: draft\n"
                        "---\n# Title\n\n## Rules\nkeep sentinel\n"
                    )
                    expected = content.replace("status: draft\n", "")
                    self.assertEqual(lifecycle_state._normalize_context_v1(content), expected)

    def test_quoted_flow_keys_detect_nested_drift_via_cli(self) -> None:
        self.initialize_state()
        for index, key in enumerate(('"meta:x"', '"meta#x"', '"meta\\\"#x"', "'meta''#x'")):
            requirement_id = f"REQ-quoted-flow-key-{index}"
            content = (
                f"---\n{key}: {{\nstatus: reject-empty\n}}\nstatus: draft\n"
                "---\n# Title\n\n## Rules\nkeep sentinel\n"
            )
            product_ref = self.capture_documented(requirement_id, content)
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id=requirement_id)
            for old, new, code, expected_result in (
                ("status: reject-empty", "status: accept-empty", 1, "stale"),
                ("status: draft", "status: ready", 0, "match"),
            ):
                with self.subTest(key=key, changed=old):
                    self.write_context(product_ref, content.replace(old, new))
                    result = self.verify_cli("--requirement-id", requirement_id)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["result"], expected_result)

    def test_invalid_backtick_info_does_not_open_fence(self) -> None:
        self.initialize_state()
        for index, invalid in enumerate(("```python```", "```lang`meta")):
            with self.subTest(invalid=invalid):
                content = (
                    f"# Title\n{invalid}\n```\n- 文档状态：code sentinel\n```\n"
                    "- 文档状态：draft\n## Rules\nbody sentinel\n"
                )
                requirement_id = f"REQ-invalid-fence-{index}"
                product_ref = self.capture_documented(requirement_id, content)
                lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id=requirement_id)
                self.write_context(product_ref, content.replace("code sentinel", "changed sentinel"))
                result = self.verify_cli("--requirement-id", requirement_id)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(json.loads(result.stdout)["result"], "stale")
                expected = content.replace("- 文档状态：draft\n", "")
                self.assertEqual(lifecycle_state._normalize_context_v1(content), expected)

        tilde = "# Title\n~~~lang`meta\n- 文档状态：code sentinel\n~~~\n- 文档状态：draft\n## Rules\nbody sentinel\n"
        self.assertEqual(
            lifecycle_state._normalize_context_v1(tilde),
            tilde.replace("- 文档状态：draft\n", ""),
        )

    def test_prefixed_containers_and_uncertain_scalars_are_preserved(self) -> None:
        normalize = lifecycle_state._normalize_context_v1
        for prefix in ("&anchor", "!custom"):
            for value in ("{\nstatus: nested\n}", '"first\nstatus: nested\nlast"'):
                with self.subTest(prefix=prefix, value=value):
                    content = f"---\nmeta: {prefix} {value}\nstatus: outer\n---\n# Title\n## Rules\nbody sentinel\n"
                    self.assertEqual(normalize(content), content.replace("status: outer\n", ""))

        for value in ("# comment only", "value: nested", "- nested", '"bad\\q"'):
            with self.subTest(value=value):
                content = f"---\nstatus: {value}\n---\n# Title\n## Rules\nbody sentinel\n"
                self.assertEqual(normalize(content), content)

    def test_ambiguous_frontmatter_contexts_keep_complete_body(self) -> None:
        normalize = lifecycle_state._normalize_context_v1
        for opening in ('meta: "unclosed', "meta: {"):
            with self.subTest(opening=opening):
                content = f"---\n{opening}\n---\n# Title\n- 文档状态：body sentinel\n## Rules\nlast sentinel\n"
                self.assertEqual(normalize(content), content)

        separated_flow = (
            "---\nmeta: &anchor\n  {\nstatus: nested\n  }\n"
            "status: outer\n---\n# Title\n## Rules\nbody sentinel\n"
        )
        self.assertEqual(normalize(separated_flow), separated_flow.replace("status: outer\n", ""))

        quoted_flow = (
            '---\nmeta: {\nkey: "first\n}\nstatus: inside quote\nlast",\n'
            "status: inside flow\n}\nstatus: outer\n---\n# Title\n## Rules\nbody sentinel\n"
        )
        self.assertEqual(normalize(quoted_flow), quoted_flow.replace("status: outer\n", ""))

    def test_normalization_unit_boundaries_are_conservative(self) -> None:
        normalize = lifecycle_state._normalize_context_v1

        def document(frontmatter: str, body: str) -> str:
            return f"---\n{frontmatter}---\n{body}"

        multiline_value = document(
            "updated_at: 2026-01-01T00:00:00Z\n  continued-from-previous\nstatus: draft\n",
            "# Title\n- 文档状态：区域行\n",
        )
        self.assertNotEqual(normalize(multiline_value), normalize(multiline_value.replace("continued-from-previous", "changed")))

        nested_key = document(
            "meta:\n  status: inner-value\nstatus: outer\n",
            "# Title\n- 文档状态：区域行\n",
        )
        self.assertNotEqual(normalize(nested_key), normalize(nested_key.replace("inner-value", "changed")))

        incomplete = "---\nupdated_at: 2026-01-01T00:00:00Z\n# Title\n- 文档状态：区域行\n"
        self.assertNotEqual(normalize(incomplete), normalize(incomplete.replace("2026-01-01", "2026-01-02")))

        no_heading = "updated_at: 2026-01-01T00:00:00Z\n- 文档状态：没有标题不豁免\n"
        self.assertNotEqual(normalize(no_heading), normalize(no_heading.replace("不豁免", "changed")))

        before_heading = "- 文档状态：标题之前不豁免\n# Title\n- 文档状态：区域行\n## Next\n"
        self.assertNotEqual(
            normalize(before_heading),
            normalize(before_heading.replace("标题之前不豁免", "changed")),
        )

        after_h2 = "# Title\n## Next\n- 文档状态：二级标题之后不豁免\n"
        self.assertNotEqual(normalize(after_h2), normalize(after_h2.replace("不豁免", "changed")))

        region = "# Title\n\n- 文档状态：区域行\n- 文档状态：另一行\n## Next\n正文\n"
        self.assertEqual(normalize(region), normalize(region.replace("区域行", "changed").replace("另一行", "changed2")))

    def test_frontmatter_quoted_multiline_values_keep_metadata_like_lines(self) -> None:
        normalize = lifecycle_state._normalize_context_v1

        quoted = (
            "---\n"
            "title: \"第一行\n"
            "status: reject-empty\n"
            "第二行\"\n"
            "updated_at: 2026-11-13T00:00:00Z\n"
            "owner: product-owner\n"
            "---\n"
            "# 产品规格\n"
            "## 验收条件\n"
            "- 接受标准：拒绝空值\n"
        )
        # A metadata-like line inside a cross-line quoted value stays byte-sensitive.
        self.assertNotEqual(
            normalize(quoted),
            normalize(quoted.replace("status: reject-empty", "status: accept-empty")),
        )
        # The genuine top-level scalar after the quoted value is still excluded.
        self.assertEqual(
            normalize(quoted),
            normalize(quoted.replace("2026-11-13", "2026-11-14")),
        )
        # A complete single-line quoted scalar remains excludable.
        closed = "---\nstatus: \"draft\"\n---\n# Title\n"
        self.assertEqual(normalize(closed), normalize(closed.replace("\"draft\"", "\"ready\"")))
        # Unclosed quoted values and flow collections stay conservatively kept.
        unclosed = "---\nstatus: \"draft\n---\n# Title\n"
        self.assertNotEqual(normalize(unclosed), normalize(unclosed.replace("\"draft", "\"ready")))
        flow = "---\nstatus: [a, b]\n---\n# Title\n"
        self.assertNotEqual(normalize(flow), normalize(flow.replace("[a, b]", "[a]")))

    def test_fenced_code_blocks_are_not_document_metadata(self) -> None:
        normalize = lifecycle_state._normalize_context_v1

        pre_heading = (
            "---\n"
            "updated_at: 2026-11-13T00:00:00Z\n"
            "---\n"
            "```text\n"
            "# Example heading\n"
            "## Example state\n"
            "- 文档状态：示例（首标题前代码块内）\n"
            "```\n"
            "# 产品规格\n"
            "- 文档状态：区域真行\n"
            "## 验收条件\n"
            "- 接受标准：拒绝空值\n"
        )
        self.assertNotEqual(
            normalize(pre_heading),
            normalize(pre_heading.replace("示例（首标题前代码块内）", "示例已修改")),
        )
        self.assertNotEqual(
            normalize(pre_heading),
            normalize(pre_heading.replace("# Example heading", "# Changed heading")),
        )
        self.assertEqual(
            normalize(pre_heading),
            normalize(pre_heading.replace("区域真行", "区域真行改")),
        )

        in_region = (
            "# 产品规格\n"
            "```text\n"
            "- 文档状态：示例（元数据区代码块内）\n"
            "**状态**：示例\n"
            "```\n"
            "- 文档状态：区域真行\n"
            "## 验收条件\n"
            "- 接受标准：拒绝空值\n"
        )
        self.assertNotEqual(
            normalize(in_region),
            normalize(in_region.replace("示例（元数据区代码块内）", "示例已修改")),
        )
        self.assertEqual(
            normalize(in_region),
            normalize(in_region.replace("区域真行", "区域真行改")),
        )

        variants = (
            "# 产品规格\n"
            "  ```python\n"
            "- 文档状态：缩进围栏内\n"
            "  ```\n"
            "~~~~~\n"
            "- 文档状态：长波浪线围栏内\n"
            "~~~\n"
            "- 文档状态：短波浪线不闭合围栏\n"
            "~~~~~\n"
            "- 文档状态：区域真行\n"
            "## Next\n"
        )
        self.assertNotEqual(normalize(variants), normalize(variants.replace("缩进围栏内", "改")))
        self.assertNotEqual(normalize(variants), normalize(variants.replace("长波浪线围栏内", "改")))
        self.assertNotEqual(normalize(variants), normalize(variants.replace("短波浪线不闭合围栏", "改")))
        self.assertEqual(normalize(variants), normalize(variants.replace("区域真行", "改")))

        unclosed = (
            "# 产品规格\n"
            "```text\n"
            "- 文档状态：未闭合围栏内\n"
            "## Next\n"
            "- 文档状态：围栏后的区域行\n"
        )
        self.assertNotEqual(normalize(unclosed), normalize(unclosed.replace("未闭合围栏内", "改")))
        # No exclusion survives an unterminated fence: conservatively keep every line.
        self.assertNotEqual(normalize(unclosed), normalize(unclosed.replace("围栏后的区域行", "改")))

    def test_invalid_utf8_context_is_a_clear_error_and_records_nothing(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-utf8", self.spec_document())
        self.write_context(product_ref, raw=b"# \xff\xfe invalid\n")

        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "context-not-valid-utf8",
        ):
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-utf8")
        self.assertEqual(self.acceptance_of(requirement_id="REQ-utf8"), None)
        self.assertEqual(
            lifecycle_state.load(self.repo)["requirements"]["REQ-utf8"]["status"], "captured",
        )

        # A query against a previously valid snapshot is an error, not a three-state result.
        self.write_context(product_ref, self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-utf8")
        self.write_context(product_ref, raw=b"# \xff\xfe invalid\n")
        result = self.verify_cli("--requirement-id", "REQ-utf8")
        self.assertEqual(result.returncode, 2)
        self.assertIn("context-not-valid-utf8", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_and_mixed_results_and_exit_codes(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-mixed", "FEAT-mixed")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-mixed", decision="approved")
        state_path = lifecycle_state.state_path(self.repo)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        del state["features"]["FEAT-mixed"]["acceptance"]["review"]
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )

        only_missing = self.run_cli("verify-acceptance", "--feature-id", "FEAT-mixed")
        self.assertEqual(only_missing.returncode, 0, only_missing.stderr)
        payload = json.loads(only_missing.stdout)
        self.assertEqual(payload["result"], "missing")
        self.assertEqual(payload["points"][3]["point"], "review")
        self.assertEqual(payload["points"][3]["result"], "missing")
        self.assertEqual(payload["points"][3]["files"], [])
        self.assertEqual({point["result"] for point in payload["points"][:3]}, {"match"})

        # A missing point must not mask another point's stale result.
        self.write_context(engineering_ref, "# engineering-FEAT-mixed drifted\n")
        mixed = self.run_cli("verify-acceptance", "--feature-id", "FEAT-mixed")
        self.assertEqual(mixed.returncode, 1, mixed.stderr)
        mixed_payload = json.loads(mixed.stdout)
        self.assertEqual(mixed_payload["result"], "stale")
        self.assertIn("missing", {point["result"] for point in mixed_payload["points"]})
        self.assertIsNotNone(product_ref)

    def test_invalid_selectors_and_unknown_targets_are_errors(self) -> None:
        self.initialize_state()
        self.capture("REQ-select")

        both = self.run_cli(
            "verify-acceptance", "--requirement-id", "REQ-select", "--feature-id", "FEAT-none",
        )
        self.assertEqual(both.returncode, 2)
        self.assertIn("not allowed with argument", both.stderr)
        neither = self.run_cli("verify-acceptance")
        self.assertEqual(neither.returncode, 2)
        self.assertIn("one of the arguments", neither.stderr)
        wrong_point = self.run_cli(
            "verify-acceptance", "--requirement-id", "REQ-select", "--point", "plan",
        )
        self.assertEqual(wrong_point.returncode, 2)
        self.assertIn("lifecycle-state-error: invalid-acceptance-point:plan", wrong_point.stderr)
        bogus_point = self.run_cli(
            "verify-acceptance", "--requirement-id", "REQ-select", "--point", "bogus",
        )
        self.assertEqual(bogus_point.returncode, 2)
        self.assertIn("invalid choice", bogus_point.stderr)
        unknown_feature = self.verify_cli("--feature-id", "FEAT-missing")
        self.assertEqual(unknown_feature.returncode, 2)
        self.assertIn("feature-not-found:FEAT-missing", unknown_feature.stderr)
        unknown_requirement = self.verify_cli("--requirement-id", "REQ-missing")
        self.assertEqual(unknown_requirement.returncode, 2)
        self.assertIn("requirement-not-found:REQ-missing", unknown_requirement.stderr)

    def test_corrupted_acceptance_records_are_state_errors_not_missing(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-corrupt", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-corrupt")
        snapshot = self.acceptance_of(requirement_id="REQ-corrupt")
        self.assertIsNotNone(snapshot)

        def rewrite(acceptance: dict) -> None:
            state_path = lifecycle_state.state_path(self.repo)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["requirements"]["REQ-corrupt"]["acceptance"] = acceptance
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            )

        unknown_point = dict(snapshot)
        unknown_point["bogus"] = dict(snapshot["spec_ready"])
        rewrite(unknown_point)
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "invalid-requirement-acceptance-fields"):
            lifecycle_state.load(self.repo)
        corrupted_query = self.verify_cli("--requirement-id", "REQ-corrupt")
        self.assertEqual(corrupted_query.returncode, 2)
        self.assertIn("invalid-requirement-acceptance-fields", corrupted_query.stderr)

        bad_digest = {"spec_ready": dict(snapshot["spec_ready"])}
        bad_digest["spec_ready"]["documents"] = dict(bad_digest["spec_ready"]["documents"])
        ref = next(iter(bad_digest["spec_ready"]["documents"]))
        bad_digest["spec_ready"]["documents"][ref] = "zz" * 32
        rewrite(bad_digest)
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "invalid-.*-digest"):
            lifecycle_state.load(self.repo)

        bad_algorithm = {"spec_ready": dict(snapshot["spec_ready"])}
        bad_algorithm["spec_ready"]["algorithm"] = "md5"
        rewrite(bad_algorithm)
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "invalid-.*-algorithm"):
            lifecycle_state.load(self.repo)

    def test_query_rejects_symlinked_bound_file(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-link", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-link")
        (self.repo / product_ref).unlink()
        (self.repo / product_ref).symlink_to(self.repo / "README.md")

        result = self.verify_cli("--requirement-id", "REQ-link")

        self.assertEqual(result.returncode, 2)
        self.assertIn("context-cannot-be-symlink", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_unconfirmed_context_existence_is_an_error_not_missing(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("context permission boundaries require a non-root runner")
        self.initialize_state()
        product_ref = self.capture_documented("REQ-permission", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-permission")
        context_directory = self.repo / ".sdlc-v1/context"
        context_directory.chmod(0o000)
        try:
            # A query cannot pretend an unreadable path is a missing file.
            result = self.verify_cli("--requirement-id", "REQ-permission")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("cannot-confirm-context", result.stderr)
            self.assertEqual(result.stdout, "")

            # The record path reports the same access failure and records nothing.
            before = self.state_bytes()
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "cannot-confirm-context",
            ):
                lifecycle_state.mark_requirement_ready(
                    repo=self.repo, requirement_id="REQ-permission", refresh_acceptance=True,
                )
            self.assertEqual(self.state_bytes(), before)
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "product-context-cannot-confirm",
            ):
                lifecycle_state.capture_requirement(
                    repo=self.repo, requirement_id="REQ-permission-second", title="Second",
                    product_context_ref=product_ref,
                )
            self.assertEqual(self.state_bytes(), before)
        finally:
            context_directory.chmod(0o755)

    def test_query_is_read_only_and_initializes_nothing(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-readonly", "FEAT-readonly")

        def repo_snapshot() -> dict[str, bytes]:
            listing: dict[str, bytes] = {}
            for path in sorted(self.repo.rglob("*")):
                relative = path.relative_to(self.repo).as_posix()
                if relative.startswith(".git/"):
                    continue
                if path.is_file():
                    listing[relative] = path.read_bytes()
            return listing

        before_files = repo_snapshot()
        match_result = self.run_cli("verify-acceptance", "--feature-id", "FEAT-readonly")
        self.assertEqual(match_result.returncode, 0, match_result.stderr)
        self.assertEqual(repo_snapshot(), before_files)

        self.write_context(engineering_ref, "# engineering-FEAT-readonly drifted\n")
        before_stale_files = repo_snapshot()
        stale_result = self.run_cli("verify-acceptance", "--feature-id", "FEAT-readonly")
        self.assertEqual(stale_result.returncode, 1, stale_result.stderr)
        self.assertEqual(repo_snapshot(), before_stale_files)
        self.assertIsNotNone(product_ref)

        uninitialized = self.base / "empty-repo"
        test_support.initialize_git_repo(uninitialized, readme="fresh\n")
        result = subprocess.run(
            [
                sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(uninitialized),
                "verify-acceptance", "--requirement-id", "REQ-anything",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("state-not-initialized", result.stderr)
        self.assertFalse((uninitialized / ".sdlc-v1").exists())

    def test_old_state_is_read_without_backfill_and_extensions_round_trip(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-legacy", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-legacy")
        state_path = lifecycle_state.state_path(self.repo)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        del state["requirements"]["REQ-legacy"]["acceptance"]
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        self.assertEqual(lifecycle_state.load(self.repo)["state_version"], 3)

        missing = self.verify_cli("--requirement-id", "REQ-legacy")
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertEqual(json.loads(missing.stdout)["result"], "missing")

        # Unrelated mutations must not backfill removed fingerprints.
        lifecycle_state.capture_requirement(
            repo=self.repo, requirement_id="REQ-second", title="Second",
            product_context_ref=self.context("product-REQ-second"),
        )
        loaded = lifecycle_state.load(self.repo)
        self.assertNotIn("acceptance", loaded["requirements"]["REQ-legacy"])
        self.assertNotIn("acceptance", loaded["requirements"]["REQ-second"])
        self.assertEqual(loaded["state_version"], 3)

        # A state carrying optional acceptance fields round-trips unchanged.
        self.capture_documented("REQ-roundtrip", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-roundtrip")
        before = lifecycle_state.load(self.repo)["requirements"]["REQ-roundtrip"]["acceptance"]
        lifecycle_state.capture_requirement(
            repo=self.repo, requirement_id="REQ-third", title="Third",
            product_context_ref=self.context("product-REQ-third"),
        )
        after = lifecycle_state.load(self.repo)["requirements"]["REQ-roundtrip"]["acceptance"]
        self.assertEqual(after, before)

    def test_feature_records_do_not_crosstalk(self) -> None:
        self.initialize_state()
        product_a, engineering_a = self.deliver_through_validation("REQ-a", "FEAT-a")
        product_b = self.capture("REQ-b")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-b")
        engineering_b = self.start("REQ-b", "FEAT-b")

        results_a = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-a").stdout)["points"]
        }
        self.assertEqual(results_a["validation"], "match")
        results_b = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-b").stdout)["points"]
        }
        self.assertEqual(results_b["plan"], "match")
        self.assertEqual(results_b["validation"], "missing")

        self.write_context(engineering_a, "# engineering-FEAT-a drifted\n")
        results_a = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-a").stdout)["points"]
        }
        results_b = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-b").stdout)["points"]
        }
        self.assertEqual(results_a["validation"], "stale")
        self.assertEqual(results_b["plan"], "match")
        self.assertIsNotNone(product_a and product_b)

    def test_revoked_pass_records_revoke_their_snapshots(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-revoke", "FEAT-revoke")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-revoke", decision="approved", by="owner")
        approved = json.loads(self.verify_cli("--feature-id", "FEAT-revoke").stdout)
        self.assertEqual({point["point"]: point["result"] for point in approved["points"]},
                         dict.fromkeys(ACCEPTANCE_POINTS, "match"))

        # Re-validation revokes the review approval and refreshes the validation fingerprint.
        self.write_context(engineering_ref, "# engineering-FEAT-revoke revised\n")
        lifecycle_state.record_validation(
            repo=self.repo, feature_id="FEAT-revoke", result="pass", command="python -m unittest",
        )
        after_revalidation = json.loads(self.verify_cli("--feature-id", "FEAT-revoke").stdout)
        results = {point["point"]: point["result"] for point in after_revalidation["points"]}
        self.assertEqual(results["validation"], "match")
        self.assertEqual(results["review"], "missing")
        self.assertEqual(results["plan"], "stale")

        lifecycle_state.record_validation(repo=self.repo, feature_id="FEAT-revoke", result="fail")
        failed = json.loads(self.verify_cli("--feature-id", "FEAT-revoke", "--point", "validation").stdout)
        self.assertEqual(failed["points"][0]["result"], "missing")

        lifecycle_state.record_validation(
            repo=self.repo, feature_id="FEAT-revoke", result="pass", command="python -m unittest",
        )
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-revoke", decision="approved", by="owner")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-revoke", decision="changes_requested")
        review_missing = json.loads(self.verify_cli("--feature-id", "FEAT-revoke", "--point", "review").stdout)
        validation_kept = json.loads(self.verify_cli("--feature-id", "FEAT-revoke", "--point", "validation").stdout)
        self.assertEqual(review_missing["points"][0]["result"], "missing")
        self.assertEqual(validation_kept["points"][0]["result"], "match")
        self.assertIsNotNone(product_ref)

    def test_task_reopen_clears_validation_and_review_snapshots_but_keeps_plan(self) -> None:
        self.initialize_state()
        self.deliver_through_validation("REQ-reopen-fp", "FEAT-reopen-fp")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-reopen-fp", decision="approved", by="owner")
        before_plan = self.acceptance_of(feature_id="FEAT-reopen-fp")["plan"]

        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-reopen-fp", task_id="TASK-one", status="todo",
        )

        acceptance = self.acceptance_of(feature_id="FEAT-reopen-fp")
        self.assertEqual(acceptance["plan"], before_plan)
        self.assertNotIn("validation", acceptance)
        self.assertNotIn("review", acceptance)
        results = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-reopen-fp").stdout)["points"]
        }
        self.assertEqual(
            results,
            {"spec_ready": "match", "plan": "match", "validation": "missing", "review": "missing"},
        )

    def test_refresh_acceptance_updates_spec_snapshot_after_renewed_approval(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-refresh", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-refresh")
        original_digest = self.acceptance_of(requirement_id="REQ-refresh")["spec_ready"]["documents"][product_ref]

        # Without the flag the existing preconditions stay unchanged.
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "requirement-not-captured"):
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-refresh")

        self.write_context(product_ref, self.spec_document(body_rule="接受空值"))
        refreshed = lifecycle_state.mark_requirement_ready(
            repo=self.repo, requirement_id="REQ-refresh", refresh_acceptance=True,
        )
        self.assertEqual(refreshed["requirement"]["status"], "ready")
        new_digest = self.acceptance_of(requirement_id="REQ-refresh")["spec_ready"]["documents"][product_ref]
        self.assertNotEqual(new_digest, original_digest)
        result = json.loads(self.verify_cli("--requirement-id", "REQ-refresh").stdout)
        self.assertEqual(result["result"], "match")

        # Refreshing a requirement without an existing snapshot cannot backfill history.
        self.capture("REQ-no-snapshot")
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "acceptance-snapshot-missing:REQ-no-snapshot/spec_ready",
        ):
            lifecycle_state.mark_requirement_ready(
                repo=self.repo, requirement_id="REQ-no-snapshot", refresh_acceptance=True,
            )

    def test_refresh_acceptance_rerecords_spec_after_delivery_started(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-refresh-live", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-refresh-live")
        self.start("REQ-refresh-live", "FEAT-refresh-live")
        before = lifecycle_state.load(self.repo)
        original_digest = (
            self.acceptance_of(requirement_id="REQ-refresh-live")["spec_ready"]["documents"][product_ref]
        )

        self.write_context(product_ref, self.spec_document(body_rule="接受空值"))
        refreshed = self.run_cli(
            "mark-requirement-ready", "--requirement-id", "REQ-refresh-live", "--refresh-acceptance",
        )
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)

        after = lifecycle_state.load(self.repo)
        self.assertEqual(after["requirements"]["REQ-refresh-live"]["status"], "in_delivery")
        self.assertEqual(after["features"]["FEAT-refresh-live"], before["features"]["FEAT-refresh-live"])
        self.assertEqual(
            after["features"]["FEAT-refresh-live"]["acceptance"]["plan"],
            before["features"]["FEAT-refresh-live"]["acceptance"]["plan"],
        )
        new_digest = (
            self.acceptance_of(requirement_id="REQ-refresh-live")["spec_ready"]["documents"][product_ref]
        )
        self.assertNotEqual(new_digest, original_digest)

        # The refreshed spec point matches while the untouched plan point stays visibly stale.
        results = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-refresh-live").stdout)["points"]
        }
        self.assertEqual(results["spec_ready"], "match")
        self.assertEqual(results["plan"], "stale")

        # Closed requirements stay closed for refresh.
        state_path = lifecycle_state.state_path(self.repo)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-refresh-live"]["status"] = "cancelled"
        state["features"]["FEAT-refresh-live"]["status"] = "cancelled"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        before_cancelled = self.state_bytes()
        with self.assertRaisesRegex(
            lifecycle_state.LifecycleStateError, "requirement-not-open-for-refresh",
        ):
            lifecycle_state.mark_requirement_ready(
                repo=self.repo, requirement_id="REQ-refresh-live", refresh_acceptance=True,
            )
        self.assertEqual(self.state_bytes(), before_cancelled)

    def test_refresh_acceptance_updates_plan_snapshot_without_touching_downstream(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-plan-refresh", "FEAT-plan-refresh")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-plan-refresh", decision="approved", by="owner")
        before = lifecycle_state.load(self.repo)

        self.write_context(engineering_ref, "# engineering-FEAT-plan-refresh revised\n")
        lifecycle_state.start_feature(
            repo=self.repo,
            requirement_id="REQ-plan-refresh",
            feature_id="FEAT-plan-refresh",
            branch="feature/FEAT-plan-refresh",
            engineering_context_ref=engineering_ref,
            refresh_acceptance=True,
        )
        after = lifecycle_state.load(self.repo)
        refreshed_feature = after["features"]["FEAT-plan-refresh"]
        self.assertEqual(refreshed_feature["tasks"], before["features"]["FEAT-plan-refresh"]["tasks"])
        self.assertEqual(refreshed_feature["status"], "reviewed")
        self.assertEqual(
            refreshed_feature["validation"], before["features"]["FEAT-plan-refresh"]["validation"],
        )
        self.assertEqual(refreshed_feature["review"], before["features"]["FEAT-plan-refresh"]["review"])
        self.assertEqual(refreshed_feature["release"], before["features"]["FEAT-plan-refresh"]["release"])
        self.assertEqual(after["requirements"]["REQ-plan-refresh"]["feature_id"], "FEAT-plan-refresh")
        self.assertEqual(after["requirements"]["REQ-plan-refresh"]["status"], "validated")

        results = {
            point["point"]: point["result"]
            for point in json.loads(self.verify_cli("--feature-id", "FEAT-plan-refresh").stdout)["points"]
        }
        self.assertEqual(results["plan"], "match")
        self.assertEqual(results["validation"], "stale")
        self.assertEqual(results["review"], "stale")
        self.assertEqual(results["spec_ready"], "match")
        self.assertIsNotNone(product_ref)

    def test_refresh_acceptance_rejects_identity_mismatch_and_closed_targets(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-guard", "FEAT-guard")
        self.capture("REQ-other")
        self.write_context(".sdlc-v1/context/engineering-other.md", "# engineering-other\n")
        before = self.state_bytes()

        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-identity-mismatch:FEAT-guard"):
            lifecycle_state.start_feature(
                repo=self.repo, requirement_id="REQ-guard", feature_id="FEAT-guard",
                branch="feature/other", engineering_context_ref=engineering_ref, refresh_acceptance=True,
            )
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-identity-mismatch:FEAT-guard"):
            lifecycle_state.start_feature(
                repo=self.repo, requirement_id="REQ-guard", feature_id="FEAT-guard",
                branch="feature/FEAT-guard",
                engineering_context_ref=".sdlc-v1/context/engineering-other.md", refresh_acceptance=True,
            )
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-identity-mismatch:FEAT-guard"):
            lifecycle_state.start_feature(
                repo=self.repo, requirement_id="REQ-other", feature_id="FEAT-guard",
                branch="feature/FEAT-guard", engineering_context_ref=engineering_ref, refresh_acceptance=True,
            )
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-not-found:FEAT-new"):
            lifecycle_state.start_feature(
                repo=self.repo, requirement_id="REQ-guard", feature_id="FEAT-new",
                branch="feature/FEAT-new", engineering_context_ref=engineering_ref, refresh_acceptance=True,
            )

        state_path = lifecycle_state.state_path(self.repo)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["features"]["FEAT-guard"]["status"] = "cancelled"
        state["requirements"]["REQ-guard"]["status"] = "cancelled"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        before_cancelled = self.state_bytes()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "feature-not-open-for-refresh:FEAT-guard"):
            lifecycle_state.start_feature(
                repo=self.repo, requirement_id="REQ-guard", feature_id="FEAT-guard",
                branch="feature/FEAT-guard", engineering_context_ref=engineering_ref, refresh_acceptance=True,
            )
        self.assertEqual(self.state_bytes(), before_cancelled)

    def test_cli_help_documents_refresh_and_verify(self) -> None:
        ready_help = self.run_cli("mark-requirement-ready", "--help")
        self.assertEqual(ready_help.returncode, 0, ready_help.stderr)
        self.assertIn("--refresh-acceptance", ready_help.stdout)
        start_help = self.run_cli("start-feature", "--help")
        self.assertEqual(start_help.returncode, 0, start_help.stderr)
        self.assertIn("--refresh-acceptance", start_help.stdout)
        verify_help = self.run_cli("verify-acceptance", "--help")
        self.assertEqual(verify_help.returncode, 0, verify_help.stderr)
        for option in ("--requirement-id", "--feature-id", "--point"):
            self.assertIn(option, verify_help.stdout)

    def test_byte_identical_clone_matches_and_active_checkout_drift_is_visible(self) -> None:
        self.initialize_state()
        product_ref, engineering_ref = self.deliver_through_validation("REQ-clone", "FEAT-clone")
        lifecycle_state.record_review(repo=self.repo, feature_id="FEAT-clone", decision="approved", by="owner")
        self.commit_state("share fingerprints")
        remote = self.base / "fingerprint-remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "HEAD")
        clone = self.base / "fingerprint-clone"
        subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True, text=True)

        clone_command = [
            sys.executable, str(HERE / "lifecycle_state.py"), "--repo", str(clone),
            "verify-acceptance", "--feature-id", "FEAT-clone",
        ]
        clone_match = subprocess.run(clone_command, capture_output=True, text=True)
        self.assertEqual(clone_match.returncode, 0, clone_match.stderr)
        self.assertEqual(json.loads(clone_match.stdout)["result"], "match")

        (clone / engineering_ref).write_text("# engineering-FEAT-clone drifted in clone\n", encoding="utf-8")
        clone_stale = subprocess.run(clone_command, capture_output=True, text=True)
        self.assertEqual(clone_stale.returncode, 1, clone_stale.stderr)
        self.assertEqual(json.loads(clone_stale.stdout)["result"], "stale")

        origin_match = self.run_cli("verify-acceptance", "--feature-id", "FEAT-clone")
        self.assertEqual(origin_match.returncode, 0, origin_match.stderr)
        self.assertEqual(json.loads(origin_match.stdout)["result"], "match")
        self.assertIsNotNone(product_ref)

    def test_branch_migration_preserves_snapshots(self) -> None:
        self.prepare_branch_migration()
        before = lifecycle_state.load(self.repo)["features"]["FEAT-migrate"]["acceptance"]
        self.assertIn("plan", before)

        lifecycle_state.migrate_feature_branch(**self.migration_arguments(), at="2026-10-07T00:00:00Z")

        after = lifecycle_state.load(self.repo)
        self.assertEqual(after["features"]["FEAT-migrate"]["acceptance"], before)
        result = json.loads(self.verify_cli("--feature-id", "FEAT-migrate").stdout)
        self.assertEqual(result["points"][1]["point"], "plan")
        self.assertEqual(result["points"][1]["result"], "match")

    def test_record_detects_context_change_between_reads_without_sleep(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-race", self.spec_document())
        before = self.state_bytes()
        with mock.patch.object(
            lifecycle_state, "_read_context_bytes",
            side_effect=[b"first version\n", b"second version\n"],
        ):
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "context-changed-during-snapshot",
            ):
                lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-race")
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(lifecycle_state.load(self.repo)["requirements"]["REQ-race"]["status"], "captured")

    def test_record_rejects_replaced_context_file_between_reads(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-swap", self.spec_document())
        before = self.state_bytes()
        original_build = lifecycle_state._build_acceptance_snapshot

        def build_then_swap_files(root: Path, refs: list[str], *, at: str) -> tuple:
            snapshot, raw_digests, identities = original_build(root, refs, at=at)
            for ref in refs:
                path = root / ref
                handle, name = tempfile.mkstemp(prefix=".swap-", dir=str(path.parent))
                temporary = Path(name)
                try:
                    with os.fdopen(handle, "wb") as stream:
                        stream.write(path.read_bytes())
                    os.replace(temporary, path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            return snapshot, raw_digests, identities

        # Same bytes, different file identity: the record must still be rejected.
        with mock.patch.object(
            lifecycle_state, "_build_acceptance_snapshot", side_effect=build_then_swap_files,
        ):
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "context-changed-during-snapshot",
            ):
                lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-swap")
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(
            lifecycle_state.load(self.repo)["requirements"]["REQ-swap"]["status"], "captured",
        )

    def test_record_review_detects_change_between_reads_without_sleep(self) -> None:
        self.initialize_state()
        self.deliver_through_validation("REQ-review-race", "FEAT-review-race")
        before = self.state_bytes()
        with mock.patch.object(
            lifecycle_state, "_read_context_bytes",
            side_effect=[b"product\n", b"engineering\n", b"product-changed\n", b"engineering\n"],
        ):
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "context-changed-during-snapshot",
            ):
                lifecycle_state.record_review(
                    repo=self.repo, feature_id="FEAT-review-race", decision="approved", by="owner",
                )
        self.assertEqual(self.state_bytes(), before)

    def test_record_failure_leaves_state_unchanged(self) -> None:
        self.initialize_state()
        product_ref = self.capture_documented("REQ-readfail", self.spec_document())
        state_path = lifecycle_state.state_path(self.repo)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-readfail"]["product_context_ref"] = ".sdlc-v1/context/nowhere.md"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        before = self.state_bytes()
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "context-not-found"):
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-readfail")
        self.assertEqual(self.state_bytes(), before)

        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["requirements"]["REQ-readfail"]["product_context_ref"] = product_ref
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        before_symlink = self.state_bytes()
        (self.repo / product_ref).unlink()
        (self.repo / product_ref).symlink_to(self.repo / "README.md")
        with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "context-cannot-be-symlink"):
            lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-readfail")
        self.assertEqual(self.state_bytes(), before_symlink)

    def test_query_detects_change_during_read(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-qrace", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-qrace")
        before = self.state_bytes()
        with mock.patch.object(
            lifecycle_state, "_read_verification_context_bytes",
            side_effect=[b"first\n", b"second\n"],
        ):
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "context-changed-during-verification",
            ):
                lifecycle_state.verify_acceptance(repo=self.repo, requirement_id="REQ-qrace")
        self.assertEqual(self.state_bytes(), before)

    def test_query_reports_vanished_file_between_reads_as_change(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-vanish", self.spec_document())
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-vanish")
        before = self.state_bytes()
        with mock.patch.object(
            lifecycle_state, "_read_verification_context_bytes",
            side_effect=[b"first\n", None],
        ):
            with self.assertRaisesRegex(
                lifecycle_state.LifecycleStateError, "context-changed-during-verification",
            ):
                lifecycle_state.verify_acceptance(repo=self.repo, requirement_id="REQ-vanish")
        self.assertEqual(self.state_bytes(), before)

        # The CLI entry surfaces the same deterministic race as a lifecycle error.
        with mock.patch.object(
            lifecycle_state, "_read_verification_context_bytes",
            side_effect=[b"first\n", None],
        ):
            with mock.patch.object(sys, "stderr", new=io.StringIO()) as stderr:
                code = lifecycle_state.main([
                    "--repo", str(self.repo), "verify-acceptance", "--requirement-id", "REQ-vanish",
                ])
        self.assertEqual(code, 2)
        self.assertIn("lifecycle-state-error: context-changed-during-verification", stderr.getvalue())

    def test_postreplace_failure_keeps_existing_recovery_semantics(self) -> None:
        self.initialize_state()
        self.capture_documented("REQ-postreplace", self.spec_document())
        with mock.patch.object(lifecycle_state, "_sync_directory", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(lifecycle_state.LifecycleStateError, "cannot-write-state"):
                lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-postreplace")
        loaded = lifecycle_state.load(self.repo)
        self.assertEqual(loaded["requirements"]["REQ-postreplace"]["status"], "ready")
        self.assertIn("spec_ready", loaded["requirements"]["REQ-postreplace"]["acceptance"])


if __name__ == "__main__":
    unittest.main()
