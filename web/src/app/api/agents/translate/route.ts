import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { TranslateRequest } from "@/lib/agents/types";

const SYSTEM = `You are an expert translator of classical Arabic texts. Translate the given Arabic sentence to English, preserving the scholarly register.

Also identify the primary root (جذر) of the most significant content word in the sentence and provide 4-6 related words from the same root.

For Islamic/Arabic terms that are commonly transliterated (e.g., hadith, fiqh, sunnah, i'rab), transliterate them and add a brief parenthetical gloss on first use.

Return a JSON object with:
- translation: the English translation
- related_words: array of objects with { word (Arabic with tashkeel), root (Arabic letters spaced), meaning (English) }

Return ONLY valid JSON, no markdown fences.`;

export async function POST(request: Request): Promise<Response> {
  let body: Partial<TranslateRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { sentence } = body;
  if (!sentence) {
    return NextResponse.json({ error: "sentence is required" }, { status: 400 });
  }

  try {
    const text = await callAnthropic({
      system: SYSTEM,
      messages: [
        { role: "user", content: `Translate this Arabic sentence and provide related vocabulary:\n\n${sentence}` },
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
