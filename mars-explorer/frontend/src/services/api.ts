/**
 * Centralised HTTP client for the Django API. All errors are normalised to ApiError.
 */
import type { ApiErrorBody } from "../types/api";

/**
 * Backend base URL. VITE_API_BASE_URL wins (e.g. https://api.example.org/api/v1). Without it a
 * production build calls its own origin ("/api/v1", for a host that proxies /api to the backend)
 * and development calls the local Django server.
 */
export function resolveApiBase(configured: string | undefined, isProd: boolean): string {
  const v = (configured ?? "").trim().replace(/\/+$/, "");
  if (v) return v;
  return isProd ? "/api/v1" : "http://127.0.0.1:8000/api/v1";
}

export const API_BASE_URL: string = resolveApiBase(import.meta.env.VITE_API_BASE_URL, import.meta.env.PROD);

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
    /** Parsed JSON body of a non-2xx response (v0.4: e.g. a rejected interpretation, calculation_status). */
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Network failure, timeout or CORS problem: the backend could not be reached. */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

function isApiErrorBody(v: unknown): v is ApiErrorBody {
  return (
    typeof v === "object" &&
    v !== null &&
    "error" in v &&
    typeof (v as ApiErrorBody).error === "object" &&
    typeof (v as ApiErrorBody).error?.code === "string"
  );
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}, fetchImpl: typeof fetch = fetch): Promise<T> {
  const url = new URL(API_BASE_URL + path, typeof window !== "undefined" ? window.location.origin : "http://localhost");
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined) url.searchParams.set(k, String(v));
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 20_000);
  opts.signal?.addEventListener("abort", () => controller.abort());
  let res: Response;
  try {
    res = await fetchImpl(url.toString(), {
      method: opts.method ?? "GET",
      headers: { Accept: "application/json", ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === "AbortError";
    throw new ApiError(0, aborted ? "TIMEOUT" : "NETWORK_ERROR", aborted ? "Backend request timed out" : `Backend unreachable at ${API_BASE_URL}`);
  } finally {
    clearTimeout(timeout);
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(res.status, "INVALID_RESPONSE", `Backend returned non-JSON response (HTTP ${res.status})`);
    }
  }
  if (!res.ok) {
    if (isApiErrorBody(data)) throw new ApiError(res.status, data.error.code, data.error.message, data.error.details, data);
    throw new ApiError(res.status, `HTTP_${res.status}`, `Request failed with HTTP ${res.status}`, undefined, data);
  }
  return data as T;
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.code}: ${err.message}`;
  if (err instanceof Error) return err.message;
  return String(err);
}

/** Flatten DRF field errors ({"field": ["msg"]}) into readable lines. */
export function fieldErrors(err: unknown): string[] {
  if (!(err instanceof ApiError) || typeof err.details !== "object" || err.details === null) return [];
  return Object.entries(err.details as Record<string, unknown>).map(
    ([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : JSON.stringify(v)}`,
  );
}
