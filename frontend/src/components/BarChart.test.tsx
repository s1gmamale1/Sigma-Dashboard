import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { BarChart } from "./BarChart";

const data = [
  { label: "Oliver", value: 3 },
  { label: "Sam", value: 5 }
];

describe("BarChart", () => {
  it("renders an accessible figure with one rect per datum", () => {
    const { container } = render(<BarChart data={data} ariaLabel="Lates per person" />);
    expect(screen.getByRole("img", { name: /lates per person/i })).toBeInTheDocument();
    expect(container.querySelectorAll("rect.bar").length).toBe(2);
  });

  it("exposes the data in a visually-hidden table", () => {
    const { container } = render(<BarChart data={data} ariaLabel="Lates" />);
    const caption = container.querySelector("figcaption");
    expect(caption?.textContent).toContain("Oliver");
    expect(caption?.textContent).toContain("5");
  });
});
