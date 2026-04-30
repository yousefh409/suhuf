import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
  title: "Internal — Suhuf",
};

export const viewport: Viewport = { themeColor: "#fafafa" };

export default function InternalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <div className="border-b border-amber-300 bg-amber-50 px-3 py-1 text-xs font-mono text-amber-900">
        INTERNAL · not for public access
      </div>
      {children}
    </div>
  );
}
