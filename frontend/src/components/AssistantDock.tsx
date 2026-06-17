import { useRef, useState } from "react";
import { streamAssistant, abortAssistant, type AssistantEvent } from "../lib/api";
import { ViperOrb } from "./ViperOrb";

type Msg = { role: "you" | "viper"; text: string };

const CHIPS = ["Who's at risk this week?", "This week's lateness", "Summarize Aiden's month"];

export function AssistantDock({ token }: { token: string | null }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const runIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function send(text: string) {
    const q = text.trim();
    if (!q || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "you", text: q }, { role: "viper", text: "" }]);
    setStreaming(true);
    runIdRef.current = null;
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const appendToViper = (chunk: string) =>
      setMessages((m) => {
        const next = m.slice();
        const last = next[next.length - 1];
        if (last && last.role === "viper") next[next.length - 1] = { ...last, text: last.text + chunk };
        return next;
      });

    try {
      await streamAssistant(
        token,
        q,
        (e: AssistantEvent) => {
          if (e.kind === "run") runIdRef.current = e.runId;
          else if (e.kind === "delta") appendToViper(e.text);
          else if (e.kind === "error") appendToViper(`\n[error: ${e.message}]`);
        },
        ctrl.signal,
      );
    } catch (err) {
      appendToViper(`\n[connection error]`);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    if (runIdRef.current) void abortAssistant(token, runIdRef.current);
    setStreaming(false);
  }

  if (!open) {
    return <ViperOrb state={streaming ? "streaming" : "idle"} onClick={() => setOpen(true)} label="Open Ask Viper" />;
  }

  return (
    <section className="viper-dock glass" aria-label="Ask Viper">
      <header className="viper-dock__head">
        <ViperOrb state={streaming ? "streaming" : "idle"} label="Viper" />
        <span className="viper-dock__title">Ask Viper</span>
        <button type="button" className="viper-dock__close" onClick={() => setOpen(false)} aria-label="Collapse">
          ×
        </button>
      </header>

      <div className="viper-dock__log" role="log" aria-live="polite">
        {messages.length === 0 ? (
          <p className="viper-dock__hint">Ask about goals, lateness, or a person's month.</p>
        ) : (
          messages.map((m, i) => (
            <p key={i} className={`viper-msg viper-msg--${m.role}`}>
              <span className="viper-msg__who">{m.role}</span>
              {m.text || (m.role === "viper" && streaming ? "…" : "")}
            </p>
          ))
        )}
      </div>

      <div className="viper-dock__chips">
        {CHIPS.map((c) => (
          <button key={c} type="button" className="viper-chip" onClick={() => send(c)} disabled={streaming}>
            {c}
          </button>
        ))}
      </div>

      <form
        className="viper-dock__input"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask…"
          aria-label="Message"
          disabled={streaming}
        />
        {streaming ? (
          <button type="button" onClick={stop}>Stop</button>
        ) : (
          <button type="submit" aria-label="Send">▶</button>
        )}
      </form>
    </section>
  );
}
