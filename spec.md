# `git env` — specification

## Overview

`git env` is a git extension that manages environment files (initially `.env`) across linked worktrees. It is distributed as a `git-env` executable on `PATH`, invoked as `git env <subcommand>`.

The initial release ships one subcommand, `sync`, which copies environment files from the **primary worktree** into the **current linked worktree**. The architecture must accommodate future subcommands without breaking changes.

## Terminology

- **Primary worktree** — the worktree whose `.git` is a directory, i.e. the original clone. Located via `git rev-parse --path-format=absolute --git-common-dir` then resolving its parent.
- **Linked worktree** — a worktree created by `git worktree add`. Its `.git` is a file pointing into the primary's `.git/worktrees/<name>/`.
- **Env files** — files matched by the configured patterns (default: `.env` and `.env.*`, excluding `.env.example` and `.env.sample`).

## Commands

### `git env sync`

Copies env files from the primary worktree into the current linked worktree, preserving relative paths.

**Flags:**
- `--dry-run`, `-n` — print actions, change nothing. Exit 0 if up to date, 1 if changes would be made.
- `--force`, `-f` — overwrite local files even when they differ from the primary. Without this, conflicts abort the sync for that file (see Conflict handling).
- `--verbose`, `-v` — print every file considered, including skips.
- `--quiet`, `-q` — suppress non-error output.
- `--pattern <glob>` — override configured patterns for this run (repeatable).
- `--path <subdir>` — restrict to a subdirectory of the worktree.

**Exit codes:**
- `0` — success, or dry-run with no changes pending
- `1` — sync completed with per-file conflicts skipped
- `2` — refused to run (e.g. invoked inside primary worktree, not a git repo, bare repo)
- `3` — usage error (bad flag, unknown subcommand)
- `4` — I/O error during copy

### `git env --version`

Prints version. `--version` is top-level only (before any subcommand) to avoid clashing with `sync`'s `-v`/`--verbose`.

### `git env --help` / `git env help [subcommand]`

Prints usage. `git help env` must route to the manpage (see Documentation).

## Behavior rules

### Repository detection

1. Run `git rev-parse --is-inside-work-tree`. If false or it errors, exit 2 with "not inside a git worktree".
2. Detect bare repos via `git rev-parse --is-bare-repository`. If true, exit 2 with "bare repositories are not supported".
3. Compare `git rev-parse --git-dir` and `git rev-parse --git-common-dir`. If they resolve to the same path, this **is** the primary worktree — exit 2 with a clear message ("`git env sync` runs from a linked worktree; you appear to be in the primary at <path>").
4. The primary worktree root is `dirname` of the common git dir.

### File discovery

- Walk the primary worktree, matching files against the configured patterns.
- Do **not** respect `.gitignore` — env files are typically gitignored, which is the whole point. Do respect a dedicated `.envsyncignore` (see Configuration) for opt-out.
- Skip symlinks by default; follow them only with `env.sync.followSymlinks = true`.
- Skip files larger than `env.sync.maxFileSize` (default 1 MiB) with a warning — env files shouldn't be huge, and a large match usually indicates a misconfigured pattern.
- Submodules are not traversed; their env files are not synced. Document this limitation.

### Copy semantics

- Preserve relative path from primary root to worktree root.
- Preserve mode bits (especially the executable bit; some `.envrc` files are executable).
- Atomic write: copy to `<dest>.envsync.tmp` then `rename(2)` over the destination.
- Do not copy mtime — let the destination reflect when it was synced, which helps users see staleness.

### Conflict handling

A "conflict" is when the destination file exists and differs from the source. Default behavior:

- If destination doesn't exist → copy.
- If destination is byte-identical to source → skip silently.
- If destination differs → skip with a warning, set exit code 1, and tell the user to use `--force` or resolve manually. Print a one-line diff summary (e.g. "3 lines differ").

With `--force`, always overwrite, but back up the previous content to `<dest>.envsync.bak` (single backup, overwritten on subsequent forces) so a mistake is recoverable.

### Safety rails

