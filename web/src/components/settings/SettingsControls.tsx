"use client";

import { useEffect, useState } from "react";
import {
  THEMES,
  TEXT_SIZES,
  ARABIC_FONTS,
  LINE_SPACINGS,
  type Theme,
  type TextSize,
  type ArabicFont,
  type LineSpacing,
} from "@/lib/preferences/types";
import { usePreferences } from "@/components/preferences/PreferencesProvider";
import { stripTashkeel } from "@/lib/reader/tashkeel";
import {
  PAGE_MARKERS_KEY,
  HADITH_CARD_KEY,
  READER_LAYOUT_KEY,
} from "@/lib/reader/storageKeys";

// ─── helpers ─────────────────────────────────────────────────────────────────

const THEME_META: Record<
  Theme,
  { label: string; bg: string; bar1: string; bar2: string }
> = {
  paper: { label: "Paper", bg: "#F5EEE4", bar1: "#2A1F17", bar2: "#2A1F17" },
  sepia: { label: "Sepia", bg: "#E8D6B3", bar1: "#3A2E22", bar2: "#3A2E22" },
  night: { label: "Night", bg: "#14110D", bar1: "#E8DDC9", bar2: "#E8DDC9" },
};

const FONT_META: Record<ArabicFont, { label: string; family: string }> = {
  scheherazade: {
    label: "Scheherazade",
    family: "var(--font-scheherazade), serif",
  },
  amiri: { label: "Amiri", family: "var(--font-amiri), serif" },
  "noto-naskh": {
    label: "Noto Naskh",
    family: "var(--font-noto-naskh), serif",
  },
};

const TEXT_SIZE_LABELS: Record<TextSize, string> = {
  s: "S",
  m: "M",
  l: "L",
  xl: "XL",
};

const LINE_SPACING_LABELS: Record<LineSpacing, string> = {
  comfortable: "Comfortable",
  compact: "Compact",
};

// ─── Segmented control ───────────────────────────────────────────────────────

export function Segmented<T extends string>({
  options,
  value,
  getLabel,
  onChange,
}: {
  options: readonly T[];
  value: T;
  getLabel: (v: T) => string;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-full bg-ink/5 p-1">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={[
            "rounded-full px-4 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25",
            opt === value
              ? "bg-parchment-warm text-ink shadow-sm"
              : "text-ink/60 hover:text-ink",
          ].join(" ")}
        >
          {getLabel(opt)}
        </button>
      ))}
    </div>
  );
}

// ─── Section label ────────────────────────────────────────────────────────────

export const SectionLabel = ({ children }: { children: React.ReactNode }) => (
  <p className="text-[11px] tracking-wider uppercase text-ink/50 mb-3">
    {children}
  </p>
);

// ─── Live preview ─────────────────────────────────────────────────────────────

const PREVIEW_TEXT =
  "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ. الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ. الرَّحْمَٰنِ الرَّحِيمِ. مَالِكِ يَوْمِ الدِّينِ.";

// A mini-reader sample that reflects every reading preference live: theme colors,
// Arabic font, text size, line spacing, and diacritics. Font/size/spacing read the
// global CSS vars (updated on each change); diacritics and theme re-render via context.
function ReadingPreview() {
  const { prefs } = usePreferences();
  const text = prefs.tashkeel ? PREVIEW_TEXT : stripTashkeel(PREVIEW_TEXT);

  return (
    <div>
      <SectionLabel>Preview</SectionLabel>
      <div
        className="rounded-xl border border-ink/10 px-5 py-6 overflow-hidden"
        style={{ background: "var(--reader-bg)" }}
      >
        <p
          dir="rtl"
          className="reader-article"
          style={{
            fontSize: "var(--reading-size)",
            lineHeight: "var(--reading-leading)",
            color: "var(--reader-fg)",
          }}
        >
          {text}
        </p>
      </div>
    </div>
  );
}

// ─── Appearance controls ─────────────────────────────────────────────────────

