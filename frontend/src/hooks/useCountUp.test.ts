import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useCountUp } from "./useCountUp";

describe("useCountUp", () => {
  it("returns the target immediately when animation is disabled", () => {
    const { result } = renderHook(() => useCountUp(42, { animate: false }));
    expect(result.current).toBe(42);
  });

  it("ends at the target after animation completes", () => {
    vi.useFakeTimers();
    let raf = 0;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      raf += 16;
      setTimeout(() => cb(raf), 16);
      return raf;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    const { result } = renderHook(() => useCountUp(10, { animate: true, durationMs: 100 }));
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current).toBe(10);
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});
