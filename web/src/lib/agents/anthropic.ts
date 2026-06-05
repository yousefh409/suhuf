// Routed through OpenRouter's Anthropic-compatible Messages endpoint, so the
// request/response shape is still the native Anthropic format — only the host,
// auth header, and model slug change. Bump deliberately when the prompt or model
// changes.
const MODEL = "anthropic/claude-sonnet-4";

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
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) throw new AgentError("OPENROUTER_API_KEY is not set", 500);

  const res = await fetch("https://openrouter.ai/api/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
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
