/**
 * API client skeleton.
 *
 * The backend's shared error envelope is:
 *   { "error": { "code": number, "message": string, "detail"?: unknown } }
 *
 * `apiFetch` surfaces non-2xx responses as `ApiError` with that envelope, so
 * page code can branch on `err.code` / `err.message` without re-parsing.
 *
 * Route-specific calls (health, products, pairs) are thin wrappers. Response
 * shapes mirror the Wave 1 stubs; they will be tightened in Wave 2 / Wave 3.
 */

// Default to a relative URL so the API resolves against the document base URL
// — works when the SPA is mounted under any path prefix (e.g. /pulse-check).
// Local dev overrides via VITE_API_URL in .env.development to hit the
// separately-running uvicorn on its own port.
const BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "./api";

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

/* ---------- typed route helpers (Wave 1 shapes) ---------- */

export interface HealthResponse {
  status: "ok";
  version: string;
  timestamp: string;
}

export interface ProductsResponse {
  products: unknown[];
  note?: string;
}

export interface PairsResponse {
  pairs: unknown[];
  note?: string;
}

export const api = {
  health: (): Promise<HealthResponse> => apiFetch<HealthResponse>("/health"),
  products: (): Promise<ProductsResponse> => apiFetch<ProductsResponse>("/products"),
  pairs: (): Promise<PairsResponse> => apiFetch<PairsResponse>("/pairs"),
} as const;

export { BASE_URL };