- Refuse to run if the primary worktree has uncommitted changes to **tracked** files matching the env patterns. (Edge case: someone is mid-edit on a tracked template; don't propagate half-edits. Override with `--force`.)
- Refuse if `$PWD` is not within the current worktree (paranoid check against weird invocations).
- Never write outside the current worktree root, even if a pattern or symlink would resolve there.

## Configuration

Read via `git config`, supporting standard precedence (system → global → local → worktree).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `env.sync.patterns` | multi-value | `.env`, `.env.*` | Globs to sync. Multi-value so users can append rather than replace. |
| `env.sync.exclude` | multi-value | `.env.example`, `.env.sample`, `.env.template` | Patterns to never sync (committed templates). |
| `env.sync.followSymlinks` | bool | `false` | |
| `env.sync.maxFileSize` | int (bytes) | `1048576` | |
| `env.sync.onConflict` | enum | `skip` | `skip`, `overwrite`, `prompt` |
| `env.sync.backup` | bool | `true` | Whether `--force` writes `.envsync.bak`. |

Per-repo overrides live in `.git/config` of the primary; per-worktree overrides in the worktree's config. An optional `.envsync` file at the primary root can pin patterns into version control for team consistency (parsed as `key=value`, same keys as above minus the `env.sync.` prefix).

A `.envsyncignore` file (gitignore syntax) at the primary root excludes paths from sync regardless of pattern matches.

## Extensibility

To avoid painting the project into a corner:

1. **Dispatcher pattern.** `git-env` is a thin script that resolves `git env <sub>` → `git-env-<sub>` (looked up first inside the install dir, then on `PATH`). New subcommands are new files; the dispatcher doesn't change. This mirrors how git itself works and makes third-party subcommands possible.
2. **Reserved subcommand names.** Document that `sync`, `push`, `diff`, `status`, `list`, `edit`, `check` are reserved for future official use, so users don't write `git-env-status` that later conflicts.
3. **Stable exit codes.** Codes 0–4 above are part of the contract; scripts will depend on them.
4. **Output mode flag.** Reserve `--porcelain` for machine-readable output in a future version. v1 should error on it rather than ignore it, so users learn not to grep human output.
5. **No format parsing in v1.** Treat env files as opaque bytes. The moment the tool parses `KEY=VALUE`, it takes on dotenv-spec compatibility debt. Leave that for a future `git env merge` if ever needed.

### Future scope: `git env push`

`sync` is strictly one-way (primary → linked). A future `git env push` subcommand may go the other direction (linked → primary), for the case where a developer edits env files in a worktree and wants to promote them. **Not implemented in v1.** Bidirectional sync is intentionally out of scope; the two directions remain separate subcommands so each has clear semantics.

### Out of scope

- **Bare repositories.** Detected and rejected with exit code 2.
- **Submodules / multiple primaries.** Submodule env files are not synced. The tool assumes a single primary worktree per invocation.

## Documentation

- **Manpage**: ship `git-env.1` (and `git-env-sync.1`) installed under a directory on `MANPATH`. `git help env` calls `man git-env`, so the filename must be exactly `git-env.1`.
- **`git env --help`** prints a short usage; `git help env` opens the manpage. Both must work.
- **README** with: install instructions, quickstart, config reference, FAQ ("why not just symlink?", "does this work with bare repos?", "what about secrets in env files?").

## Tab completion

- **Bash**: ship `completions/git-env.bash` that hooks into git's existing completion via `__git_complete` or by defining `_git_env`. Document sourcing it from `~/.bash_completion.d/` or similar.
- **Zsh**: ship `_git-env` following zsh's `_git` plugin convention (file starts with `#compdef git-env`, placed on `$fpath`).
- **Fish**: ship `completions/git-env.fish`.
- Completion should offer subcommands (`sync`), flags per subcommand, and for `--pattern` it's fine to not complete values.

Provide a `git-env --install-completions <shell>` helper that prints the right snippet for the user's rc file, or copies the file into a standard location with `--install-completions <shell> --write`.

## Implementation language

Python, using [arguably](https://treykeown.github.io/arguably/) as the CLI argument parser. `arguably` provides subcommand dispatch, flag parsing, and help text generation from docstrings, keeping the implementation concise without a custom dispatcher.

## Installation

- Python package, installable via `pip install git-env` or `pipx install git-env`. The `git-env` entry point (and `git-env-sync` if split) is declared in `pyproject.toml`.
- `make install` with `PREFIX` (default `/usr/local`) installing:
  - `$PREFIX/bin/git-env` (and `git-env-sync` if split into files)
  - `$PREFIX/share/man/man1/git-env.1`
  - `$PREFIX/share/bash-completion/completions/git-env`
  - `$PREFIX/share/zsh/site-functions/_git-env`
  - `$PREFIX/share/fish/vendor_completions.d/git-env.fish`
- Homebrew formula as a stretch goal; the layout above makes it straightforward.

## Logging and output

- Default output: one line per file changed (`synced .env`, `synced apps/web/.env.local`), summary line at end (`2 files synced, 1 skipped`).
- Errors to stderr, normal output to stdout.
- Respect `NO_COLOR` and `--no-color`; auto-detect TTY for colorized output otherwise. Match git's color conventions (green for added, yellow for skipped, red for errors).

## Testing

- A test harness that creates a primary worktree, adds linked worktrees with `git worktree add`, seeds env files, and asserts post-sync state.
- Cases to cover: clean sync, no-op sync, conflict skip, conflict force, dry-run, run-from-primary refusal, run-from-bare-repo refusal, run-outside-repo refusal, symlink handling, large-file skip, pattern overrides, `.envsyncignore`, missing primary (worktree pointing at a moved repo).
- CI matrix: at minimum Linux + macOS, bash 3.2 (macOS default) and 5.x, git 2.30+.

