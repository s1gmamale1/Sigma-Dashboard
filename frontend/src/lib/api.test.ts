import { describe, it, expect, vi, afterEach } from "vitest";
import { apiFetch, apiFetchEnvelope } from "./api";

// Every API call in the app funnels through apiFetchEnvelope; these tests pin its
// three failure branches (non-OK status, 200-with-error envelope, missing message)
// and its header behavior. Raw fetch is only mocked here — component tests mock
// the lib/api module itself instead.
function mockFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body)
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetchEnvelope", () => {
  it("resolves data and meta from a successful envelope", async () => {
    mockFetch(200, { data: { id: 7 }, meta: { latest_report_date: "2026-06-11" }, error: null });
    const { data, meta } = await apiFetchEnvelope<{ id: number }>("/api/v1/x", "tok");
    expect(data).toEqual({ id: 7 });
    expect(meta).toEqual({ latest_report_date: "2026-06-11" });
  });

  it("throws the envelope's error message on a non-OK status", async () => {
    mockFetch(403, {
      data: null,
      meta: {},
      error: { code: "forbidden", message: "This account is read-only" }
    });
    await expect(apiFetch("/api/v1/users", "tok")).rejects.toThrow("This account is read-only");
  });

  it("throws a status fallback when the error body has no message", async () => {
    mockFetch(500, {});
    await expect(apiFetch("/api/v1/x", "tok")).rejects.toThrow("Request failed with 500");
  });

  it("throws even on a 200 when the envelope itself carries an error", async () => {
    mockFetch(200, {
      data: null,
      meta: {},
      error: { code: "business_rule", message: "Business rule violated" }
    });
    await expect(apiFetch("/api/v1/x", "tok")).rejects.toThrow("Business rule violated");
  });

  it("sends the bearer token when present", async () => {
    const fetchMock = mockFetch(200, { data: {}, meta: {}, error: null });
    await apiFetchEnvelope("/api/v1/x", "tok123");
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok123");
  });

  it("omits the Authorization header when the token is null", async () => {
    const fetchMock = mockFetch(200, { data: {}, meta: {}, error: null });
    await apiFetchEnvelope("/api/v1/x", null);
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
  });

  it("sets Content-Type json for requests with a body, without clobbering an explicit one", async () => {
    const fetchMock = mockFetch(200, { data: {}, meta: {}, error: null });
    await apiFetchEnvelope("/api/v1/x", null, { method: "POST", body: JSON.stringify({ a: 1 }) });
    let headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");

    await apiFetchEnvelope("/api/v1/x", null, {
      method: "POST",
      body: "raw",
      headers: { "Content-Type": "text/plain" }
    });
    headers = fetchMock.mock.calls[1][1].headers as Headers;
    expect(headers.get("Content-Type")).toBe("text/plain");
  });
});
