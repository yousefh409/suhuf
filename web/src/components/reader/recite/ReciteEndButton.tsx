"use client";
import { Square } from "lucide-react";

/**
 * End button — tears the recitation session fully down (closes the socket,
 * clears highlights) and returns to idle. Shown only while a session is active;
 * distinct from the main button, which only pauses.
 */
export function ReciteEndButton({ onEnd }: { onEnd: () => void }) {
  return (
    <button
      type="button"
      onClick={onEnd}
      className="reader-iconbtn"
      title="End session — stop and reset"
      aria-label="End recitation session"
    >
      <Square size={16} fill="currentColor" />
    </button>
  );
}
