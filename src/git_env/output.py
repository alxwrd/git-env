"""Minimal stdout/stderr printer used by sync until colorized output lands
(see "Implement output formatting and color" todo).
"""

from __future__ import annotations

import sys


class Reporter:
    """Routes sync messages to stdout/stderr according to -v/-q."""

    def __init__(self, *, verbose: bool = False, quiet: bool = False) -> None:
        self.verbose = verbose
        self.quiet = quiet

    def info(self, message: str) -> None:
        """Always-shown progress, e.g. "synced .env". Suppressed by --quiet."""
        if not self.quiet:
            print(message)

    def detail(self, message: str) -> None:
        """Verbose-only progress, e.g. skipped/unchanged files."""
        if self.verbose and not self.quiet:
            print(message)

    def warn(self, message: str) -> None:
        """Non-fatal warnings (conflicts, oversized files): always shown, on stderr."""
        if not self.quiet:
            print(f"warning: {message}", file=sys.stderr)

    def error(self, message: str) -> None:
        """Fatal errors: always shown, even under --quiet."""
        print(f"error: {message}", file=sys.stderr)
