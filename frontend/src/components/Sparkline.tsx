import { useId } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";
import type { RatingPoint } from "../lib/types";

const RATING_MIN = 0;
const RATING_MAX = 100;

/**
 * Tiny inline SVG line/area chart of a rating trend (x = index, y = score 0..100).
 * Values are finite-coerced and clamped so a missing/NaN datum can never produce
 * invalid SVG geometry (NaN path coords). Reduced-motion friendly.
 */
export function Sparkline({
  data,
  width = 88,
  height = 28,
  ariaLabel
}: {
  data: RatingPoint[];
  width?: number;
  height?: number;
  ariaLabel?: string;
}) {
  const reduced = useReducedMotion();
  const gradientId = useId();
  const pad = 2;

  // Coerce to a finite, clamped rating so a missing datum never yields NaN SVG.
  const ratings = data.map((d) =>
    Math.max(RATING_MIN, Math.min(RATING_MAX, Number.isFinite(d.rating) ? d.rating : RATING_MIN))
  );

  const label =
    ariaLabel ??
    (ratings.length
      ? `Rating trend, ${ratings.length} points, latest ${ratings[ratings.length - 1]}%`
      : "No rating trend");

  if (ratings.length === 0) {
    return (
      <span className="sparkline sparkline--empty num" role="img" aria-label="No rating trend">
        —
      </span>
    );
  }

  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const span = RATING_MAX - RATING_MIN;
  const stepX = ratings.length > 1 ? innerW / (ratings.length - 1) : 0;

  const x = (i: number) => pad + (ratings.length > 1 ? stepX * i : innerW / 2);
  const y = (r: number) => pad + innerH - ((r - RATING_MIN) / span) * innerH;

  const points = ratings.map((r, i) => ({ x: x(i), y: y(r) }));
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(2)} ${(height - pad).toFixed(
    2
  )} L${points[0].x.toFixed(2)} ${(height - pad).toFixed(2)} Z`;
  const last = points[points.length - 1];

  return (
    <svg
      className="sparkline"
      role="img"
      aria-label={label}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" className="sparkline__stop-top" />
          <stop offset="100%" className="sparkline__stop-bottom" />
        </linearGradient>
      </defs>
      <path className="sparkline__area" d={areaPath} fill={`url(#${gradientId})`} />
      <path
        className="sparkline__line"
        d={linePath}
        style={{
          animation: reduced ? "none" : `sparkline-draw var(--dur-smooth) var(--ease-out) both`
        }}
      />
      <circle className="sparkline__dot" cx={last.x} cy={last.y} r="2" />
    </svg>
  );
}
