import { execFileSync } from "node:child_process";

function git(args, opts = {}) {
  return execFileSync("git", args, { encoding: "utf8", ...opts }).trimEnd();
}

export function currentBranch(opts = {}) {
  return git(["rev-parse", "--abbrev-ref", "HEAD"], opts);
}

export function changedPaths(base, opts = {}) {
  const out = git(["diff", "--name-only", `${base}...HEAD`], opts);
  return out ? out.split("\n") : [];
}

export function hasUncommitted(opts = {}) {
  return git(["status", "--porcelain"], opts).length > 0;
}

export function commitSha(ref = "HEAD", opts = {}) {
  return git(["rev-parse", ref], opts);
}

export function commitsBehind(base, ref, opts = {}) {
  return parseInt(git(["rev-list", "--count", `${ref}..${base}`], opts), 10);
}

export function fastForward(remote, branch, sha, opts = {}) {
  return git(["push", remote, `${sha}:refs/heads/${branch}`], opts);
}
