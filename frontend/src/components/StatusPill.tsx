import type { ChaseState, Status } from "../lib/types";

type PillValue = Status | "missing" | ChaseState | "active" | "overdue" | "done" | "paused";

const labels: Record<PillValue, string> = {
  on_time: "On time",
  late: "Late",
  late_15: "15+ Late",
  no_show: "No Show",
  absent: "Absent",
  missing: "Missing",
  none: "None",
  needs_chase: "Needs chase",
  chased: "Chased",
  resolved: "Resolved",
  active: "Active",
  overdue: "Overdue",
  done: "Done",
  paused: "Paused"
};

export function StatusPill({ value }: { value: PillValue }) {
  return (
    <span className={`pill pill-${value}`}>
      <span className="pill__dot" aria-hidden="true" />
      {labels[value]}
    </span>
  );
}
