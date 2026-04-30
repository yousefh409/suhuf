"use client";

import type { Token, ReaderMode } from "@/lib/reader/types";
import { stripTashkeel } from "@/lib/reader/tashkeel";

type Props = {
  token: Token;
  mode: ReaderMode;
  showTashkeel: boolean;   // reader toggle
  showDiff: boolean;       // inspector-only diff toggle
  accentClass?: string;    // optional class applied in reader mode (e.g. transmission-verb accent)
};

export function TokenText({ token, mode, showTashkeel, showDiff, accentClass }: Props) {
  const display = showTashkeel ? token.text : stripTashkeel(token.text);
  const raw = token.text_raw ?? null;
  const showRawAbove = mode === "inspector" && showDiff && raw && raw !== token.text;

  if (mode === "reader") {
    if (accentClass) {
      return <span className={accentClass}>{display} </span>;
    }
    return <span>{display} </span>;
  }

  const onClick = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(token.id).catch(() => undefined);
    }
  };

  return (
    <span
      data-token-id={token.id}
      title={token.id}
      onClick={onClick}
      className="cursor-pointer underline decoration-dotted underline-offset-4 decoration-zinc-300 hover:decoration-zinc-600"
    >
      {showRawAbove ? (
        <ruby>
          {display}
          <rt className="text-zinc-400 line-through text-[0.6em]">{raw}</rt>
        </ruby>
      ) : (
        display
      )}{" "}
    </span>
  );
}
