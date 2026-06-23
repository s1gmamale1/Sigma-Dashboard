import { describe, expect, it } from "vitest";
import { formatStaleness, stalenessLevel } from "./staleness";

describe("stalenessLevel", () => {
  it("returns unknown when no timestamp", () => {
    expect(stalenessLevel(null)).toBe("unknown");
  });
  it("returns live within 120s", () => {
    expect(stalenessLevel(0)).toBe("live");
    expect(stalenessLevel(120)).toBe("live");
  });
  it("returns stale between 120s and 600s", () => {
    expect(stalenessLevel(121)).toBe("stale");
    expect(stalenessLevel(600)).toBe("stale");
  });
  it("returns dead beyond 600s", () => {
    expect(stalenessLevel(601)).toBe("dead");
    expect(stalenessLevel(99999)).toBe("dead");
  });
});

describe("formatStaleness", () => {
  it("formats null as a dash", () => {
    expect(formatStaleness(null)).toBe("—");
  });
  it("formats seconds, minutes, hours, days", () => {
    expect(formatStaleness(5)).toBe("5s ago");
    expect(formatStaleness(90)).toBe("1m ago");
    expect(formatStaleness(3700)).toBe("1h ago");
    expect(formatStaleness(90000)).toBe("1d ago");
  });
});
