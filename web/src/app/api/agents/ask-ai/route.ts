import { NextResponse } from "next/server";
import { callAnthropic, AgentError } from "@/lib/agents/anthropic";
import type { AskAiRequest, ChatTurn } from "@/lib/agents/types";

export async function POST(request: Request): Promise<Response> {
  let body: Partial<AskAiRequest>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { word, sentence, question, history } = body;
  if (!word || !sentence || !question) {
    return NextResponse.json(
      { error: "word, sentence, and question are required" },
      { status: 400 },
    );
  }

  const system = `You are a patient, knowledgeable Arabic grammar teacher. A student is reading a classical Arabic text and has a question about a specific word.

Context:
- Word: ${word}
- Sentence: ${sentence}

Answer their question clearly, mixing Arabic grammar terminology with English explanations. Use examples when helpful. Keep answers concise (2-4 paragraphs max). When referencing Arabic grammatical terms, show them in Arabic script.`;

  const messages = [
    ...((history ?? []) as ChatTurn[]).map((m) => ({ role: m.role, content: m.content })),
    { role: "user" as const, content: question },
  ];

  try {
    const text = await callAnthropic({ system, messages, maxTokens: 800 });
    return NextResponse.json({ response: text });
  } catch (e) {
    const status = e instanceof AgentError ? e.status : 500;
    return NextResponse.json({ error: (e as Error).message }, { status });
  }
}
