/* Data layer: one query per dashboard endpoint and filter set. Like the web app it re-reads every minute (the server
   reads Google at most once a minute), keeps the previous numbers on screen while filters change, and also
   re-reads whenever the app comes back to the foreground. */
import { focusManager, keepPreviousData, QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { AppState, Platform } from "react-native";
import { api, ApiError, type Params } from "./api";
import type { Envelope, StatusData } from "./types";

export const REFRESH_MS = 60_000;

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, err) => count < 2 && !(err instanceof ApiError && (err.status === 401 || err.status === 422)),
      retryDelay: (n) => Math.min(1500 * 2 ** n, 8000),
    },
  },
});

/** Tells react-query when the app is in front, so it refreshes on return and pauses polling in the background. */
export function useAppFocus() {
  useEffect(() => {
    if (Platform.OS === "web") return;
    const sub = AppState.addEventListener("change", (s) => focusManager.setFocused(s === "active"));
    return () => sub.remove();
  }, []);
}

export function useDashboard<T extends Envelope>(path: string, params: Params = {}) {
  return useQuery<T, Error>({
    queryKey: [path, params],
    queryFn: () => api<T>(path, params),
    refetchInterval: REFRESH_MS,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  });
}

export function useStatus() {
  return useQuery<StatusData, Error>({ queryKey: ["/status"], queryFn: () => api<StatusData>("/status"), refetchInterval: REFRESH_MS });
}

/** Pull-to-refresh: asks the server to read the sheets now (rate-limited there), then reloads every screen. */
export function useRefreshAll() {
  const qc = useQueryClient();
  return async () => {
    try {
      await api("/refresh", undefined, { method: "POST", timeoutMs: 30_000 });
    } catch {
      /* cooldown or offline: the normal reload still runs */
    }
    await qc.invalidateQueries();
  };
}
