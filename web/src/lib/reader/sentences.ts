import type { Token } from "./types";

export type ReaderSentence = { tokenIds: string[]; text: string };

export type WordSelection = {
  word: string; // token surface form (with tashkeel)
  sentence: string; // full sentence text the word sits in
  position: number; // 0-based index of the word within its sentence
};

// Arabic + ASCII terminal punctuation that ends a sentence.
const TERMINALS = [".", "؟", "!", ":", "؛", "?"];

function endsSentence(text: string): boolean {
  const trimmed = text.trimEnd();
  return TERMINALS.some((p) => trimmed.endsWith(p));
}

export function segmentSentences(tokens: Token[]): ReaderSentence[] {
  const out: ReaderSentence[] = [];
  let current: Token[] = [];
  for (const t of tokens) {
    current.push(t);
    if (endsSentence(t.text)) {
      out.push(toSentence(current));
      current = [];
    }
  }
  if (current.length > 0) out.push(toSentence(current));
  return out;
}

function toSentence(tokens: Token[]): ReaderSentence {
  return {
    tokenIds: tokens.map((t) => t.id),
    text: tokens.map((t) => t.text).join(" "),
  };
}

export function buildSelectionMap(tokens: Token[]): Map<string, WordSelection> {
  const map = new Map<string, WordSelection>();
  for (const sentence of segmentSentences(tokens)) {
    sentence.tokenIds.forEach((id, position) => {
      const word = tokens.find((t) => t.id === id)!.text;
      map.set(id, { word, sentence: sentence.text, position });
    });
  }
  return map;
}
