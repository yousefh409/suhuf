import * as git from "../lib/git.mjs";
import * as wts from "../lib/worktrees.mjs";

export async function run() {
  const branch = git.currentBranch();
  const active = wts.list();
  const current = process.cwd();
  const worktrees = active
    .filter((w) => w.path !== current && w.branch !== "main")
    .map((w) => ({
      path: w.path,
      branch: w.branch,
      lag: wts.lag(w) ?? 0,
      touched: wts.touchedPaths(w),
    }));

  const overlaps = [];
  for (let i = 0; i < worktrees.length; i++) {
    for (let j = i + 1; j < worktrees.length; j++) {
      const shared = worktrees[i].touched.filter((p) => worktrees[j].touched.includes(p));
      if (shared.length) {
        overlaps.push({ branches: [worktrees[i].branch, worktrees[j].branch], paths: shared });
      }
    }
  }

  const lines = [];
  lines.push(`Branch: ${branch}`);
  lines.push("");
  lines.push("Worktrees:");
  if (worktrees.length === 0) lines.push("  No active worktrees.");
  for (const w of worktrees) {
    const lag = w.lag === 0 ? "up to date" : `${w.lag} behind`;
    lines.push(`  ${w.branch.padEnd(30)} ${lag}   ${w.path}`);
  }
  if (overlaps.length) {
    lines.push("");
    lines.push("Path overlaps (branches touch the same files):");
    for (const o of overlaps) {
      lines.push(`  ${o.branches.join(" / ")}: ${o.paths.slice(0, 3).join(", ")}${o.paths.length > 3 ? ", …" : ""}`);
    }
  }
  console.log(lines.join("\n"));
}
