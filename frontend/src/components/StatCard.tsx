import type { ReactNode } from "react";
import { useCountUp } from "../hooks/useCountUp";
import { useReducedMotion } from "../hooks/useReducedMotion";

export function StatCard({
  icon,
  label,
  value,
  animate
}: {
  icon?: ReactNode;
  label: string;
  value: number;
  animate?: boolean;
}) {
  const reduced = useReducedMotion();
  const shown = useCountUp(value, { animate: (animate ?? true) && !reduced });
  return (
    <div className="stat tile">
      {icon ? (
        <span className="stat__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <span className="stat__label">{label}</span>
      <strong className="stat__value num">{shown}</strong>
    </div>
  );
}
