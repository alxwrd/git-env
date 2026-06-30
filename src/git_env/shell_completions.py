"""Shell completion scripts and the `git env --install-completions` helper.

The completion scripts themselves live in `git_env/completions/` (package
data, so they ship inside the installed wheel) and are shipped under their
target filenames (`git-env.bash`, `_git-env`, `git-env.fish`) per spec.md
"Tab completion".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

SUPPORTED_SHELLS = ("bash", "zsh", "fish")

_PACKAGE_FILENAMES = {
    "bash": "git-env.bash",
    "zsh": "_git-env",
    "fish": "git-env.fish",
}


@dataclass(frozen=True)
class CompletionTarget:
    """Where a shell's completion file is installed, and how to enable it."""

    install_path: Path
    enable_snippet: str


def completion_target(shell: str) -> CompletionTarget:
    """Resolve the standard user-level install path and rc snippet for `shell`."""
    home = Path.home()
    if shell == "bash":
        path = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "bash-completion" / "completions" / "git-env"
        snippet = f'source "{path}"'
    elif shell == "zsh":
        path = home / ".zsh" / "completions" / "_git-env"
        snippet = f'fpath=("{path.parent}" $fpath)\nautoload -Uz compinit && compinit'
    elif shell == "fish":
        path = home / ".config" / "fish" / "completions" / "git-env.fish"
        snippet = f"# fish loads completions from {path.parent} automatically, nothing else to do"
    else:
        raise ValueError(f"unsupported shell: {shell!r}")
    return CompletionTarget(install_path=path, enable_snippet=snippet)


def completion_source(shell: str) -> str:
    """Return the packaged completion script content for `shell`."""
    filename = _PACKAGE_FILENAMES[shell]
    return resources.files("git_env.completions").joinpath(filename).read_text()


def install_completions(shell: str, *, write: bool) -> str:
    """
    Print an rc snippet plus the completion script for `shell`, or write the
    script to its standard location with `write=True`.

    Returns the message to print to the user. Raises ValueError for an
    unsupported shell.
    """
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(
            f"unsupported shell {shell!r}, expected one of {', '.join(SUPPORTED_SHELLS)}"
        )

    source = completion_source(shell)
    target = completion_target(shell)

    if not write:
        return (
            f"{source}\n"
            f"# add this to your shell rc file to enable completions:\n"
            f"# {target.enable_snippet}"
        )

    target.install_path.parent.mkdir(parents=True, exist_ok=True)
    target.install_path.write_text(source)
    message = f"installed {shell} completions to {target.install_path}"
    if shell != "fish":
        message += (
            "\nadd this to your shell rc file if not already present:\n"
            f"{target.enable_snippet}"
        )
    return message
