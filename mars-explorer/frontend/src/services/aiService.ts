/**
 * Optional AI assistance (backend /api/v1/ai/). The assistant proposes planning CONSTRAINTS from
 * text and explains computed results; it never computes or edits a route. Without it, every
 * planner feature works unchanged.
 */
import type { RoutePlanResponse } from "../types/api";
import { ApiError, apiRequest } from "./api";

export interface AiStatus {
  assistant: { status: "AVAILABLE" | "UNAVAILABLE" | "DISABLED" | "MISCONFIGURED"; reason?: string | null; provider?: string; model?: string; is_language_model?: boolean };
  perception: { status: string; reason: string; classes: string[] };
  route_engine: string;
  note: string;
}

export interface RouteConstraints {
  max_slope_deg: number;
  allow_unknown_terrain: boolean;
  avoid_known_hazards: boolean;
  prefer_lower_roughness?: boolean;
  require_return_route?: boolean;
  include_alternative?: boolean;
  hazard_buffer_m?: number;
  max_roughness_m?: number;
  max_local_relief_m?: number;
  required_resolution_m?: number;
  connectivity?: 4 | 8;
  profile?: "CONSERVATIVE" | "STANDARD";
  notes?: string;
}

export interface Interpretation {
  accepted: boolean;
  constraints: RouteConstraints | null;
  plan_fields: Record<string, unknown> | null;
  problems: string[];
  code: string | null;
  interaction_id: number;
  provider: { name: string; model: string; model_version: string; is_language_model: boolean };
  note: string;
}

export interface Explanation {
  explanation: { summary: string; cost_factors: string[]; uncertain_data: string[]; alternatives: string[]; limitations: string[] };
  generator: { name: string; model?: string; is_language_model: boolean };
  validation: { accepted: boolean; reason?: string; fallback?: string; checks?: string[] };
  note: string;
}

type Req = typeof apiRequest;

export const aiStatus = (request: Req = apiRequest) => request<AiStatus>("/ai/status/", { timeoutMs: 15_000 });

/** A rejected interpretation comes back as HTTP 422 with the same body; it is returned, not thrown. */
export async function interpretInstruction(instruction: string, request: Req = apiRequest): Promise<Interpretation> {
  try {
    return await request<Interpretation>("/ai/interpret/", { method: "POST", body: { instruction }, timeoutMs: 90_000 });
  } catch (err) {
    const body = err instanceof ApiError ? (err.body as Interpretation | undefined) : undefined;
    if (body && typeof body === "object" && "accepted" in body) return body;
    throw err;
  }
}

export const explainRoute = (routeId: number, request: Req = apiRequest) =>
  request<Explanation>("/ai/explain/", { method: "POST", body: { route_id: routeId }, timeoutMs: 90_000 });

/** Map validated constraints onto the planner form. Unknown terrain is never enabled from here. */
export function constraintsToForm(c: RouteConstraints): {
  profile: "CONSERVATIVE" | "STANDARD";
  maxSlope: number;
  requiredResolution: number | null;
  maxRoughness: number | null;
  hazardBuffer: number | null;
  connectivity: 4 | 8;
  preferSmooth: boolean;
  ret: boolean;
  alt: boolean;
} {
  return {
    profile: c.profile ?? "CONSERVATIVE",
    maxSlope: c.max_slope_deg,
    requiredResolution: c.required_resolution_m ?? null,
    maxRoughness: c.max_roughness_m ?? null,
    hazardBuffer: c.hazard_buffer_m ?? null,
    connectivity: c.connectivity ?? 8,
    preferSmooth: !!c.prefer_lower_roughness,
    ret: !!c.require_return_route,
    alt: c.include_alternative ?? true,
  };
}

export type { RoutePlanResponse };
