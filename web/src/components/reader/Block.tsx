import type { Block as BlockT, ReaderMode } from "@/lib/reader/types";
import { BLOCK_BORDER, BLOCK_BADGE } from "@/lib/reader/colors";
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
      <div className="my-4 space-y-2">
        {block.hemistichs.map((verse, vi) => (
          <div key={vi} className="grid grid-cols-2 gap-x-8 text-center">
            {verse.map((hemistich, hi) => (
              <div key={hi}>
                {hemistich.map((t) => (
                  <TokenText
                    key={t.id}
                    token={t}
                    mode={mode}
                    showTashkeel={showTashkeel}
                    showDiff={showDiff}
                  />
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  const tokens = block.tokens.map((t) => (
    <TokenText
      key={t.id}
      token={t}
      mode={mode}
      showTashkeel={showTashkeel}
      showDiff={showDiff}
    />
  ));

  switch (block.type) {
    case "heading":
      // Heading blocks don't carry a level today (parser drops it onto the chapter
      // entry instead). Render uniformly as h2; revisit if/when blocks gain a level.
      return <h2 className="font-bold text-xl mt-6 mb-2">{tokens}</h2>;
    case "isnad":
      return <p className="text-zinc-600 leading-loose">{tokens}</p>;
    case "matn":
      return <p className="font-medium leading-loose">{tokens}</p>;
    case "biography":
      return (
        <aside className="bg-zinc-50 rounded p-3 my-3 italic leading-relaxed">
          {tokens}
        </aside>
      );
    case "hadith":
    case "prose":
    default:
      return <p className="leading-loose my-2">{tokens}</p>;
  }
}
