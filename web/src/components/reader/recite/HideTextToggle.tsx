"use client";
import { Eye, EyeOff } from "lucide-react";

/**
 * Hide-text toggle — when on, the passage is blurred and each word un-blurs as
 * you recite it (reveal-as-read). For memorisation practice. Disabled when the
 * chapter isn't recitable (no tashkeel).
 */
export function HideTextToggle({
  hidden,
  onToggle,
  disabled,
}: {
  hidden: boolean;
  onToggle: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      className={`reader-iconbtn${hidden ? " is-on" : ""}`}
      title={
        disabled
          ? "No tashkeel — hide-text unavailable"
          : hidden
            ? "Hide text: on — words reveal as you recite"
            : "Hide text: off"
      }
      aria-label="Hide text"
      aria-pressed={hidden}
    >
      {hidden ? <EyeOff size={16} /> : <Eye size={16} />}
    </button>
  );
}
