import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { IrabRequest } from "@/lib/agents/types";

const SYSTEM = `You are an expert Arabic grammarian (نحوي). You analyze Arabic words in their sentence context and return grammatical analysis (إعراب).

Return a JSON object with these exact fields:
- pos: part of speech in English (noun, verb, particle, adjective, pronoun, etc.)
- role: grammatical role in English (subject, object, predicate, mudaf_ilayh, khabar, mubtada, etc.)
- role_ar: grammatical role in Arabic (مبتدأ، خبر، فاعل، مفعول به، مضاف إليه، etc.)
- case: grammatical case in English (marfu, mansub, majrur, majzum, mabni)
- case_ar: grammatical case in Arabic (مرفوع، منصوب، مجرور، مجزوم، مبني)
- marker: case marker in English (damma, fatha, kasra, sukun, tanween_damma, tanween_fatha, tanween_kasra)
- marker_ar: case marker in Arabic (ضمة، فتحة، كسرة، سكون، تنوين ضم، تنوين فتح، تنوين كسر)
- why: 1-2 sentence explanation mixing Arabic grammar terms with English explanation of WHY this word has this case in this sentence. Reference the specific grammar rule.
- meaning: brief English dictionary meaning of the word

Return ONLY valid JSON, no markdown fences.`;

export async function POST(request: Request): Promise<Response> {
  let body: Partial<IrabRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { word, sentence, position } = body;
  if (!word || !sentence) {
    return NextResponse.json({ error: "word and sentence are required" }, { status: 400 });
  }

  const userPrompt = `Analyze this word in context:

Word: ${word}
Full sentence: ${sentence}
Position in sentence: ${position ?? 0}

Provide the full إعراب analysis as JSON.`;

  try {
    const text = await callAnthropic({
      system: SYSTEM,
      messages: [{ role: "user", content: userPrompt }],
      maxTokens: 500,
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
