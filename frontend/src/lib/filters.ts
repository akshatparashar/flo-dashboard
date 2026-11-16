import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/** Filter state lives in the URL (?month=April-26&month=May-26&vendor=...), so a filtered view can be shared,
 *  bookmarked and survives a reload. Each page names the keys it uses. */
export function useFilters(keys: string[]) {
  const [sp, setSp] = useSearchParams();
  const values = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const k of keys) out[k] = sp.getAll(k).filter(Boolean);
    return out;
  }, [sp, keys]);

  const set = useCallback(
    (key: string, vals: string[]) => {
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete(key);
          vals.forEach((v) => next.append(key, v));
          return next;
        },
        { replace: true },
      );
    },
    [setSp],
  );

  const reset = useCallback(() => {
    setSp(
      (prev) => {
        const next = new URLSearchParams(prev);
        keys.forEach((k) => next.delete(k));
        return next;
      },
      { replace: true },
    );
  }, [setSp, keys]);

  const active = keys.reduce((n, k) => n + (values[k].length ? 1 : 0), 0);
  return { values, set, reset, active };
}

/** Month-range helper: the months between two labels (inclusive), in the given order. */
export function monthRange(all: string[], from: string, to: string): string[] {
  const i = all.indexOf(from);
  const j = all.indexOf(to);
  if (i < 0 || j < 0) return [];
  const [a, b] = i <= j ? [i, j] : [j, i];
  return all.slice(a, b + 1);
}

/** If a selection is one unbroken run of months, describe it as a range. */
export function describeMonths(sel: string[], all: string[], short: (m: string) => string): string {
  if (!sel.length) return "All months";
  const idx = sel.map((m) => all.indexOf(m)).filter((i) => i >= 0).sort((a, b) => a - b);
  const contiguous = idx.length === sel.length && idx.every((v, k) => k === 0 || v === idx[k - 1] + 1);
  if (idx.length === 1) return short(all[idx[0]]);
  if (contiguous) return `${short(all[idx[0]])} – ${short(all[idx[idx.length - 1]])}`;
  if (sel.length <= 2) return sel.map(short).join(", ");
  return `${sel.length} months`;
}
