const COMMANDS = {
  ship: () => import("./commands/ship.mjs"),
  quickfix: () => import("./commands/quickfix.mjs"),
  verify: () => import("./commands/verify.mjs"),
  status: () => import("./commands/status.mjs"),
  worktree: () => import("./commands/worktree.mjs"),
  "sync-worktrees": () => import("./commands/sync-worktrees.mjs"),
};

const HELP = `Usage: suhuf <command> [args]

Commands:
  ship             Rebase current branch onto origin/main, verify, push --force-with-lease
  quickfix [msg]   Commit on main, push temp branch, wait for CI, fast-forward main
  verify           Run lint/typecheck/test for affected packages
  status           Branches, worktrees, drift
  worktree <sub>   new <branch> | finish | prune
  sync-worktrees   Rebase every non-current worktree onto origin/main
`;

export async function main(argv) {
  if (argv.length === 0 || argv[0] === "--help" || argv[0] === "-h") {
    console.log(HELP);
    return;
  }
  const [cmd, ...rest] = argv;
  const loader = COMMANDS[cmd];
  if (!loader) {
    console.error(`Unknown command: ${cmd}\n\n${HELP}`);
    process.exit(2);
  }
  const mod = await loader();
  await mod.run(rest);
}
