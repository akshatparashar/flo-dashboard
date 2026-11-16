/* Live sync state shared by the top bar, the data-flow view and every page.
   A "pulse" fires only when the data version from the server really changes, so the motion on screen is the
   evidence of a real sync, never decoration. */
import { useSyncExternalStore } from "react";
import type { Meta } from "../api/types";

export interface LiveState {
  meta: Meta | null;
  lastFetchAt: number;      // when the browser last received any response
  lastChangeAt: number;     // when a data version last changed
  pulses: number;           // increments on every real change
  changedSources: string[]; // sources whose version changed in the last pulse
  fetching: boolean;
  error: string | null;
}

let state: LiveState = {
  meta: null,
  lastFetchAt: 0,
  lastChangeAt: 0,
  pulses: 0,
  changedSources: [],
  fetching: false,
  error: null,
};
const versions = new Map<string, string>();
const listeners = new Set<() => void>();

function emit(next: Partial<LiveState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

export function reportMeta(meta: Meta) {
  const changed: string[] = [];
  let first = true;
  for (const s of meta.sources) {
    const prev = versions.get(s.source);
    if (prev !== undefined) first = false;
    if (prev !== undefined && prev !== s.version) changed.push(s.source);
    versions.set(s.source, s.version);
  }
  const now = Date.now();
  if (changed.length) {
    emit({ meta, lastFetchAt: now, lastChangeAt: now, pulses: state.pulses + 1, changedSources: changed, error: null });
  } else {
    emit({ meta, lastFetchAt: now, lastChangeAt: first ? now : state.lastChangeAt, error: null });
  }
}

export function reportFetching(fetching: boolean) {
  if (fetching !== state.fetching) emit({ fetching });
}

export function reportError(error: string | null) {
  if (error !== state.error) emit({ error });
}

export function useLive(): LiveState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
    () => state,
  );
}

export function getLive(): LiveState {
  return state;
}

/** Test helper */
export function _resetLive() {
  versions.clear();
  state = { meta: null, lastFetchAt: 0, lastChangeAt: 0, pulses: 0, changedSources: [], fetching: false, error: null };
}
