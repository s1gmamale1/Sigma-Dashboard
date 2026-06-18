import { useEffect, useRef, useState } from "react";
import { streamAssistant, abortAssistant, type AssistantEvent } from "../lib/api";
import { ViperOrb } from "./ViperOrb";
import { useReducedMotion } from "../hooks/useReducedMotion";

type Msg = { role: "you" | "viper"; text: string };

// Curated list of safe slash-commands to show in the palette.
// Destructive or session-resetting commands are deliberately excluded.
const SLASH_COMMANDS: { cmd: string; description: string }[] = [
  { cmd: "/compact",  description: "Summarize & shrink the session context" },
  { cmd: "/status",   description: "Session health snapshot" },
  { cmd: "/usage",    description: "Token / cost summary" },
  { cmd: "/think",    description: "Set thinking level" },
  { cmd: "/model",    description: "Show or change the model" },
  { cmd: "/stop",     description: "Stop the current run" },
  { cmd: "/help",     description: "List available commands" },
];

interface ViperSession {
  id: string;
  name: string;
  key: string; // the <session> suffix, e.g. "dashboard" or "dashboard-ab12cd"
}

const CHIPS = ["Who's at risk this week?", "This week's lateness", "Summarize Aiden's month"];

const LS_SESSIONS = "viper-sessions";
const LS_ACTIVE = "viper-active-session";
const lsTranscript = (id: string) => `viper-session-${id}`;

let _sessionCounter = 0;

function genKey(): string {
  _sessionCounter += 1;
  return `dashboard-${Date.now().toString(36)}${_sessionCounter.toString(36)}`;
}

const DEFAULT_SESSION: ViperSession = { id: "default", name: "Main", key: "dashboard" };

function loadSessions(): ViperSession[] {
  try {
    const raw = localStorage.getItem(LS_SESSIONS);
    if (raw) return JSON.parse(raw) as ViperSession[];
  } catch { /* ignore */ }
  return [DEFAULT_SESSION];
}

function saveSessions(sessions: ViperSession[]): void {
  localStorage.setItem(LS_SESSIONS, JSON.stringify(sessions));
}

function loadActiveId(sessions: ViperSession[]): string {
  const stored = localStorage.getItem(LS_ACTIVE);
  if (stored && sessions.some((s) => s.id === stored)) return stored;
  return sessions[0]?.id ?? DEFAULT_SESSION.id;
}

function loadTranscript(id: string): Msg[] {
  try {
    const raw = localStorage.getItem(lsTranscript(id));
    if (raw) return JSON.parse(raw) as Msg[];
  } catch { /* ignore */ }
  return [];
}

function saveTranscript(id: string, messages: Msg[]): void {
  localStorage.setItem(lsTranscript(id), JSON.stringify(messages));
}

