import { arc, pie } from "d3-shape";
import { useState } from "react";
import type { Slice } from "../../api/types";
import { fmtInt, titleCase } from "../../lib/format";

/* Shares of a whole as a donut with a legend that carries the numbers. Slices are told apart by tint (the palette
   has only a few hues), so the legend shows every name, share and value, and hovering a row or a slice lifts it. */
const TINTS = [
  "var(--accent)",
  "var(--series-ref)",
  "color-mix(in srgb, var(--accent) 55%, var(--sheet))",
  "color-mix(in srgb, var(--series-ref) 55%, var(--sheet))",
  "var(--series-pale)",
  "color-mix(in srgb, var(--accent) 35%, var(--series-ref))",
  "var(--series-grey)",
  "color-mix(in srgb, var(--series-ref) 30%, var(--series-grey))",
];

export function Pie({ items, unit = "", label, size = 220 }: { items: Slice[]; unit?: string; label: string; size?: number }) {
  const parts = items.filter((i) => i.value > 0);
  const total = parts.reduce((a, b) => a + b.value, 0);
  const [hot, setHot] = useState<number | null>(null);
  if (!total) return <div className="state">Nothing to show for these filters.</div>;
  const r = size / 2;
  const slices = pie<Slice>().value((d) => d.value).sort(null).padAngle(parts.length > 1 ? 0.012 : 0)(parts);
  const path = arc<(typeof slices)[number]>().innerRadius(r * 0.58).outerRadius(r - 2).cornerRadius(2);
  const lift = arc<(typeof slices)[number]>().innerRadius(r * 0.58).outerRadius(r + 2).cornerRadius(2);
  const col = (i: number) => TINTS[i % TINTS.length];
  const show = hot === null ? null : parts[hot];
  return (
    <div className="pie" role="group" aria-label={label}>
      <svg width={size} height={size} viewBox={`${-r} ${-r} ${size} ${size}`} role="img" aria-label={label}>
        {slices.map((s, i) => (
          <path key={s.data.label} d={(hot === i ? lift : path)(s) ?? ""} fill={col(i)} onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(null)}>
            <title>{`${titleCase(s.data.label)}: ${fmtInt(s.data.value)}${unit ? ` ${unit}` : ""} (${((s.data.value / total) * 100).toFixed(1)}%)`}</title>
          </path>
        ))}
        <text className="pie-total" textAnchor="middle" y={show ? -4 : 2}>
          {fmtInt(show ? show.value : total)}
        </text>
        <text className="pie-sub" textAnchor="middle" y={show ? 14 : 20}>
          {show ? `${((show.value / total) * 100).toFixed(1)}% · ${titleCase(show.label).slice(0, 16)}` : unit || "total"}
        </text>
      </svg>
      <div className="split-legend pie-legend">
        {parts.map((p, i) => (
          <div key={p.label} className={hot === i ? "hot" : undefined} onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(null)}>
            <i style={{ background: col(i) }} />
            <span>{titleCase(p.label)}</span>
            <span className="pc num">{((p.value / total) * 100).toFixed(1)}%</span>
            <b className="num">{`${fmtInt(p.value)}${unit ? ` ${unit}` : ""}`}</b>
          </div>
        ))}
      </div>
    </div>
  );
}
