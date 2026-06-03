"use client";

import { useEffect, useRef } from "react";

const HEARTBEAT_MS = 30_000;
const POSITION_DEBOUNCE_MS = 1_500;
const ENDPOINT = "/api/reading/progress";

type Props = {
  /** The book's openiti_id (the reader is local-file driven; the API maps it to Supabase). */
  openitiId: string;
};

type Current = { pageNumber: number; volume: number };

/**
 * Records reading activity for a signed-in reader. Mounted only when logged in
 * (the reader page gates it), so it never fires for public visitors.
 *
 * Watches the page <section data-page-number> elements via IntersectionObserver
 * to know the current page, accumulates visible reading time + distinct pages
 * seen, and flushes to /api/reading/progress on page change (debounced), on a
 * heartbeat, and when the tab is hidden/closed.
 */
export default function ReadingTracker({ openitiId }: Props) {
  const current = useRef<Current | null>(null);
  const pendingPages = useRef<Set<number>>(new Set());
  const pendingSeconds = useRef(0);
  const lastTickAt = useRef<number | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const sections = Array.from(
      document.querySelectorAll<HTMLElement>("[data-page-number]"),
    );
    if (sections.length === 0) return;

    // --- flush: send accumulated activity + current position ---
    const flush = (useBeacon = false) => {
      const cur = current.current;
      if (!cur) return;
      const pagesRead = pendingPages.current.size;
      const durationSeconds = Math.round(pendingSeconds.current);
      pendingPages.current = new Set();
      pendingSeconds.current = 0;

      const payload = {
        openitiId,
        pageNumber: cur.pageNumber,
        volume: cur.volume,
        pagesRead,
        durationSeconds,
      };
      const json = JSON.stringify(payload);

      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon(ENDPOINT, new Blob([json], { type: "application/json" }));
        return;
      }
      void fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: json,
        keepalive: true,
      }).catch(() => {});
    };

    // --- time accrual: only count seconds while the tab is visible ---
    const accrue = () => {
      const now = Date.now();
      if (lastTickAt.current !== null && document.visibilityState === "visible") {
        pendingSeconds.current += (now - lastTickAt.current) / 1000;
      }
      lastTickAt.current = now;
    };
    if (document.visibilityState === "visible") lastTickAt.current = Date.now();

    // --- current page via intersection ratios ---
    const ratios = new Map<HTMLElement, number>();
    let debounce: ReturnType<typeof setTimeout> | null = null;

    const recomputeCurrent = () => {
      let best: HTMLElement | null = null;
      let bestRatio = 0;
      for (const [el, ratio] of ratios) {
        if (ratio > bestRatio) {
          bestRatio = ratio;
          best = el;
        }
      }
      if (!best) return;
      const pageNumber = Number(best.dataset.pageNumber);
      const volume = Number(best.dataset.volume ?? 1);
      if (Number.isNaN(pageNumber)) return;

      const changed =
        !current.current ||
        current.current.pageNumber !== pageNumber ||
        current.current.volume !== volume;

      current.current = { pageNumber, volume };
      pendingPages.current.add(pageNumber);

      if (changed) {
        accrue();
        if (debounce) clearTimeout(debounce);
        debounce = setTimeout(() => flush(), POSITION_DEBOUNCE_MS);
      }
    };

    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          ratios.set(e.target as HTMLElement, e.isIntersecting ? e.intersectionRatio : 0);
        }
        recomputeCurrent();
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    sections.forEach((s) => observer.observe(s));

    const heartbeat = setInterval(() => {
      accrue();
      flush();
    }, HEARTBEAT_MS);

    const onVisibility = () => {
      accrue();
      if (document.visibilityState === "hidden") flush(true);
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", () => {
      accrue();
      flush(true);
    });

    return () => {
      observer.disconnect();
      clearInterval(heartbeat);
      if (debounce) clearTimeout(debounce);
      document.removeEventListener("visibilitychange", onVisibility);
      accrue();
      flush(true);
    };
  }, [openitiId]);

  return null;
}