export function AssistantDock({ token }: { token: string | null }) {
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [typing, setTyping] = useState(false);
  const [input, setInput] = useState("");

  // Session state — initialised lazily so localStorage is read only once.
  const [sessions, setSessions] = useState<ViperSession[]>(() => loadSessions());
  const [activeId, setActiveId] = useState<string>(() => loadActiveId(loadSessions()));
  const [messages, setMessages] = useState<Msg[]>(() => {
    const sess = loadSessions();
    const id = loadActiveId(sess);
    return loadTranscript(id);
  });

  // Editing the session name inline.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const runIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const reduced = useReducedMotion();

  // Slash-command palette: visible when input starts with "/" and not yet sent.
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Persist transcript whenever messages change.
  useEffect(() => {
    saveTranscript(activeId, messages);
  }, [activeId, messages]);

  // Persist session list whenever it changes.
  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  // Persist active id whenever it changes.
  useEffect(() => {
    localStorage.setItem(LS_ACTIVE, activeId);
  }, [activeId]);

  const activeSession = sessions.find((s) => s.id === activeId) ?? sessions[0] ?? DEFAULT_SESSION;

  function close() {
    if (reduced) {
      setOpen(false);
    } else {
      setClosing(true);
    }
  }

  function switchSession(id: string) {
    if (id === activeId) return;
    // Persist current transcript before switching.
    saveTranscript(activeId, messages);
    setActiveId(id);
    setMessages(loadTranscript(id));
  }

  function newSession() {
    const n = sessions.length + 1;
    const id = `sess-${Date.now().toString(36)}`;
    const newSess: ViperSession = { id, name: `Session ${n}`, key: genKey() };
    const next = [...sessions, newSess];
    setSessions(next);
    saveTranscript(activeId, messages);
    setActiveId(id);
    setMessages([]);
  }

  function startRename(sess: ViperSession) {
    setEditingId(sess.id);
    setEditingName(sess.name);
  }

  function commitRename() {
    if (!editingId) return;
    const trimmed = editingName.trim();
    if (trimmed) {
      setSessions((ss) => ss.map((s) => s.id === editingId ? { ...s, name: trimmed } : s));
    }
    setEditingId(null);
  }

  async function send(text: string) {
    let q = text.trim();
    if (!q || streaming) return;
    // /compress is an alias for /compact (same effect, not a gateway command).
    if (/^\/compress(\s|$)/i.test(q)) {
      q = "/compact" + q.slice("/compress".length);
    }
    setPaletteOpen(false);
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
        activeSession.key,
        (e: AssistantEvent) => {
          if (e.kind === "run") runIdRef.current = e.runId;
          else if (e.kind === "delta") appendToViper(e.text);
          else if (e.kind === "error") appendToViper(`\n[error: ${e.message}]`);
        },
        ctrl.signal,
      );
    } catch {
      appendToViper(`\n[connection error]`);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    if (runIdRef.current) void abortAssistant(token, runIdRef.current, activeSession.key);
    setStreaming(false);
  }

  if (!open) {
    return <ViperOrb state={streaming ? "streaming" : "idle"} onClick={() => { setClosing(false); setOpen(true); }} label="Open Ask Viper" />;
  }

  const dockDataAttrs = {
    "data-streaming": streaming ? "true" : "false",
    "data-reduced": reduced ? "true" : "false",
    "data-closing": closing ? "true" : "false",
  };

  return (
    <section
      className="viper-dock glass"
      aria-label="Ask Viper"
      {...dockDataAttrs}
      onAnimationEnd={(e) => {
        if (e.animationName === "viper-pop-out") {
          setOpen(false);
          setClosing(false);
        }
      }}
    >
      <header className="viper-dock__head">
        <span className="viper-dock__title">Ask Viper</span>

        {/* Session controls */}
        <div className="viper-sessions">
          {editingId === activeId ? (
            <input
              className="viper-sessions__rename"
              value={editingName}
              autoFocus
              onChange={(e) => setEditingName(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitRename();
                else if (e.key === "Escape") setEditingId(null);
              }}
              aria-label="Rename session"
            />
          ) : (
            <select
              className="viper-sessions__select"
              value={activeId}
              onChange={(e) => switchSession(e.target.value)}
              aria-label="Switch session"
              disabled={streaming}
            >
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="viper-sessions__rename-btn"
            onClick={() => startRename(activeSession)}
            aria-label="Rename session"
            title="Rename"
            disabled={streaming}
          >
            ✎
          </button>
          <button
            type="button"
            className="viper-sessions__new"
            onClick={newSession}
            aria-label="New session"
            title="New session"
            disabled={streaming}
          >
            ＋
          </button>
        </div>

        <button type="button" className="viper-dock__close" onClick={close} aria-label="Collapse">
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
        {streaming && (
          <div className="viper-dock__bubbles" aria-hidden="true">
            <span className="viper-bubble" />
            <span className="viper-bubble" />
            <span className="viper-bubble" />
          </div>
        )}
      </div>

      {messages.length === 0 && (
        <div className="viper-dock__chips">
          {CHIPS.map((c) => (
            <button key={c} type="button" className="viper-chip" onClick={() => send(c)} disabled={streaming}>
              {c}
            </button>
          ))}
        </div>
      )}

      {paletteOpen && (() => {
        const query = input.slice(1).toLowerCase();
        const matches = SLASH_COMMANDS.filter(({ cmd }) =>
          cmd.slice(1).startsWith(query)
        );
        if (matches.length === 0) return null;
        return (
          <ul className="viper-cmd-palette" role="listbox" aria-label="Slash commands">
            {matches.map(({ cmd, description }) => (
              <li
                key={cmd}
                className="viper-cmd-palette__item"
                role="option"
                aria-selected={false}
                onMouseDown={(e) => {
                  // mouseDown fires before input blur; prevent blur so we can setInput.
                  e.preventDefault();
                  setInput(cmd);
                  setPaletteOpen(false);
                }}
              >
                <span className="viper-cmd-palette__cmd">{cmd}</span>
                <span className="viper-cmd-palette__desc">{description}</span>
              </li>
            ))}
          </ul>
        );
      })()}

      <form
        className="viper-dock__input"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => {
            const val = e.target.value;
            setInput(val);
            setTyping(val.length > 0);
            setPaletteOpen(val.startsWith("/") && !streaming);
          }}
          onBlur={() => setTyping(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && paletteOpen) {
              e.preventDefault();
              setPaletteOpen(false);
            }
          }}
          placeholder="Ask…"
          aria-label="Message"
          disabled={streaming}
          data-typing={typing && !streaming ? "true" : "false"}
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
