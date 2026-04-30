"use client";
import { useEffect, useRef, useState } from "react";

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
    if (isActive) onStop();
    else if (topVisibleKey) onStart(topVisibleKey);
  };

  return (
    <button
      type="button"
      onClick={handle}
      disabled={disabled || (!isActive && !topVisibleKey)}
      className={`text-xs px-2 py-1 rounded font-mono ${
        isActive
          ? "bg-red-100 text-red-800 animate-pulse"
          : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 disabled:opacity-40"
      }`}
      title={disabled ? "No tashkeel — recite unavailable" : isActive ? "Stop" : "Recite"}
    >
      {isActive ? "● Stop" : "Recite"}
    </button>
  );
}
