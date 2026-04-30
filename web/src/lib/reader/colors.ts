import type { BlockType } from "./types";

// Tailwind classes for inspector mode block borders + badges.
// Pick distinct hues per block type to make boundaries scannable.
export const BLOCK_BORDER: Record<BlockType, string> = {
  prose:          "border-zinc-300",
  heading:        "border-amber-400",
  hadith:         "border-emerald-400",
  isnad:          "border-sky-400",
  matn:           "border-violet-400",
  takhrij:        "border-fuchsia-400",
  hadith_grading: "border-yellow-500",
  poetry:         "border-rose-400",
  biography:      "border-teal-400",
  commentary:     "border-indigo-300",
  quoted_text:    "border-amber-500",
  editor_note:    "border-zinc-400 border-dashed",
};

export const BLOCK_BADGE: Record<BlockType, string> = {
  prose:          "bg-zinc-100 text-zinc-700",
  heading:        "bg-amber-100 text-amber-800",
  hadith:         "bg-emerald-100 text-emerald-800",
  isnad:          "bg-sky-100 text-sky-800",
  matn:           "bg-violet-100 text-violet-800",
  takhrij:        "bg-fuchsia-100 text-fuchsia-800",
  hadith_grading: "bg-yellow-100 text-yellow-800",
  poetry:         "bg-rose-100 text-rose-800",
  biography:      "bg-teal-100 text-teal-800",
  commentary:     "bg-indigo-100 text-indigo-800",
  quoted_text:    "bg-amber-100 text-amber-800",
  editor_note:    "bg-zinc-200 text-zinc-600",
};