export function AppearanceControls() {
  const { prefs, setPref } = usePreferences();

  return (
    <div className="space-y-8">
      <ReadingPreview />

      {/* Theme */}
      <div>
        <SectionLabel>Theme</SectionLabel>
        <div className="flex gap-3 flex-wrap">
          {THEMES.map((theme) => {
            const meta = THEME_META[theme];
            const isActive = prefs.theme === theme;
            return (
              <button
                key={theme}
                type="button"
                onClick={() => setPref("theme", theme)}
                className={[
                  "flex flex-col items-center gap-2 rounded-xl p-2 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25",
                  isActive ? "ring-2 ring-gold" : "ring-1 ring-ink/10 hover:ring-ink/25",
                ].join(" ")}
              >
                {/* Swatch */}
                <div
                  className="rounded-lg overflow-hidden"
                  style={{ width: 64, height: 40, background: meta.bg }}
                >
                  <div className="flex flex-col justify-center h-full px-2 gap-1.5">
                    <div
                      className="rounded-full"
                      style={{ height: 3, background: meta.bar1, opacity: 0.8 }}
                    />
                    <div
                      className="rounded-full"
                      style={{
                        height: 3,
                        width: "60%",
                        background: meta.bar2,
                        opacity: 0.5,
                      }}
                    />
                  </div>
                </div>
                <span className="text-xs text-ink/70">{meta.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Text size */}
      <div>
        <SectionLabel>Text Size</SectionLabel>
        <Segmented
          options={TEXT_SIZES}
          value={prefs.textSize}
          getLabel={(v) => TEXT_SIZE_LABELS[v]}
          onChange={(v) => setPref("textSize", v)}
        />
      </div>

      {/* Line spacing */}
      <div>
        <SectionLabel>Line Spacing</SectionLabel>
        <Segmented
          options={LINE_SPACINGS}
          value={prefs.lineSpacing}
          getLabel={(v) => LINE_SPACING_LABELS[v]}
          onChange={(v) => setPref("lineSpacing", v)}
        />
      </div>

      {/* Arabic font */}
      <div>
        <SectionLabel>Arabic Font</SectionLabel>
        <div className="space-y-2">
          {ARABIC_FONTS.map((font) => {
            const meta = FONT_META[font];
            const isActive = prefs.arabicFont === font;
            return (
              <button
                key={font}
                type="button"
                onClick={() => setPref("arabicFont", font)}
                className={[
                  "w-full text-left rounded-xl border px-4 py-3 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25",
                  isActive
                    ? "ring-2 ring-gold border-transparent bg-parchment-warm"
                    : "border-ink/10 hover:border-ink/20 bg-parchment-warm",
                ].join(" ")}
              >
                <div className="flex flex-col gap-1">
                  <span className="text-xs text-ink/50 font-sans">{meta.label}</span>
                  <span
                    dir="rtl"
                    style={{ fontFamily: meta.family, fontSize: 22 }}
                    className="text-ink leading-relaxed"
                  >
                    بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Reading controls ─────────────────────────────────────────────────────────

export function ReadingControls() {
  const { prefs, setPref } = usePreferences();

  return (
    <div className="space-y-8">
      {/* Diacritics */}
      <div>
        <SectionLabel>Diacritics (Tashkeel)</SectionLabel>
        <div className="flex flex-col gap-1.5">
          <Segmented
            options={["on", "off"] as const}
            value={prefs.tashkeel ? "on" : "off"}
            getLabel={(v) => (v === "on" ? "On" : "Off")}
            onChange={(v) => setPref("tashkeel", v === "on")}
          />
          <p className="text-xs text-ink/50 mt-1">
            Show harakat (vowel marks) by default in the reader.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Reader-view controls ─────────────────────────────────────────────────────
// Page markers and hadith cards are per-reader view options held in localStorage
// (no persisted preference). ChapterScroll listens for the storage event these
// dispatch, so the reader updates live.

function useLocalToggle(key: string, fallback: boolean) {
  const [on, setOn] = useState(fallback);

  useEffect(() => {
    const v = window.localStorage.getItem(key);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (v !== null) setOn(v === "1");
    const onStorage = (e: StorageEvent) => {
      if (e.key === key && e.newValue !== null) setOn(e.newValue === "1");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key]);

  const set = (next: boolean) => {
    setOn(next);
    window.localStorage.setItem(key, next ? "1" : "0");
    window.dispatchEvent(new StorageEvent("storage", { key, newValue: next ? "1" : "0" }));
  };

  return [on, set] as const;
}

function useLocalString<T extends string>(key: string, fallback: T, allowed: readonly T[]) {
  const [value, setValue] = useState<T>(fallback);

  useEffect(() => {
    const v = window.localStorage.getItem(key);
    if (v !== null && (allowed as readonly string[]).includes(v)) setValue(v as T);
    const onStorage = (e: StorageEvent) => {
      if (e.key === key && e.newValue !== null && (allowed as readonly string[]).includes(e.newValue))
        setValue(e.newValue as T);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = (next: T) => {
    setValue(next);
    window.localStorage.setItem(key, next);
    window.dispatchEvent(new StorageEvent("storage", { key, newValue: next }));
  };

  return [value, set] as const;
}

function ToggleRow({
  label,
  caption,
  value,
  onChange,
}: {
  label: string;
  caption: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div className="flex flex-col gap-1.5">
        <Segmented
          options={["on", "off"] as const}
          value={value ? "on" : "off"}
          getLabel={(v) => (v === "on" ? "On" : "Off")}
          onChange={(v) => onChange(v === "on")}
        />
        <p className="text-xs text-ink/50 mt-1">{caption}</p>
      </div>
    </div>
  );
}

const LAYOUTS = ["scroll", "paged"] as const;

export function ReaderViewControls() {
  const [layout, setLayout] = useLocalString(READER_LAYOUT_KEY, "scroll", LAYOUTS);
  const [pageMarkers, setPageMarkers] = useLocalToggle(PAGE_MARKERS_KEY, true);
  const [cards, setCards] = useLocalToggle(HADITH_CARD_KEY, false);

  return (
    <div className="space-y-8">
      <div>
        <SectionLabel>Layout</SectionLabel>
        <div className="flex flex-col gap-1.5">
          <Segmented
            options={LAYOUTS}
            value={layout}
            getLabel={(v) => (v === "scroll" ? "Scroll" : "Pages")}
            onChange={setLayout}
          />
          <p className="text-xs text-ink/50 mt-1">
            Scroll continuously, or read one manuscript page at a time and flip with ← →.
          </p>
        </div>
      </div>
      <ToggleRow
        label="Page markers"
        caption="Show the ✦ markers where each original manuscript page breaks."
        value={pageMarkers}
        onChange={setPageMarkers}
      />
      <ToggleRow
        label="Hadith cards"
        caption="Group each hadith's chain (isnad) and text (matn) into a numbered card."
        value={cards}
        onChange={setCards}
      />
    </div>
  );
}
