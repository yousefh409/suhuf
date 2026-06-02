import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { TranslateRequest } from "@/lib/agents/types";

const SYSTEM = `You are an expert translator of classical Arabic texts. You are given a full Arabic sentence and one focus word from within it (the word the reader tapped).

Translate the full sentence to English, preserving the scholarly register.

Then take the FOCUS WORD specifically: identify its root (جذر) and provide 4-6 related words that share that same root. The related words MUST derive from the focus word's root, not from any other word in the sentence.

For Islamic/Arabic terms that are commonly transliterated (e.g., hadith, fiqh, sunnah, i'rab), transliterate them and add a brief parenthetical gloss on first use.

Return a JSON object with:
- translation: the English translation of the full sentence
- related_words: array of objects with { word (Arabic with tashkeel), root (Arabic letters spaced), meaning (English) }, all sharing the focus word's root

Return ONLY valid JSON, no markdown fences.`;

export async function POST(request: Request): Promise<Response> {
  let body: Partial<TranslateRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { sentence, word } = body;
  if (!sentence || !word) {
    return NextResponse.json({ error: "sentence and word are required" }, { status: 400 });
  }

  try {
    const text = await callAnthropic({
      system: SYSTEM,
      messages: [
        {
          role: "user",
          content: `Focus word: ${word}\nFull sentence: ${sentence}\n\nTranslate the sentence and provide related vocabulary from the focus word's root.`,
        },
      ],
      maxTokens: 600,
    });
    let result: unknown;
    try {
      result = JSON.parse(text);
    } catch {
      throw new AgentError("Model did not return valid JSON", 502);
    }
    return NextResponse.json(result);
  } catch (e) {
    const status = e instanceof AgentError ? e.status : 500;
    return NextResponse.json({ error: (e as Error).message }, { status });
  }
}
