import type { ReactNode } from "react";

// Public route group: Discover (/library) and Reader (/reader/<id>).
// Unlike (app), this layout does NOT require a session and does NOT redirect —
// logged-out visitors can browse and read. Indexable (inherits root metadata).
export default function CatalogLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-white text-zinc-900">{children}</div>;
}
