// Model matches the current Supabase edge functions; bump deliberately when the
// prompt or model changes.
const MODEL = "claude-sonnet-4-20250514";

export class AgentError extends Error {
  status: number;
  constructor(message: string, status = 500) {
    super(message);
    this.name = "AgentError";
    this.status = status;
  }
}

type Message = { role: "user" | "assistant"; content: string };

export async function callAnthropic(opts: {
  system: string;
  messages: Message[];
  maxTokens: number;
}): Promise<string> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new AgentError("ANTHROPIC_API_KEY is not set", 500);

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: opts.maxTokens,
      system: opts.system,
      messages: opts.messages,
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new AgentError(`Anthropic API error ${res.status}: ${detail}`, 502);
  }

  const data = await res.json();
  const text = data?.content?.[0]?.text;
  if (typeof text !== "string") throw new AgentError("Malformed Anthropic response", 502);
  return text;
}
