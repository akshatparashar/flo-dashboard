import { scaleLinear } from "d3-scale";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { axisLabel } from "../../lib/format";

/* Colour by meaning, never by position: the same subject keeps one colour on every chart.
   Blue = the thing that went right / main series, navy = the reference (ordered, target, in production),
   red = what needs attention (pending, remaining, rejected, overdue), pale/grey = the rest. */
const SEMANTIC: [RegExp, string][] = [
  [/^(received|approved|achieved|new|rcvd|cumulative achieved|achieved \(new\)|on time)/i, "var(--accent)"],
  [/^(pending|remaining|rejected|overdue|delayed|overdue \(pending\))/i, "var(--neg)"],
  [/^(in production|under production|ordered|total|target|repeat|monthly target|cumulative target|fabric issue)/i, "var(--series-ref)"],
  [/^(on hold|open|monthly incoming|in process)/i, "var(--series-pale)"],
  [/^(other|no date|cancelled)/i, "var(--series-grey)"],
];
const RAMP = ["var(--accent)", "var(--series-ref)", "var(--series-pale)", "var(--series-grey)"];

export function colorFor(name: string, i = 0): string {
  for (const [re, c] of SEMANTIC) if (re.test(name.trim())) return c;
  return RAMP[i % RAMP.length];
}

export function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export function niceScale(min: number, max: number, range: [number, number], count = 4) {
  const lo = Math.min(0, min);
  const hi = Math.max(max, lo === 0 ? 1 : 0);
  const s = scaleLinear().domain([lo, hi]).nice(count).range(range);
  const ticks = s.ticks(count);
  // keep the top tick above the maximum so marks never touch the plot's edge
  const top = s.domain()[1];
  if (ticks.length && hi >= top * 0.999 && hi > 0) s.domain([lo, top + (ticks[1] - ticks[0])]).nice(count);
  return { s, ticks: s.ticks(count) };
}

export function tickText(v: number, money: boolean, pct = false) {
  if (pct) return `${v}%`;
  return axisLabel(v, money);
}

/** Picks every n-th label so at most `max` labels show and none overlap. */
export function labelStep(count: number, width: number, minGap = 54): number {
  const fit = Math.max(1, Math.floor(width / minGap));
  return Math.max(1, Math.ceil(count / fit));
}

export function Legend({ items }: { items: { name: string; color: string; kind?: "box" | "line" | "dash" }[] }) {
  if (items.length < 2) return null;
  return (
    <div className="legend" aria-hidden="true">
      {items.map((it) => (
        <span key={it.name}>
          <i className={it.kind === "line" ? "line" : it.kind === "dash" ? "dash" : undefined} style={{ background: it.color, borderColor: it.color }} />
          {it.name}
        </span>
      ))}
    </div>
  );
}

export interface TipState {
  x: number;
  y: number;
  title: string;
  rows: { name: string; color: string; value: string }[];
}

export function Tooltip({ tip }: { tip: TipState | null }) {
  if (!tip) return null;
  return (
    <div className="tooltip" style={{ left: tip.x, top: tip.y }} role="status">
      <div className="tt-title">{tip.title}</div>
      {tip.rows.map((r) => (
        <div className="tt-row" key={r.name}>
          <i style={{ background: r.color }} />
          {r.name}
          <b>{r.value}</b>
        </div>
      ))}
    </div>
  );
}

export function ChartFrame({ children, height, label }: { children: ReactNode; height: number; label: string }) {
  return (
    <div className="chart" style={{ height }} role="img" aria-label={label}>
      {children}
    </div>
  );
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Stable key that changes when the drawn data changes, used to replay the grow animation. */
export function useDataKey(data: unknown): string {
  const [key, setKey] = useState("");
  const json = JSON.stringify(data);
  useEffect(() => setKey(json), [json]);
  return key;
}

export const TIMING_COLORS: Record<string, string> = {
  "On Time": "var(--accent)",
  Delayed: "var(--series-ref)",
  "Overdue (Pending)": "var(--neg)",
  "Open (Within Deadline)": "var(--series-pale)",
  "No Date": "var(--series-grey)",
  Cancelled: "var(--series-grey)",
};
