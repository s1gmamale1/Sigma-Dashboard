import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ChaseControl } from "./ChaseControl";

describe("ChaseControl", () => {
  it("calls onChange with the clicked chase state", async () => {
    const onChange = vi.fn();
    render(<ChaseControl value="none" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /chased/i }));
    expect(onChange).toHaveBeenCalledWith("chased");
  });

  it("marks the active state pressed", () => {
    render(<ChaseControl value="resolved" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /resolved/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("does not fire when disabled", async () => {
    const onChange = vi.fn();
    render(<ChaseControl value="none" onChange={onChange} disabled />);
    await userEvent.click(screen.getByRole("button", { name: /chased/i }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
