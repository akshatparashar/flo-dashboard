import { scaleLinear } from "d3-scale";
import { useMemo, useState } from "react";
import { inr } from "../../lib/format";
import { useWidth } from "./common";

interface Props {
  categories: string[];
  series: { name: string; values: (number | null)[]; best: boolean[] }[];
  colors: string[];
  label: string;
}

/** Price map: one row per fabric, one dot per vendor on a ₹ scale. A soft band spans the cheapest to the dearest
 *  vendor; the best price is ringed, starred and named at the end of its row. Hover a dot, or a vendor in the key,
 *  to follow one vendor down the list. */
export function VendorDots({ categories, series, colors, label }: Props) {
  const [ref, avail] = useWidth<HTMLDivElement>();
  const [focus, setFocus] = useState<string | null>(null);
  const rowH = 46;
  const m = { t: 30, r: 150, b: 8, l: Math.min(190, Math.max(110, avail * 0.2)) };
  const iw = Math.max(260, avail - m.l - m.r);
  const height = m.t + m.b + categories.length * rowH;
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const x = useMemo(() => {
    const pad = Math.max(10, (hi - lo) * 0.08);
    return scaleLinear().domain([Math.max(0, Math.floor((lo - pad) / 10) * 10), Math.ceil((hi + pad) / 10) * 10]).range([0, iw]).nice(5);
  }, [lo, hi, iw]);
  const ticks = x.ticks(6);
  if (!categories.length || !all.length) return <div className="state">No rates for these filters.</div>;
  const color = (k: number) => colors[k % colors.length];
  return (
    <div ref={ref} className="vd">
      <div className="vd-key" role="group" aria-label="Vendors">
        {series.map((s, k) => (
          <button key={s.name} type="button" className={focus && focus !== s.name ? "dim" : undefined} onMouseEnter={() => setFocus(s.name)} onMouseLeave={() => setFocus(null)} onFocus={() => setFocus(s.name)} onBlur={() => setFocus(null)}>
            <i style={{ background: color(k) }} />
            {s.name}
          </button>
        ))}
      </div>
      <div className="chart" role="img" aria-label={label} style={{ height }}>
        {avail > 0 && (
          <svg width={avail} height={height}>
            <g transform={`translate(${m.l},${m.t})`}>
              {ticks.map((t) => (
                <g key={t} transform={`translate(${x(t)},0)`}>
                  <line className="vd-grid" y1={-6} y2={categories.length * rowH} />
                  <text className="vd-tick" y={-12} textAnchor="middle">
                    ₹{t}
                  </text>
                </g>
              ))}
              {categories.map((cat, i) => {
                const cy = i * rowH + rowH / 2;
                const cells = series.map((s, k) => ({ s, k, v: s.values[i], best: s.best[i] })).filter((c) => c.v !== null) as { s: Props["series"][number]; k: number; v: number; best: boolean }[];
                const min = Math.min(...cells.map((c) => c.v));
                const max = Math.max(...cells.map((c) => c.v));
                const winners = cells.filter((c) => c.best).map((c) => c.s.name);
                const same: Record<number, number> = {};
                return (
                  <g key={cat}>
                    {i % 2 === 0 && <rect className="vd-band" x={-m.l} y={i * rowH} width={avail} height={rowH} />}
                    <text className="vd-cat" x={-14} y={cy} dy="0.34em" textAnchor="end">
                      {cat.length > 24 ? `${cat.slice(0, 23)}…` : cat}
                    </text>
                    {cells.length > 1 && <line className="vd-range" x1={x(min)} x2={x(max)} y1={cy} y2={cy} />}
                    {cells.map((c) => {
                      const n = (same[c.v] = (same[c.v] ?? 0) + 1) - 1;
                      const total = cells.filter((o) => o.v === c.v).length;
                      const dy = (n - (total - 1) / 2) * 9;
                      const faded = focus !== null && focus !== c.s.name;
                      return (
                        <g key={c.s.name} opacity={faded ? 0.18 : 1} onMouseEnter={() => setFocus(c.s.name)} onMouseLeave={() => setFocus(null)}>
                          <title>{`${c.s.name} · ${cat}: ${inr(c.v)}${c.best ? " ★ Best Price" : ""}`}</title>
                          {c.best && <circle cx={x(c.v)} cy={cy + dy} r={11} className="vd-ring" />}
                          <circle cx={x(c.v)} cy={cy + dy} r={c.best ? 7 : 6} fill={color(c.k)} className="vd-dot" />
                        </g>
                      );
                    })}
                    {winners.length > 0 && (
                      <text className="vd-best" x={x(max) + 18} y={cy} dy="0.34em">
                        ★ {winners.length > 2 ? `${winners.length} vendors` : winners.join(", ")} {inr(min)}
                      </text>
                    )}
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
