import { keepPreviousData, useIsFetching, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { reportError, reportFetching, reportMeta } from "../lib/live";
import { api, type Params } from "./client";
import type { Envelope, Health, StatusData } from "./types";

export const REFRESH_MS = 60_000;

/** One dashboard endpoint. Re-reads every minute (the server re-reads Google at most once a minute), keeps the
 *  previous result on screen while filters change, and reports its sync state to the live store. */
export function useDashboard<T extends Envelope>(path: string, params: Params) {
  const q = useQuery<T, Error>({
    queryKey: [path, params],
    queryFn: () => api<T>(path, params),
    refetchInterval: REFRESH_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
    retry: (count, err) => count < 3 && !("status" in err && (err as { status: number }).status === 401),
  });
  useEffect(() => {
    if (q.data?.meta) reportMeta(q.data.meta);
  }, [q.data]);
  useEffect(() => {
    reportError(q.error ? q.error.message : null);
  }, [q.error]);
  return q;
}

export function useStatus() {
  return useQuery<StatusData, Error>({
    queryKey: ["/status"],
    queryFn: () => api<StatusData>("/status"),
    refetchInterval: REFRESH_MS,
    staleTime: 15_000,
  });
}

export function useHealth() {
  return useQuery<Health, Error>({ queryKey: ["/health"], queryFn: () => api<Health>("/health"), staleTime: 300_000 });
}

/** Mirrors react-query's in-flight count into the live store (drives the top bar's sync indicator). */
export function useFetchingReporter() {
  const n = useIsFetching();
  useEffect(() => reportFetching(n > 0), [n]);
}

export function useRefreshAll() {
  const qc = useQueryClient();
  return async () => {
    try {
      await api("/refresh", undefined, { method: "POST" });
    } catch {
      /* cooldown or offline: the normal refetch still runs */
    }
    await qc.invalidateQueries();
  };
}
