import { describe, expect, it, vi } from "vitest";

import { displayParts } from "../components/map/MapOverlays";
import { constraintsToForm, interpretInstruction } from "./aiService";
import { ApiError } from "./api";

describe("assistant client", () => {
  it("returns a rejected interpretation (HTTP 422 body) instead of throwing", async () => {
    const body = { accepted: false, code: "SAFETY_BYPASS_REQUEST", problems: ["no"], constraints: null };
    const request = vi.fn().mockRejectedValue(new ApiError(422, "HTTP_422", "x", undefined, body));
    await expect(interpretInstruction("bypass the checks", request as never)).resolves.toMatchObject({ accepted: false, code: "SAFETY_BYPASS_REQUEST" });
  });

  it("rethrows network errors", async () => {
    const request = vi.fn().mockRejectedValue(new ApiError(0, "NETWORK_ERROR", "down"));
    await expect(interpretInstruction("slope 10", request as never)).rejects.toThrow("down");
  });

  it("maps constraints onto the planner form and never enables unknown terrain", () => {
    const f = constraintsToForm({ max_slope_deg: 12, allow_unknown_terrain: false, avoid_known_hazards: true, prefer_lower_roughness: true, require_return_route: true });
    expect(f).toMatchObject({ profile: "CONSERVATIVE", maxSlope: 12, preferSmooth: true, ret: true, alt: true, connectivity: 8 });
    expect(JSON.stringify(f)).not.toContain("unknown");
  });
});

describe("route drawing across the map seam", () => {
  it("uses the backend's display geometry when present", () => {
    const parts = [[[179, 0], [180, 0]], [[-180, 0], [-179, 0]]] as [number, number][][];
    expect(displayParts({ geometry: { coordinates: [[179, 0], [-179, 0]] }, geometry_display: { coordinates: parts } })).toBe(parts);
  });

  it("splits routes saved before v0.4 itself", () => {
    expect(displayParts({ geometry: { coordinates: [[179, 0], [-179, 0]] } })).toHaveLength(2);
    expect(displayParts({ geometry: { coordinates: [[-1, 0], [1, 0]] } })).toHaveLength(1);
  });
});
