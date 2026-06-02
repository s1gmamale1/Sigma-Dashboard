import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";

export interface Segment {
  id: string;
  label: string;
  icon?: ReactNode;
}

export function SegmentedControl({
  items,
  value,
  onChange,
  ariaLabel
}: {
  items: Segment[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel: string;
}) {
  const reduced = useReducedMotion();
  const listRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ x: number; w: number } | null>(null);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const measure = () => {
      const active = list.querySelector<HTMLElement>(`[data-id="${value}"]`);
      if (active) setIndicator({ x: active.offsetLeft, w: active.offsetWidth });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(list);
    return () => ro.disconnect();
  }, [value, items]);

  const onKey = (e: KeyboardEvent) => {
    const i = items.findIndex((s) => s.id === value);
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      onChange(items[(i + 1) % items.length].id);
    }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      onChange(items[(i - 1 + items.length) % items.length].id);
    }
  };

  return (
    <div className="segmented" role="tablist" aria-label={ariaLabel} ref={listRef} onKeyDown={onKey}>
      {indicator ? (
        <span
          className="segmented__indicator"
          aria-hidden="true"
          style={{
            transform: `translateX(${indicator.x}px)`,
            width: indicator.w,
            transition: reduced
              ? "none"
              : `transform var(--dur-snappy) var(--spring-snappy), width var(--dur-snappy) var(--spring-snappy)`
          }}
        />
      ) : null}
      {items.map((s) => (
        <button
          key={s.id}
          data-id={s.id}
          role="tab"
          type="button"
          aria-selected={s.id === value}
          tabIndex={s.id === value ? 0 : -1}
          className={`segmented__item${s.id === value ? " is-active" : ""}`}
          title={s.label}
          onClick={() => onChange(s.id)}
        >
          {s.icon}
          <span className="segmented__label">{s.label}</span>
        </button>
      ))}
    </div>
  );
}
