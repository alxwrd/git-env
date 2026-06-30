<div align="center">
    <h1><code>git-env</code></h1>
    <p align="center"><i>
        Copies untracked env files to your worktrees
    </i></p>
    <img width="256px" src="https://github.com/alxwrd/git-env/raw/main/.github/assets/man-reading-the-mail-768.png">
    <div align="center">
        <a href="https://github.com/alxwrd/git-env/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/alxwrd/git-env/ci.yml?branch=main&label=main"></a>
        <a href="https://pypi.python.org/pypi/git-env"><img src="https://img.shields.io/pypi/v/git-env"></a>
        <a href="https://github.com/alxwrd/git-env/blob/main/LICENCE"><img src="https://img.shields.io/pypi/l/git-env"></a>
    </div>
</div>


## Example

```sh
cd ~/repos/myproject                         # primary worktree, has .env
git worktree add ~/worktrees/my-feature      # create a linked worktree
cd ~/worktrees/my-feature
git env sync                                 # copies .env from the primary
```

```plain
$ git env sync
synced  .env
2 files synced, 0 unchanged, 0 conflicts skipped
```

Run it again later to pick up any changes made in the primary. By default,
`sync` won't clobber a file that has diverged locally — pass `--force` if
you want the primary's copy to win.


## Installation

```shell
uv tool install git-env
```

Or, with pipx:

```shell
pipx install git-env
```

This installs a `git-env` executable on your `PATH`, which git picks up
automatically as the `env` subcommand:

```sh
git env --version
```


## Syncing

`git env sync` copies env files from the primary worktree into the linked
worktree you're standing in. The primary worktree is the original clone — the
one whose `.git` is a real directory, not a file. `sync` locates it via
`git rev-parse --git-common-dir`.

Files are matched by glob against the entire primary worktree tree.
`.gitignore` is **not** consulted (env files are normally gitignored, which is
the point), but a `.envsyncignore` file at the primary root is. A file that
doesn't exist at the destination is copied. A file that's byte-identical is
skipped silently. A file that differs is skipped with a warning and a one-line
diff summary, unless `--force` is given.

Writes are atomic: each file is written to `<dest>.envsync.tmp` then renamed
over the destination. Mode bits (including the executable bit) are preserved;
mtimes are not, so a synced file's timestamp tells you when it was synced.

`sync` must run from a **linked** worktree — it refuses to run from the
primary itself, and refuses on bare repositories.

```
git env sync [--dry-run] [--force] [--verbose | --quiet]
             [--pattern <glob>]... [--path <subdir>]
```

| Flag | Short | Meaning |
|---|---|---|
| `--dry-run` | `-n` | Print what would happen; change nothing. |
| `--force` | `-f` | Overwrite local files that differ from the primary, backing up the previous content first. |
| `--verbose` | `-v` | Print every file considered, including skips. |
| `--quiet` | `-q` | Suppress non-error output. |
| `--pattern <glob>` | | Override configured patterns for this run. Repeatable. |
| `--path <subdir>` | | Restrict the sync to a subdirectory of the worktree. |

`--verbose` and `--quiet` are mutually exclusive.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, or dry-run with nothing to change. |
| `1` | Sync completed but one or more files were skipped due to conflicts. |
| `2` | Refused to run (not a git worktree, bare repo, invoked from the primary worktree, or the primary has uncommitted changes to tracked env files). |
| `3` | Usage error (bad flag, unknown or reserved subcommand). |
| `4` | I/O error while copying. |

These codes are part of the contract — scripts can rely on them.


## Configuration

All keys live under `env.sync.*` and are read with standard git config
precedence (system → global → local → worktree):

| Key | Type | Default | Meaning |
|---|---|---|---|
| `env.sync.patterns` | multi-value | `.env` | Globs to sync. Multi-value, so additional `git config --add` calls append rather than replace. |
| `env.sync.exclude` | multi-value | `.env.example`, `.env.sample`, `.env.template` | Patterns never synced, even if they match `patterns` (typically committed templates). |
| `env.sync.followSymlinks` | bool | `false` | Follow symlinked env files instead of skipping them. |
| `env.sync.maxFileSize` | int (bytes) | `1048576` | Files larger than this are skipped with a warning. |
| `env.sync.onConflict` | enum | `skip` | `skip`, `overwrite`, or `prompt`. |
| `env.sync.backup` | bool | `true` | Whether `--force` writes a `<dest>.envsync.bak` backup before overwriting. |

Set per-repo in the primary worktree's `.git/config`, or per-worktree in
that worktree's own config:

```sh
git config env.sync.onConflict overwrite
git config --add env.sync.patterns ".env.local"
```

### `.envsync`

An optional `key=value` file at the primary worktree root, for pinning
patterns into version control so the whole team gets the same defaults
without everyone running `git config`. Same keys as above, minus the
`env.sync.` prefix:

```
patterns=.env
exclude=.env.example
followSymlinks=false
```

Repeated keys accumulate (for multi-value settings). `git config` values,
if set, always take precedence over `.envsync`.

### `.envsyncignore`

A `gitignore`-syntax file at the primary worktree root. Paths it matches
are excluded from sync regardless of `env.sync.patterns` — use it to opt a
specific file or directory out without changing the glob patterns themselves.


## Shell completion

```sh
git env --install-completions bash   # print a snippet for your rc file
git env --install-completions zsh --write   # install the completion file directly
git env --install-completions fish
```

Supported shells: `bash`, `zsh`, `fish`. Without `--write`, the command
prints what to add to your shell config; with `--write`, it installs the
completion file to a standard location for that shell.


## FAQ

**Why not just symlink the env files instead?**
A symlink means there's only ever one copy, so editing the file in a linked
worktree edits the primary too — that defeats the purpose of having isolated
worktrees in the first place (e.g. running two branches with different API
keys or feature flags side by side). `git env sync` gives each worktree its
own independent copy, seeded from the primary, that you can then diverge from
intentionally.

**Does this work with bare repositories?**
No. `git env sync` requires a primary worktree with a real working tree to
copy *from*. Bare repos are detected and rejected with exit code `2`.

**What about secrets in env files?**
`git env sync` only ever copies bytes between worktrees on your local
filesystem — it doesn't transmit, log, or store file contents anywhere else,
and it never touches git history (env files are normally gitignored and stay
that way). The usual rules still apply: don't commit secrets, and be mindful
that `--force` backups (`<dest>.envsync.bak`) leave a second copy of the
previous content on disk.

**Can I sync changes back from a worktree to the primary?**
Not yet. `sync` is one-way (primary → linked). A `git env push` for the
reverse direction is planned but not implemented in v1 — see Limitations.


## Limitations

- **One-way sync only.** `git env sync` copies primary → linked. There is no
  bidirectional sync in v1; pushing changes from a linked worktree back to the
  primary isn't supported yet.
- **Submodules aren't traversed.** Env files inside submodules are not
  discovered or synced.
- **Single primary per invocation.** The tool assumes one primary worktree and
  doesn't support syncing between two linked worktrees directly.
- **No format parsing.** Env files are treated as opaque bytes; `git env`
  doesn't understand `KEY=VALUE` syntax, so it can't merge or diff values
  semantically — only whole-file conflict detection.
- **`--porcelain` is reserved but not implemented.** Passing it is a usage
  error in v1, by design, so scripts don't silently depend on output that may
  change later.

`push`, `diff`, `status`, `list`, `edit`, and `check` are reserved for
future official subcommands and will error if invoked, so a third-party
`git-env-<name>` script doesn't collide with them later.
