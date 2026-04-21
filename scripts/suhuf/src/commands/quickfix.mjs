import { execSync } from "node:child_process";
import * as git from "../lib/git.mjs";
import { waitForChecks } from "../lib/github.mjs";
import { deleteBranch } from "../lib/github.mjs";

const REQUIRED_JOBS = ["verify"];

export async function run(args) {
  const branch = git.currentBranch();
  if (branch !== "main") {
    console.error(`suhuf quickfix: must be run from main (you are on ${branch}). Use \`suhuf ship\` on a branch.`);
    process.exit(2);
  }

  const message = args.join(" ").trim();
  if (git.hasUncommitted()) {
    if (!message) {
      console.error('suhuf quickfix: working tree is dirty. Provide a commit message: `suhuf quickfix "msg"`.');
      process.exit(2);
    }
    execSync("git add -A", { stdio: "inherit" });
    execSync(`git commit -m "${message.replace(/"/g, '\\"')}"`, { stdio: "inherit" });
  }

  const sha = git.commitSha();
  const tempBranch = `quickfix/${Date.now()}`;
  console.log(`▶ Pushing temp branch ${tempBranch} @ ${sha.slice(0, 7)}…`);
  execSync(`git push origin HEAD:refs/heads/${tempBranch}`, { stdio: "inherit" });

  console.log(`▶ Waiting for CI on ${sha.slice(0, 7)}…`);
  try {
    const r = await waitForChecks(sha, {
      requiredJobs: REQUIRED_JOBS,
      timeoutMs: 20 * 60 * 1000,
    });
    if (r.status !== "success") {
      console.error(`✗ CI failed on ${tempBranch}. Inspect: \`gh run list --branch ${tempBranch}\`.`);
      console.error("  Main NOT updated. Fix on the temp branch, or abandon the quickfix.");
      process.exit(1);
    }
  } catch (e) {
    console.error(`✗ ${e.message}. Temp branch ${tempBranch} left in place.`);
    process.exit(1);
  }

  console.log(`▶ Fast-forwarding main to ${sha.slice(0, 7)}…`);
  git.fastForward("origin", "main", sha);

  console.log(`▶ Deleting temp branch ${tempBranch}…`);
  deleteBranch("origin", tempBranch);

  console.log("✓ Shipped to main. Run `suhuf sync-worktrees` if other worktrees are active.");
}
