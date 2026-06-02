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
  height = 200
}: {
  data: Datum[];
  ariaLabel: string;
  format?: (n: number) => string;
  max?: number;
  height?: number;
}) {
  const reduced = useReducedMotion();
  const grouped = data.some((d) => d.value2 != null);
  const max = maxProp ?? Math.max(1, ...data.flatMap((d) => [d.value, d.value2 ?? 0]));
  const W = 100;
  const H = 100;
  const pad = 4;
  const slot = (W - pad * 2) / Math.max(1, data.length);
  const barW = grouped ? slot * 0.3 : slot * 0.5;

  return (
    <figure className="chart" role="img" aria-label={ariaLabel} style={{ height }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="chart__svg">
        <line x1="0" y1={H - pad} x2={W} y2={H - pad} className="chart__axis" />
        {data.map((d, i) => {
          const cx = pad + slot * i + slot / 2;
          const h1 = ((H - pad * 2) * d.value) / max;
          const bars = [{ v: d.value, cls: "bar", x: grouped ? cx - barW - 1 : cx - barW / 2, h: h1 }];
          if (grouped) {
            bars.push({ v: d.value2 ?? 0, cls: "bar bar--2", x: cx + 1, h: ((H - pad * 2) * (d.value2 ?? 0)) / max });
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
          <tbody>
            {data.map((d) => (
              <tr key={d.label}>
                <th>{d.label}</th>
                <td>{format(d.value)}</td>
                {d.value2 != null ? <td>{format(d.value2)}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
