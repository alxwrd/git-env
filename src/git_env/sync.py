"""Core `git env sync` logic: copy env files from the primary worktree into
the current linked worktree.

Implements the "Copy semantics" and "Conflict handling" rules from spec.md,
including line-diff summaries, `.envsync.bak` backups, and the
`env.sync.onConflict` modes. The safety-rail refusals beyond repository
detection are tracked as separate follow-up work.
"""

from __future__ import annotations

import difflib
import filecmp
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import SyncConfig
from .discovery import DiscoveredFile, discover_env_files
from .output import Reporter
from .repo import Repository

#: Suffix used for the atomic-write temp file (spec: copy to `<dest>.envsync.tmp`
#: then `rename(2)` over the destination).
_TMP_SUFFIX = ".envsync.tmp"


class SyncIOError(Exception):
    """Raised on an I/O failure during copy. Always corresponds to exit code 4."""


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync run, used to derive the process exit code."""

    synced: int = 0
    skipped_unchanged: int = 0
    conflicts: int = 0
    would_change: int = 0
    """Files that would be copied/overwritten; only meaningful for --dry-run."""

    @property
    def exit_code(self) -> int:
        if self.conflicts:
            return 1
        return 0


def _filter_path(files: list[DiscoveredFile], path: str | None) -> list[DiscoveredFile]:
    if path is None:
        return files
    prefix = Path(path)
    return [f for f in files if prefix in (f.relative_path, *f.relative_path.parents)]


def _resolve_dest(worktree_root: Path, relative_path: Path) -> Path:
    """Resolve `relative_path` against `worktree_root`, refusing escapes.

    Guards against a pattern or symlinked source resolving outside the
    current worktree (spec: "Never write outside the current worktree root").
    """
    dest = (worktree_root / relative_path).resolve()
    if worktree_root not in dest.parents and dest != worktree_root:
        raise SyncIOError(
            f"refusing to write outside the worktree: {relative_path}"
        )
    return dest


def _diff_summary(src: Path, dest: Path) -> str:
    """Describe how `dest` differs from `src`, e.g. "3 lines differ"."""
    try:
        src_lines = src.read_text().splitlines()
        dest_lines = dest.read_text().splitlines()
    except (UnicodeDecodeError, OSError):
        return "binary files differ"
    matcher = difflib.SequenceMatcher(a=dest_lines, b=src_lines)
    changed = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )
    noun = "line" if changed == 1 else "lines"
    return f"{changed} {noun} differ"


def _backup(dest: Path) -> None:
    """Back up `dest`'s current content to `<dest>.envsync.bak` before an
    overwrite (spec: "single backup, overwritten on subsequent forces").
    """
    backup_path = dest.with_name(dest.name + ".envsync.bak")
    try:
        shutil.copyfile(dest, backup_path)
        shutil.copymode(dest, backup_path)
    except OSError as exc:
        raise SyncIOError(f"failed to back up {dest}: {exc}") from exc


def _prompt_overwrite(rel: Path, diff_desc: str, reporter: Reporter) -> bool:
    try:
        answer = input(f"{rel}: {diff_desc}. Overwrite? [y/N] ")
    except EOFError:
        reporter.warn(f"{rel}: cannot prompt for input, skipping")
        return False
    return answer.strip().lower() in {"y", "yes"}


def _atomic_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + _TMP_SUFFIX)
    try:
        shutil.copyfile(src, tmp)
        shutil.copymode(src, tmp)
        os.replace(tmp, dest)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise SyncIOError(f"failed to copy {src} -> {dest}: {exc}") from exc


def run_sync(
    repo: Repository,
    config: SyncConfig,
    *,
    dry_run: bool = False,
    force: bool = False,
    path: str | None = None,
    reporter: Reporter,
) -> SyncResult:
    """Sync env files from `repo.primary_root` into `repo.worktree_root`."""
    files, warnings = discover_env_files(repo.primary_root, config)
    files = _filter_path(files, path)

    for warning in warnings:
        reporter.warn(f"{warning.relative_path}: {warning.message}")

    synced = 0
    skipped_unchanged = 0
    conflicts = 0
    would_change = 0

    for discovered in files:
        rel = discovered.relative_path
        dest = _resolve_dest(repo.worktree_root, rel)

        if not dest.exists():
            if dry_run:
                would_change += 1
                reporter.info(f"would sync {rel}")
                continue
            _atomic_copy(discovered.absolute_path, dest)
            synced += 1
            reporter.info(f"synced {rel}")
            continue

        if filecmp.cmp(discovered.absolute_path, dest, shallow=False):
            skipped_unchanged += 1
            reporter.detail(f"unchanged {rel}")
            continue

        diff_desc = _diff_summary(discovered.absolute_path, dest)
        should_overwrite = force or config.on_conflict == "overwrite"

        if not should_overwrite and config.on_conflict == "prompt" and not dry_run:
            should_overwrite = _prompt_overwrite(rel, diff_desc, reporter)

        if should_overwrite:
            if dry_run:
                would_change += 1
                reporter.info(f"would overwrite {rel} ({diff_desc})")
                continue
            if config.backup:
                _backup(dest)
            _atomic_copy(discovered.absolute_path, dest)
            synced += 1
            reporter.info(f"synced {rel} (overwrote, {diff_desc})")
            continue

        conflicts += 1
        reporter.warn(f"{rel}: {diff_desc}, skipping (use --force to overwrite)")

    total_changes = synced + (would_change if dry_run else 0)
    reporter.info(
        f"{total_changes if dry_run else synced} files synced, "
        f"{skipped_unchanged} unchanged, {conflicts} conflicts skipped"
    )

    return SyncResult(
        synced=synced,
        skipped_unchanged=skipped_unchanged,
        conflicts=conflicts,
        would_change=would_change,
    )
