/* FLO Assistant: a floating robot on every page that opens a chat about the dashboard.

   - The round launcher sits bottom-right; its robot waves every 15 seconds.
   - Its small × tucks it into a tab on the screen edge; the tab brings it back.
   - The panel answers from POST /api/chat, which reads only the dashboard's own numbers (read-only).
   - The conversation is kept for the browser tab (sessionStorage), so it survives page changes and reloads.
   - The server remembers the last 15 messages of each chat by its conversation id (used for follow-ups);
     "New chat" starts a new id. */
import { ArrowUpRight, RotateCcw, SendHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../../api/client";
import { RichText } from "./rich";
import { Robot } from "./Robot";
import "./assistant.css";

export type ChatReply = {
  answer: string;
  page: string | null;
  page_label: string | null;
  context: Record<string, unknown>;
  understood: boolean;
  intent: string;
  engine: string;
  conversation_id?: string;
};

type History = { conversation_id: string; messages: { role: "user" | "assistant"; text: string; page: string | null; page_label: string | null }[] };

type Msg = { id: number; role: "user" | "bot"; text: string; page?: string | null; pageLabel?: string | null; error?: boolean; retry?: string };

const CHAT_KEY = "flo-assistant-chat";
const DOCK_KEY = "flo-assistant-dock";
const MAX_LEN = 500;
const WELCOME = "Hi! I'm **FLO Assistant**. Ask me anything about this dashboard: any number, name or month, in English or Hinglish.";

type ChatState = { msgs: Msg[]; ctx: Record<string, unknown> | null; conv: string | null };

function load(): ChatState {
  try {
    const raw = sessionStorage.getItem(CHAT_KEY);
    if (raw) {
      const v = JSON.parse(raw);
      if (Array.isArray(v.msgs)) return { msgs: v.msgs, ctx: v.ctx ?? null, conv: typeof v.conv === "string" ? v.conv : null };
    }
  } catch {
    /* storage blocked or corrupt: start fresh */
  }
  return { msgs: [], ctx: null, conv: null };
}

function save(msgs: Msg[], ctx: Record<string, unknown> | null, conv: string | null) {
  try {
    sessionStorage.setItem(CHAT_KEY, JSON.stringify({ msgs: msgs.slice(-60), ctx, conv }));
  } catch {
    /* ignore */
  }
}

function dockedAway(): boolean {
  try {
    return localStorage.getItem(DOCK_KEY) === "tucked";
  } catch {
    return false;
  }
}

export function Assistant() {
  const [open, setOpen] = useState(false);
  const [tucked, setTucked] = useState(dockedAway);
  const [{ msgs, ctx, conv }, setState] = useState<ChatState>(load);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const nextId = useRef(msgs.reduce((m, x) => Math.max(m, x.id), 0) + 1);
  const loc = useLocation();

  useEffect(() => save(msgs, ctx, conv), [msgs, ctx, conv]);
  // A chat id without its messages (e.g. storage was cleared): show what the server remembers.
  useEffect(() => {
    if (!conv || msgs.length) return;
    api<History>(`/chat/${conv}`)
      .then((h) =>
        setState((s) =>
          s.msgs.length
            ? s
            : {
                ...s,
                msgs: h.messages.map((m) => ({ id: nextId.current++, role: m.role === "assistant" ? "bot" : "user", text: m.text, page: m.page, pageLabel: m.page_label })),
              },
        ),
      )
      .catch(() => setState((s) => ({ ...s, conv: null })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy, open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const setTuck = (v: boolean) => {
    setTucked(v);
    try {
      if (v) localStorage.setItem(DOCK_KEY, "tucked");
      else localStorage.removeItem(DOCK_KEY);
    } catch {
      /* ignore */
    }
  };

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus());
  };

  const push = (m: Omit<Msg, "id">, newCtx?: Record<string, unknown> | null, newConv?: string) =>
    setState((s) => ({
      msgs: [...s.msgs, { ...m, id: nextId.current++ }],
      ctx: newCtx === undefined ? s.ctx : newCtx,
      conv: newConv ?? s.conv,
    }));

  const send = async (text: string) => {
    const message = text.trim().slice(0, MAX_LEN);
    if (!message || busy) return;
    push({ role: "user", text: message });
    setDraft("");
    setBusy(true);
    try {
      const r = await api<ChatReply>("/chat", undefined, {
        method: "POST",
        body: JSON.stringify({ message, context: ctx, conversation_id: conv ?? undefined }),
      });
      push({ role: "bot", text: r.answer, page: r.page, pageLabel: r.page_label }, r.understood ? r.context : ctx, r.conversation_id);
    } catch (e) {
      push({ role: "bot", text: (e as Error).message || "Something went wrong. Please try again.", error: true, retry: message });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  /** Drops the failed question and its error, then asks again. */
  const retry = (m: Msg) => {
    setState((s) => {
      const i = s.msgs.findIndex((x) => x.id === m.id);
      const from = i > 0 && s.msgs[i - 1].role === "user" ? i - 1 : i;
      return { ...s, msgs: [...s.msgs.slice(0, from), ...s.msgs.slice(i + 1)] };
    });
    if (m.retry) void send(m.retry);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(draft);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send(draft);
    }
  };

  const reset = () => {
    setState({ msgs: [], ctx: null, conv: null });
    inputRef.current?.focus();
  };

  if (tucked && !open) {
    return (
      <button className="fa-tab" onClick={() => setTuck(false)} aria-label="Show FLO Assistant" title="Show FLO Assistant">
        <Robot size={20} />
      </button>
    );
  }

  return (
    <>
      {!open && (
        <div className="fa-dock">
          <button ref={launcherRef} className="fa-launcher" onClick={() => setOpen(true)} aria-label="Open FLO Assistant" aria-expanded={false} aria-haspopup="dialog" title="Ask FLO Assistant">
            <Robot size={30} />
          </button>
          <button className="fa-tuck" onClick={() => setTuck(true)} aria-label="Hide FLO Assistant to the screen edge" title="Hide">
            <X />
          </button>
        </div>
      )}
      {open && (
        <section className="fa-panel" role="dialog" aria-label="FLO Assistant" aria-modal="false">
          <header className="fa-head">
            <span className="fa-avatar">
              <Robot size={24} />
            </span>
            <div className="fa-title">
              <b>FLO Assistant</b>
              <span>Answers from this dashboard · read-only</span>
            </div>
            <button className="btn ghost icon" onClick={reset} aria-label="Start a new chat" title="New chat" disabled={!msgs.length || busy}>
              <RotateCcw />
            </button>
            <button className="btn ghost icon" onClick={close} aria-label="Close FLO Assistant" title="Close (Esc)">
              <X />
            </button>
          </header>
          <div className="fa-list" ref={listRef} aria-live="polite" aria-relevant="additions">
            <div className="fa-msg bot">
              <RichText text={WELCOME} />
            </div>
            {msgs.map((m) => (
              <div key={m.id} className={`fa-msg ${m.role}${m.error ? " error" : ""}`}>
                {m.role === "bot" ? <RichText text={m.text} /> : <p>{m.text}</p>}
                {m.role === "bot" && m.page && m.page !== loc.pathname && (
                  <Link className="fa-open" to={m.page}>
                    Open {m.pageLabel ?? "page"} <ArrowUpRight />
                  </Link>
                )}
                {m.error && m.retry && (
                  <button className="btn sm" onClick={() => retry(m)} disabled={busy}>
                    Try again
                  </button>
                )}
              </div>
            ))}
            {busy && (
              <div className="fa-msg bot fa-typing" aria-label="FLO Assistant is typing">
                <i />
                <i />
                <i />
              </div>
            )}
          </div>
          <form className="fa-input" onSubmit={submit}>
            <textarea
              ref={inputRef}
              rows={1}
              value={draft}
              maxLength={MAX_LEN}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask about the dashboard…"
              aria-label="Your question"
            />
            <button className="fa-send" type="submit" disabled={!draft.trim() || busy} aria-label="Send">
              <SendHorizontal />
            </button>
          </form>
        </section>
      )}
    </>
  );
}
