import type {
  IrabRequest,
  IrabResult,
  TranslateRequest,
  TranslateResult,
  AskAiRequest,
  AskAiResult,
} from "./types";

async function postJson<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = j?.error ?? "";
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(detail || `Request to ${path} failed (${res.status})`);
  }
  return (await res.json()) as TRes;
}

export function fetchIrab(input: IrabRequest): Promise<IrabResult> {
  return postJson<IrabRequest, IrabResult>("/api/agents/irab", input);
}

export function fetchTranslation(input: TranslateRequest): Promise<TranslateResult> {
  return postJson<TranslateRequest, TranslateResult>("/api/agents/translate", input);
}

export function askAi(input: AskAiRequest): Promise<AskAiResult> {
  return postJson<AskAiRequest, AskAiResult>("/api/agents/ask-ai", input);
}
