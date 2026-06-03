import { useEffect, useRef, useState } from "react";

interface Options {
  animate?: boolean;
  durationMs?: number;
}

export function useCountUp(target: number, { animate = true, durationMs = 600 }: Options = {}): number {
  const [value, setValue] = useState(animate ? 0 : target);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!animate) {
      setValue(target);
      return;
    }
    startRef.current = null;
    let id = 0;
    const tick = (t: number) => {
      if (startRef.current === null) startRef.current = t;
      const p = Math.min(1, (t - startRef.current) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      setValue(Math.round(target * eased));
      if (p < 1) id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [target, animate, durationMs]);

  return value;
}
