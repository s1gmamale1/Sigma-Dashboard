import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ActionsPanel } from "./ActionsPanel";
import { hqApi, type HQActionsStatus } from "../../lib/hq";

vi.mock("../../lib/hq", async () => {
  const actual = await vi.importActual<typeof import("../../lib/hq")>("../../lib/hq");
  return { ...actual, hqApi: { ...actual.hqApi, submitAction: vi.fn() } };
});

function makeCaps(overrides: Partial<HQActionsStatus> = {}): HQActionsStatus {
  return {
    enabled: true,
    destructive_enabled: false,
    signoff_required: true,
    signoff_configured: true,
    actions: [
      { name: "list_panes", tool: "list_panes", required: [], destructive: false },
      { name: "stop_pane", tool: "stop_pane", required: ["pane_id"], destructive: true }
    ],
    ...overrides
  };
}

function renderPanel(caps: HQActionsStatus) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ActionsPanel token="t" capabilities={caps} />
    </QueryClientProvider>
  );
}

describe("ActionsPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the capability gate labels", () => {
    renderPanel(makeCaps());
    expect(screen.getByText("enabled")).toBeInTheDocument();
    expect(screen.getByText("destructive")).toBeInTheDocument();
    expect(screen.getByText("signoff")).toBeInTheDocument();
  });

  it("defaults the dry-run toggle to ON", () => {
    renderPanel(makeCaps());
    const dryRun = screen.getByRole("checkbox", { name: /Dry-run/i });
    expect(dryRun).toBeChecked();
  });

  it("shows the destructive warning when a destructive action runs live", () => {
    renderPanel(makeCaps({ destructive_enabled: true }));
    // pick the destructive action and turn dry-run off
    fireEvent.change(screen.getByLabelText("Action"), { target: { value: "stop_pane" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Dry-run/i }));
    expect(screen.getByText(/changes real fleet state/i)).toBeInTheDocument();
  });

  it("disables submit when capabilities.enabled is false", () => {
    renderPanel(makeCaps({ enabled: false }));
    const button = screen.getByRole("button", { name: /Validate \(dry-run\)/i });
    expect(button).toBeDisabled();
    expect(screen.getByText(/Control plane disabled/i)).toBeInTheDocument();
  });

  it("submits a dry-run with the signoff token via hqApi.submitAction", async () => {
    const submit = vi.mocked(hqApi.submitAction);
    submit.mockResolvedValue({
      action: "list_panes",
      dry_run: true,
      destructive: false,
      status: "validated",
      would_invoke: { tool: "list_panes" }
    });
    renderPanel(makeCaps());
    fireEvent.change(screen.getByLabelText(/Signoff token/i), { target: { value: "tok-123" } });
    fireEvent.click(screen.getByRole("button", { name: /Validate \(dry-run\)/i }));
    // The result appears once the mutation resolves; assert call args after.
    expect(await screen.findByText("validated")).toBeInTheDocument();
    expect(submit).toHaveBeenCalledWith("t", "list_panes", {}, true, "tok-123");
  });
});
