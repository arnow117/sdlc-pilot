"""Shared local Git repository setup for deterministic tests."""
from __future__ import annotations

from pathlib import Path
import subprocess


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def initialize_git_repo(repo: Path, *, readme: str) -> None:
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "SDLC tests")
    (repo / "README.md").write_text(readme, encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "initial")
