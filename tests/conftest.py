"""Shared fixtures for the git-env test harness.

Builds real git repositories on disk (a primary worktree plus linked
worktrees via `git worktree add`) so tests exercise the actual `git`
binary rather than mocking it. Git's system/global config is isolated
per-test so a developer's machine config can't leak into results.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


def _run_git(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed in {cwd}:\n{result.stdout}\n{result.stderr}"
    )
    return result


@dataclass
class GitEnv:
    """Test handle: a primary worktree, its env, and helpers to drive git-env."""

    tmp_path: Path
    primary: Path
    env: dict[str, str]

    def git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return _run_git(list(args), cwd=cwd or self.primary, env=self.env)

    def add_worktree(self, name: str = "wt") -> Path:
        worktree_path = self.tmp_path / name
        self.git("worktree", "add", str(worktree_path), "-b", f"{name}-branch")
        return worktree_path

    def commit_all(self, message: str = "update", *, cwd: Path | None = None) -> None:
        cwd = cwd or self.primary
        self.git("add", "-A", cwd=cwd)
        self.git("commit", "-m", message, cwd=cwd)

    def run_cli(
        self, args: list[str], *, cwd: Path, pwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Invoke the `git-env` CLI entry point as a subprocess from `cwd`.

        `pwd` overrides the reported `$PWD` independently of the real
        process `cwd`, to exercise the "$PWD must be within the worktree"
        safety rail.
        """
        env = {**self.env, "PWD": str(pwd if pwd is not None else cwd)}
        return subprocess.run(
            [sys.executable, "-c", "from git_env import main; main()", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
        )

    def sync(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_cli(["sync", *args], cwd=cwd or self.tmp_path / "wt")


@pytest.fixture
def isolated_git_env(tmp_path: Path) -> dict[str, str]:
    """Environment with git's system/global config neutralized."""
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = str(tmp_path / "gitconfig_global_unused")
    env["HOME"] = str(tmp_path)
    env["GIT_AUTHOR_NAME"] = "Test User"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test User"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


@pytest.fixture
def git_env(tmp_path: Path, isolated_git_env: dict[str, str]) -> GitEnv:
    """A primary worktree with one commit, ready for `git worktree add`."""
    primary = tmp_path / "primary"
    primary.mkdir()
    _run_git(["init", "-b", "main"], cwd=primary, env=isolated_git_env)
    (primary / "README.md").write_text("hello\n")
    _run_git(["add", "-A"], cwd=primary, env=isolated_git_env)
    _run_git(
        ["commit", "-m", "initial commit"], cwd=primary, env=isolated_git_env
    )
    return GitEnv(tmp_path=tmp_path, primary=primary, env=isolated_git_env)
