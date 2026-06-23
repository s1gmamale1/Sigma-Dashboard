import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ShieldAlert, Sliders } from "lucide-react";
import { hqApi, type HQActionResult, type HQActionsStatus, type HQActionSpec } from "../../lib/hq";
import { Card } from "../Card";
import { SectionHeader } from "../SectionHeader";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

// Capability gate chips — mirrors the control pill in HQPage but spelled out.
function GateChip({ label, on }: { label: string; on: boolean }) {
  return (
    <span className={`hq-gate hq-gate--${on ? "on" : "off"}`}>
      <span className="hq-gate__dot" aria-hidden="true" />
      {label}
    </span>
  );
}

export function ActionsPanel({
  token,
  capabilities
}: {
  token: string;
  capabilities: HQActionsStatus;
}) {
  const actions = capabilities.actions;
  const [actionName, setActionName] = useState<string>(actions[0]?.name ?? "");
  const [targetText, setTargetText] = useState<string>("{}");
  const [dryRun, setDryRun] = useState(true);
  // Explicit confirm gate for live execution — re-armed whenever dry-run flips back on.
  const [confirmExecute, setConfirmExecute] = useState(false);
  // Signoff token lives ONLY in component state. Never localStorage, never logged.
  const [signoff, setSignoff] = useState("");
  const [targetError, setTargetError] = useState<string | null>(null);

  const selected: HQActionSpec | undefined = useMemo(
    () => actions.find((a) => a.name === actionName),
    [actions, actionName]
  );
  const isDestructive = !!selected?.destructive;

  const mutation = useMutation<HQActionResult, Error, void>({
    mutationFn: () => {
      const target = JSON.parse(targetText) as Record<string, unknown>;
      return hqApi.submitAction(token, actionName, target, dryRun, signoff);
    }
  });

  const gatesBlocked = !capabilities.enabled || !capabilities.signoff_configured;
  const executeNeedsConfirm = !dryRun && !confirmExecute;
  const destructiveBlocked = isDestructive && !dryRun && !capabilities.destructive_enabled;
  const submitDisabled =
    gatesBlocked ||
    !actionName ||
    !signoff.trim() ||
    executeNeedsConfirm ||
    destructiveBlocked ||
    mutation.isPending;

  function disabledReason(): string | null {
    if (!capabilities.enabled) return "Control plane disabled (backend returns 403).";
    if (!capabilities.signoff_configured) return "No signoff secret configured on the backend.";
    if (!actionName) return "Select an action.";
    if (!signoff.trim()) return "Paste an operator-minted signoff token.";
    if (destructiveBlocked) return "Destructive execution is not enabled on the backend.";
    if (executeNeedsConfirm) return "Tick the confirm box to run a live (non-dry-run) action.";
    return null;
  }

  function onDryRunChange(next: boolean) {
    setDryRun(next);
    if (next) setConfirmExecute(false); // re-arm the confirm gate when returning to dry-run
  }

  function submit() {
    setTargetError(null);
    try {
      JSON.parse(targetText);
    } catch {
      setTargetError("Target must be valid JSON.");
      return;
    }
    mutation.mutate();
  }

  const reason = disabledReason();

  return (
    <section className="view-grid">
      <Card wide className="tile hq-actions">
        <SectionHeader
          title="Control actions"
          eyebrow="Operator-signed · dry-run first"
          actions={
            <div className="hq-gates">
              <GateChip label="enabled" on={capabilities.enabled} />
              <GateChip label="destructive" on={capabilities.destructive_enabled} />
              <GateChip label="signoff" on={capabilities.signoff_configured} />
            </div>
          }
        />

        <div className="field">
          <span className="field__head">
            <label htmlFor="hq-action">Action</label>
          </span>
          <select
            id="hq-action"
            value={actionName}
            onChange={(e) => setActionName(e.target.value)}
            disabled={!actions.length}
          >
            {actions.length === 0 ? (
              <option value="">No actions available</option>
            ) : (
              actions.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                  {a.destructive ? " ⚠ destructive" : ""}
                </option>
              ))
            )}
          </select>
        </div>

        <div className="field">
          <span className="field__head">
            <label htmlFor="hq-target">Target (JSON)</label>
            {selected && selected.required.length > 0 ? (
              <span className="muted hq-actions__hint">
                required: {selected.required.join(", ")}
              </span>
            ) : null}
          </span>
          <textarea
            id="hq-target"
            rows={4}
            spellCheck={false}
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            placeholder='{"pane_id": "..."}'
          />
          {targetError ? <p className="form-error">{targetError}</p> : null}
        </div>

        <label className="hq-actions__toggle">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => onDryRunChange(e.target.checked)}
          />
          <span>
            <strong>Dry-run</strong>
            <span className="muted"> — validate only, no side effects</span>
          </span>
        </label>

        {!dryRun ? (
          <div className={`hq-actions__warn${isDestructive ? " hq-actions__warn--destructive" : ""}`}>
            {isDestructive ? (
              <ShieldAlert size={18} aria-hidden="true" />
            ) : (
              <AlertTriangle size={18} aria-hidden="true" />
            )}
            <div>
              <strong>
                {isDestructive
                  ? "Live destructive action — this changes real fleet state."
                  : "Live action — this will execute against the fleet."}
              </strong>
              <label className="hq-actions__confirm">
                <input
                  type="checkbox"
                  checked={confirmExecute}
                  onChange={(e) => setConfirmExecute(e.target.checked)}
                />
                <span>I understand — run it for real (not a dry-run).</span>
              </label>
            </div>
          </div>
        ) : null}

        <div className="field">
          <span className="field__head">
            <label htmlFor="hq-signoff">Signoff token</label>
          </span>
          <input
            id="hq-signoff"
            type="password"
            autoComplete="off"
            value={signoff}
            onChange={(e) => setSignoff(e.target.value)}
            placeholder="X-Sigma-Signoff — minted out-of-band via scripts/hq_sign_action.py"
          />
        </div>

        <div className="hq-actions__submit">
          <button
            type="button"
            className={!dryRun && isDestructive ? "danger-button" : "primary-button"}
            onClick={submit}
            disabled={submitDisabled}
          >
            <Sliders size={16} aria-hidden="true" />
            {mutation.isPending ? "Submitting" : dryRun ? "Validate (dry-run)" : "Execute"}
          </button>
          {reason ? <span className="muted hq-actions__reason">{reason}</span> : null}
        </div>

        {mutation.error ? (
          <div className="hq-actions__result hq-actions__result--error" role="alert">
            <strong>Error</strong>
            <pre>{errorMessage(mutation.error, "Action failed")}</pre>
          </div>
        ) : null}
        {mutation.data ? (
          <div className="hq-actions__result hq-actions__result--ok" role="status">
            <strong>{mutation.data.status}</strong>
            <pre>{JSON.stringify(mutation.data, null, 2)}</pre>
          </div>
        ) : null}
      </Card>
    </section>
  );
}
