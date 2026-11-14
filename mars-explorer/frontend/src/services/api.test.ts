import { describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest, fieldErrors } from "./api";

const json = (status: number, body: unknown) =>
  vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })) as unknown as typeof fetch;

describe("apiRequest", () => {
  it("returns parsed JSON and encodes the query", async () => {
    const f = json(200, { status: "ok" });
    await expect(apiRequest("/health/", { query: { lon: 77.45, lat: 18.44 } }, f)).resolves.toEqual({ status: "ok" });
    const url = (f as unknown as { mock: { calls: [string][] } }).mock.calls[0]![0];
    expect(url).toContain("/health/?lon=77.45&lat=18.44");
  });

  it("maps the backend error envelope to ApiError (missing DEM)", async () => {
    const f = json(404, { error: { code: "DEM_NOT_AVAILABLE", message: "Elevation: DATA NOT AVAILABLE", details: {} } });
    const err = await apiRequest("/terrain/sample/", {}, f).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).code).toBe("DEM_NOT_AVAILABLE");
  });

  it("flags network failures", async () => {
    const f = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const err = (await apiRequest("/health/", {}, f).catch((e: unknown) => e)) as ApiError;
    expect(err.isNetworkError).toBe(true);
    expect(err.code).toBe("NETWORK_ERROR");
  });

  it("extracts DRF field errors", async () => {
    const f = json(400, { error: { code: "VALIDATION_ERROR", message: "Invalid input", details: { lat_deg: ["too big"] } } });
    const err = await apiRequest("/hazards/", { method: "POST", body: {} }, f).catch((e: unknown) => e);
    expect(fieldErrors(err)).toEqual(["lat_deg: too big"]);
  });

  it("handles 204 No Content", async () => {
    const f = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch;
    await expect(apiRequest("/hazards/1/", { method: "DELETE" }, f)).resolves.toBeUndefined();
  });
});
