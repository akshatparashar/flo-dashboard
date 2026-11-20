import { useMemo } from "react";
import { inr } from "../../lib/format";
import { niceScale, tickText, useWidth } from "./common";

interface Props {
  categories: string[];
  series: { name: string; values: (number | null)[]; best: boolean[] }[];
  colors: string[];
  label: string;
}

/** Cheapest rate per fabric: one horizontal bar per fabric, coloured by the vendor that wins it and named at the bar's
 *  end. A thin tick marks the dearest vendor's rate, so the gap you could lose by picking wrongly is visible. */
export function BestPriceBars({ categories, series, colors, label }: Props) {
  const [ref, avail] = useWidth<HTMLDivElement>();
  const rows = useMemo(
    () =>
      categories
        .map((c, i) => {
          const cells = series.map((s, k) => ({ v: s.values[i], k, name: s.name, best: s.best[i] })).filter((x): x is { v: number; k: number; name: string; best: boolean } => x.v !== null);
          const min = Math.min(...cells.map((x) => x.v));
          const max = Math.max(...cells.map((x) => x.v));
          const win = cells.filter((x) => x.best);
          return { c, min, max, win, n: cells.length };
        })
        .filter((r) => Number.isFinite(r.min))
        .sort((a, b) => a.min - b.min),
    [categories, series],
  );
  const rowH = 40;
  const m = { t: 26, r: 24, b: 6, l: Math.min(180, Math.max(110, avail * 0.2)) };
  const iw = Math.max(220, avail - m.l - m.r - 150);
  const height = m.t + m.b + rows.length * rowH;
  const top = Math.max(1, ...rows.map((r) => r.max));
  const { s: x, ticks } = useMemo(() => niceScale(0, top, [0, iw], 5), [top, iw]);
  if (!rows.length) return <div className="state">No rates for these filters.</div>;
  return (
    <div ref={ref}>
      <div className="chart" role="img" aria-label={label} style={{ height }}>
        {avail > 0 && (
          <svg width={avail} height={height}>
            <g transform={`translate(${m.l},${m.t})`}>
              {ticks.map((t) => (
                <g key={t} transform={`translate(${x(t)},0)`}>
                  <line className="vd-grid" y1={-6} y2={rows.length * rowH} />
                  <text className="vd-tick" y={-12} textAnchor="middle">
                    {tickText(t, true)}
                  </text>
                </g>
              ))}
              {rows.map((r, i) => {
                const cy = i * rowH + rowH / 2;
                const w = r.win[0];
                const col = colors[w.k % colors.length];
                return (
                  <g key={r.c}>
                    <title>{`${r.c}: cheapest ${inr(r.min)} (${r.win.map((q) => q.name).join(", ")}) · dearest ${inr(r.max)} · ${r.n} vendor${r.n === 1 ? "" : "s"}`}</title>
                    <text className="vd-cat" x={-14} y={cy} dy="0.34em" textAnchor="end">
                      {r.c.length > 24 ? `${r.c.slice(0, 23)}…` : r.c}
                    </text>
                    <rect x={0} y={cy - 11} width={Math.max(2, x(r.min))} height={22} rx={5} fill={col} fillOpacity={0.9} />
                    {r.n > 1 && r.max > r.min && <line className="bp-max" x1={x(r.max)} x2={x(r.max)} y1={cy - 13} y2={cy + 13} />}
                    <text className="bp-val" x={Math.max(2, x(r.min)) + 10} y={cy} dy="0.34em" style={{ transform: r.max > r.min && x(r.max) - x(r.min) < 120 ? `translateX(${x(r.max) - x(r.min)}px)` : undefined }}>
                      {inr(r.min)} <tspan className="bp-who">{r.win.length > 2 ? `${r.win.length} vendors` : r.win.map((q) => q.name).join(", ")}</tspan>
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>
      <p className="stamp" style={{ whiteSpace: "normal", marginTop: 6 }}>
        Bar = cheapest rate for the fabric, coloured by the vendor that offers it · the thin tick marks the dearest rate
      </p>
    </div>
  );
}
