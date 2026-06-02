"use client";

import type { Token, ReaderMode, SpanLabel } from "@/lib/reader/types";
import { stripTashkeel } from "@/lib/reader/tashkeel";
import { useRecitationStatus } from "./recite/RecitationProvider";
import { useWordPopover } from "./word/WordPopoverProvider";
import type { WordSelection } from "@/lib/reader/sentences";
import "./recite/recite.css";

type Props = {
  token: Token;
  mode: ReaderMode;
  showTashkeel: boolean;   // reader toggle
  showDiff: boolean;       // inspector-only diff toggle
  accentClass?: string;    // optional class applied in reader mode (e.g. transmission-verb accent)
  spanLabel?: SpanLabel;   // when this token sits inside an annotated span
  spanRef?: string | null; // ref payload (e.g. "51:56" for qur_quote) — exposed via title attr
  selection?: WordSelection;   // reader-mode tap target; absent → not tappable
};

export function TokenText({ token, mode, showTashkeel, showDiff, accentClass, spanLabel, spanRef, selection }: Props) {
  const display = showTashkeel ? token.text : stripTashkeel(token.text);
  const raw = token.text_raw ?? null;
  const showRawAbove = mode === "inspector" && showDiff && raw && raw !== token.text;
  const spanClass = spanLabel ? `reader-span reader-span-${spanLabel}` : undefined;
  const recitationStatus = useRecitationStatus(token.id);
  const recitationClass = recitationStatus ? `tok--${recitationStatus}` : undefined;
  const title = spanRef ?? undefined;
  const popover = useWordPopover();

  if (mode === "reader") {
    const tappable = !!selection && !!popover;
    const className =
      [accentClass, spanClass, recitationClass, tappable ? "reader-word" : null]
        .filter(Boolean)
        .join(" ") || undefined;
    const onClick = tappable
      ? (e: React.MouseEvent<HTMLSpanElement>) => popover!.open(selection!, e.currentTarget)
      : undefined;
    if (className || onClick) {
      return (
        <span className={className} title={title} onClick={onClick}>
          {display}{" "}
        </span>
      );
    }
    return <span>{display} </span>;
  }

  const onClick = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(token.id).catch(() => undefined);
    }
  };

  const inspectorClass =
    "cursor-pointer underline decoration-dotted underline-offset-4 decoration-zinc-300 hover:decoration-zinc-600";
  const combined = [inspectorClass, spanClass, recitationClass].filter(Boolean).join(" ");

  return (
    <span
      data-token-id={token.id}
      title={title ?? token.id}
      onClick={onClick}
      className={combined}
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
