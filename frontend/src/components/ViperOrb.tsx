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
  return (
    <button
      type="button"
      className="viper-orb"
      data-state={state}
      data-reduced={reduced ? "true" : "false"}
      onClick={onClick}
      aria-label={label}
    >
      <span className="viper-orb__core" aria-hidden="true" />
      <span className="viper-orb__rim" aria-hidden="true" />
    </button>
  );
}
