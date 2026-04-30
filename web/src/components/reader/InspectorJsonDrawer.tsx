"use client";

import { useState } from "react";
import type { Page } from "@/lib/reader/types";

type Props = { pages: Page[] };

export function InspectorJsonDrawer({ pages }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed top-0 right-0 h-full z-20 flex" dir="ltr">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="self-center bg-zinc-900 text-white text-xs font-mono px-2 py-3 rounded-l"
      >
        {open ? "▶" : "◀"} JSON
      </button>
      {open && (
        <aside className="w-[480px] max-w-[40vw] h-full bg-white border-l border-zinc-200 overflow-y-auto p-3">
          {pages.map((p) => (
            <details key={`${p.volume}-${p.page_number}`} className="mb-3 text-xs font-mono">
              <summary className="cursor-pointer text-zinc-700">
                V{p.volume} P{p.page_number} ({p.content_blocks.length} blocks)
              </summary>
              <pre className="mt-2 bg-zinc-50 p-2 rounded overflow-x-auto whitespace-pre">
{JSON.stringify(p.content_blocks, null, 2)}
              </pre>
            </details>
          ))}
        </aside>
      )}
    </div>
  );
}
