import { useReducedMotion } from "../hooks/useReducedMotion";

export interface Datum {
  label: string;
  value: number;
  value2?: number;
}

export function BarChart({
  data,
  ariaLabel,
  format = (n: number) => String(n),
  max: maxProp,
  height = 200,
  seriesLabels
}: {
  data: Datum[];
  ariaLabel: string;
  format?: (n: number) => string;
  max?: number;
  height?: number;
  seriesLabels?: [string, string];
}) {
  const reduced = useReducedMotion();
  // Coerce to a finite number so a missing/NaN datum can never produce invalid SVG geometry.
  const num = (n: number | undefined) => (Number.isFinite(n) ? (n as number) : 0);
  const grouped = data.some((d) => d.value2 != null);
  const max = maxProp ?? Math.max(1, ...data.flatMap((d) => [num(d.value), num(d.value2)]));
  const W = 100;
  const H = 100;
  const pad = 4;
  const slot = (W - pad * 2) / Math.max(1, data.length);
  const barW = grouped ? slot * 0.3 : slot * 0.5;

  return (
    <figure className="chart" role="img" aria-label={ariaLabel}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="chart__svg"
        style={{ height: `${height}px` }}
      >
        <line x1="0" y1={H - pad} x2={W} y2={H - pad} className="chart__axis" />
        {data.map((d, i) => {
          const cx = pad + slot * i + slot / 2;
          const v1 = num(d.value);
          const v2 = num(d.value2);
          const h1 = ((H - pad * 2) * v1) / max;
          const bars = [{ v: v1, cls: "bar", x: grouped ? cx - barW - 1 : cx - barW / 2, h: h1 }];
          if (grouped) {
            bars.push({ v: v2, cls: "bar bar--2", x: cx + 1, h: ((H - pad * 2) * v2) / max });
          }
          return bars.map((b, j) => (
            <rect
              key={`${i}-${j}`}
              className={b.cls}
              x={b.x}
              y={H - pad - b.h}
              width={barW}
              height={Math.max(0, b.h)}
              rx="1.5"
              style={{
                transformOrigin: `center ${H - pad}px`,
                animation: reduced ? "none" : `chart-grow var(--dur-smooth) var(--spring-smooth) both`,
                animationDelay: reduced ? undefined : `${i * 30}ms`
              }}
            >
              <title>{`${d.label}: ${format(b.v)}`}</title>
            </rect>
          ));
        })}
      </svg>
      <div className="chart__labels">
        {data.map((d) => (
          <span key={d.label}>{d.label}</span>
        ))}
      </div>
      <figcaption className="sr-only">
        <table>
          {grouped && seriesLabels ? (
            <thead>
              <tr>
                <th />
                <th>{seriesLabels[0]}</th>
                <th>{seriesLabels[1]}</th>
              </tr>
            </thead>
          ) : null}
          <tbody>
            {data.map((d, i) => (
              <tr key={`${d.label}-${i}`}>
                <th>{d.label}</th>
                <td>{format(num(d.value))}</td>
                {d.value2 != null ? <td>{format(num(d.value2))}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
