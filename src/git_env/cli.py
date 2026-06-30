"""Top-level CLI: dispatches `git env <subcommand>` via arguably.

Exit codes are part of the spec's contract (see spec.md):
  0 success, 1 sync conflicts skipped, 2 refused to run, 3 usage error, 4 I/O error.
argparse itself always raises `SystemExit(2)` for usage errors (bad flag, unknown
subcommand), which collides with our "refused to run" code. `GitEnvExit` lets
command bodies signal an intentional exit code; any other `SystemExit(2)` reaching
`main()` therefore came from argparse and is remapped to 3.
"""

from __future__ import annotations

import sys

import arguably

from .config import ConfigError, load_config
from .output import Reporter
from .repo import RepoError, check_primary_clean, detect_repository
from .shell_completions import SUPPORTED_SHELLS
from .shell_completions import install_completions as render_completions_install
from .sync import SyncIOError, run_sync

#: Names set aside for future official subcommands (see spec.md Extensibility).
RESERVED_SUBCOMMANDS = frozenset({"push", "diff", "status", "list", "edit", "check"})


class GitEnvExit(Exception):
    """Raised by command bodies to request a specific process exit code."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


@arguably.command
def __root__(
    *, porcelain: bool = False, install_completions: str | None = None, write: bool = False
) -> None:
    """
    git env: sync environment files across linked git worktrees.

    Args:
        porcelain: reserved for a future machine-readable output mode (not yet supported)
        install_completions: print a completion snippet for [bash|zsh|fish]; combine with
            --write to install the completion file instead of printing it
        write: used with --install-completions, write the completion file to its standard
            location instead of printing a snippet
    """
    if porcelain:
        print(
            "git env: --porcelain is reserved for a future version and is not yet"
            " supported",
            file=sys.stderr,
        )
        raise GitEnvExit(3)
    if install_completions is not None:
        if install_completions not in SUPPORTED_SHELLS:
            print(
                "git env: --install-completions expects one of "
                f"{', '.join(SUPPORTED_SHELLS)}, got {install_completions!r}",
                file=sys.stderr,
            )
            raise GitEnvExit(3)
        print(render_completions_install(install_completions, write=write))
        raise GitEnvExit(0)
    if write:
        print("git env: --write requires --install-completions", file=sys.stderr)
        raise GitEnvExit(3)
    if arguably.is_target():
        arguably.error("a subcommand is required, try 'git env --help'")


@arguably.command
def sync(
    *,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
    quiet: bool = False,
    pattern: list[str] | None = None,
    path: str | None = None,
) -> None:
    """
    Copy env files from the primary worktree into the current linked worktree.

    Args:
        dry_run: [-n] print actions, change nothing
        force: [-f] overwrite local files even when they differ from the primary
        verbose: [-v] print every file considered, including skips
        quiet: [-q] suppress non-error output
        pattern: glob to sync, repeatable; overrides configured patterns for this run
        path: restrict to a subdirectory of the worktree
    """
    if verbose and quiet:
        print("git env sync: --verbose and --quiet are mutually exclusive", file=sys.stderr)
        raise GitEnvExit(3)

    reporter = Reporter(verbose=verbose, quiet=quiet)

    try:
        repo = detect_repository()
    except RepoError as exc:
        reporter.error(str(exc))
        raise GitEnvExit(2) from None

    try:
        config = load_config(repo.primary_root)
    except ConfigError as exc:
        reporter.error(str(exc))
        raise GitEnvExit(3) from None

    if pattern:
        config = type(config)(**{**config.__dict__, "patterns": tuple(pattern)})

    if not force:
        dirty = check_primary_clean(repo.primary_root, config.patterns, config.exclude)
        if dirty:
            reporter.error(
                "primary worktree has uncommitted changes to tracked env files: "
                f"{', '.join(dirty)} (use --force to override)"
            )
            raise GitEnvExit(2)

    try:
        result = run_sync(
            repo,
            config,
            dry_run=dry_run,
            force=force,
            path=path,
            reporter=reporter,
        )
    except SyncIOError as exc:
        reporter.error(str(exc))
        raise GitEnvExit(4) from None

    if dry_run:
        raise GitEnvExit(1 if result.would_change or result.conflicts else 0)
    raise GitEnvExit(result.exit_code)


def _rewrite_help_subcommand(argv: list[str]) -> list[str]:
    """Translate `git env help [subcommand]` into `git env [subcommand] --help`."""
    if argv and argv[0] == "help":
        rest = argv[1:]
        return [*rest, "--help"]
    return argv


def _reject_reserved_subcommand(argv: list[str]) -> None:
    """Give a clearer error than argparse's "invalid choice" for reserved names."""
    for token in argv:
        if token == "--":
            return
        if token.startswith("-"):
            continue
        if token in RESERVED_SUBCOMMANDS:
            print(
                f"git env: '{token}' is reserved for future use and is not yet"
                " implemented",
                file=sys.stderr,
            )
            raise GitEnvExit(3)
        return


def main() -> None:
    argv = _rewrite_help_subcommand(sys.argv[1:])
    sys.argv = [sys.argv[0], *argv]
    try:
        _reject_reserved_subcommand(argv)
        arguably.run(
            name="git env",
            version_flag=True,
        )
    except GitEnvExit as exc:
        sys.exit(exc.code)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 2:
            sys.exit(3)
        raise
