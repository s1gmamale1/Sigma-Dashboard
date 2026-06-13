import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ReportsView } from "./ReportsView";
import type { Person, Report } from "../lib/types";

const person: Person = {
  id: 1,
  slug: "ada",
  display_name: "Ada Lovelace",
  active: true,
  sort_order: 0
};

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    id: 1,
    person,
    report_date: "2026-06-12",
    summary: "Shipped the analytics engine.",
    extras: null,
    rating: 82,
    missing: false,
    source_topic: "Analytics",
    assignments: [],
    ...overrides
  };
}

describe("ReportsView", () => {
  it("shows a fallback banner when displaying an earlier date than requested", () => {
    render(
      <ReportsView reports={[makeReport()]} requestedDate="2026-06-13" fallbackDate="2026-06-12" />
    );
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/No reports filed for/i);
    expect(banner).toHaveTextContent(/Jun 13/);
    expect(banner).toHaveTextContent(/Jun 12/);
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("renders no banner when showing the requested date", () => {
    render(
      <ReportsView reports={[makeReport()]} requestedDate="2026-06-13" fallbackDate={null} />
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("keeps the empty state when there are no reports at all", () => {
    render(<ReportsView reports={[]} requestedDate="2026-06-13" fallbackDate={null} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("No reports for this date")).toBeInTheDocument();
  });
});
