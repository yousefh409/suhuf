"use client";

import { useEffect, useState } from "react";

import { HADITH_CARD_KEY as KEY } from "@/lib/reader/storageKeys";

export function HadithCardToggle() {
  const [on, setOn] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const v = window.localStorage.getItem(KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (v !== null) setOn(v === "1");
  }, []);

  const flip = () => {
    const next = !on;
    setOn(next);
    window.localStorage.setItem(KEY, next ? "1" : "0");
    window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: next ? "1" : "0" }));
  };

  return (
    <button
      type="button"
      onClick={flip}
      className="reader-chip text-xs font-mono px-2 py-1 rounded"
    >
      Cards: {on ? "On" : "Off"}
    </button>
  );
}
