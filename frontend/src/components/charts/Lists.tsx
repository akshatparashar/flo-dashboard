import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef } from "react";
import type { Slice } from "../../api/types";
import { fmtInt, inr, inrShort, titleCase } from "../../lib/format";
import { colorFor, prefersReducedMotion } from "./common";

function useGrow(dep: unknown, selector: string, axis: "x" | "y" = "x") {
  const ref = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      if (!ref.current || prefersReducedMotion()) return;
      gsap.fromTo(ref.current.querySelectorAll(selector), axis === "x" ? { scaleX: 0 } : { scaleY: 0 }, { scaleX: 1, scaleY: 1, duration: 0.8, ease: "expo.out", stagger: 0.03 });
    },
    { scope: ref, dependencies: [JSON.stringify(dep)], revertOnUpdate: true },
  );
  return ref;
}

/** Ranked list: who ranks. Biggest first, top item in the data hue, the rest in navy; share shown beside the value. */
export function BarList({ items, money = false, unit = "", max = 8, tone = "accent", label, share = true, decimals = 0 }: { items: Slice[]; money?: boolean; unit?: string; max?: number; tone?: "accent" | "neg"; label: string; share?: boolean; decimals?: number }) {
  const sorted = [...items].filter((i) => i.value > 0).sort((a, b) => b.value - a.value);
  const shown = sorted.slice(0, max);
  const total = sorted.reduce((a, b) => a + b.value, 0);
  const top = shown[0]?.value ?? 0;
  const ref = useGrow(items, ".fill");
  if (!shown.length) return <div className="state">Nothing to rank for these filters.</div>;
  return (
    <div className="barlist" ref={ref} role="list" aria-label={label}>
      {shown.map((it, i) => (
        <div className={`barlist-row${i === 0 ? (tone === "neg" ? " neg" : " top") : ""}`} key={it.label} role="listitem">
          <span className="name">{titleCase(it.label)}</span>
          <span className="v num">
            {money ? inrShort(it.value) : `${decimals ? it.value.toFixed(decimals) : fmtInt(it.value)}${unit === "%" ? "%" : unit ? ` ${unit}` : ""}`}
            {share && <small>{total ? `${((it.value / total) * 100).toFixed(1)}%` : ""}</small>}
          </span>
          <span className="track">
            <span className="fill" style={{ width: `${top ? (it.value / top) * 100 : 0}%`, display: "block" }} />
          </span>
        </div>
      ))}
      {sorted.length > shown.length && (
        <div className="stamp">
          +{sorted.length - shown.length} more · {money ? inr(sorted.slice(max).reduce((a, b) => a + b.value, 0)) : fmtInt(sorted.slice(max).reduce((a, b) => a + b.value, 0))}
        </div>
      )}
    </div>
  );
}

/** Parts of a whole as one 100% bar with a legend that carries the numbers. Five parts at most read cleanly. */
export function Split({ items, unit = "", money = false, colors, label }: { items: Slice[]; unit?: string; money?: boolean; colors?: Record<string, string>; label: string }) {
  const parts = items.filter((i) => i.value > 0);
  const total = parts.reduce((a, b) => a + b.value, 0);
  const ref = useGrow(items, ".split span");
  if (!total) return <div className="state">Nothing to split for these filters.</div>;
  const col = (n: string, i: number) => colors?.[n] ?? colorFor(n, i);
  return (
    <div ref={ref} aria-label={label} role="group">
      <div className="split">
        {parts.map((p, i) => (
          <span key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: col(p.label, i), transformOrigin: "left center" }} title={p.label} />
        ))}
      </div>
      <div className="split-legend">
        {parts.map((p, i) => (
          <div key={p.label}>
            <i style={{ background: col(p.label, i) }} />
            <span>{titleCase(p.label)}</span>
            <span className="pc num">{((p.value / total) * 100).toFixed(1)}%</span>
            <b className="num">{money ? inrShort(p.value) : `${fmtInt(p.value)}${unit ? ` ${unit}` : ""}`}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

/** How far to the target: the fill is the true ratio, both ends labelled, a tick at 100%. */
export function Progress({ value, max, leftLabel, rightLabel, marker }: { value: number; max: number; leftLabel: string; rightLabel: string; marker?: number }) {
  const ref = useGrow(value, ".fill");
  const scaleMax = Math.max(max, value, marker ?? 0);
  const pct = scaleMax ? Math.min(100, (value / scaleMax) * 100) : 0;
  return (
    <div className="progress" ref={ref}>
      <div className="track" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
        <div className="fill" style={{ width: `${pct}%` }} />
        {marker !== undefined && scaleMax > 0 && <span className="marker" style={{ left: `${(marker / scaleMax) * 100}%` }} title="Where the schedule says we should be" />}
      </div>
      <div className="ends">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
    </div>
  );
}

/** Rows x months matrix in one hue, darker = more. Used instead of rainbow stacks. */
export function Heatmap({ rows, columns, values, decimals = 0, label, rowLabel = titleCase }: { rows: string[]; columns: string[]; values: number[][]; decimals?: number; label: string; rowLabel?: (s: string) => string }) {
  const max = Math.max(0, ...values.flat());
  const ref = useGrow(values, ".hcell", "y");
  return (
    <div className="heat" ref={ref} role="table" aria-label={label} style={{ ["--n" as string]: columns.length }}>
      <div className="hrow" role="row">
        <span />
        {columns.map((c) => (
          <span className="hhead" key={c} role="columnheader">
            {c}
          </span>
        ))}
      </div>
      {rows.map((r, i) => (
        <div className="hrow" key={r} role="row">
          <span className="hname" role="rowheader" title={r}>
            {rowLabel(r)}
          </span>
          {values[i].map((v, j) => {
            const t = max ? v / max : 0;
            return (
              <span
                key={j}
                className="hcell num"
                role="cell"
                title={`${rowLabel(r)} · ${columns[j]}: ${v.toLocaleString("en-US", { maximumFractionDigits: decimals })}`}
                style={{
                  background: v ? `color-mix(in srgb, var(--accent) ${Math.round(8 + t * 82)}%, var(--sheet))` : "var(--well)",
                  color: t > 0.55 ? "#fff" : v ? "var(--ink)" : "var(--faint)",
                  transformOrigin: "50% 100%",
                }}
              >
                {v ? (v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : v.toFixed(decimals)) : "0"}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}
