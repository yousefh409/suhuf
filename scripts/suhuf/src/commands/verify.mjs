import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { PACKAGES, affectedPackages } from "../lib/packages.mjs";
import * as git from "../lib/git.mjs";

function ensureDeps(pkg) {
  if (pkg.kind !== "node") return;
  if (existsSync(join(pkg.path, "node_modules"))) return;
  const installCmd = existsSync(join(pkg.path, "package-lock.json")) ? "npm ci" : "npm install";
  console.log(`\n▶ [${pkg.name}] install: ${installCmd}`);
  const r = spawnSync(installCmd, { cwd: pkg.path, stdio: "inherit", shell: true });
  if (r.status !== 0) throw new Error(`install failed in ${pkg.name}`);
}

function runStep(pkg, step) {
  console.log(`\n▶ [${pkg.name}] ${step.kind}: ${step.cmd}`);
  const r = spawnSync(step.cmd, { cwd: pkg.path, stdio: "inherit", shell: true });
  const allow = step.allowExits || [];
  return r.status === 0 || allow.includes(r.status);
}

export async function run(args) {
  const base = args.includes("--base") ? args[args.indexOf("--base") + 1] : "origin/main";
  const all = args.includes("--all");
  const names = all
    ? PACKAGES.map((p) => p.name)
    : affectedPackages(git.changedPaths(base));
  if (names.length === 0) {
    console.log("No affected packages.");
    return;
  }
  console.log(`Affected: ${names.join(", ")}`);
  let failed = 0;
  for (const name of names) {
    const pkg = PACKAGES.find((p) => p.name === name);
    if (!pkg) continue;
    try {
      ensureDeps(pkg);
    } catch {
      console.error(`✗ ${name}:install failed`);
      failed++;
      continue;
    }
    for (const step of pkg.steps) {
      if (!runStep(pkg, step)) {
        console.error(`✗ ${name}:${step.kind} failed`);
        failed++;
      }
    }
  }
  if (failed > 0) {
    console.error(`\n${failed} step(s) failed`);
    process.exit(1);
  }
  console.log("\n✓ verify passed");
}
