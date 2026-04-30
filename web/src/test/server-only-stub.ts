// Stub for the Next.js `server-only` marker package during vitest runs.
// Real Next.js builds resolve `server-only` from next/dist/compiled, but
// vitest doesn't see those internals — this no-op stub lets server-side
// modules be imported in unit tests for their pure helpers.
export {};
