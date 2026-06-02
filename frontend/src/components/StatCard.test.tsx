import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatCard } from "./StatCard";

describe("StatCard", () => {
  it("renders label and final value (no animation in tests)", () => {
    render(<StatCard label="Missing reports" value={3} animate={false} />);
    expect(screen.getByText("Missing reports")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
