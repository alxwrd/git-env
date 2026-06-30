# Bash completion for `git env` / `git-env`.
#
# Source this file directly, or install it where bash-completion looks for
# completions (see `git env --install-completions bash --write`).
#
# Defining `_git_env` lets git's own completion machinery dispatch
# `git env <TAB>` to this function automatically once git-completion.bash is
# loaded (it tries `_git_<subcommand>` for any subcommand it doesn't know
# about natively). The explicit `complete`/`__git_complete` call below also
# covers invoking the `git-env` binary directly.

_git_env_subcommands="sync"
_git_env_sync_opts="--dry-run -n --force -f --verbose -v --quiet -q --pattern --path --help -h"
_git_env_root_opts="--help -h --version --install-completions --write"

_git_env()
{
	local cur prev words cword
	if declare -F _get_comp_words_by_ref >/dev/null 2>&1; then
		_get_comp_words_by_ref -n =: cur prev words cword
	else
		cur="${COMP_WORDS[COMP_CWORD]}"
		prev="${COMP_WORDS[COMP_CWORD-1]:-}"
		words=("${COMP_WORDS[@]}")
		cword=$COMP_CWORD
	fi

	if [[ "$prev" == "--install-completions" ]]; then
		COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur"))
		return
	fi

	local subcommand="" i
	for ((i = 1; i < cword; i++)); do
		case "${words[i]}" in
			-*) ;;
			*)
				subcommand="${words[i]}"
				break
				;;
		esac
	done

	if [[ -z "$subcommand" ]]; then
		COMPREPLY=($(compgen -W "${_git_env_subcommands} ${_git_env_root_opts}" -- "$cur"))
		return
	fi

	case "$subcommand" in
		sync)
			COMPREPLY=($(compgen -W "${_git_env_sync_opts}" -- "$cur"))
			;;
		*)
			COMPREPLY=()
			;;
	esac
}

if declare -F __git_complete >/dev/null 2>&1; then
	__git_complete git-env _git_env
else
	complete -o bashdefault -o default -F _git_env git-env 2>/dev/null \
		|| complete -F _git_env git-env
fi
