#!/usr/bin/env bash
# Injects Suhuf shipping protocol into the agent context at session start.
# Branch-aware: main uses `suhuf quickfix`; feature branches / worktrees use `suhuf ship`.
set -eo pipefail

branch=$(git branch --show-current 2>/dev/null || echo "")
[ -z "$branch" ] && exit 0

if [ "$branch" = "main" ]; then
  ctx=$(cat <<'EOF'
## Suhuf shipping protocol — you are on `main`

For any change landing on main, use `./bin/suhuf quickfix "<msg>"`. Do NOT run raw `git push`, `git commit` + push, or edit main directly without this wrapper.

What `suhuf quickfix` does:
- Stages + commits the dirty tree with your message
- Pushes a temp branch `quickfix/<ts>` (main is NOT touched yet)
- Waits for the `verify` CI job
- On green: fast-forwards `origin/main` and deletes the temp branch
- On red: leaves main untouched, reports failure

## End-of-task checklist
1. Run local tests / `./bin/suhuf verify` first
2. Ask the user: "Ready to quickfix?" — wait for confirmation
3. On yes → `./bin/suhuf quickfix "<commit msg>"`
4. Report merge status back to the user
EOF
)
else
  ctx=$(cat <<EOF
## Suhuf shipping protocol — you are on branch \`$branch\`

For any change on this branch/worktree, use \`./bin/suhuf ship\`. Do NOT run raw \`git push\` — it is blocked by a PreToolUse hook and will fail.

What \`suhuf ship\` does:
- Refuses if working tree is dirty (commit first)
- Fetches origin/main, rebases this branch onto it
- Runs \`suhuf verify --base origin/main\` (affected-package lint/typecheck/test)
- Pushes with \`--force-with-lease\`

## End-of-task checklist
1. Commit all changes
2. Ask the user: "Ready to ship?" — wait for confirmation
3. On yes → \`./bin/suhuf ship\`
4. Open PR: \`gh pr create --fill\`
5. Optionally: \`gh pr merge --rebase\` (confirm first)
6. Wait for CI and report status
EOF
)
fi

jq -n --arg ctx "$ctx" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $ctx
  }
}'
