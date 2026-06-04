"use client";
import { useEffect, useRef, useState } from "react";
import { AudioLines, Loader2, AlertCircle, Pause, Play } from "lucide-react";
import type { RecitePhase } from "@/lib/recitation/state";

type Props = {
  onStart: (anchorBlockKey: string) => void;
  onPause: () => void;
  onResume: () => void;
  onEnd: () => void;
  disabled?: boolean;
  phase: RecitePhase;
  error?: string;
};

export function ReciteToggle({
  onStart, onPause, onResume, onEnd, disabled, phase, error,
}: Props) {
  const [topVisibleKey, setTopVisibleKey] = useState<string | null>(null);
  const ioRef = useRef<IntersectionObserver | null>(null);

  // After a failed start, show the error briefly, then quietly reset to idle so
  // the button doesn't stay stuck on "Try again".
  useEffect(() => {
    if (phase !== "error") return;
    const t = setTimeout(() => onEnd(), 4000);
    return () => clearTimeout(t);
  }, [phase, onEnd]);

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
    if (phase === "listening") return onPause();
    if (phase === "paused") return onResume();
    if (phase === "connecting") return; // use the End button to cancel
    // idle or error → start at the topmost block visible in the viewport.
    const anchor =
      topVisibleKey ??
      (document.querySelector("[data-block-key]") as HTMLElement | null)?.dataset
        .blockKey;
    if (anchor) onStart(anchor);
  };

  const view = {
    disabled: {
      cls: "",
      title: "No tashkeel — recite unavailable",
      icon: <AudioLines size={16} />,
      label: "Recite",
    },
    idle: {
      cls: "",
      title: "Recite — read aloud and get scored",
      icon: <AudioLines size={16} />,
      label: "Recite",
    },
    connecting: {
      cls: " is-connecting",
      title: "Connecting — use the stop button to cancel",
      icon: <Loader2 size={15} className="animate-spin" />,
      label: "Connecting…",
    },
    listening: {
      cls: " is-active",
      title: "Listening — tap to pause",
      icon: <Pause size={15} />,
      label: "Pause",
    },
    paused: {
      cls: " is-paused",
      title: "Paused — tap to resume",
      icon: <Play size={15} />,
      label: "Resume",
    },
    error: {
      cls: " is-error",
      title: error ?? "Couldn't start — tap to try again",
      icon: <AlertCircle size={15} />,
      label: "Try again",
    },
  }[disabled ? "disabled" : phase];

  return (
    <button
      type="button"
      onClick={handle}
      disabled={disabled}
      className={`reader-recite${view.cls}`}
      title={view.title}
    >
      {view.icon}
      <span>{view.label}</span>
    </button>
  );
}
