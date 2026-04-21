#!/usr/bin/env bash
# Reminds the agent at turn-end if there is unshipped work on a feature branch.
# No-op on main (quickfix handles that path) and on clean, fully-pushed branches.
set -eo pipefail

branch=$(git branch --show-current 2>/dev/null || echo "")
[ -z "$branch" ] && exit 0
[ "$branch" = "main" ] && exit 0

dirty=$(git status --porcelain 2>/dev/null | head -1)

ahead=0
if git rev-parse --abbrev-ref "$branch@{upstream}" >/dev/null 2>&1; then
  ahead=$(git rev-list --count "@{upstream}..HEAD" 2>/dev/null || echo 0)
else
  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    ahead=$(git rev-list --count "origin/main..HEAD" 2>/dev/null || echo 0)
  fi
fi

if [ -z "$dirty" ] && [ "$ahead" = "0" ]; then
  exit 0
fi

status=""
[ -n "$dirty" ] && status="$status uncommitted changes;"
[ "$ahead" != "0" ] && status="$status $ahead commit(s) ahead of upstream;"

msg="Unshipped work on '$branch':$status Ask the user: \"Ready to ship?\" → commit, then \`./bin/suhuf ship\`, then \`gh pr create --fill\`."

jq -n --arg msg "$msg" '{systemMessage: $msg}'
