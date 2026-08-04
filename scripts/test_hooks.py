#!/usr/bin/env python3
"""Behavior tests for SDLC worktree identity and Git hook routing."""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
GUARD = ROOT / "skills/sdlc/scripts/sdlc-guard"
PRE_COMMIT = ROOT / "skills/sdlc/references/templates/hooks/pre-commit"
PRE_PUSH = ROOT / "skills/sdlc/references/templates/hooks/pre-push"
POST_CHECKOUT = ROOT / "skills/sdlc/references/templates/hooks/post-checkout"
ONBOARD = ROOT / "skills/sdlc-onboard/SKILL.md"
ZERO_SHA = "0" * 40


def run_process(args, *, cwd, input_text=None, env=None):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=str(cwd),
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def git(repo, *args, check=True):
    result = run_process(["git", *args], cwd=repo)
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def git_stdout(repo, *args):
    return git(repo, *args).stdout.strip()


def write_file(repo, relative, content):
    path = pathlib.Path(repo) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git_stdout(repo, "rev-parse", "HEAD")


def init_repo(parent, *, seed_path="app.txt"):
    repo = pathlib.Path(parent) / "repo"
    repo.mkdir()
    result = run_process(["git", "init", "-q", "-b", "main"], cwd=repo)
    if result.returncode != 0:
        git(repo, "init", "-q")
        git(repo, "branch", "-M", "main")
    git(repo, "config", "user.email", "hooks@example.test")
    git(repo, "config", "user.name", "Hook Tests")
    write_file(repo, seed_path, "seed\n")
    commit_all(repo, "seed")
    return repo


def repo_root(repo):
    return git_stdout(repo, "rev-parse", "--show-toplevel")


def write_state(repo, *, branch=None, worktree=None, execution_mode=None, gate=None):
    lines = ["# SDLC State: hook-test", "stage: validate", "status: in-progress"]
    if branch is not None:
        lines.append(f"branch: {branch}")
    if worktree is not None:
        lines.append(f"worktree: {worktree}")
    lines.extend(["source-leaf: user.auth.login"])
    if execution_mode is not None:
        lines.append(f"execution-mode: {execution_mode}")
    if gate is not None:
        lines.append(f"sdlc-gate: {gate}")
    write_file(repo, ".sdlc/STATE.md", "\n".join(lines) + "\n")


def write_task(repo, *, task_branch=None, worktree=None, branch_base=None,
               allowed_write_set=("task.py",), omit=()):
    head = git_stdout(repo, "rev-parse", "HEAD")
    fields = {
        "execution-mode": "shared-control",
        "feature-id": "feature-hooks",
        "task-id": "P1-T1",
        "feature-branch": "feature/feature-hooks",
        "task-branch": task_branch or git_stdout(repo, "branch", "--show-current"),
        "worktree": worktree or repo_root(repo),
        "branch-base-sha": branch_base or head,
        "plan-revision": head,
        "control-head": head,
        "control-ref": "sdlc-control",
        "control-base-sha": head,
        "owner": "agent-hooks",
    }
    body = ["# SDLC Task Context: P1-T1"]
    body.extend(f"{key}: {value}" for key, value in fields.items() if key not in omit)
    body.extend(["", "## Allowed write set", ""])
    body.extend(f"- {path}" for path in allowed_write_set)
    body.extend(["", "## Contract", "", "- Test context."])
    write_file(repo, ".sdlc/TASK.md", "\n".join(body) + "\n")


def run_guard(repo):
    return run_process(["sh", GUARD], cwd=repo)


def push_line(repo, local_ref, remote_ref, remote_sha):
    local_sha = ZERO_SHA if local_ref == "(delete)" else git_stdout(repo, "rev-parse", local_ref)
    rendered_local_ref = "(delete)" if local_ref == "(delete)" else local_ref
    return f"{rendered_local_ref} {local_sha} {remote_ref} {remote_sha}\n"


def run_pre_push(repo, stdin):
    return run_process(["sh", PRE_PUSH, "origin", "unused"], cwd=repo, input_text=stdin)


class GuardContextTest(unittest.TestCase):
    def test_state_and_task_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            write_state(repo, branch="main", worktree=repo_root(repo))
            write_task(repo)
            result = run_guard(repo)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("STATE", result.stdout + result.stderr)
            self.assertIn("TASK", result.stdout + result.stderr)

    def test_task_identity_requires_all_fields_and_exact_branch_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            git(repo, "switch", "-q", "-c", "task/feature-hooks/P1-T1")
            write_task(repo)
            self.assertEqual(run_guard(repo).returncode, 0)

            write_task(repo, task_branch="task/feature-hooks/wrong")
            self.assertNotEqual(run_guard(repo).returncode, 0)

            write_task(repo, worktree="/tmp/not-this-worktree")
            self.assertNotEqual(run_guard(repo).returncode, 0)

            write_task(repo, omit={"task-id"})
            missing = run_guard(repo)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("task-id", missing.stdout + missing.stderr)

            write_task(repo)
            task_path = repo / ".sdlc/TASK.md"
            task_path.write_text(
                task_path.read_text(encoding="utf-8").replace(
                    "execution-mode: shared-control", "control-mode: shared"
                ),
                encoding="utf-8",
            )
            old_protocol = run_guard(repo)
            self.assertNotEqual(old_protocol.returncode, 0)
            self.assertIn("execution-mode", old_protocol.stdout + old_protocol.stderr)


