import { execSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import * as wts from "../lib/worktrees.mjs";
import * as git from "../lib/git.mjs";

const WT_ROOT = ".claude/worktrees";

export async function run(args) {
  const sub = args[0];
  if (sub === "new") return runNew(args.slice(1));
  if (sub === "finish") return runFinish();
  if (sub === "prune") return runPrune();
  console.error("Usage: suhuf worktree <new|finish|prune>");
  process.exit(2);
}

function runNew(args) {
  const branch = args[0];
  if (!branch) {
    console.error("suhuf worktree new <branch>");
    process.exit(2);
  }
  execSync("git fetch origin main", { stdio: "inherit" });
  const existing = wts.list().filter((w) => w.branch && w.branch !== "main");
  const warnings = [];
  for (const e of existing) {
    const touched = wts.touchedPaths(e);
    if (touched.length && e.branch !== branch) {
      warnings.push({ branch: e.branch, paths: touched });
    }
  }
  if (!existsSync(WT_ROOT)) mkdirSync(WT_ROOT, { recursive: true });
  const path = join(WT_ROOT, branch);
  execSync(`git worktree add -b ${branch} ${path} origin/main`, { stdio: "inherit" });
  if (warnings.length) {
    console.log("\n⚠  Other worktrees currently have changes in:");
    for (const w of warnings) {
      console.log(`   ${w.branch}: ${w.paths.slice(0, 5).join(", ")}${w.paths.length > 5 ? ", …" : ""}`);
    }
    console.log("   Review for overlap before making conflicting edits.");
  }
  console.log(`\n✓ Worktree ready at ${path}`);
}

async function runFinish() {
  const branch = git.currentBranch();
  if (branch === "main") {
    console.error("Can't finish main.");
    process.exit(2);
  }
  execSync("node scripts/suhuf/bin/suhuf.mjs ship", { stdio: "inherit" });
  console.log(`\n✓ Shipped ${branch}. To merge: \`gh pr create --fill && gh pr merge --rebase --delete-branch\``);
}

function runPrune() {
  const all = wts.list();
  const current = process.cwd();
  let removed = 0;
  for (const w of all) {
    if (w.path === current) continue;
    if (!wts.safeToPrune(w)) continue;
    execSync(`git worktree remove ${w.path} --force`, { stdio: "inherit" });
    try {
      execSync(`git branch -d ${w.branch}`, { stdio: "inherit" });
    } catch {}
    removed++;
  }
  console.log(`Pruned ${removed} worktree(s).`);
}
