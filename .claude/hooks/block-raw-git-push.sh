#!/usr/bin/env bash
# Blocks raw `git push` from agent Bash calls. Forces use of `./bin/suhuf ship`
# (on a branch) or `./bin/suhuf quickfix` (on main). suhuf pushes via Node
# execSync, which bypasses this hook.
set -eo pipefail

input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // ""')

if ! echo "$cmd" | grep -qE '(^|[[:space:]]|;|&&|\|\|)git[[:space:]]+push([[:space:]]|$)'; then
  exit 0
fi

branch=$(git branch --show-current 2>/dev/null || echo "")

if [ "$branch" = "main" ]; then
  reason="Raw 'git push' from main is blocked. Use \`./bin/suhuf quickfix \"<msg>\"\` — it commits, pushes a temp branch, waits for CI, then fast-forwards main. Confirm with the user first."
else
  reason="Raw 'git push' is blocked on branch '$branch'. Use \`./bin/suhuf ship\` — it rebases onto origin/main, runs verify, and force-with-lease pushes. Confirm with the user first."
fi

jq -n --arg reason "$reason" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $reason
  }
}'
