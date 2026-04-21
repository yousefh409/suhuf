import { execSync } from "node:child_process";
import * as git from "../lib/git.mjs";

export async function run() {
  const branch = git.currentBranch();
  if (branch === "main") {
    console.error('suhuf ship: refusing to run on main. Use `suhuf quickfix "<msg>"` for direct-to-main changes.');
    process.exit(2);
  }
  if (git.hasUncommitted()) {
    console.error("suhuf ship: working tree has uncommitted changes. Commit or stash first.");
    process.exit(2);
  }
  console.log("▶ Fetching origin/main…");
  execSync("git fetch origin main", { stdio: "inherit" });
  console.log(`▶ Rebasing ${branch} onto origin/main…`);
  try {
    execSync("git rebase origin/main", { stdio: "inherit" });
  } catch {
    console.error("Rebase conflict. Resolve, `git rebase --continue`, then re-run `suhuf ship`.");
    process.exit(1);
  }
  console.log("▶ Running suhuf verify…");
  execSync("node scripts/suhuf/bin/suhuf.mjs verify --base origin/main", { stdio: "inherit" });
  console.log(`▶ Pushing ${branch}…`);
  execSync(`git push --force-with-lease -u origin ${branch}`, { stdio: "inherit" });
  console.log(`✓ Shipped ${branch}. Open a PR: \`gh pr create --fill\`.`);
}
