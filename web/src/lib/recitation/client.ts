// web/src/lib/recitation/client.ts
import type {
  InitMessage, AppendMessage, ScoreEvent, ServerErrorEvent, ConnectionState,
} from "./types";

type Listener<T> = (v: T) => void;

type Init = Omit<InitMessage, "passage" | "auth_token"> & {
  passage: InitMessage["passage"];
};

export type RecitationClientOpts = {
  url: string;
  tokenProvider?: () => Promise<string>;
  // For tests: inject a fake WebSocket constructor.
  WebSocketImpl?: typeof WebSocket;
};

export class RecitationClient {
  private opts: RecitationClientOpts;
  private ws: WebSocket | null = null;
  private state: ConnectionState = "idle";
  private scoreListeners: Listener<ScoreEvent>[] = [];
  private errorListeners: Listener<ServerErrorEvent>[] = [];
  private stateListeners: Listener<ConnectionState>[] = [];

  constructor(opts: RecitationClientOpts) {
    this.opts = opts;
  }

  onScore(fn: Listener<ScoreEvent>) { this.scoreListeners.push(fn); }
  onError(fn: Listener<ServerErrorEvent>) { this.errorListeners.push(fn); }
  onState(fn: Listener<ConnectionState>) { this.stateListeners.push(fn); }

  getState(): ConnectionState { return this.state; }

  async connect(init: Init): Promise<void> {
    this.setState("connecting");
    const Impl = this.opts.WebSocketImpl ?? WebSocket;

    let authToken: string | undefined;
    if (this.opts.tokenProvider) {
      authToken = await this.opts.tokenProvider();
    }

    return new Promise((resolve, reject) => {
      const ws = new Impl(this.opts.url);
      this.ws = ws;
      ws.onopen = () => {
        const payload: InitMessage = {
          passage: init.passage,
          lookbehind_count: init.lookbehind_count ?? 0,
          ...(authToken ? { auth_token: authToken } : {}),
        };
        ws.send(JSON.stringify(payload));
        this.setState("connected");
        resolve();
      };
      ws.onmessage = (ev) => this.handleMessage(ev);
      ws.onerror = () => {
        this.setState("error");
        reject(new Error("WS error"));
      };
      ws.onclose = () => {
        if (this.state !== "error") this.setState("idle");
      };
    });
  }

  sendAudio(buf: Float32Array | ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    this.ws.send(buf instanceof Float32Array ? buf.buffer : buf);
  }

  appendPhrases(phrases: string[]): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    const msg: AppendMessage = { type: "append_phrases", phrases };
    this.ws.send(JSON.stringify(msg));
  }

  done(): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    this.ws.send("done");
  }

  close(): void {
    try { this.ws?.close(); } catch { /* noop */ }
    this.ws = null;
    this.setState("idle");
  }

  private handleMessage(ev: MessageEvent): void {
    let data: unknown;
    try {
      data = typeof ev.data === "string" ? JSON.parse(ev.data) : null;
    } catch {
      return;
    }
    if (!data || typeof data !== "object") return;
    const obj = data as Record<string, unknown>;
    if (obj.type === "ping") {
      this.ws?.send("pong");
      return;
    }
    if (obj.type === "error") {
      this.errorListeners.forEach((fn) => fn(obj as unknown as ServerErrorEvent));
      this.setState("error");
      return;
    }
    if (Array.isArray(obj.words)) {
      this.scoreListeners.forEach((fn) => fn(obj as unknown as ScoreEvent));
    }
  }

  private setState(s: ConnectionState): void {
    this.state = s;
    this.stateListeners.forEach((fn) => fn(s));
  }
}
