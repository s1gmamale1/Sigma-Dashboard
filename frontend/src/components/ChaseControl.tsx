import type { ChaseState } from "../lib/types";

const options: { id: ChaseState; label: string }[] = [
  { id: "none", label: "None" },
  { id: "needs_chase", label: "Needs chase" },
  { id: "chased", label: "Chased" },
  { id: "resolved", label: "Resolved" }
];

export function ChaseControl({
  value,
  onChange,
  disabled
}: {
  value: ChaseState;
  onChange: (state: ChaseState) => void;
  disabled?: boolean;
}) {
  return (
    <div className="chase" role="group" aria-label="Chase state">
      {options.map((option) => {
        const active = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            aria-pressed={active}
            className={`chase__btn${active ? " is-active" : ""}`}
            onClick={() => onChange(option.id)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
