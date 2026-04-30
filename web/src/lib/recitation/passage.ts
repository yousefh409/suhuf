// web/src/lib/recitation/passage.ts
import type { Block } from "@/lib/reader/types";

const PHRASE_WORD_CAP = 40;
// Common Arabic + ASCII pause markers, in priority order
const PAUSE_MARKERS = /[.،؛:!؟?]/u;

type PhraseUnit = {
  text: string;
  tokenIds: string[]; // one per space-split word in `text`
  blockKey: string;
};

export type BuildPassageInput = {
  chapterBlocks: Block[];
  anchorBlockKey: string;
  lookbehindCount?: number;
  lookaheadPhraseCount?: number;
};

export type BuildPassageResult = {
  phrases: string[];
  wordIndexToTokenId: string[];
  startCursor: number;
};

export function buildPassage(
  input: BuildPassageInput,
): BuildPassageResult | null {
  const lookbehindCount = input.lookbehindCount ?? 2;
  const lookaheadPhraseCount = input.lookaheadPhraseCount ?? 15;

  // Step 1: convert all chapter blocks to phrase units
  const allUnits: PhraseUnit[] = [];
  for (const block of input.chapterBlocks) {
    if (block.type === "heading") continue;
    const units = blockToUnits(block);
    allUnits.push(...units);
  }
  if (allUnits.length === 0) return null;

  // Step 2: locate anchor (first phrase belonging to the anchor block, or first unit if not found)
  let anchorIdx = allUnits.findIndex((u) => u.blockKey === input.anchorBlockKey);
  if (anchorIdx < 0) anchorIdx = 0;

  // Step 3: slice [anchor - lookbehind … anchor + lookahead]
  const startIdx = Math.max(0, anchorIdx - lookbehindCount);
  const endIdx = Math.min(allUnits.length, anchorIdx + lookaheadPhraseCount + 1);
  const window = allUnits.slice(startIdx, endIdx);

  if (window.length === 0) return null;

  return {
    phrases: window.map((u) => u.text),
    wordIndexToTokenId: window.flatMap((u) => u.tokenIds),
    startCursor: anchorIdx - startIdx,
  };
}

function blockToUnits(block: Block): PhraseUnit[] {
  if (block.type === "poetry") {
    const out: PhraseUnit[] = [];
    for (const verse of block.hemistichs) {
      for (const hemistich of verse) {
        const text = hemistich.map((t) => t.text).join(" ").trim();
        if (!text) continue;
        out.push({
          text,
          tokenIds: hemistich.map((t) => t.id),
          blockKey: block.key,
        });
      }
    }
    return out;
  }

  // Prose-like: tokens = block.tokens
  const tokens = block.tokens;
  if (!tokens || tokens.length === 0) return [];

  // If short enough, one unit
  if (tokens.length <= PHRASE_WORD_CAP) {
    const text = tokens.map((t) => t.text).join(" ").trim();
    if (!text) return [];
    return [{ text, tokenIds: tokens.map((t) => t.id), blockKey: block.key }];
  }

  // Long block: split at pause markers, then hard-cap
  return splitLong(tokens, block.key);
}

function splitLong(
  tokens: { id: string; text: string }[],
  blockKey: string,
): PhraseUnit[] {
  const units: PhraseUnit[] = [];
  let cur: typeof tokens = [];

  const flush = () => {
    if (cur.length === 0) return;
    units.push({
      text: cur.map((t) => t.text).join(" "),
      tokenIds: cur.map((t) => t.id),
      blockKey,
    });
    cur = [];
  };

  for (const t of tokens) {
    cur.push(t);
    const hasPause = PAUSE_MARKERS.test(t.text);
    if (hasPause && cur.length >= 6) {
      flush();
      continue;
    }
    if (cur.length >= PHRASE_WORD_CAP) {
      flush();
    }
  }
  flush();
  return units;
}
