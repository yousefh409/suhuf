"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { LibraryStatus } from "@/lib/dashboard/types";

interface TabDef {
  status: LibraryStatus;
  label: string;
  count: number;
  dotClass: string;
}

interface LibraryTabsProps {
  tabs: TabDef[];
  grids: Record<LibraryStatus, React.ReactNode>;
  fullLibraryHref: string;
}

export default function LibraryTabs({ tabs, grids, fullLibraryHref }: LibraryTabsProps) {
  const [active, setActive] = useState<LibraryStatus>("in_progress");

  return (
    <div className="space-y-5">
      {/* Tab row */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          {tabs.map((tab) => {
            const isActive = tab.status === active;
            return (
              <button
                key={tab.status}
                type="button"
                onClick={() => setActive(tab.status)}
                className={`flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm transition-colors ${
                  isActive
                    ? "bg-ink/5 text-ink"
                    : "text-ink/50 hover:text-ink"
                }`}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${tab.dotClass}`} />
                <span>{tab.label}</span>
                <span className="text-ink/40 font-sans">{tab.count}</span>
              </button>
            );
          })}
        </div>

        {/* Full library link */}
        <Link
          href={fullLibraryHref}
          className="shrink-0 flex items-center gap-1.5 bg-cta-dark text-parchment-warm text-sm rounded-full px-5 py-2 hover:opacity-90 transition-opacity"
        >
          Full Library
          <ArrowRight size={14} />
        </Link>
      </div>

      {/* Active grid */}
      <div>{grids[active]}</div>
    </div>
  );
}
