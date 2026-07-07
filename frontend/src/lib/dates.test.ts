import { describe, it, expect } from "vitest";
import { parseServerDate } from "./dates";

// Regression guard for the naive-UTC bug: the backend serializes some timestamps
// via utc_now() with no Z/offset designator. parseServerDate must treat those as
// UTC — "simplifying" it back to `new Date(iso)` would shift every display by the
// local UTC offset (+5h in Tashkent). Assertions compare against UTC epoch values
// so they hold in any test-runner timezone.
describe("parseServerDate", () => {
  it("treats a designator-less ISO string as UTC, not local time", () => {
    const d = parseServerDate("2026-06-12T10:00:00");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 10, 0, 0));
  });

  it("treats a designator-less string with milliseconds as UTC", () => {
    const d = parseServerDate("2026-06-12T10:00:00.500");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 10, 0, 0, 500));
  });

  it("respects an explicit Z suffix without double-converting", () => {
    const d = parseServerDate("2026-06-12T10:00:00Z");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 10, 0, 0));
  });

  it("respects a lowercase z suffix", () => {
    const d = parseServerDate("2026-06-12T10:00:00z");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 10, 0, 0));
  });

  it("respects an explicit +HH:MM offset", () => {
    const d = parseServerDate("2026-06-12T10:00:00+05:00");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 5, 0, 0));
  });

  it("respects an explicit -HH:MM offset", () => {
    const d = parseServerDate("2026-06-12T10:00:00-03:00");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 13, 0, 0));
  });

  it("respects a colon-less +HHMM offset", () => {
    const d = parseServerDate("2026-06-12T10:00:00+0500");
    expect(d.getTime()).toBe(Date.UTC(2026, 5, 12, 5, 0, 0));
  });
});
