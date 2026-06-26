import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useToast } from "./Toast";
import { Button, Spinner } from "./ui";

const NAME = "Sable";

interface Msg {
  role: "user" | "assistant";
  content: string;
  id?: number;        // exchange id (assistant messages, for rating)
  rated?: number;     // score given, if any
  noteOpen?: boolean;
  note?: string;
}

function IconChat(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" width={18} height={18} {...props}>
      <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 0 1-.9-3.8A8.38 8.38 0 0 1 11.5 3a8.38 8.38 0 0 1 9.5 8.5z" />
    </svg>
  );
}

/**
 * Sable — a dockable cybersecurity assistant. Lives in the app shell, so it
 * follows the analyst across every page. It is isolated from client data
 * (general security knowledge only). Rate answers 1–10 to teach it.
 */
export default function AssistantWidget() {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, busy]);

  const send = async () => {
    const q = input.trim();
    if (!q || busy) return;
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setBusy(true);
    try {
      const r = await api.askSable(q, history);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, id: r.id }]);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : `${NAME} is unavailable.`);
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: `(${NAME} couldn't answer — is the local model running?)` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const setMsg = (idx: number, patch: Partial<Msg>) =>
    setMsgs((m) => m.map((x, i) => (i === idx ? { ...x, ...patch } : x)));

  const rate = async (idx: number, score: number) => {
    const m = msgs[idx];
    if (!m.id) return;
    setMsg(idx, { rated: score });
    try {
      await api.rateSable(m.id, score, m.note);
    } catch {
      /* non-fatal — the rating just won't persist */
    }
  };

  const saveNote = async (idx: number) => {
    const m = msgs[idx];
    if (!m.id || !m.rated) {
      toast.info("Give a 1–10 rating first, then add your note.");
      return;
    }
    try {
      await api.rateSable(m.id, m.rated, m.note);
      toast.success("Thanks — that helps Sable improve.");
      setMsg(idx, { noteOpen: false });
    } catch {
      toast.error("Couldn't save the note.");
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-900/40 transition-colors hover:bg-indigo-500"
        title={`Ask ${NAME}`}
      >
        <IconChat /> Ask {NAME}
      </button>
    );
  }

  return (
    <div
      className={`fixed bottom-5 right-5 z-30 flex flex-col rounded-xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/50 ${
        expanded ? "h-[80vh] w-[min(640px,calc(100vw-2.5rem))]" : "h-[28rem] w-[min(380px,calc(100vw-2.5rem))]"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/15 text-indigo-300">
            <IconChat />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-slate-100">{NAME}</p>
            <p className="text-[10px] text-slate-500">Cybersecurity assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded((e) => !e)}
            title={expanded ? "Dock" : "Pop out"}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            {expanded ? "▢" : "⤢"}
          </button>
          <button
            onClick={() => setOpen(false)}
            title="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={bodyRef} className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {msgs.length === 0 && (
          <div className="mt-6 text-center text-xs text-slate-500">
            <p className="mb-1 text-slate-400">Ask {NAME} anything about threat hunting.</p>
            <p>MITRE ATT&amp;CK, detection logic, KQL/SPL, malware TTPs…</p>
            <p className="mt-3 text-[10px] text-slate-600">
              General security knowledge only — {NAME} can’t see client data.
            </p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-800 bg-slate-950/60 text-slate-200"
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
              {m.role === "assistant" && m.id && (
                <div className="mt-2 border-t border-slate-800 pt-1.5">
                  <div className="flex flex-wrap items-center gap-1">
                    <span className="mr-1 text-[10px] uppercase tracking-wide text-slate-500">
                      {m.rated ? `Rated ${m.rated}/10` : "Rate"}
                    </span>
                    {Array.from({ length: 10 }, (_, n) => n + 1).map((n) => (
                      <button
                        key={n}
                        onClick={() => rate(i, n)}
                        className={`h-5 w-5 rounded text-[10px] ${
                          m.rated === n
                            ? "bg-indigo-600 text-white"
                            : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                    <button
                      onClick={() => setMsg(i, { noteOpen: !m.noteOpen })}
                      className="ml-1 text-[10px] text-slate-500 hover:text-slate-300"
                    >
                      {m.noteOpen ? "hide note" : "+ note"}
                    </button>
                  </div>
                  {m.noteOpen && (
                    <div className="mt-1.5 flex gap-1">
                      <input
                        value={m.note ?? ""}
                        onChange={(e) => setMsg(i, { note: e.target.value })}
                        placeholder="What was good or wrong?"
                        className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-100"
                      />
                      <button
                        onClick={() => saveNote(i)}
                        className="rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                      >
                        Save
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Spinner /> {NAME} is thinking…
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-slate-800 p-2">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder={`Ask ${NAME}…  (Enter to send)`}
            className="max-h-28 flex-1 resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none"
          />
          <Button onClick={send} disabled={busy || !input.trim()}>
            {busy ? <Spinner /> : "Send"}
          </Button>
        </div>
      </div>
    </div>
  );
}
