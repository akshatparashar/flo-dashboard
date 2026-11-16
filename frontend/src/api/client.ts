/* Minimal API client. Same-origin /api in the browser; the mobile app sets its own base URL. */

const TOKEN_KEY = "flo-token";
let base = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export function setApiBase(url: string) {
  base = url.replace(/\/$/, "");
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the session still works until reload */
  }
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
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else q.append(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function api<T>(path: string, params?: Params, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init?.body) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${base}/api${path}${toQuery(params)}`, { ...init, headers: { ...headers, ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection; the dashboard will retry by itself.");
  }
  if (!res.ok) {
    let msg = `The server answered ${res.status}.`;
    try {
      const body = await res.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : msg;
    } catch {
      /* not JSON */
    }
    if (res.status === 401) window.dispatchEvent(new Event("flo:signed-out"));
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}
