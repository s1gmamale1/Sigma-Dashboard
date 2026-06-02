import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SegmentedControl } from "./SegmentedControl";

const items = [
  { id: "a", label: "A" },
  { id: "b", label: "B" },
  { id: "c", label: "C" }
];

describe("SegmentedControl", () => {
  it("marks the active segment selected", () => {
    render(<SegmentedControl items={items} value="b" onChange={() => {}} ariaLabel="Views" />);
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");
  });

  it("calls onChange when a segment is clicked", async () => {
    const onChange = vi.fn();
    render(<SegmentedControl items={items} value="a" onChange={onChange} ariaLabel="Views" />);
    await userEvent.click(screen.getByRole("tab", { name: "C" }));
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("moves selection with ArrowRight", async () => {
    const onChange = vi.fn();
    render(<SegmentedControl items={items} value="a" onChange={onChange} ariaLabel="Views" />);
    screen.getByRole("tab", { name: "A" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("b");
  });
});
