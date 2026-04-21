import { execSync } from "node:child_process";
import * as wts from "../lib/worktrees.mjs";
import * as git from "../lib/git.mjs";

export async function run() {
  execSync("git fetch origin main", { stdio: "inherit" });
  const current = process.cwd();
  const targets = wts.list().filter((w) => w.path !== current && w.branch && w.branch !== "main");
  if (targets.length === 0) {
    console.log("No other active worktrees.");
    return;
  }
  const results = await Promise.all(
    targets.map(async (w) => {
      try {
        if (git.hasUncommitted({ cwd: w.path })) {
          return { branch: w.branch, status: "skipped", reason: "uncommitted changes" };
        }
        execSync("git rebase origin/main", { cwd: w.path, stdio: "pipe" });
        return { branch: w.branch, status: "clean" };
      } catch (e) {
        try { execSync("git rebase --abort", { cwd: w.path, stdio: "pipe" }); } catch {}
        return { branch: w.branch, status: "conflict", reason: (e.stderr || e.message || "").toString().slice(0, 300) };
      }
    })
  );
  for (const r of results) {
    const tag = r.status === "clean" ? "✓" : r.status === "skipped" ? "-" : "✗";
    console.log(`${tag} ${r.branch}  ${r.status}${r.reason ? `  (${r.reason})` : ""}`);
  }
  if (results.some((r) => r.status === "conflict")) process.exit(1);
}
