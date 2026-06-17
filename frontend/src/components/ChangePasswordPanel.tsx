import { FormEvent, useState } from "react";
import { api } from "../lib/api";

interface ChangePasswordPanelProps {
  token: string;
  displayName: string;
  onChanged: () => void;
  onLogout: () => void;
}

/** Shown after login when the account is on a temporary password — the rest of the
 *  app stays gated (backend returns 403) until a new password is set. */
export function ChangePasswordPanel({ token, displayName, onChanged, onLogout }: ChangePasswordPanelProps) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next.length < 6) {
      setError("New password must be at least 6 characters");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(token, current, next);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-panel card materialize" onSubmit={submit}>
        <div className="login-mark sigma-orb" aria-hidden="true" />
        <h1 className="title">Set a new password</h1>
        <p className="form-hint">
          Welcome, {displayName}. Choose a new password to finish signing in.
        </p>
        <label className="field">
          Current (temporary) password
          <input
            type="password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        <label className="field">
          New password
          <input
            type="password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            autoComplete="new-password"
          />
        </label>
        <label className="field">
          Confirm new password
          <input
            type="password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="primary-button hero" disabled={busy}>
          {busy ? "Saving" : "Save and continue"}
        </button>
        <button type="button" className="ghost-button" onClick={onLogout}>
          Sign out
        </button>
      </form>
    </main>
  );
}