class PreCommitWorktreeTest(unittest.TestCase):
    def test_pre_commit_finds_guard_in_git_common_hooks_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            worktree = pathlib.Path(tmp) / "task-wt"
            git(repo, "worktree", "add", "-q", "-b", "task/feature-hooks/P1-T1", worktree)

            common_dir = pathlib.Path(
                git_stdout(repo, "rev-parse", "--git-common-dir")
            )
            if not common_dir.is_absolute():
                common_dir = repo / common_dir
            hooks = common_dir / "hooks"
            hooks.mkdir(parents=True, exist_ok=True)
            installed_hook = hooks / "pre-commit"
            installed_guard = hooks / "sdlc-guard"
            shutil.copy2(PRE_COMMIT, installed_hook)
            shutil.copy2(GUARD, installed_guard)
            installed_hook.chmod(installed_hook.stat().st_mode | stat.S_IXUSR)
            installed_guard.chmod(installed_guard.stat().st_mode | stat.S_IXUSR)

            write_task(worktree, task_branch="task/feature-hooks/not-current")
            result = run_process([installed_hook], cwd=worktree)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TASK", result.stdout + result.stderr)


class PrePushRoutingTest(unittest.TestCase):
    def test_task_push_only_allows_declared_task_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            branch = "task/feature-hooks/P1-T1"
            git(repo, "switch", "-q", "-c", branch)
            base = git_stdout(repo, "rev-parse", "HEAD")
            write_file(repo, "task.py", "done = True\n")
            commit_all(repo, "task result")
            write_task(repo, task_branch=branch, branch_base=base)

            allowed = run_pre_push(
                repo,
                push_line(repo, f"refs/heads/{branch}", f"refs/heads/{branch}", base),
            )
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

            wrong = run_pre_push(
                repo,
                push_line(
                    repo,
                    f"refs/heads/{branch}",
                    "refs/heads/task/feature-hooks/P1-T2",
                    base,
                ),
            )
            self.assertNotEqual(wrong.returncode, 0)

            main = run_pre_push(
                repo, push_line(repo, f"refs/heads/{branch}", "refs/heads/main", base)
            )
            self.assertNotEqual(main.returncode, 0)

    def test_task_push_rejects_paths_outside_declared_write_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            branch = "task/feature-hooks/P1-T1"
            git(repo, "switch", "-q", "-c", branch)
            base = git_stdout(repo, "rev-parse", "HEAD")
            write_file(repo, "outside.py", "changed = True\n")
            commit_all(repo, "out of scope")
            write_task(repo, task_branch=branch, branch_base=base,
                       allowed_write_set=("task.py",))
            result = run_pre_push(
                repo, push_line(repo, f"refs/heads/{branch}", f"refs/heads/{branch}", base))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Allowed write set", result.stdout + result.stderr)

    def test_control_push_requires_non_delete_fast_forward_and_control_only_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp, seed_path=".sdlc-control/seed.md")
            base = git_stdout(repo, "rev-parse", "HEAD")
            write_file(repo, ".sdlc-control/claims/leaf.md", "status: active\n")
            head = commit_all(repo, "control claim")

            allowed = run_pre_push(
                repo,
                f"refs/heads/control-update {head} refs/heads/sdlc-control {base}\n",
            )
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

            deletion = run_pre_push(
                repo,
                f"(delete) {ZERO_SHA} refs/heads/sdlc-control {head}\n",
            )
            self.assertNotEqual(deletion.returncode, 0)

            git(repo, "switch", "-q", "-c", "remote-control", base)
            write_file(repo, ".sdlc-control/remote.md", "remote\n")
            remote_head = commit_all(repo, "remote update")
            git(repo, "switch", "-q", "-c", "local-control", base)
            write_file(repo, ".sdlc-control/local.md", "local\n")
            local_head = commit_all(repo, "local update")
            non_ff = run_pre_push(
                repo,
                f"refs/heads/local-control {local_head} refs/heads/sdlc-control {remote_head}\n",
            )
            self.assertNotEqual(non_ff.returncode, 0)

            git(repo, "switch", "-q", "-c", "bad-control", base)
            write_file(repo, "business.py", "not_control = True\n")
            bad_head = commit_all(repo, "bad control update")
            bad_path = run_pre_push(
                repo,
                f"refs/heads/bad-control {bad_head} refs/heads/sdlc-control {base}\n",
            )
            self.assertNotEqual(bad_path.returncode, 0)

    def test_new_control_branch_must_contain_only_control_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp, seed_path=".sdlc-control/seed.md")
            head = git_stdout(repo, "rev-parse", "HEAD")
            allowed = run_pre_push(
                repo,
                f"refs/heads/control-init {head} refs/heads/sdlc-control {ZERO_SHA}\n",
            )
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp, seed_path="business.py")
            head = git_stdout(repo, "rev-parse", "HEAD")
            rejected = run_pre_push(
                repo,
                f"refs/heads/control-init {head} refs/heads/sdlc-control {ZERO_SHA}\n",
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_existing_control_branch_target_tree_cannot_retain_business_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp, seed_path="business.py")
            base = git_stdout(repo, "rev-parse", "HEAD")
            write_file(repo, ".sdlc-control/claims/leaf.md", "status: active\n")
            head = commit_all(repo, "add control data to an invalid mixed tree")
            rejected = run_pre_push(
                repo,
                f"refs/heads/control-update {head} refs/heads/sdlc-control {base}\n",
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_reviewed_head_must_match_when_code_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            git(repo, "switch", "-q", "-c", "feature/reviewed")
            reviewed = git_stdout(repo, "rev-parse", "HEAD")
            write_file(repo, "app.txt", "changed after review\n")
            head = commit_all(repo, "change after review")
            write_state(
                repo,
                branch="feature/reviewed",
                worktree=repo_root(repo),
                gate=f"PASS reviewed-head={reviewed}",
            )
            rejected = run_pre_push(
                repo,
                f"refs/heads/feature/reviewed {head} refs/heads/feature/reviewed {reviewed}\n",
            )
            self.assertNotEqual(rejected.returncode, 0)

            write_state(
                repo,
                branch="feature/reviewed",
                worktree=repo_root(repo),
                gate=f"PASS reviewed-head={head}",
            )
            allowed = run_pre_push(
                repo,
                f"refs/heads/feature/reviewed {head} refs/heads/feature/reviewed {reviewed}\n",
            )
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    def test_gate_requires_exact_pass_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            git(repo, "switch", "-q", "-c", "feature/not-pass")
            head = git_stdout(repo, "rev-parse", "HEAD")
            write_state(
                repo,
                branch="feature/not-pass",
                worktree=repo_root(repo),
                gate=f"BLOCK previous=PASS reviewed-head={head}",
            )
            rejected = run_pre_push(
                repo,
                f"refs/heads/feature/not-pass {head} refs/heads/feature/not-pass {head}\n",
            )
            self.assertNotEqual(rejected.returncode, 0)


class PostCheckoutCompatibilityTest(unittest.TestCase):
    def _install_fake_backlog(self, repo):
        return write_file(
            repo,
            "scripts/backlog.py",
            textwrap.dedent(
                """\
                import os
                import pathlib
                pathlib.Path(os.environ["HOOK_MARKER"]).write_text("called", encoding="utf-8")
                """
            ),
        )

    def _run(self, repo, marker):
        env = os.environ.copy()
        env["HOOK_MARKER"] = str(marker)
        return run_process(["sh", POST_CHECKOUT, "old", "new", "1"], cwd=repo, env=env)

    def test_shared_feature_and_task_contexts_do_not_flush(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            marker = pathlib.Path(tmp) / "called"
            self._install_fake_backlog(repo)
            (repo / ".sdlc/requirements").mkdir(parents=True)
            write_state(
                repo,
                branch="main",
                worktree=repo_root(repo),
                execution_mode="shared-control",
            )
            self.assertEqual(self._run(repo, marker).returncode, 0)
            self.assertFalse(marker.exists())

            (repo / ".sdlc/STATE.md").unlink()
            write_state(
                repo,
                branch="main",
                worktree=repo_root(repo),
                execution_mode="local-serial",
            )
            self.assertEqual(self._run(repo, marker).returncode, 0)
            self.assertFalse(marker.exists())

            (repo / ".sdlc/STATE.md").unlink()
            write_task(repo)
            self.assertEqual(self._run(repo, marker).returncode, 0)
            self.assertFalse(marker.exists())

    def test_control_branch_does_not_flush(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            git(repo, "switch", "-q", "-c", "sdlc-control")
            marker = pathlib.Path(tmp) / "called"
            self._install_fake_backlog(repo)
            (repo / ".sdlc/requirements").mkdir(parents=True)
            write_state(repo, branch="sdlc-control", worktree=repo_root(repo))
            self.assertEqual(self._run(repo, marker).returncode, 0)
            self.assertFalse(marker.exists())

    def test_legacy_state_keeps_stage_flush(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(tmp)
            marker = pathlib.Path(tmp) / "called"
            self._install_fake_backlog(repo)
            (repo / ".sdlc/requirements").mkdir(parents=True)
            write_state(repo, branch="main", worktree=repo_root(repo))
            result = self._run(repo, marker)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(marker.exists())


class OnboardInstallContractTest(unittest.TestCase):
    def test_onboard_resolves_common_hooks_directory(self):
        text = ONBOARD.read_text(encoding="utf-8")
        self.assertIn("git rev-parse --git-common-dir", text)
        self.assertIn("common hooks", text.lower())


if __name__ == "__main__":
    unittest.main()
