import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom does not implement matchMedia — provide a sane default (no reduced motion).
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn()
    }) as unknown as MediaQueryList;
}

// jsdom does not implement ResizeObserver — used by SegmentedControl.
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
