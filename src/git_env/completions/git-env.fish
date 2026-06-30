# Fish completions for `git-env` (and `git env`, which fish resolves to the
# same binary once `complete -c git-env` rules exist).

set -l subcommands sync

complete -c git-env -f

complete -c git-env -n "not __fish_seen_subcommand_from $subcommands" -a sync \
	-d "Sync env files from the primary worktree into the current linked worktree"
complete -c git-env -n "not __fish_seen_subcommand_from $subcommands" -l version \
	-d "Print the version"
complete -c git-env -n "not __fish_seen_subcommand_from $subcommands" -l install-completions \
	-x -a "bash zsh fish" -d "Print a completion snippet for a shell"
complete -c git-env -n "not __fish_seen_subcommand_from $subcommands" -l write \
	-d "Write the completion file instead of printing a snippet"
complete -c git-env -n "not __fish_seen_subcommand_from $subcommands" -s h -l help \
	-d "Show help"

complete -c git-env -n "__fish_seen_subcommand_from sync" -s n -l dry-run \
	-d "Print actions, change nothing"
complete -c git-env -n "__fish_seen_subcommand_from sync" -s f -l force \
	-d "Overwrite local files even when they differ from the primary"
complete -c git-env -n "__fish_seen_subcommand_from sync" -s v -l verbose \
	-d "Print every file considered, including skips"
complete -c git-env -n "__fish_seen_subcommand_from sync" -s q -l quiet \
	-d "Suppress non-error output"
complete -c git-env -n "__fish_seen_subcommand_from sync" -l pattern -r \
	-d "Glob to sync (repeatable)"
complete -c git-env -n "__fish_seen_subcommand_from sync" -l path -r -a "(__fish_complete_directories)" \
	-d "Restrict to a subdirectory of the worktree"
complete -c git-env -n "__fish_seen_subcommand_from sync" -s h -l help \
	-d "Show help"
