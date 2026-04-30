// Top-level packages. `prefix` matches changed paths against this directory.
// Python dirs use `py_compile` for syntax + `pytest --co` for collection (tolerates
// exit 5 = "no tests collected") so CI green does not require tests to exist yet.
export const PACKAGES = [
  {
    name: "web",
    path: "web",
    prefix: "web/",
    kind: "node",
    steps: [
      { kind: "lint",      cmd: "npm run lint" },
      { kind: "typecheck", cmd: "npx tsc --noEmit" },
      { kind: "build",     cmd: "npm run build" },
    ],
  },
  {
    name: "ingestion",
    path: "ingestion",
    prefix: "ingestion/",
    kind: "python",
    steps: [
      { kind: "syntax", cmd: "python -m compileall -q ." },
      { kind: "test",   cmd: "pytest --co -q", allowExits: [5] },
    ],
  },
  {
    name: "recitation",
    path: "recitation",
    prefix: "recitation/",
    kind: "python",
    steps: [
      { kind: "syntax", cmd: "python -m compileall -q ." },
      { kind: "test",   cmd: "pytest --co -q", allowExits: [5] },
    ],
  },
];

export function affectedPackages(changedPaths) {
  const hit = new Set();
  for (const p of changedPaths) {
    for (const pkg of PACKAGES) {
      if (p.startsWith(pkg.prefix)) hit.add(pkg.name);
    }
  }
  return [...hit];
}
