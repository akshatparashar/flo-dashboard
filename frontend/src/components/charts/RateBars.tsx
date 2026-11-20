import { useMemo } from "react";
import { inr, inrShort } from "../../lib/format";
import { niceScale, tickText, useWidth } from "./common";

interface Props {
  vendors: string[];
  series: { name: string; values: (number | null)[]; best: boolean[] }[];
  colors: string[];
  label: string;
  height?: number;
  bar?: number;          // bar width; thin bars drop the value labels (hover shows them) and keep the ★
}

/** Grouped columns, one group per vendor and one bar per width. Each bar carries its rate; the cheapest rate of a
 *  width is marked ★ (Best Price). Groups never get narrower than they can be read: a long list scrolls sideways. */
export function RateBars({ vendors, series, colors, label, height = 340, bar = 30 }: Props) {
  const [ref, avail] = useWidth<HTMLDivElement>();
  const m = { t: 28, r: 8, b: 44, l: 52 };
  const values = bar >= 26;
  const group = series.length * bar + 28;
  const width = Math.max(avail, m.l + m.r + vendors.length * group);
  const iw = width - m.l - m.r;
  const ih = height - m.t - m.b;
  const band = vendors.length ? iw / vendors.length : iw;
  const max = Math.max(0, ...series.flatMap((s) => s.values.map((v) => v ?? 0)));
  const { s: y, ticks } = useMemo(() => niceScale(0, max, [ih, 0], 4), [max, ih]);
  if (!vendors.length) return <div className="state">No per-metre rates in this category.</div>;
  return (
    <div ref={ref} className="rate-bars">
      <div className="chart" role="img" aria-label={label} style={{ height, width }}>
        {avail > 0 && (
          <svg width={width} height={height}>
            <g transform={`translate(${m.l},${m.t})`}>
              <g className="grid">
                {ticks.map((t) => (
                  <g key={t} transform={`translate(0,${y(t)})`}>
                    <line x1={0} x2={iw} />
                    <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                      {tickText(t, true)}
                    </text>
                  </g>
                ))}
              </g>
              {vendors.map((v, i) => {
                const gx = i * band + (band - series.length * bar) / 2;
                return (
                  <g key={v}>
                    {series.map((s, k) => {
                      const val = s.values[i];
                      if (val === null || val === undefined) return null;
                      const x = gx + k * bar;
                      const top = y(val);
                      return (
                        <g key={s.name}>
                          <title>{`${v} · ${s.name}: ${inr(val)}${s.best[i] ? " ★ Best Price" : ""}`}</title>
                          <rect x={x + 2} y={top} width={bar - 4} height={Math.max(0, ih - top)} rx={2} fill={colors[k % colors.length]} />
                          {(values || s.best[i]) && (
                            <text x={x + bar / 2} y={top - 6} textAnchor="middle" className="rate-val">
                              {values ? inrShort(val) : ""}
                              {s.best[i] && <tspan className="rate-star">{values ? " ★" : "★"}</tspan>}
                            </text>
                          )}
                        </g>
                      );
                    })}
                    <text className="xtick" x={i * band + band / 2} y={ih + 18} textAnchor="middle">
                      {v.length > 18 ? `${v.slice(0, 17)}…` : v}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>
    </div>
  );
}
