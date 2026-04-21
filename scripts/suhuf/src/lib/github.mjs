import { execFileSync } from "node:child_process";

function gh(args) {
  return execFileSync("gh", args, { encoding: "utf8" }).trim();
}

export async function pollUntil(fn, { intervalMs = 5000, timeoutMs = 15 * 60 * 1000 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const v = await fn();
    if (v) return v;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("pollUntil: timed out");
}

export function checksForSha(sha, { requiredJobs } = {}) {
  const out = gh(["api", `repos/{owner}/{repo}/commits/${sha}/check-runs`, "--paginate"]);
  const runs = JSON.parse(out).check_runs ?? [];
  const required = requiredJobs ? runs.filter((r) => requiredJobs.includes(r.name)) : runs;
  if (required.length === 0) return { status: "pending", runs: [] };
  const done = required.every((r) => r.status === "completed");
  const allPassed = required.every((r) => r.conclusion === "success");
  return {
    status: done ? (allPassed ? "success" : "failure") : "pending",
    runs: required,
  };
}

export async function waitForChecks(sha, { requiredJobs, timeoutMs } = {}) {
  return pollUntil(async () => {
    const r = checksForSha(sha, { requiredJobs });
    if (r.status === "pending") return null;
    return r;
  }, { timeoutMs });
}

export function deleteBranch(remote, branch) {
  return execFileSync("git", ["push", remote, `:refs/heads/${branch}`], { encoding: "utf8" });
}
