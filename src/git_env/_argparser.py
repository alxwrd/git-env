from __future__ import annotations

import argparse
from importlib.metadata import version

from .shell_completions import SUPPORTED_SHELLS


class GitEnvExit(Exception):
    """Raised by command bodies to request a specific process exit code."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def rewrite_help_subcommand(argv: list[str]) -> list[str]:
    """Translate `git env help [subcommand]` into `git env [subcommand] --help`."""
    if argv and argv[0] == "help":
        return [*argv[1:], "--help"]
    return argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git env",
        description="sync environment files across linked git worktrees",
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('git-env')}"
    )
    parser.add_argument(
        "--porcelain",
        action="store_true",
        help="reserved for a future machine-readable output mode (not yet supported)",
    )
    parser.add_argument(
        "--install-completions",
        choices=SUPPORTED_SHELLS,
        metavar="{" + "|".join(SUPPORTED_SHELLS) + "}",
        help="print a completion snippet for the given shell; combine with --write to install",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="used with --install-completions: write the file instead of printing",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print every file considered, including skips",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress non-error output"
    )

    sub = parser.add_subparsers(dest="command")

    p_sync = sub.add_parser(
        "sync",
        help="copy env files from primary worktree into current linked worktree",
    )
    p_sync.add_argument(
        "-n", "--dry-run", action="store_true", help="print actions, change nothing"
    )
    p_sync.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="overwrite local files even when they differ from primary",
    )
    p_sync.add_argument(
        "--pattern",
        action="append",
        metavar="GLOB",
        help="glob to sync, repeatable; overrides configured patterns",
    )
    p_sync.add_argument(
        "--path", metavar="PATH", help="restrict to a subdirectory of the worktree"
    )

    return parser
