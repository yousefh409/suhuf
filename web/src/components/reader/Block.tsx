import type { Block as BlockT, ReaderMode, Token } from "@/lib/reader/types";
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

export function Block({ block, pageNumber, mode, showTashkeel, showDiff, anchorId }: Props) {
  const inner = renderInner(block, mode, showTashkeel, showDiff);

  if (mode === "reader") {
    return (
      <div data-block-key={block.key} id={anchorId} className={anchorId ? "scroll-mt-16" : undefined}>
        {inner}
      </div>
    );
  }

  // Inspector: add bordered wrapper + badge
  return (
    <div
      data-block-key={block.key}
      data-block-type={block.type}
      id={anchorId}
      className={`relative my-3 border-r-2 pr-3 ${BLOCK_BORDER[block.type]} ${anchorId ? "scroll-mt-16" : ""}`}
    >
      <span
        className={`absolute -left-2 -top-3 px-1.5 py-0.5 rounded text-[10px] font-mono ${BLOCK_BADGE[block.type]}`}
      >
        {block.type} · {block.key} · p{pageNumber}
      </span>
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

  const tokens = block.tokens.map((t) => (
    <TokenText
      key={t.id}
      token={t}
      mode={mode}
      showTashkeel={showTashkeel}
      showDiff={showDiff}
      accentClass={isnadAccent && isTransmissionVerb(t) ? "reader-isnad-verb" : undefined}
    />
  ));

  switch (block.type) {
    case "heading":
      return isReader ? (
        <h2
          className="font-bold text-[1.55em] leading-snug mt-10 mb-4 text-center"
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
        <p className="font-medium leading-[2.05] my-1">{tokens}</p>
      ) : (
        <p className="font-medium leading-loose">{tokens}</p>
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
    case "hadith":
    case "prose":
    default:
      return <p className="leading-[2] my-2">{tokens}</p>;
  }
}
