#!/usr/bin/env bash
set -euo pipefail

# ── constants ────────────────────────────────────────────────────────────────
SOLO_PROJECT_ID=4
MAX_ITERATIONS=30
POLL_INTERVAL=15        # seconds between status-file checks (and log fetches)
MAX_ITER_WAIT=600       # seconds before giving up on a single iteration

STATUS_FILE="/tmp/git-env-impl-$$.status"
STATUS_DONE="ALL_TODOS_DONE"
STATUS_COMPLETED="COMPLETED"

# ── colours ──────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD=$'\e[1m'; DIM=$'\e[2m'; GREEN=$'\e[32m'; CYAN=$'\e[36m'
  YELLOW=$'\e[33m'; RED=$'\e[31m'; RESET=$'\e[0m'
else
  BOLD=''; DIM=''; GREEN=''; CYAN=''; YELLOW=''; RED=''; RESET=''
fi

log()     { echo "${DIM}[$(date '+%H:%M:%S')]${RESET} $*"; }
info()    { echo "${CYAN}${BOLD}[$(date '+%H:%M:%S')] $*${RESET}"; }
success() { echo "${GREEN}${BOLD}[$(date '+%H:%M:%S')] $*${RESET}"; }
warn()    { echo "${YELLOW}[$(date '+%H:%M:%S')] $*${RESET}"; }
error()   { echo "${RED}${BOLD}[$(date '+%H:%M:%S')] $*${RESET}" >&2; }
divider() { echo "${DIM}$(printf '─%.0s' {1..60})${RESET}"; }

trap 'rm -f "$STATUS_FILE"' EXIT

# ── prompt ───────────────────────────────────────────────────────────────────
build_prompt() {
  cat <<PROMPT
You are implementing the git-env project in /Users/alxwrd/repos/git-env.

Follow these steps exactly:

1. Call mcp__solo__todo_list with project_id=${SOLO_PROJECT_ID} and completed=false.

2. If the list is EMPTY, run this Bash command and then stop:
     echo "${STATUS_DONE}" > ${STATUS_FILE}

3. Otherwise pick the single highest-priority incomplete todo
   (high > medium > low; break ties by lowest todo_id).

4. Implement it fully inside /Users/alxwrd/repos/git-env.
   - Read spec.md for guidance.
   - Check pyproject.toml and existing src/ files before writing anything.
   - Write real, working code — no stubs or placeholders.
   - The project uses Python with arguably (https://treykeown.github.io/arguably/).

5. Mark the todo done: call mcp__solo__todo_complete with the todo id and
   project_id=${SOLO_PROJECT_ID}.

6. Write a status line and then stop:
     echo "${STATUS_COMPLETED}: <todo title>" > ${STATUS_FILE}

Do not start the next todo. Stop after writing to ${STATUS_FILE}.

Constraints:
- Only write files inside /Users/alxwrd/repos/git-env.
- If a todo depends on one not yet done, skip it and pick the next available.
- Never leave a todo partially done — either finish it or skip it.
PROMPT
}

# ── wait for a background session to finish ──────────────────────────────────
wait_for_completion() {
  local session_id="$1"
  local deadline=$(( $(date +%s) + MAX_ITER_WAIT ))

  # Phase 1: wait for the session to appear (it may not be listed immediately)
  log "Waiting for session ${session_id} to appear…"
  until claude agents --json 2>/dev/null | grep -qF "$session_id"; do
    if (( $(date +%s) >= deadline )); then
      error "Session ${session_id} never appeared in agents list."
      exit 1
    fi
    sleep 2
  done
  log "Session ${session_id} is running."

  # Phase 2: wait for it to disappear
  while claude agents --json 2>/dev/null | grep -qF "$session_id"; do
    if (( $(date +%s) >= deadline )); then
      error "Timed out after ${MAX_ITER_WAIT}s waiting for session ${session_id}."
      exit 1
    fi
    sleep "$POLL_INTERVAL"
  done
}

# ── main loop ────────────────────────────────────────────────────────────────
iteration=0
start_time=$(date +%s)

info "git-env autonomous implementation loop"
log  "Project: Solo #${SOLO_PROJECT_ID} | Max iterations: ${MAX_ITERATIONS}"
log  "Status file: ${STATUS_FILE}"
divider

while (( iteration < MAX_ITERATIONS )); do
  iteration=$(( iteration + 1 ))
  > "$STATUS_FILE"   # clear from previous iteration

  echo ""
  divider
  info "Iteration ${iteration}/${MAX_ITERATIONS}  —  $(date '+%H:%M:%S')"
  divider

  PROMPT="$(build_prompt)"

  # Write prompt to a temp file to avoid any arg-length / quoting issues
  prompt_file=$(mktemp /tmp/git-env-prompt-XXXXXX.txt)
  echo "$PROMPT" > "$prompt_file"

  # Launch as a named background agent — visible in agentsview
  bg_output=$(claude --bg \
    -n "git-env: iter ${iteration}" \
    "$(cat "$prompt_file")" 2>&1) || {
      error "claude --bg failed (exit $?):"
      echo "$bg_output"
      rm -f "$prompt_file"
      exit 1
    }
  rm -f "$prompt_file"

  echo "$bg_output"

  # Parse short session ID from output: "backgrounded · a1b2c3d4 (…)"
  session_id=$(echo "$bg_output" | grep -oE '[0-9a-f]{8}' | head -1 || true)

  if [[ -n "$session_id" ]]; then
    log "Session: ${session_id}"
    log "  claude attach ${session_id}   ← open in another terminal"
    log "  claude logs   ${session_id}   ← view output snapshot"
  else
    warn "Could not parse session ID; will still wait on status file."
  fi

  # Block until the session disappears from the agents list
  wait_for_completion "$session_id"

  status_content=$(cat "$STATUS_FILE" 2>/dev/null || true)
  log "Agent wrote: ${status_content:-<nothing>}"

  if [[ -z "$status_content" ]]; then
    warn "Session ${session_id} ended without writing to status file."
    warn "Check agentsview or run: claude logs ${session_id}"
    error "Aborting. Re-run ./implement.sh to retry."
    exit 1
  fi

  if [[ "$status_content" == "$STATUS_DONE" ]]; then
    echo ""
    divider
    elapsed=$(( $(date +%s) - start_time ))
    success "All todos complete after ${iteration} iteration(s) (${elapsed}s)."
    divider
    exit 0
  fi

  if [[ "$status_content" != ${STATUS_COMPLETED}:* ]]; then
    warn "Unexpected status: '${status_content}' — continuing anyway."
  fi

  log "Iteration ${iteration} done. Starting next…"
done

echo ""
divider
warn "Reached cap of ${MAX_ITERATIONS} iterations without finishing all todos."
warn "Run ./implement.sh again to continue."
divider
exit 1
