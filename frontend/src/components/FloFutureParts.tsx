import { useMemo } from "react";
import type { FloFutureData } from "../api/types";
import { fmtInt } from "../lib/format";
import { niceScale, useWidth } from "./charts/common";

/* Pieces of the FLO Future page that follow the original Streamlit tab: coloured KPI tiles, the stacked
   designer chart, the sample detail table and the visits & meetings chart. They only draw what the API sends. */

/* App palette (same colours as the other tabs): blue = done, red = overdue, amber = due soon, pale blue = the rest. */
export const FF = {
  done: "var(--accent)",
  overdue: "var(--neg)",
  soon: "var(--warn)",
  later: "var(--series-pale)",
  ref: "var(--series-ref)",
  grey: "var(--series-grey)",
};

export function doneColor(p: number) {
  return p >= 80 ? "var(--pos)" : p >= 40 ? "var(--warn)" : "var(--neg)";
}

// ------------------------------------------------------------------------------------------------ designer chart
type DesignerChart = NonNullable<FloFutureData["charts"]>["designers"];
export const DESIGNER_SERIES: [string, string][] = [
  ["Completed", FF.done],
  ["Pending · Overdue", FF.overdue],
  ["Pending · Due in 0-3 Days", FF.soon],
  ["Pending · Due later / No date", FF.later],
];

