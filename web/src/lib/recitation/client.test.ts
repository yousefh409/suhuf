// web/src/lib/recitation/client.test.ts
import { describe, it, expect, vi } from "vitest";
import { RecitationClient } from "./client";
import type { ScoreEvent } from "./types";

class FakeWS {
  static instances: FakeWS[] = [];
  url: string;
  readyState = 0; // CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sent: Array<string | ArrayBuffer | Float32Array> = [];

  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }
  send(data: string | ArrayBuffer | Float32Array) { this.sent.push(data); }
  close() {
    this.readyState = 3; // CLOSED
    this.onclose?.({ code: 1000, reason: "", wasClean: true } as CloseEvent);
  }
  // Helpers for tests
  _open() { this.readyState = 1; this.onopen?.({} as Event); }
  _emit(payload: unknown) { this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent); }
}

describe("RecitationClient", () => {
  it("sends init on connect", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const connectP = c.connect({
      passage: { id: "x", phrases: ["hello"] },
      lookbehind_count: 0,
    });
    FakeWS.instances[0]._open();
    await connectP;

    expect(FakeWS.instances[0].sent.length).toBe(1);
    const init = JSON.parse(FakeWS.instances[0].sent[0] as string);
    expect(init.passage.phrases).toEqual(["hello"]);
    expect(init.lookbehind_count).toBe(0);
  });

  it("emits score events to subscribers", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const handler = vi.fn();
    c.onScore(handler);
    const p = c.connect({ passage: { id: "x", phrases: ["a"] } });
    FakeWS.instances[0]._open();
    await p;

    const score: ScoreEvent = { words: [], matched_phrase_idx: 0 };
    FakeWS.instances[0]._emit(score);
    expect(handler).toHaveBeenCalledWith(score);
  });

  it("appendPhrases sends a typed text frame", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const p = c.connect({ passage: { id: "x", phrases: ["a"] } });
    FakeWS.instances[0]._open();
    await p;

    c.appendPhrases(["b", "c"]);
    const last = JSON.parse(FakeWS.instances[0].sent.at(-1) as string);
    expect(last).toEqual({ type: "append_phrases", phrases: ["b", "c"] });
  });

  it("ping → pong", async () => {
    FakeWS.instances = [];
    const c = new RecitationClient({
      url: "ws://test/ws",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      WebSocketImpl: FakeWS as any,
    });
    const p = c.connect({ passage: { id: "x", phrases: ["a"] } });
    FakeWS.instances[0]._open();
    await p;

    FakeWS.instances[0]._emit({ type: "ping" });
    expect(FakeWS.instances[0].sent.at(-1)).toBe("pong");
  });
});
