"use client";

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

function Segmented<T extends string>({
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

const SectionLabel = ({ children }: { children: React.ReactNode }) => (
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
