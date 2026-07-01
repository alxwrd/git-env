"""Top-level CLI: dispatches `git env <subcommand>` via argparse.

Exit codes are part of the spec's contract (see spec.md):
  0 success, 1 sync conflicts skipped, 2 refused to run, 3 usage error, 4 I/O error.
argparse itself always raises `SystemExit(2)` for usage errors (bad flag, unknown
subcommand), which collides with our "refused to run" code. `GitEnvExit` lets
command bodies signal an intentional exit code; any other `SystemExit(2)` reaching
`main()` therefore came from argparse and is remapped to 3.
"""

from __future__ import annotations

import sys

from ._argparser import GitEnvExit, build_parser, rewrite_help_subcommand
from .config import ConfigError, load_config
from .output import Reporter
from .repo import RepoError, check_primary_clean, detect_repository
from .shell_completions import install_completions as render_completions_install
from .sync import SyncIOError, run_sync


def sync(
    *,
    pattern: list[str] | None = None,
    path: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    reporter: Reporter,
) -> None:
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


def main() -> None:
    argv = rewrite_help_subcommand(sys.argv[1:])
    try:
        parser = build_parser()
        args = parser.parse_args(argv)

        if args.porcelain:
            print(
                "git env: --porcelain is reserved for a future version and is not yet"
                " supported",
                file=sys.stderr,
            )
            raise GitEnvExit(3)
        if args.install_completions is not None:
            print(
                render_completions_install(args.install_completions, write=args.write)
            )
            raise GitEnvExit(0)
        if args.write:
            print("git env: --write requires --install-completions", file=sys.stderr)
            raise GitEnvExit(3)
        if args.verbose and args.quiet:
            print(
                "git env: --verbose and --quiet are mutually exclusive", file=sys.stderr
            )
            raise GitEnvExit(3)

        reporter = Reporter(verbose=args.verbose, quiet=args.quiet)

        match args.command:
            case None:
                parser.error("a subcommand is required, try 'git env --help'")
            case "sync":
                sync(
                    pattern=args.pattern,
                    path=args.path,
                    dry_run=args.dry_run,
                    force=args.force,
                    reporter=reporter,
                )

    except GitEnvExit as exc:
        sys.exit(exc.code)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 2:
            sys.exit(3)
        raise
