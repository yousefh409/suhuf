"use client";
import { useEffect, useRef, useState } from "react";
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  FloatingPortal,
} from "@floating-ui/react";
import { useWordPopover } from "./WordPopoverProvider";
import { fetchIrab, fetchTranslation, askAi } from "@/lib/agents/client";
import type { IrabResult, TranslateResult, ChatTurn } from "@/lib/agents/types";
import "./word-popover.css";

type Tab = "irab" | "translate" | "ask";

export function WordPopover() {
  const popover = useWordPopover();
  const selection = popover?.selection ?? null;
  const anchorEl = popover?.anchorEl ?? null;

  const { refs, floatingStyles } = useFloating({
    placement: "bottom",
    open: !!selection,
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    refs.setReference(anchorEl);
  }, [anchorEl, refs]);

  const [tab, setTab] = useState<Tab>("irab");
  const prevSelectionRef = useRef(selection);
  if (prevSelectionRef.current !== selection) {
    prevSelectionRef.current = selection;
    if (tab !== "irab") setTab("irab"); // reset when a new word is opened
  }

  // Close on Escape + outside click.
  const floatingRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!selection) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && popover?.close();
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (floatingRef.current?.contains(target)) return;
      if (anchorEl?.contains(target)) return;
      popover?.close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [selection, anchorEl, popover]);

  if (!popover || !selection) return null;

  return (
    <FloatingPortal>
      <div
        ref={(node) => {
          refs.setFloating(node);
          floatingRef.current = node;
        }}
        style={floatingStyles}
        className="word-popover"
        dir="ltr"
      >
        <div className="word-popover__header">
          <span className="word-popover__word" dir="rtl">{selection.word}</span>
          <button className="word-popover__close" onClick={popover.close} aria-label="Close">×</button>
        </div>
        <div className="word-popover__tabs">
          <TabButton id="irab" tab={tab} setTab={setTab}>I&apos;rab</TabButton>
          <TabButton id="translate" tab={tab} setTab={setTab}>Translation</TabButton>
          <TabButton id="ask" tab={tab} setTab={setTab}>Ask AI</TabButton>
        </div>
        <div className="word-popover__body">
          {tab === "irab" && <IrabTab word={selection.word} sentence={selection.sentence} position={selection.position} />}
          {tab === "translate" && <TranslateTab word={selection.word} sentence={selection.sentence} />}
          {tab === "ask" && <AskTab word={selection.word} sentence={selection.sentence} />}
        </div>
      </div>
    </FloatingPortal>
  );
}

function TabButton({ id, tab, setTab, children }: { id: Tab; tab: Tab; setTab: (t: Tab) => void; children: React.ReactNode }) {
  return (
    <button
      className={`word-popover__tab ${tab === id ? "word-popover__tab--active" : ""}`}
      onClick={() => setTab(id)}
    >
      {children}
    </button>
  );
}

// Generic lazy-loader hook keyed on a dependency list.
function useLazy<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    load()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState({ error: e.message, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return { ...state, retry: () => setNonce((n) => n + 1) };
}

function ErrorRow({ error, retry }: { error: string; retry: () => void }) {
  return (
    <div>
      <div className="word-popover__error">{error}</div>
      <button className="word-popover__retry" onClick={retry}>Retry</button>
    </div>
  );
}

function IrabTab({ word, sentence, position }: { word: string; sentence: string; position: number }) {
  const { data, error, loading, retry } = useLazy<IrabResult>(
    () => fetchIrab({ word, sentence, position }),
    [word, sentence, position],
  );
  if (loading) return <div>Analyzing…</div>;
  if (error) return <ErrorRow error={error} retry={retry} />;
  if (!data) return null;
  return (
    <dl>
      <Row k="Part of speech" v={data.pos} />
      <Row k="Role" v={`${data.role_ar} — ${data.role}`} />
      <Row k="Case" v={`${data.case_ar} — ${data.case}`} />
      <Row k="Marker" v={`${data.marker_ar} — ${data.marker}`} />
      <Row k="Meaning" v={data.meaning} />
      <div style={{ marginTop: 8 }}>{data.why}</div>
    </dl>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="word-popover__row">
      <dt>{k}</dt>
      <dd dir="auto">{v}</dd>
    </div>
  );
}

function TranslateTab({ word, sentence }: { word: string; sentence: string }) {
  const { data, error, loading, retry } = useLazy<TranslateResult>(
    () => fetchTranslation({ word, sentence }),
    [word, sentence],
  );
  if (loading) return <div>Translating…</div>;
  if (error) return <ErrorRow error={error} retry={retry} />;
  if (!data) return null;
  return (
    <div>
      <p>{data.translation}</p>
      {data.related_words?.length > 0 && (
        <dl style={{ marginTop: 8 }}>
          {data.related_words.map((w, i) => (
            <div className="word-popover__row" key={i}>
              <dt dir="rtl">{w.word} <span style={{ opacity: 0.6 }}>({w.root})</span></dt>
              <dd>{w.meaning}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function AskTab({ word, sentence }: { word: string; sentence: string }) {
  const [thread, setThread] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the conversation when the word changes.
  useEffect(() => {
    setThread([]);
    setInput("");
    setError(null);
  }, [word, sentence]);

  const send = async () => {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const history = thread;
    setThread([...history, { role: "user", content: question }]);
    try {
      const { response } = await askAi({ word, sentence, question, history });
      setThread((t) => [...t, { role: "assistant", content: response }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="word-popover__chat">
      {thread.map((turn, i) => (
        <div key={i} className={turn.role === "user" ? "word-popover__turn--user" : undefined} dir="auto">
          {turn.content}
        </div>
      ))}
      {busy && <div>Thinking…</div>}
      {error && <div className="word-popover__error">{error}</div>}
      <div className="word-popover__ask">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about this word…"
        />
        <button onClick={send} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
