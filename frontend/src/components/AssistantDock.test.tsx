import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AssistantDock } from "./AssistantDock";

// The dock only displays a stored transcript here; the streaming API is never
// called, so a light module mock keeps the import graph happy without network.
vi.mock("../lib/api", () => ({
  streamAssistant: vi.fn(),
  abortAssistant: vi.fn(),
}));

function seedTranscript(text: string) {
  localStorage.setItem("viper-active-session", "default");
  localStorage.setItem(
    "viper-session-default",
    JSON.stringify([{ role: "viper", text }]),
  );
}

function openDock() {
  fireEvent.click(screen.getByLabelText("Open Ask Viper"));
}

describe("AssistantDock — Viper markdown", () => {
  beforeEach(() => localStorage.clear());

  it("renders **bold** as a <strong>, not literal asterisks", () => {
    seedTranscript("This is **important** news");
    render(<AssistantDock token="t" />);
    openDock();
    const strong = screen.getByText("important");
    expect(strong.tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*important\*\*/)).toBeNull();
  });

  it("renders a GFM pipe-table as a real <table>", () => {
    seedTranscript("| Person | Mon |\n|---|---|\n| Oliver | Late |");
    render(<AssistantDock token="t" />);
    openDock();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Person" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Oliver" })).toBeInTheDocument();
  });

  it("keeps the user's own message literal (no markdown parsing)", () => {
    localStorage.setItem("viper-active-session", "default");
    localStorage.setItem(
      "viper-session-default",
      JSON.stringify([{ role: "you", text: "show **raw** stars" }]),
    );
    render(<AssistantDock token="t" />);
    openDock();
    expect(screen.getByText("show **raw** stars")).toBeInTheDocument();
  });
});
