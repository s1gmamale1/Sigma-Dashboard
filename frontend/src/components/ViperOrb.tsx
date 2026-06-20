import { useReducedMotion } from "../hooks/useReducedMotion";

export function ViperOrb({
  state,
  onClick,
  label,
}: {
  state: "idle" | "streaming";
  onClick?: () => void;
  label: string;
}) {
  const reduced = useReducedMotion();
  // Identical to the topbar brand orb: the whole iridescent bubble renders from
  // .sigma-orb's own ::before swirl + ::after glass shell, so it needs no children.
  return (
    <button
      type="button"
      className="viper-orb sigma-orb"
      data-state={state}
      data-reduced={reduced ? "true" : "false"}
      onClick={onClick}
      aria-label={label}
    />
  );
}
