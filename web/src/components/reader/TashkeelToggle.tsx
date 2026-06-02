"use client";

import { useEffect, useState } from "react";

import { TASHKEEL_KEY as KEY } from "@/lib/reader/storageKeys";

export function TashkeelToggle() {
  const [on, setOn] = useState(true);

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
      Tashkeel: {on ? "On" : "Off"}
    </button>
  );
}
