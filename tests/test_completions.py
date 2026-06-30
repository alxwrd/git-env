"""Tests for `git env --install-completions` (see spec.md "Tab completion")."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(args: list[str], *, home: Path) -> subprocess.CompletedProcess[str]:
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-c", "from git_env import main; main()", *args],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_install_completions_prints_snippet(shell: str, tmp_path: Path) -> None:
    result = _run_cli(["--install-completions", shell], home=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "git-env" in result.stdout
    assert "shell rc file" in result.stdout


@pytest.mark.parametrize(
    ("shell", "relative_path"),
    [
        ("bash", ".local/share/bash-completion/completions/git-env"),
        ("zsh", ".zsh/completions/_git-env"),
        ("fish", ".config/fish/completions/git-env.fish"),
    ],
)
def test_install_completions_write_creates_file(
    shell: str, relative_path: str, tmp_path: Path
) -> None:
    result = _run_cli(["--install-completions", shell, "--write"], home=tmp_path)

    assert result.returncode == 0, result.stderr
    installed = tmp_path / relative_path
    assert installed.is_file()
    assert "git-env" in installed.read_text()


def test_install_completions_rejects_unknown_shell(tmp_path: Path) -> None:
    result = _run_cli(["--install-completions", "powershell"], home=tmp_path)

    assert result.returncode == 3
    assert "powershell" in result.stderr


def test_write_without_install_completions_is_usage_error(tmp_path: Path) -> None:
    result = _run_cli(["--write"], home=tmp_path)

    assert result.returncode == 3
    assert "--install-completions" in result.stderr
