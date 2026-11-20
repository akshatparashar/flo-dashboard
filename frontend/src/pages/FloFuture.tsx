import { useDashboard } from "../api/hooks";
import type { FloFutureData } from "../api/types";
import { DataTable } from "../components/DataTable";
import { DESIGNER_SERIES, DesignerColumns, KpiTiles, SampleDetail, VISIT_SERIES, VisitColumns } from "../components/FloFutureParts";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, Notices, Panel } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageState } from "./common";

/* The FLO Future tab of the original Streamlit dashboard, drawn section by section in the same order: banner, filters,
   KPI tiles, designer-wise target vs completed, designer-wise table, sample detail, visits & meetings. Every number
   comes from GET /api/flo-future (backend/app/dashboards/flo_future.py). */
const KEYS = ["designer", "team", "status", "due"];

function Badge({ children }: { children: React.ReactNode }) {
  return <div className="ff-badge">{children}</div>;
}

function Key({ items }: { items: [string, string][] }) {
  return (
    <div className="ff-key">
      {items.map(([name, color]) => (
        <span key={name}>
          <i style={{ background: color }} />
          {name}
        </span>
      ))}
    </div>
  );
}

function updated(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true });
}

export default function FloFuture() {
  const f = useFilters(KEYS);
  const q = useDashboard<FloFutureData>("/flo-future", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const banner = (
            <div className="ff-banner" data-reveal>
              <h1>🔮 FLO Future – Promised Actions{d.period ? ` · ${d.period}` : ""} ({d.meta.fy})</h1>
              <span className="ff-updated">🕒 Updated {updated(d.meta.synced_at)}</span>
            </div>
          );
          const visits = d.visits;
          const visitsBlock = (
            <>
              <hr className="ff-rule" />
              <Badge>🗓️ Visits &amp; Meetings (this month)</Badge>
              {visits.chart.categories.length ? (
                <Panel
                  title="Visits & Meetings: Required vs Done"
                  sub={`${visits.totals.done} / ${visits.totals.required} done · Done = 'X' or STATUS 'Done' in the sheet · Missed = date passed but not marked done · hover a bar for names and dates`}
                >
                  <Key items={VISIT_SERIES} />
                  <VisitColumns data={visits.chart} />
                </Panel>
              ) : (
                <Notices items={d.notices} />
              )}
            </>
          );
          if (d.empty || !d.summary || !d.tables || !d.charts)
            return (
              <>
                {banner}
                <Notices items={d.notices} />
                <Empty title="No promised samples">The FLO Future sheet's Samples tab has no rows yet.</Empty>
                {visitsBlock}
              </>
            );
          const s = d.summary;
          const c = d.charts;
          return (
            <>
              {banner}
              <Badge>🔎 Filters (leave empty = ALL) · apply to Samples</Badge>
              <FilterBar active={f.active} onReset={f.reset}>
                <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} pretty={(x) => x} />
                <MultiSelect label="Team" options={d.options.team} value={f.values.team} onChange={(v) => f.set("team", v)} pretty={(x) => x} />
                <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(v) => f.set("status", v)} pretty={(x) => x} />
                <MultiSelect label="Due Status" options={d.options.due} value={f.values.due} onChange={(v) => f.set("due", v)} pretty={(x) => x} />
              </FilterBar>
              <p className="ff-caption">
                Today: {d.today} · Pending = Qty Promised − Completed · Overdue = Due Date has passed and Status is not 'Complete' (same rule as the sheet) · Days Left = Due Date − today.
              </p>
              <Notices items={d.notices} />

              {d.no_match ? (
                <Empty title="No promised samples found for the selected filters" />
              ) : (
                <>
                  <Badge>📊 Key Performance Indicators</Badge>
                  <KpiTiles s={s} />

                  <hr className="ff-rule" />
                  <Badge>👩‍🎨 Designer-wise Target vs Completed</Badge>
                  <p className="ff-caption">The Designer filter is not applied here so all designers can be compared; the other filters apply.</p>
                  <Panel
                    title="Designer-wise Target vs Completed (Pcs)"
                    sub={`Total ${fmtInt(c.designers.labels.reduce((a, l) => a + l.completed, 0))} / ${fmtInt(c.designers.labels.reduce((a, l) => a + l.target, 0))} done (${(c.designers.labels.reduce((a, l) => a + l.target, 0) ? (c.designers.labels.reduce((a, l) => a + l.completed, 0) / c.designers.labels.reduce((a, l) => a + l.target, 0)) * 100 : 0).toFixed(1)}%) · top label = Done % and done/target · hover for full details`}
                  >
                    <Key items={DESIGNER_SERIES} />
                    <DesignerColumns data={c.designers} />
                  </Panel>

                  <hr className="ff-rule" />
                  <Badge>📊 Designer-wise Table</Badge>
                  <p className="ff-caption">
                    Done % colour: <i className="ff-dot" style={{ background: "#059669" }} /> ≥80% <i className="ff-dot" style={{ background: "#d97706" }} /> 40-79% <i className="ff-dot" style={{ background: "#dc2626" }} /> &lt;40%.
                  </p>
                  <Panel flush>
                    <DataTable table={d.tables.designers} name="flo_future_designer" maxRows={15} titleCaseFirst={false} />
                  </Panel>

                  <hr className="ff-rule" />
                  <Badge>📋 Sample Detail (all items · most urgent first)</Badge>
                  <p className="ff-caption">All filters above apply here - pick one designer to see their full list. Days Left: 🔴 late 🟡 0-3 days 🟢 3+ days / done.</p>
                  <Panel flush>
                    <SampleDetail table={d.tables.items} name="flo_future_samples" />
                  </Panel>
                </>
              )}

              {visitsBlock}
            </>
          );
        }}
      </PageState>
    </div>
  );
}
