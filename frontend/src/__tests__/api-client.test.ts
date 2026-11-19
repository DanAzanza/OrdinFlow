import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiRequest,
  casesApi,
  encodePathSegments,
  getSessionToken,
  inboxApi,
} from "@/lib/api-client";

describe("api-client", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    document.head.innerHTML = "";
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("reads session token from meta[name='ordinflow-token']", () => {
    expect(getSessionToken()).toBe("");
    const meta = document.createElement("meta");
    meta.name = "ordinflow-token";
    meta.content = "  sec-tok-123  ";
    document.head.appendChild(meta);
    expect(getSessionToken()).toBe("sec-tok-123");
  });

  it("encodes path segments individually while preserving slash separators", () => {
    expect(encodePathSegments("Case 2025/Max Müller/sub folder")).toBe(
      "Case%202025/Max%20M%C3%BCller/sub%20folder",
    );
    expect(encodePathSegments("")).toBe("");
    expect(encodePathSegments("file#1.pdf")).toBe("file%231.pdf");
  });

  it("injects X-OrdinFlow-Token header, uses same-origin credentials, and never leaks token in URL", async () => {
    const meta = document.createElement("meta");
    meta.name = "ordinflow-token";
    meta.content = "tok-xyz";
    document.head.appendChild(meta);

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ name: "a.pdf" }],
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const result = await inboxApi.list();
    expect(result).toEqual([{ name: "a.pdf" }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [calledUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe("/api/inbox");
    expect(calledUrl).not.toContain("token=");
    expect(init.credentials).toBe("same-origin");
    const headers = new Headers(init.headers);
    expect(headers.get("X-OrdinFlow-Token")).toBe("tok-xyz");
  });

  it("builds segment-encoded URLs for nested case folders", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ folder: "Doe/1990", files: [] }),
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await casesApi.getDetail("Doe Max/1990-01-02");
    const [calledUrl] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toBe("/api/cases/Doe%20Max/1990-01-02");
  });

  it("throws typed ApiError with JSON error or text fallback on 403/500 responses", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ error: "Invalid session token" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error("not json");
        },
        text: async () => "Internal crash detail",
      }) as unknown as typeof fetch;

    await expect(apiRequest("/api/inbox")).rejects.toEqual(
      expect.objectContaining({
        name: "ApiError",
        status: 403,
        message: "Invalid session token",
      }),
    );

    try {
      await apiRequest("/api/inbox");
      expect.unreachable("Should throw ApiError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
      expect((err as ApiError).message).toBe("Internal crash detail");
    }
  });
});
