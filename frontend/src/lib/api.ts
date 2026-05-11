/**
 * API client.
 *
 * The backend's shared error envelope is:
 *   { "error": { "code": number, "message": string, "detail"?: unknown } }
 *
 * `apiFetch` surfaces non-2xx responses as `ApiError` with that envelope, so
 * page code can branch on `err.code` / `err.message` without re-parsing.
 *
 * Response types come from `lib/types.ts`, which mirrors `pulse_check/api/schemas.py`.
 */

import type {
  BriefView,
  MentionView,
  ProductDetail,
  ProductSummary,
} from "@/lib/types";

// Default to a relative URL so the API resolves against the document base URL
// — works when the SPA is mounted under any path prefix (e.g. /pulse-check).
// Local dev overrides via VITE_API_URL in .env.development to hit the
// separately-running uvicorn on its own port. `||` (not `??`) is intentional:
// `.env.production` sets `VITE_API_URL=` (empty string), which `??` would
// pass through unchanged — leaving BASE_URL as "" and routing every fetch
// to the SPA fallback. `||` falls back on empty string as well as
// null/undefined, matching the .env.production comment's intent.
const _envApiUrl = import.meta.env.VITE_API_URL as string | undefined;
const BASE_URL: string = _envApiUrl || "./api";

export interface ApiErrorEnvelope {
  error: {
    code: number;
    message: string;
    detail?: unknown;
  };
}

export class ApiError extends Error {
  readonly code: number;
  readonly detail: unknown;
  constructor(code: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.detail = detail;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const bodyText = await response.text();
  const parsed: unknown = bodyText ? JSON.parse(bodyText) : null;
  if (!response.ok) {
    const env = parsed as Partial<ApiErrorEnvelope> | null;
    const err = env?.error;
    throw new ApiError(
      err?.code ?? response.status,
      err?.message ?? response.statusText,
      err?.detail,
    );
  }
  return parsed as T;
}

/* ---------- typed route helpers (Wave 2 shapes) ---------- */

export interface HealthResponse {
  status: "ok";
  version: string;
  timestamp: string;
}

export interface ProductsResponse {
  products: ProductSummary[];
}

export interface MentionsResponse {
  mentions: MentionView[];
}

export const api = {
  health: (): Promise<HealthResponse> => apiFetch<HealthResponse>("/health"),
  products: (): Promise<ProductsResponse> =>
    apiFetch<ProductsResponse>("/products"),
  productById: (productId: string): Promise<ProductDetail> =>
    apiFetch<ProductDetail>(`/product/${encodeURIComponent(productId)}`),
  brief: (briefId: number): Promise<BriefView> =>
    apiFetch<BriefView>(`/brief/${briefId}`),
  // Empty `ids` would 400 server-side; callers short-circuit instead of
  // round-tripping a request guaranteed to fail.
  mentions: (ids: string[]): Promise<MentionsResponse> => {
    if (ids.length === 0) return Promise.resolve({ mentions: [] });
    const csv = ids.map(encodeURIComponent).join(",");
    return apiFetch<MentionsResponse>(`/mentions?ids=${csv}`);
  },
} as const;

export { BASE_URL };
