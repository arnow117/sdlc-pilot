#!/usr/bin/env python3
"""Contract tests for the Git-tracked lightweight lifecycle state."""
from __future__ import annotations

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


class LifecycleStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "user.name", "SDLC tests")
        (self.repo / "README.md").write_text("test repository\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "initial")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True,
        )

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


if __name__ == "__main__":
    unittest.main()
