import useSWR, { type SWRConfiguration } from "swr";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message);
  }
}

type Options = { method?: string; json?: unknown };

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === "string") return b.detail;
    if (Array.isArray(b.detail) && b.detail.length) {
      const first = b.detail[0] as { loc?: unknown[]; msg?: string };
      const field = first.loc?.slice(1).join(".");
      return field ? `${field}: ${first.msg}` : (first.msg ?? "Invalid input");
    }
    if (typeof b.message === "string") return b.message;
  }
  return status >= 500 ? "Something went wrong. Try again." : `Request failed (${status})`;
}

/** Calls the FastAPI backend through the /api rewrite (see next.config.ts). */
export async function api<T>(path: string, { method, json }: Options = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: method ?? (json === undefined ? "GET" : "POST"),
    headers: json === undefined ? undefined : { "Content-Type": "application/json" },
    body: json === undefined ? undefined : JSON.stringify(json),
    credentials: "same-origin",
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(messageFrom(body, res.status), res.status, body);
  return body as T;
}

/** GET with caching and revalidation; pass null to skip. */
export function useApi<T>(path: string | null, config?: SWRConfiguration<T, ApiError>) {
  return useSWR<T, ApiError>(path, (p: string) => api<T>(p), config);
}
