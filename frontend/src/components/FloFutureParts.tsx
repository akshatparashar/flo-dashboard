import { Download } from "lucide-react";
import { useMemo } from "react";
import type { FloFutureData, TableData } from "../api/types";
import { downloadCsv, toCsv } from "../lib/csv";
import { fmtInt } from "../lib/format";
import { niceScale, useWidth } from "./charts/common";

/* Pieces of the FLO Future page that follow the original Streamlit tab: coloured KPI tiles, the stacked
   designer chart, the sample detail table and the visits & meetings chart. They only draw what the API sends. */

export const FF = {
  green: "#059669",
  red: "#dc2626",
  orange: "#ea580c",
  amber: "#d97706",
  blue: "#2563eb",
  slate: "#94a3b8",
  light: "color-mix(in srgb, #2563eb 32%, var(--sheet))",
};

export function doneColor(p: number) {
  return p >= 80 ? FF.green : p >= 40 ? FF.amber : FF.red;
}

// ------------------------------------------------------------------------------------------------ KPI tiles
const TONES = ["#2563eb", "#059669", "#d97706", "#dc2626", "#ea580c", "#7c3aed", "#0d9488", "#db2777", "#2563eb"];

export function KpiTiles({ s }: { s: NonNullable<FloFutureData["summary"]> }) {
  const mp = s.most_pending;
  const lo = s.longest_overdue;
  const tiles: [string, string][] = [
    ["Target Qty (Promised)", `${fmtInt(s.target)} Pcs`],
    ["Completed", `${fmtInt(s.completed)} Pcs`],
    ["Pending", `${fmtInt(s.pending)} Pcs`],
    ["Completion %", `${s.done_pct.toFixed(1)}%`],
    ["Overdue (Date Passed)", `${s.overdue_items} Items · ${fmtInt(s.overdue_pcs)} Pcs`],
    ["Due in Next 3 Days", `${s.due_soon} Items · ${fmtInt(s.due_soon_pcs)} Pcs`],
    ["⚠ Most Pending", mp ? `${mp.designer} (${fmtInt(mp.pending)} Pcs)` : "None"],
    ["⏰ Longest Overdue", lo ? `${lo.days} Days · ${lo.designer}` : "None"],
  ];
  if (s.visits.required) tiles.push(["Visits & Meetings Done", `${s.visits.done} / ${s.visits.required}`]);
  return (
    <div className="ff-tiles" data-reveal>
      {tiles.map(([label, value], i) => (
        <div className="ff-tile" key={label} style={{ ["--tone" as string]: TONES[i % TONES.length] }}>
          <div className="ff-tile-label">{label}</div>
          <div className="ff-tile-value num">{value}</div>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ designer chart
type DesignerChart = NonNullable<FloFutureData["charts"]>["designers"];
export const DESIGNER_SERIES: [string, string][] = [
  ["Completed", FF.green],
  ["Pending · Overdue", FF.red],
  ["Pending · Due in 0-3 Days", FF.orange],
  ["Pending · Due later / No date", FF.light],
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

// ------------------------------------------------------------------------------------------------ sample detail
const STATUS_COLORS: Record<string, string> = {
  Complete: FF.green,
  "In Progress": FF.blue,
  "In-House Process": "#0d9488",
  "Sampling Ordered": "#7c3aed",
  Corrections: FF.orange,
  "CAD In Queue": "#ca8a04",
  "CAD In Process": FF.amber,
  "Not Started": FF.red,
  "Not Updated": FF.slate,
};

function shortDate(v: unknown): string {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(v ?? ""));
  if (!m) return "—";
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1];
  return `${m[1]}-${mon}-${m[3].slice(2)}`;
}

function daysClass(text: string): string {
  if (text === "Done") return "good";
  if (text.endsWith("late")) return "bad";
  if (text === "Due today") return "mid";
  const m = /^(\d+) days? left$/.exec(text);
  return m ? (Number(m[1]) <= 3 ? "mid" : "good") : "";
}

/** Every sample, most urgent first: status pill, coloured Days Left, TOTAL row. Scrolls inside its own frame. */
export function SampleDetail({ table, name }: { table: TableData; name: string }) {
  const ix = Object.fromEntries(table.columns.map((c, i) => [c.label, i]));
  const body = table.rows.slice(0, -1);
  const tot = table.rows[table.rows.length - 1];
  if (!body.length) return <div className="state">No data for the selected filters.</div>;
  const n = (v: unknown) => (typeof v === "number" ? fmtInt(v) : "—");
  return (
    <>
      <div className="ff-table-wrap">
        <table className="ff-table">
          <thead>
            <tr>
              {["Sr", "Designer", "Collection / Sample", "Vendor", "Qty", "Completed", "Pending", "Status", "Due Date", "Days Left", "Promised To", "Remark"].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((r, i) => {
              const status = String(r[ix.Status] ?? "");
              const c = STATUS_COLORS[status] ?? FF.slate;
              const days = String(r[ix["Days Left"]] ?? "");
              return (
                <tr key={i}>
                  <td className="c">{i + 1}</td>
                  <td className="l strong">{String(r[ix.Designer])}</td>
                  <td className="l wrap">{String(r[0])}</td>
                  <td className="l">{String(r[ix.Vendor] ?? "")}</td>
                  <td>{n(r[ix.Qty])}</td>
                  <td>{n(r[ix.Completed])}</td>
                  <td className={r[ix.Pending] === 0 ? "zero" : undefined}>{n(r[ix.Pending])}</td>
                  <td className="l">
                    <span className="ff-pill" style={{ color: c, background: `color-mix(in srgb, ${c} 16%, transparent)`, borderColor: `color-mix(in srgb, ${c} 45%, transparent)` }}>
                      {status}
                    </span>
                  </td>
                  <td>{shortDate(r[ix["Due Date"]])}</td>
                  <td className={`days ${daysClass(days)}`}>{days}</td>
                  <td className="l">{String(r[ix["Promised To"]] ?? "")}</td>
                  <td className="l wrap">{String(r[ix.Remark] ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <td className="l" colSpan={4}>
                TOTAL
              </td>
              <td>{n(tot[ix.Qty])}</td>
              <td>{n(tot[ix.Completed])}</td>
              <td>{n(tot[ix.Pending])}</td>
              <td className="l">{String(tot[ix.Status] ?? "")}</td>
              <td />
              <td className="l">{String(tot[ix["Days Left"]] ?? "")}</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>
      <button type="button" className="btn ff-dl" onClick={() => downloadCsv(`${name}.csv`, toCsv({ ...table, rows: body }))}>
        <Download aria-hidden="true" /> Download CSV
      </button>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ visits chart
type VisitChart = NonNullable<FloFutureData["visits"]>["chart"];
export const VISIT_SERIES: [string, string][] = [
  ["Required", "color-mix(in srgb, #94a3b8 55%, var(--sheet))"],
  ["Done", FF.green],
  ["Missed / Not Marked", FF.red],
  ["Upcoming", FF.blue],
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
