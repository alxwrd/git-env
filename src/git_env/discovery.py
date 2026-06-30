"""File discovery: walk the primary worktree and find env files to sync.

Implements the "File discovery" rules from spec.md: match configured
patterns against the primary worktree, ignore `.gitignore` entirely, honor
an opt-out `.envsyncignore` (gitignore syntax), skip symlinks unless
configured otherwise, skip oversized files with a warning, and never
traverse into submodules.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .config import SyncConfig

#: Directory name that always marks a repository root; never descend into a
#: nested one (submodule) other than the primary worktree's own root.
_GIT_ENTRY = ".git"


@dataclass(frozen=True)
class DiscoveredFile:
    """A file in the primary worktree that matches the sync patterns."""

    relative_path: Path
    """Path relative to the primary worktree root."""

    absolute_path: Path
    """Absolute path to the file (symlink target if followed)."""


@dataclass(frozen=True)
class DiscoveryWarning:
    """A non-fatal issue encountered while discovering files."""

    relative_path: Path
    message: str


class _IgnoreMatcher:
    """Minimal gitignore-syntax matcher for `.envsyncignore`."""

    def __init__(self, lines: list[str]) -> None:
        self._rules: list[tuple[re.Pattern[str], bool, bool]] = []
        for raw in lines:
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            negate = line.startswith("!")
            if negate:
                line = line[1:]
            line = line.rstrip()
            if not line:
                continue
            dir_only = line.endswith("/")
            if dir_only:
                line = line[:-1]
            anchored = line.startswith("/")
            if anchored:
                line = line[1:]
            pattern = re.compile(self._translate(line, anchored))
            self._rules.append((pattern, negate, dir_only))

    @staticmethod
    def _translate(pattern: str, anchored: bool) -> str:
        i = 0
        n = len(pattern)
        out: list[str] = ["^" if anchored else "^(?:.*/)?"]
        while i < n:
            ch = pattern[i]
            if ch == "*":
                if pattern[i : i + 2] == "**":
                    if pattern[i : i + 3] == "**/":
                        out.append("(?:.*/)?")
                        i += 3
                        continue
                    out.append(".*")
                    i += 2
                    continue
                out.append("[^/]*")
                i += 1
                continue
            if ch == "?":
                out.append("[^/]")
                i += 1
                continue
            out.append(re.escape(ch))
            i += 1
        out.append("$")
        return "".join(out)

    def matches(self, relative_posix: str, *, is_dir: bool) -> bool:
        ignored = False
        for pattern, negate, dir_only in self._rules:
            if dir_only and not is_dir:
                continue
            if pattern.match(relative_posix):
                ignored = not negate
        return ignored


def _load_ignore_matcher(primary_root: Path) -> _IgnoreMatcher:
    ignore_file = primary_root / ".envsyncignore"
    if not ignore_file.is_file():
        return _IgnoreMatcher([])
    return _IgnoreMatcher(ignore_file.read_text().splitlines())


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def discover_env_files(
    primary_root: Path, config: SyncConfig
) -> tuple[list[DiscoveredFile], list[DiscoveryWarning]]:
    """Walk `primary_root` and return matching files plus any warnings."""
    primary_root = primary_root.resolve()
    ignore = _load_ignore_matcher(primary_root)

    files: list[DiscoveredFile] = []
    warnings: list[DiscoveryWarning] = []

    for dirpath, dirnames, filenames in os.walk(
        primary_root, followlinks=config.follow_symlinks
    ):
        dir_path = Path(dirpath)
        rel_dir = dir_path.relative_to(primary_root)

        kept_dirnames = []
        for dirname in dirnames:
            child = dir_path / dirname
            rel_child = (rel_dir / dirname) if str(rel_dir) != "." else Path(dirname)
            rel_child_posix = rel_child.as_posix()

            if dirname == _GIT_ENTRY:
                continue
            # Nested repo (submodule): a directory with its own .git entry,
            # other than the primary root itself.
            if (child / _GIT_ENTRY).exists():
                continue
            if child.is_symlink() and not config.follow_symlinks:
                continue
            if ignore.matches(rel_child_posix, is_dir=True):
                continue
            kept_dirnames.append(dirname)
        dirnames[:] = kept_dirnames

        for filename in filenames:
            abs_path = dir_path / filename
            rel_path = (rel_dir / filename) if str(rel_dir) != "." else Path(filename)
            rel_posix = rel_path.as_posix()

            if not _matches_any(filename, config.patterns):
                continue
            if _matches_any(filename, config.exclude):
                continue
            if ignore.matches(rel_posix, is_dir=False):
                continue

            is_symlink = abs_path.is_symlink()
            if is_symlink and not config.follow_symlinks:
                continue

            try:
                stat_result = abs_path.stat()
            except OSError as exc:
                warnings.append(
                    DiscoveryWarning(rel_path, f"could not stat file: {exc}")
                )
                continue

            if stat_result.st_size > config.max_file_size:
                warnings.append(
                    DiscoveryWarning(
                        rel_path,
                        f"skipped: {stat_result.st_size} bytes exceeds "
                        f"env.sync.maxFileSize ({config.max_file_size})",
                    )
                )
                continue

            files.append(
                DiscoveredFile(
                    relative_path=rel_path,
                    absolute_path=abs_path,
                )
            )

    files.sort(key=lambda f: f.relative_path.as_posix())
    return files, warnings
