#!/usr/bin/env python3
"""Tests for state-only backlog and board projections."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backlog  # noqa: E402
import lifecycle_state  # noqa: E402


class BacklogProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "user.name", "SDLC tests")
        (self.repo / "README.md").write_text("backlog tests\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "initial")
        lifecycle_state.initialize(self.repo, at="2026-08-10T00:00:00Z")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True,
        )

    def context(self, name: str) -> str:
        relative = f".sdlc-v1/context/{name}.md"
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
        return relative

    def capture(
        self, requirement_id: str, *, title: str | None = None, domain: str = "general", priority: str = "P2",
    ) -> str:
        ref = self.context(f"{requirement_id}.product")
        lifecycle_state.capture_requirement(
            repo=self.repo,
            requirement_id=requirement_id,
            title=title or requirement_id,
            domain=domain,
            priority=priority,
            product_context_ref=ref,
        )
        return ref

    def start(self, requirement_id: str, feature_id: str) -> str:
        ref = self.context(f"{feature_id}.engineering")
        lifecycle_state.start_feature(
            repo=self.repo,
            requirement_id=requirement_id,
            feature_id=feature_id,
            branch=f"feature/{feature_id}",
            engineering_context_ref=ref,
        )
        return ref

    def commit_state(self) -> None:
        self.git("add", ".sdlc-v1")
        self.git("commit", "-m", "update lifecycle state")

    def run_backlog(self, command: str, *args: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        target = self.repo if root is None else root
        return subprocess.run(
            [
                sys.executable,
                str(HERE / "backlog.py"),
                command,
                "--root",
                str(target),
                *args,
            ],
            capture_output=True,
            text=True,
        )

    def test_readyqueue_uses_only_lifecycle_state_and_priority_order(self) -> None:
        old_tree = self.repo / ".sdlc/requirements/old/domain"
        old_tree.mkdir(parents=True)
        (old_tree / "OLD.md").write_text("---\nid: OLD\nstatus: captured\n---\n", encoding="utf-8")
        self.capture("REQ-low", priority="P2")
        self.capture("REQ-high", priority="P0")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-low")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-high")

        result = self.run_backlog("readyqueue", root=old_tree)
        self.assertEqual(result.returncode, 0, result.stderr)
        items = json.loads(result.stdout)
        self.assertEqual([item["requirement_id"] for item in items], ["REQ-high", "REQ-low"])
        self.assertNotIn("OLD", result.stdout)

    def test_coverage_and_tree_are_state_projections(self) -> None:
        self.capture("REQ-billing", domain="billing", priority="P1")
        self.capture("REQ-report", domain="reporting")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-billing")
        self.start("REQ-billing", "FEAT-billing")
        lifecycle_state.add_task(
            repo=self.repo, feature_id="FEAT-billing", task_id="TASK-api", title="Add API",
        )

        coverage = self.run_backlog("coverage")
        self.assertEqual(coverage.returncode, 0, coverage.stderr)
        coverage_data = json.loads(coverage.stdout)
        self.assertEqual(coverage_data["total"], 2)
        self.assertEqual(coverage_data["domains"]["billing"]["by_status"]["in_delivery"], 1)

        tree = self.run_backlog("tree")
        self.assertEqual(tree.returncode, 0, tree.stderr)
        tree_data = json.loads(tree.stdout)
        billing = next(item for item in tree_data["domains"] if item["domain"] == "billing")
        feature = billing["requirements"][0]["feature"]
        self.assertEqual(feature["feature_id"], "FEAT-billing")
        self.assertEqual(feature["tasks"][0]["id"], "TASK-api")

    def test_lint_checks_only_cross_clone_files(self) -> None:
        product_ref = self.capture("REQ-lint")
        untracked = self.run_backlog("lint")
        self.assertEqual(untracked.returncode, 1)
        self.assertIn("untracked:.sdlc-v1/state.json", untracked.stderr)
        self.assertIn(f"untracked:{product_ref}", untracked.stderr)

        self.commit_state()
        clean = self.run_backlog("lint")
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(clean.stdout.strip(), "lint: clean")

        (self.repo / product_ref).unlink()
        missing = self.run_backlog("lint")
        self.assertEqual(missing.returncode, 1)
        self.assertIn(f"missing-context:{product_ref}", missing.stderr)

    def test_board_renders_requirement_feature_and_tasks_with_html_escaping(self) -> None:
        self.capture("REQ-board", title="<script>alert(1)</script>", domain="billing")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-board")
        self.start("REQ-board", "FEAT-board")
        lifecycle_state.add_task(
            repo=self.repo, feature_id="FEAT-board", task_id="TASK-board", title="Render <safe>",
        )
        output = self.repo / "artifacts/board.html"
        result = self.run_backlog("board", "--out", str(output), "--title", "Team <Board>")
        self.assertEqual(result.returncode, 0, result.stderr)
        page = output.read_text(encoding="utf-8")
        self.assertIn("REQ-board", page)
        self.assertIn("FEAT-board", page)
        self.assertIn("TASK-board", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("Team &lt;Board&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_board_reflects_task_progress_without_writing_a_second_state(self) -> None:
        self.capture("REQ-progress")
        lifecycle_state.mark_requirement_ready(repo=self.repo, requirement_id="REQ-progress")
        self.start("REQ-progress", "FEAT-progress")
        lifecycle_state.add_task(
            repo=self.repo, feature_id="FEAT-progress", task_id="TASK-progress", title="Progress",
        )
        lifecycle_state.set_task_status(
            repo=self.repo, feature_id="FEAT-progress", task_id="TASK-progress", status="in_progress",
        )
        output = self.repo / "board.html"
        result = self.run_backlog("board", "--out", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        page = output.read_text(encoding="utf-8")
        self.assertIn("in_progress", page)
        self.assertEqual(list((self.repo / ".sdlc-v1").glob("*.json")), [self.repo / ".sdlc-v1/state.json"])

    def test_repo_discovery_works_from_a_nested_or_missing_path(self) -> None:
        self.capture("REQ-discovery")
        nested = self.repo / "does/not/exist/yet"
        discovered = backlog.discover_lifecycle_state_repo(nested)
        self.assertEqual(discovered, self.repo.resolve())
        result = self.run_backlog("tree", root=nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REQ-discovery", result.stdout)

    def test_removed_writers_and_runtime_options_are_rejected(self) -> None:
        removed_command = subprocess.run(
            [sys.executable, str(HERE / "backlog.py"), "set-status", "--root", str(self.repo)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(removed_command.returncode, 2)
        removed_option = self.run_backlog("readyqueue", "--dual-ledger-repo", str(self.repo))
        self.assertEqual(removed_option.returncode, 2)
        self.assertIn("unrecognized arguments", removed_option.stderr)


if __name__ == "__main__":
    unittest.main()
