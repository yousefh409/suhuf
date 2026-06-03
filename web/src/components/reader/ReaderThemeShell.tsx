import type { ReactNode } from "react";

// The reader content surface. Theme now comes from the global [data-app-theme]
// on <html> (set from the preferences cookie), so this wrapper only provides the
// .reader-shell background/foreground, which read the inherited --reader-* tokens.
export function ReaderThemeShell({ children }: { children: ReactNode }) {
  return <div className="reader-shell">{children}</div>;
}
