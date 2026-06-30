"""Configuration: read env.sync.* settings via `git config` and the optional
`.envsync` file, with standard git config precedence (system -> global ->
local -> worktree) handled natively by `git config --get[-all]`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATTERNS = (".env", ".env.*")
DEFAULT_EXCLUDE = (".env.example", ".env.sample", ".env.template")
DEFAULT_FOLLOW_SYMLINKS = False
DEFAULT_MAX_FILE_SIZE = 1048576
DEFAULT_ON_CONFLICT = "skip"
DEFAULT_BACKUP = True

VALID_ON_CONFLICT = frozenset({"skip", "overwrite", "prompt"})

_TRUE_VALUES = frozenset({"true", "yes", "on", "1"})
_FALSE_VALUES = frozenset({"false", "no", "off", "0"})


class ConfigError(Exception):
    """Raised when a configuration value is malformed or invalid."""


@dataclass(frozen=True)
class SyncConfig:
    """Resolved `env.sync.*` configuration for a sync run."""

    patterns: tuple[str, ...] = DEFAULT_PATTERNS
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    follow_symlinks: bool = DEFAULT_FOLLOW_SYMLINKS
    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    on_conflict: str = DEFAULT_ON_CONFLICT
    backup: bool = DEFAULT_BACKUP


def _git_config_get_all(key: str, cwd: Path) -> list[str] | None:
    """Return every value of a multi-value key, or None if unset.

    `git config --get-all` itself walks system -> global -> local ->
    worktree, so this already reflects standard precedence.
    """
    result = subprocess.run(
        ["git", "config", "--get-all", key],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    values = [line for line in result.stdout.split("\n") if line != ""]
    return values or None


def _git_config_get(key: str, cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.rstrip("\n")
    return value or None


def _parse_envsync_file(path: Path) -> dict[str, list[str]]:
    """Parse a `.envsync` file: gitignore-flavored `key=value` lines, no
    `env.sync.` prefix. Repeated keys accumulate (for multi-value keys).
    """
    values: dict[str, list[str]] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        values.setdefault(key, []).append(value)
    return values


def _parse_bool(value: str, *, source: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ConfigError(f"invalid boolean value for {source}: {value!r}")


def _parse_int(value: str, *, source: str) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ConfigError(f"invalid integer value for {source}: {value!r}") from exc


def _resolve_multi(
    config_key: str, envsync: dict[str, list[str]], envsync_key: str, default: tuple[str, ...], cwd: Path
) -> list[str]:
    values = _git_config_get_all(config_key, cwd)
    if values is not None:
        return values
    if envsync_key in envsync:
        return list(envsync[envsync_key])
    return list(default)


def _resolve_bool(
    config_key: str, envsync: dict[str, list[str]], envsync_key: str, default: bool, cwd: Path
) -> bool:
    value = _git_config_get(config_key, cwd)
    if value is not None:
        return _parse_bool(value, source=config_key)
    if envsync_key in envsync:
        return _parse_bool(envsync[envsync_key][-1], source=f".envsync:{envsync_key}")
    return default


def _resolve_int(
    config_key: str, envsync: dict[str, list[str]], envsync_key: str, default: int, cwd: Path
) -> int:
    value = _git_config_get(config_key, cwd)
    if value is not None:
        return _parse_int(value, source=config_key)
    if envsync_key in envsync:
        return _parse_int(envsync[envsync_key][-1], source=f".envsync:{envsync_key}")
    return default


def _resolve_str(
    config_key: str, envsync: dict[str, list[str]], envsync_key: str, default: str, cwd: Path
) -> str:
    value = _git_config_get(config_key, cwd)
    if value is not None:
        return value
    if envsync_key in envsync:
        return envsync[envsync_key][-1]
    return default


def load_config(primary_root: Path) -> SyncConfig:
    """Resolve `env.sync.*` configuration for `primary_root`.

    Precedence per key: git config (system -> global -> local -> worktree)
    overrides the primary's `.envsync` file, which overrides built-in
    defaults.
    """
    envsync = _parse_envsync_file(primary_root / ".envsync")

    patterns = _resolve_multi(
        "env.sync.patterns", envsync, "patterns", DEFAULT_PATTERNS, primary_root
    )
    exclude = _resolve_multi(
        "env.sync.exclude", envsync, "exclude", DEFAULT_EXCLUDE, primary_root
    )
    follow_symlinks = _resolve_bool(
        "env.sync.followSymlinks",
        envsync,
        "followSymlinks",
        DEFAULT_FOLLOW_SYMLINKS,
        primary_root,
    )
    max_file_size = _resolve_int(
        "env.sync.maxFileSize", envsync, "maxFileSize", DEFAULT_MAX_FILE_SIZE, primary_root
    )
    on_conflict = _resolve_str(
        "env.sync.onConflict", envsync, "onConflict", DEFAULT_ON_CONFLICT, primary_root
    )
    if on_conflict not in VALID_ON_CONFLICT:
        raise ConfigError(
            f"invalid env.sync.onConflict value: {on_conflict!r}"
            f" (expected one of {sorted(VALID_ON_CONFLICT)})"
        )
    backup = _resolve_bool(
        "env.sync.backup", envsync, "backup", DEFAULT_BACKUP, primary_root
    )

    return SyncConfig(
        patterns=tuple(patterns),
        exclude=tuple(exclude),
        follow_symlinks=follow_symlinks,
        max_file_size=max_file_size,
        on_conflict=on_conflict,
        backup=backup,
    )
