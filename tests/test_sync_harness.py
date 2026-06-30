"""End-to-end test harness for `git env sync`.

Each test builds a real primary worktree + linked worktree on disk, seeds
env files, runs the actual `git-env` CLI as a subprocess, and asserts on
the resulting filesystem state and exit code. See spec.md "Testing".
"""

from __future__ import annotations

from pathlib import Path

from conftest import GitEnv


def test_clean_sync(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    (git_env.primary / "apps").mkdir()
    (git_env.primary / "apps" / ".env").write_text("BAZ=qux\n")
    wt = git_env.add_worktree()

    result = git_env.sync()

    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=bar\n"
    assert (wt / "apps" / ".env").read_text() == "BAZ=qux\n"
    assert "synced .env" in result.stdout


def test_noop_sync_when_identical(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()
    git_env.sync()

    result = git_env.sync()

    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=bar\n"
    assert "0 files synced" in result.stdout


def test_conflict_skip(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()
    (wt / ".env").write_text("FOO=local-edit\n")

    result = git_env.sync()

    assert result.returncode == 1
    assert (wt / ".env").read_text() == "FOO=local-edit\n"
    assert "skipping" in result.stderr


def test_conflict_force_backs_up_and_overwrites(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()
    (wt / ".env").write_text("FOO=local-edit\n")

    result = git_env.sync("--force")

    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=bar\n"
    assert (wt / ".env.envsync.bak").read_text() == "FOO=local-edit\n"


def test_dry_run_reports_pending_changes_without_writing(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()

    result = git_env.sync("--dry-run")

    assert result.returncode == 1
    assert not (wt / ".env").exists()
    assert "would sync .env" in result.stdout


def test_dry_run_exits_zero_when_up_to_date(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    git_env.add_worktree()
    git_env.sync()

    result = git_env.sync("--dry-run")

    assert result.returncode == 0, result.stderr


def test_refuses_to_run_from_primary(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    git_env.add_worktree()

    result = git_env.sync(cwd=git_env.primary)

    assert result.returncode == 2
    assert "primary" in result.stderr


def test_refuses_to_run_in_bare_repo(git_env: GitEnv, isolated_git_env: dict[str, str]) -> None:
    bare = git_env.tmp_path / "bare.git"
    bare.mkdir()
    git_env.git("init", "--bare", cwd=bare)

    result = git_env.run_cli(["sync"], cwd=bare)

    assert result.returncode == 2
    assert "bare" in result.stderr


def test_refuses_to_run_outside_repo(git_env: GitEnv, tmp_path: Path) -> None:
    outside = tmp_path / "not-a-repo"
    outside.mkdir()

    result = git_env.run_cli(["sync"], cwd=outside)

    assert result.returncode == 2
    assert "not inside a git worktree" in result.stderr


def test_symlink_skipped_by_default_and_followed_when_configured(git_env: GitEnv) -> None:
    target = git_env.primary / "real-secrets"
    target.write_text("FOO=symlinked\n")
    (git_env.primary / ".env").symlink_to(target)
    wt = git_env.add_worktree()

    result = git_env.sync()
    assert result.returncode == 0, result.stderr
    assert not (wt / ".env").exists()

    git_env.git("config", "env.sync.followSymlinks", "true")
    result = git_env.sync()
    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=symlinked\n"


def test_large_file_skipped_with_warning(git_env: GitEnv) -> None:
    git_env.git("config", "env.sync.maxFileSize", "10")
    (git_env.primary / ".env").write_text("this-is-more-than-ten-bytes\n")
    wt = git_env.add_worktree()

    result = git_env.sync()

    assert result.returncode == 0, result.stderr
    assert not (wt / ".env").exists()
    assert "maxFileSize" in result.stderr


def test_pattern_override(git_env: GitEnv) -> None:
    (git_env.primary / "secrets.ini").write_text("FOO=bar\n")
    wt = git_env.add_worktree()

    result = git_env.sync("--pattern", "secrets.ini")

    assert result.returncode == 0, result.stderr
    assert (wt / "secrets.ini").read_text() == "FOO=bar\n"


def test_envsyncignore_excludes_matching_paths(git_env: GitEnv) -> None:
    (git_env.primary / ".envsyncignore").write_text("ignored/\n")
    (git_env.primary / "ignored").mkdir()
    (git_env.primary / "ignored" / ".env").write_text("FOO=should-not-sync\n")
    (git_env.primary / ".env").write_text("FOO=should-sync\n")
    wt = git_env.add_worktree()

    result = git_env.sync()

    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=should-sync\n"
    assert not (wt / "ignored" / ".env").exists()


def test_refuses_when_primary_has_dirty_tracked_env_file(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    git_env.commit_all("track .env")
    (git_env.primary / ".env").write_text("FOO=mid-edit\n")
    wt = git_env.add_worktree()

    result = git_env.sync()

    assert result.returncode == 2
    assert ".env" in result.stderr
    assert (wt / ".env").read_text() == "FOO=bar\n"


def test_force_overrides_dirty_primary_check(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    git_env.commit_all("track .env")
    (git_env.primary / ".env").write_text("FOO=mid-edit\n")
    wt = git_env.add_worktree()

    result = git_env.sync("--force")

    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=mid-edit\n"


def test_dirty_tracked_template_does_not_block_sync(git_env: GitEnv) -> None:
    (git_env.primary / ".env.example").write_text("FOO=\n")
    git_env.commit_all("track template")
    (git_env.primary / ".env.example").write_text("FOO=edited\n")
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()

    result = git_env.sync()

    assert result.returncode == 0, result.stderr
    assert (wt / ".env").read_text() == "FOO=bar\n"


def test_refuses_when_pwd_outside_worktree(git_env: GitEnv, tmp_path: Path) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = git_env.run_cli(["sync"], cwd=wt, pwd=elsewhere)

    assert result.returncode == 2
    assert "PWD" in result.stderr


def test_missing_primary_is_refused(git_env: GitEnv) -> None:
    (git_env.primary / ".env").write_text("FOO=bar\n")
    wt = git_env.add_worktree()

    git_env.primary.rename(git_env.tmp_path / "primary-moved")

    result = git_env.run_cli(["sync"], cwd=wt)

    assert result.returncode == 2
