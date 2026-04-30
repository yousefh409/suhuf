import type { Block as BlockT, ReaderMode, Token, Span, SpanLabel } from "@/lib/reader/types";
import { BLOCK_BORDER, BLOCK_BADGE } from "@/lib/reader/colors";
import { stripTashkeel } from "@/lib/reader/tashkeel";
import { TokenText } from "./TokenText";

type Props = {
  block: BlockT;
  pageNumber: number;
  mode: ReaderMode;
  showTashkeel: boolean;
  showDiff: boolean;
  // When set, this block hosts a chapter anchor; the wrapper gets the id and
  // a scroll-mt offset so deep links land below the sticky header.
  anchorId?: string;
};

// Transmission verbs to faintly accent inside isnad blocks. Compared after
// stripping tashkeel so vocalised forms like حَدَّثَنَا still match.
const ISNAD_VERBS = new Set([
  "حدثنا",
  "حدثني",
  "أخبرنا",
  "أخبرني",
  "أنبأنا",
  "سمعت",
  "عن",
  "قال",
  "قالت",
  "روى",
]);

function isTransmissionVerb(token: Token): boolean {
  const stripped = stripTashkeel(token.text).replace(/[^\u0600-\u06FF]/g, "");
  return ISNAD_VERBS.has(stripped);
}

type SpanInfo = { label: SpanLabel; ref?: string | null };

/**
 * Build a token-id → span-info map for an ordered token list.
 * Marks every token from start_token_id..end_token_id (inclusive). When
 * spans overlap, the later one wins — fine for v1 since labels are
 * typically disjoint.
 */
function indexSpans(tokens: Token[], spans: Span[] | undefined): Map<string, SpanInfo> {
  const map = new Map<string, SpanInfo>();
  if (!spans || spans.length === 0) return map;
  const idToIdx = new Map<string, number>();
  tokens.forEach((t, i) => idToIdx.set(t.id, i));
  for (const s of spans) {
    const start = idToIdx.get(s.start_token_id);
    const end = idToIdx.get(s.end_token_id);
    if (start === undefined || end === undefined) continue;
    const lo = Math.min(start, end);
    const hi = Math.max(start, end);
    for (let i = lo; i <= hi; i++) {
      map.set(tokens[i].id, { label: s.label, ref: s.ref });
    }
  }
  return map;
}

export function Block({ block, pageNumber, mode, showTashkeel, showDiff, anchorId }: Props) {
  const inner = renderInner(block, mode, showTashkeel, showDiff);

  if (mode === "reader") {
    return (
      <div data-block-key={block.key} id={anchorId} className={anchorId ? "scroll-mt-16" : undefined}>
        {inner}
      </div>
    );
  }

  // Inspector: add bordered wrapper + badge. Falls back to prose styling for
  // any new block types that don't have an entry in BLOCK_BORDER yet.
  const border = BLOCK_BORDER[block.type] ?? BLOCK_BORDER.prose;
  const badge = BLOCK_BADGE[block.type] ?? BLOCK_BADGE.prose;
  const flagBadge = block.flags && block.flags.length > 0 ? (
    <span className="absolute -left-2 -top-3 ml-32 px-1.5 py-0.5 rounded text-[10px] font-mono bg-rose-100 text-rose-800">
      ⚠ {block.flags.join(",")}
    </span>
  ) : null;
  const parserDriftBadge = block.parser_type && block.parser_type !== block.type ? (
    <span className="absolute -right-1 -top-3 px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-100 text-zinc-600 border border-zinc-300">
      was: {block.parser_type}
    </span>
  ) : null;

  return (
    <div
      data-block-key={block.key}
      data-block-type={block.type}
      id={anchorId}
      className={`relative my-3 border-r-2 pr-3 ${border} ${anchorId ? "scroll-mt-16" : ""}`}
    >
      <span
        className={`absolute -left-2 -top-3 px-1.5 py-0.5 rounded text-[10px] font-mono ${badge}`}
      >
        {block.type} · {block.key} · p{pageNumber}
      </span>
      {parserDriftBadge}
      {flagBadge}
      {inner}
    </div>
  );
}