/** One stacked column per designer; the full column is the target. Above it: Done % and done / target. */
export function DesignerColumns({ data }: { data: DesignerChart }) {
  const [ref, avail] = useWidth<HTMLDivElement>();
  const height = 400;
  const m = { t: 42, r: 10, b: 52, l: 48 };
  const n = data.categories.length;
  const width = Math.max(avail, m.l + m.r + n * 66);
  const iw = width - m.l - m.r;
  const ih = height - m.t - m.b;
  const band = n ? iw / n : iw;
  const bw = Math.min(80, band * 0.68);
  const top = Math.max(1, ...data.labels.map((l) => Math.max(l.target, 0)));
  const { s: y, ticks } = useMemo(() => niceScale(0, top * 1.1, [ih, 0], 6), [top, ih]);
  if (!n) return <div className="state">No data for the selected filters.</div>;
  return (
    <div ref={ref} className="ff-scroll">
      <div className="chart" role="img" aria-label="Designer-wise target split into completed and pending pcs" style={{ height, width }}>
        {avail > 0 && (
          <svg width={width} height={height}>
            <g transform={`translate(${m.l},${m.t})`}>
              <g className="grid">
                {ticks.map((t) => (
                  <g key={t} transform={`translate(0,${y(t)})`}>
                    <line x1={0} x2={iw} />
                    <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                      {t}
                    </text>
                  </g>
                ))}
              </g>
              {data.categories.map((name, i) => {
                const l = data.labels[i];
                const cx = i * band + band / 2;
                let acc = 0;
                return (
                  <g key={name}>
                    <title>{`${l.designer} · ${l.team}\nTarget: ${fmtInt(l.target)} pcs (${l.items} items)\nCompleted: ${fmtInt(l.completed)} pcs (${l.done_pct.toFixed(1)}%)\nOverdue items: ${l.overdue_items}\nNearest open due: ${l.nearest}`}</title>
                    {data.series.map((s, k) => {
                      const v = s.values[i] ?? 0;
                      const y1 = y(acc + v);
                      const h = y(acc) - y1;
                      acc += v;
                      return v > 0 ? (
                        <g key={s.name}>
                          <rect x={cx - bw / 2} y={y1} width={bw} height={Math.max(0, h)} fill={DESIGNER_SERIES[k][1]} />
                          {h > 14 && (
                            <text x={cx} y={y1 + h / 2} dy="0.34em" textAnchor="middle" className="ff-in" fill={k === 0 || k === 1 ? "#fff" : "var(--ink)"}>
                              {fmtInt(v)}
                            </text>
                          )}
                        </g>
                      ) : null;
                    })}
                    <text x={cx} y={y(l.target) - 22} textAnchor="middle" className="ff-top" fill={doneColor(l.done_pct)}>
                      {l.done_pct.toFixed(0)}%
                    </text>
                    <text x={cx} y={y(l.target) - 8} textAnchor="middle" className="ff-top2" fill={doneColor(l.done_pct)}>
                      {fmtInt(l.completed)}/{fmtInt(l.target)}
                    </text>
                    <text x={cx} y={ih + 18} textAnchor="middle" className="ff-x">
                      {name}
                    </text>
                    <text x={cx} y={ih + 33} textAnchor="middle" className="ff-x2">
                      {l.team}
                    </text>
                  </g>
                );
              })}
              <text className="ff-axis" transform={`translate(-36,${ih / 2}) rotate(-90)`} textAnchor="middle">
                Pcs (full column = Target)
              </text>
            </g>
          </svg>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ visits chart
type VisitChart = NonNullable<FloFutureData["visits"]>["chart"];
export const VISIT_SERIES: [string, string][] = [
  ["Required", FF.grey],
  ["Done", FF.done],
  ["Missed / Not Marked", FF.overdue],
  ["Upcoming", FF.ref],
];

/** Grouped columns per activity: Required | Done | Missed | Upcoming, with "x / y done" under the name. */
export function VisitColumns({ data }: { data: VisitChart }) {
  const [ref, avail] = useWidth<HTMLDivElement>();
  const height = 360;
  const m = { t: 40, r: 10, b: 54, l: 40 };
  const n = data.categories.length;
  const width = Math.max(avail, m.l + m.r + n * 150);
  const iw = width - m.l - m.r;
  const ih = height - m.t - m.b;
  const band = n ? iw / n : iw;
  const bar = Math.min(34, (band * 0.7) / 4);
  const req = data.series[0]?.values ?? [];
  const done = data.series[1]?.values ?? [];
  const top = Math.max(1, ...req);
  const { s: y, ticks } = useMemo(() => niceScale(0, top * 1.35, [ih, 0], 6), [top, ih]);
  const tickVals = ticks.filter((t) => Number.isInteger(t));
  return (
    <div ref={ref} className="ff-scroll">
      <div className="chart" role="img" aria-label="Visits and meetings: required, done, missed and upcoming per activity" style={{ height, width }}>
        {avail > 0 && (
          <svg width={width} height={height}>
            <g transform={`translate(${m.l},${m.t})`}>
              <g className="grid">
                {tickVals.map((t) => (
                  <g key={t} transform={`translate(0,${y(t)})`}>
                    <line x1={0} x2={iw} />
                    <text className="tick" x={-8} dy="0.32em" textAnchor="end">
                      {t}
                    </text>
                  </g>
                ))}
              </g>
              {data.categories.map((name, i) => {
                const cx = i * band + band / 2;
                const x0 = cx - (bar * 4) / 2;
                return (
                  <g key={name}>
                    {data.series.map((s, k) => {
                      const v = s.values[i] ?? 0;
                      return (
                        <g key={s.name}>
                          <title>{`${name} · ${s.name}: ${v}`}</title>
                          <rect x={x0 + k * bar + 2} y={y(v)} width={bar - 4} height={Math.max(0, ih - y(v))} fill={VISIT_SERIES[k][1]} />
                          {v > 0 && (
                            <text x={x0 + k * bar + bar / 2} y={y(v) - 5} textAnchor="middle" className="ff-top2" fill="var(--ink)">
                              {v}
                            </text>
                          )}
                        </g>
                      );
                    })}
                    {data.flags[i] && (
                      <text x={cx} y={y(req[i] ?? 0) - 22} textAnchor="middle" className="ff-flag">
                        ⚠ {data.flags[i]}
                      </text>
                    )}
                    <text x={cx} y={ih + 18} textAnchor="middle" className="ff-x">
                      {name}
                    </text>
                    <text x={cx} y={ih + 33} textAnchor="middle" className="ff-x2">
                      {done[i] ?? 0}/{req[i] ?? 0} done
                    </text>
                  </g>
                );
              })}
              <text className="ff-axis" transform={`translate(-30,${ih / 2}) rotate(-90)`} textAnchor="middle">
                Count
              </text>
            </g>
          </svg>
        )}
      </div>
    </div>
  );
}
