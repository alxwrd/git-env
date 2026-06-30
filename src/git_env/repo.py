"""Repository detection: locate the primary worktree and reject unsupported layouts."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class RepoError(Exception):
    """Raised when the current location is not a usable linked worktree.

    Always corresponds to exit code 2 per the spec's repository detection rules.
    """


@dataclass(frozen=True)
class Repository:
    """The repository context for the current invocation."""

    git_dir: Path
    """Absolute path to the current worktree's git dir."""

    git_common_dir: Path
    """Absolute path to the shared git dir (inside the primary worktree's .git)."""

    primary_root: Path
    """Absolute path to the primary worktree's root directory."""

    worktree_root: Path
    """Absolute path to the current (linked) worktree's root directory."""


def _git(*args: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RepoError("git executable not found on PATH") from exc
    return result.stdout.strip()


def _git_ok(*args: str, cwd: Path | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RepoError("git executable not found on PATH") from exc
    return result.returncode == 0, result.stdout.strip()


def detect_repository(cwd: Path | None = None) -> Repository:
    """Detect the repository context for `cwd` (defaults to the process cwd).

    Raises RepoError (exit code 2) for any of:
      - not inside a git worktree
      - inside a bare repository
      - inside the primary worktree (sync only runs from a linked worktree)
    """
    cwd = (cwd or Path.cwd()).resolve()

    inside_ok, inside_out = _git_ok("rev-parse", "--is-inside-work-tree", cwd=cwd)
    bare_ok, bare_out = _git_ok("rev-parse", "--is-bare-repository", cwd=cwd)

    # A bare repo has no work tree, so --is-inside-work-tree reports "false" (not
    # an error) even when we *are* inside a git dir. Check bare-ness first so that
    # case gets its own message instead of the generic "not inside a worktree" one.
    if bare_ok and bare_out == "true":
        raise RepoError("bare repositories are not supported")

    if not inside_ok or inside_out != "true":
        raise RepoError("not inside a git worktree")

    git_dir = Path(_git("rev-parse", "--path-format=absolute", "--git-dir", cwd=cwd))
    git_common_dir = Path(
        _git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    )

    if git_dir.resolve() == git_common_dir.resolve():
        primary_root = git_common_dir.resolve().parent
        raise RepoError(
            f"git env sync runs from a linked worktree; you appear to be in the "
            f"primary at {primary_root}"
        )

    primary_root = git_common_dir.resolve().parent
    worktree_root = Path(
        _git("rev-parse", "--path-format=absolute", "--show-toplevel", cwd=cwd)
    ).resolve()

    _check_pwd_within_worktree(worktree_root)

    return Repository(
        git_dir=git_dir.resolve(),
        git_common_dir=git_common_dir.resolve(),
        primary_root=primary_root,
        worktree_root=worktree_root,
    )


def _check_pwd_within_worktree(worktree_root: Path) -> None:
    """Paranoid check (spec: "Safety rails") that the shell-reported `$PWD`
    is actually inside the worktree we just resolved. Catches weird
    invocations (e.g. a symlinked directory pointing somewhere else) where
    the shell's notion of cwd has diverged from the real one.

    Skipped if `$PWD` isn't set, since not every caller sets it.
    """
    pwd = os.environ.get("PWD")
    if not pwd:
        return
    resolved_pwd = Path(pwd).resolve()
    if resolved_pwd != worktree_root and worktree_root not in resolved_pwd.parents:
        raise RepoError(
            f"$PWD ({pwd}) is not within the current worktree at {worktree_root}"
        )


def check_primary_clean(
    primary_root: Path, patterns: tuple[str, ...], exclude: tuple[str, ...]
) -> list[str]:
    """Return relative paths of tracked env files with uncommitted changes
    in `primary_root` (spec: "Safety rails" — don't propagate half-edits on
    a tracked template). Empty list means the primary is clean.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--no-renames"],
        cwd=primary_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    dirty: list[str] = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        name = Path(path).name
        if not any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
            continue
        if any(fnmatch.fnmatch(name, pattern) for pattern in exclude):
            continue
        dirty.append(path)
    return dirty