function renderInner(
  block: BlockT,
  mode: ReaderMode,
  showTashkeel: boolean,
  showDiff: boolean,
) {
  if (block.type === "poetry") {
    return (
      <div className="my-5 space-y-3">
        {block.hemistichs.map((verse, vi) => (
          <div
            key={vi}
            className="grid grid-cols-[1fr_auto_1fr] items-baseline gap-x-6"
          >
            {/* First hemistich → visually the right side under RTL grid flow. */}
            <div className="text-left">
              {verse[0]?.map((t) => (
                <TokenText
                  key={t.id}
                  token={t}
                  mode={mode}
                  showTashkeel={showTashkeel}
                  showDiff={showDiff}
                />
              ))}
            </div>
            <span
              aria-hidden
              className="text-[0.6em] self-center"
              style={{ color: "var(--reader-rule)" }}
            >
              ◆
            </span>
            <div className="text-right">
              {verse[1]?.map((t) => (
                <TokenText
                  key={t.id}
                  token={t}
                  mode={mode}
                  showTashkeel={showTashkeel}
                  showDiff={showDiff}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  const isReader = mode === "reader";
  const isnadAccent = isReader && block.type === "isnad";
  const spanIndex = indexSpans(block.tokens, block.spans);

  const tokens = block.tokens.map((t) => {
    const span = spanIndex.get(t.id);
    return (
      <TokenText
        key={t.id}
        token={t}
        mode={mode}
        showTashkeel={showTashkeel}
        showDiff={showDiff}
        accentClass={isnadAccent && isTransmissionVerb(t) ? "reader-isnad-verb" : undefined}
        spanLabel={span?.label}
        spanRef={span?.ref ?? undefined}
      />
    );
  });

  switch (block.type) {
    case "heading":
      return isReader ? (
        <h2
          className="font-bold text-[1.2em] leading-snug mt-8 mb-3 text-center"
          style={{ color: "var(--reader-fg)" }}
        >
          {tokens}
        </h2>
      ) : (
        <h2 className="font-bold text-xl mt-6 mb-2">{tokens}</h2>
      );
    case "isnad":
      return isReader ? (
        <p
          className="text-[0.92em] leading-[2] my-1"
          style={{ color: "var(--reader-fg-muted)" }}
        >
          {tokens}
        </p>
      ) : (
        <p className="text-zinc-600 leading-loose">{tokens}</p>
      );
    case "matn":
      return isReader ? (
        <p className="font-semibold leading-[2.05] my-2 text-[1.02em]">{tokens}</p>
      ) : (
        <p className="font-medium leading-loose">{tokens}</p>
      );
    case "takhrij":
      return isReader ? (
        <p
          className="text-[0.88em] leading-[1.85] my-1 italic"
          style={{ color: "var(--reader-fg-muted)" }}
        >
          {tokens}
        </p>
      ) : (
        <p className="text-zinc-500 leading-loose">{tokens}</p>
      );
    case "hadith_grading":
      return isReader ? (
        <p
          className="text-[0.85em] leading-snug my-1 font-mono tracking-wide"
          style={{ color: "var(--reader-accent)" }}
        >
          {tokens}
        </p>
      ) : (
        <p className="text-amber-700 font-mono text-sm">{tokens}</p>
      );
    case "biography":
      return isReader ? (
        <aside
          className="rounded p-3 my-3 leading-relaxed border"
          style={{
            background: "var(--reader-card-bg)",
            borderColor: "var(--reader-card-border)",
          }}
        >
          {tokens}
        </aside>
      ) : (
        <aside className="bg-zinc-50 rounded p-3 my-3 italic leading-relaxed">
          {tokens}
        </aside>
      );
    case "commentary":
      return isReader ? (
        <p
          className="text-[0.95em] leading-[1.95] my-2"
          style={{ color: "var(--reader-fg-muted)" }}
        >
          {tokens}
        </p>
      ) : (
        <p className="text-zinc-700 leading-loose">{tokens}</p>
      );
    case "quoted_text":
      return isReader ? (
        <blockquote
          className="my-2 leading-[2] pr-3 border-r-2"
          style={{ borderColor: "var(--reader-accent)", borderRightWidth: "2px" }}
        >
          {tokens}
        </blockquote>
      ) : (
        <blockquote className="border-r-2 border-amber-400 pr-3 my-2 leading-loose">
          {tokens}
        </blockquote>
      );
    case "editor_note":
      return isReader ? (
        <p
          className="text-[0.85em] leading-snug my-1"
          style={{ color: "var(--reader-fg-faint)" }}
        >
          {tokens}
        </p>
      ) : (
        <p className="text-zinc-400 text-sm leading-loose">{tokens}</p>
      );
    case "hadith":
    case "prose":
    default:
      return <p className="leading-[2] my-2">{tokens}</p>;
  }
}
