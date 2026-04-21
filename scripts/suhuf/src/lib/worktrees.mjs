import { execFileSync } from "node:child_process";
import * as git from "./git.mjs";

export function parseWorktreeList(raw) {
  const blocks = raw.split(/\n\n+/).filter(Boolean);
  return blocks.map((b) => {
    const lines = b.split("\n");
    const get = (k) => {
      const l = lines.find((x) => x.startsWith(k + " "));
      return l ? l.slice(k.length + 1) : null;
    };
    return {
      path: get("worktree"),
      head: get("HEAD"),
      branch: (get("branch") || "").replace("refs/heads/", "") || null,
    };
  });
}

export function list() {
  const raw = execFileSync("git", ["worktree", "list", "--porcelain"], { encoding: "utf8" });
  return parseWorktreeList(raw);
}

export function lag(wt, base = "origin/main") {
  try {
    return git.commitsBehind(base, wt.head, { cwd: wt.path });
  } catch {
    return null;
  }
}

export function touchedPaths(wt, base = "origin/main") {
  try {
    return git.changedPaths(base, { cwd: wt.path });
  } catch {
    return [];
  }
}

export function safeToPrune(wt) {
  if (!wt.branch || wt.branch === "main") return false;
  try {
    if (git.hasUncommitted({ cwd: wt.path })) return false;
  } catch {
    return false;
  }
  try {
    const merged = execFileSync("git", ["branch", "--merged", "main"], { encoding: "utf8" });
    if (merged.split("\n").some((l) => l.trim().replace(/^\*\s*/, "") === wt.branch)) return true;
  } catch {}
  return false;
}
