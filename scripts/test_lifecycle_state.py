#!/usr/bin/env python3
"""Contract tests for the Git-tracked lightweight lifecycle state."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
