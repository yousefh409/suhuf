"use client";
import { useEffect, useRef, useState } from "react";
import { AudioLines, Square } from "lucide-react";

type Props = {
  onStart: (anchorBlockKey: string) => void;
  onStop: () => void;
  disabled?: boolean;
  isActive: boolean;
};

export function ReciteToggle({ onStart, onStop, disabled, isActive }: Props) {
  const [topVisibleKey, setTopVisibleKey] = useState<string | null>(null);
  const ioRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const seen = new Map<string, number>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const key = (e.target as HTMLElement).dataset.blockKey;
          if (!key) continue;
          if (e.isIntersecting) seen.set(key, e.boundingClientRect.top);
          else seen.delete(key);
        }
        // Pick the one closest to the top (smallest top offset, but still visible)
        let best: [string, number] | null = null;
        for (const [k, t] of seen) {
          if (best === null || t < best[1]) best = [k, t];
        }
        setTopVisibleKey(best?.[0] ?? null);
      },
      { threshold: 0, rootMargin: "0px 0px -50% 0px" },
    );
    ioRef.current = io;
    document.querySelectorAll<HTMLElement>("[data-block-key]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  const handle = () => {
    if (disabled) return;
    if (isActive) {
      onStop();
      return;
    }
    // Prefer the topmost block visible in the viewport. If the
    // IntersectionObserver hasn't fired yet (initial render, very short
    // chapter, headless viewport), fall back to the first block on the
    // page so the user can still start.
    const anchor =
      topVisibleKey ??
      (document.querySelector("[data-block-key]") as HTMLElement | null)?.dataset
        .blockKey;
    if (anchor) onStart(anchor);
  };

  return (
    <button
      type="button"
      onClick={handle}
      disabled={disabled}
      className={`reader-recite${isActive ? " is-active" : ""}`}
      title={disabled ? "No tashkeel — recite unavailable" : isActive ? "Stop reciting" : "Recite"}
    >
      {isActive ? <Square size={13} fill="currentColor" strokeWidth={0} /> : <AudioLines size={16} />}
      <span>{isActive ? "Stop" : "Recite"}</span>
    </button>
  );
}
