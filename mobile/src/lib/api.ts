/* The FLO API client, same contract as the web app (frontend/src/api/client.ts). The server address comes from
   EXPO_PUBLIC_API_URL at build time, or from the sign-in screen. Every call has a time limit so a dead network
   never leaves a spinner turning forever. */

let base = "";
let token: string | null = null;
const signedOut = new Set<() => void>();

/** "flo.example.com" or "https://flo.example.com/" -> "https://flo.example.com" */
export function normalizeServer(url: string): string {
  let s = url.trim().replace(/\/+$/, "").replace(/\/api$/, "");
  if (s && !/^https?:\/\//i.test(s)) s = `https://${s}`;
  return s;
}

export const DEFAULT_SERVER = normalizeServer(process.env.EXPO_PUBLIC_API_URL ?? "");

export function configureApi(opts: { server?: string; token?: string | null }) {
  if (opts.server !== undefined) base = normalizeServer(opts.server);
  if (opts.token !== undefined) token = opts.token;
}

export function onSignedOut(fn: () => void): () => void {
  signedOut.add(fn);
  return () => signedOut.delete(fn);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type Params = Record<string, string | number | string[] | undefined | null>;

export function toQuery(params: Params = {}): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    const vals = Array.isArray(v) ? v : [String(v)];
    for (const x of vals) parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(x)}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export async function api<T>(
  path: string,
  params?: Params,
  init?: { method?: "GET" | "POST"; body?: unknown; timeoutMs?: number; server?: string },
): Promise<T> {
  const root = init?.server !== undefined ? normalizeServer(init.server) : base;
  if (!root) throw new ApiError(0, "No server address is set.");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init?.body !== undefined) headers["Content-Type"] = "application/json";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), init?.timeoutMs ?? 45_000);
  let res: Response;
  try {
    res = await fetch(`${root}/api${path}${toQuery(params)}`, {
      method: init?.method ?? "GET",
      headers,
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    const aborted = (e as Error)?.name === "AbortError";
    throw new ApiError(
      0,
      aborted
        ? "The server is taking too long to answer. Please try again."
        : "Can't reach the server. Check your internet connection and try again.",
    );
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let msg = `The server answered ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") msg = body.detail;
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && token) signedOut.forEach((fn) => fn());
    throw new ApiError(res.status, msg);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(res.status, "The server sent an answer the app could not read. Check the server address.");
  }
}
