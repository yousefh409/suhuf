"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import {
  AppearanceControls,
  ReaderViewControls,
} from "@/components/settings/SettingsControls";

/**
 * Reader display & reading settings. The "Aa Display" button opens a sheet that
 * reuses the same controls as the profile Settings page (theme, text size, line
 * spacing, font, diacritics) plus reader-view rows (page markers, hadith cards).
 * The sheet keeps the parchment surface so it matches the profile Settings.
 */
export function DisplayPanel() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <>
      <button
        type="button"
        className="reader-textbtn"
        onClick={() => setOpen(true)}
        title="Display & reading settings"
      >
        <span
          aria-hidden
          style={{ fontFamily: "var(--font-arabic), serif", fontSize: 17, lineHeight: 1 }}
        >
          Aa
        </span>
        <span>Display</span>
      </button>

      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <>
            <div className="reader-scrim" onClick={close} aria-hidden />
            <aside
              role="dialog"
              aria-label="Display settings"
              className="fixed inset-y-0 right-0 z-50 flex w-[min(92vw,400px)] flex-col border-l border-ink/10 bg-parchment text-ink shadow-[-8px_0_40px_rgba(42,31,23,0.16)]"
            >
              <div className="flex items-center justify-between border-b border-ink/8 px-5 py-4">
                <h2 className="font-serif text-xl text-ink">Display</h2>
                <button
                  type="button"
                  onClick={close}
                  aria-label="Close"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-ink/50 transition-colors hover:bg-ink/5 hover:text-ink"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="space-y-8 overflow-y-auto px-5 py-6">
                <Section title="Appearance">
                  <AppearanceControls />
                </Section>
                <Section title="Reader view">
                  <ReaderViewControls />
                </Section>
              </div>
            </aside>
          </>,
          document.body,
        )}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-4 font-serif text-lg text-ink">{title}</h3>
      {children}
    </section>
  );
}
