import { useDashboard } from "../api/hooks";
import type { FloFutureData, Kpi, TableData } from "../api/types";
import { Legend } from "../components/charts/common";
import { DataTable } from "../components/DataTable";
import { DESIGNER_SERIES, DesignerColumns, VISIT_SERIES, VisitColumns } from "../components/FloFutureParts";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

/* The FLO Future tab of the original Streamlit dashboard (same filters, KPIs, charts and tables), drawn with this
   app's own page header, filter bar, KPI strip, panels and tables. Every number comes from GET /api/flo-future
   (backend/app/dashboards/flo_future.py). */
const KEYS = ["designer", "team", "status", "due"];
const SAMPLE_COLS = ["Collection / Sample", "Designer", "Vendor", "Qty", "Completed", "Pending", "Status", "Due Date", "Days Left", "Promised To", "Remark"];

const text = (id: string, label: string, value: string, hint?: string, tone?: Kpi["tone"]): Kpi => ({ id, label, value, unit: "", format: "text", hint, tone });

function kpiList(s: NonNullable<FloFutureData["summary"]>): Kpi[] {
  const mp = s.most_pending;
  const lo = s.longest_overdue;
  const out: Kpi[] = [
    text("target", "Target qty (promised)", `${fmtInt(s.target)} Pcs`, `${s.items} items`),
    text("completed", "Completed", `${fmtInt(s.completed)} Pcs`, `${s.items_done} of ${s.items} items done`),
    text("pending", "Pending", `${fmtInt(s.pending)} Pcs`),
    text("done_pct", "Completion %", `${s.done_pct.toFixed(1)}%`),
    text("overdue", "Overdue (date passed)", `${s.overdue_items} Items · ${fmtInt(s.overdue_pcs)} Pcs`, undefined, s.overdue_items ? "alert" : undefined),
    text("due_soon", "Due in next 3 days", `${s.due_soon} Items · ${fmtInt(s.due_soon_pcs)} Pcs`),
    text("most_pending", "Most pending", mp ? `${mp.designer} (${fmtInt(mp.pending)} Pcs)` : "None"),
    text("longest", "Longest overdue", lo ? `${lo.days} Days · ${lo.designer}` : "None", lo?.item),
  ];
  if (s.visits.required) out.push(text("visits", "Visits & meetings done", `${s.visits.done} / ${s.visits.required}`));
  return out;
}

/** The sample list as the original tab showed it: these columns only (the API also sends team, season, due status). */
function sampleTable(t: TableData): TableData {
  const keep = SAMPLE_COLS.map((c) => t.columns.findIndex((x) => x.label === c)).filter((i) => i >= 0);
  return { ...t, columns: keep.map((i) => t.columns[i]), rows: t.rows.map((r) => keep.map((i) => r[i])) };
}

export default function FloFuture() {
  const f = useFilters(KEYS);
  const q = useDashboard<FloFutureData>("/flo-future", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const v = d.visits;
          const visits = v.chart.categories.length > 0 && (
            <Section title="Visits and meetings" sub="This month · Done = 'X' or STATUS 'Done' in the sheet · Missed = date passed but not marked done">
              <Panel
                title="Required vs done"
                sub={`${v.totals.done} / ${v.totals.required} done · count per activity`}
                right={<Legend items={VISIT_SERIES.map(([name, color]) => ({ name, color }))} />}
              >
                <VisitColumns data={v.chart} />
              </Panel>
            </Section>
          );
          if (d.empty || !d.summary || !d.tables || !d.charts)
            return (
              <>
                <PageHead title="FLO Future" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No promised samples">The FLO Future sheet's Samples tab has no rows yet.</Empty>
                {visits}
              </>
            );
          const s = d.summary;
          const c = d.charts;
          const target = c.designers.labels.reduce((a, l) => a + l.target, 0);
          const done = c.designers.labels.reduce((a, l) => a + l.completed, 0);
          return (
            <>
              <PageHead
                title="FLO Future"
                meta={d.meta}
                lede={
                  <>
                    <strong>{s.done_pct.toFixed(1)}% done</strong>: {fmtInt(s.completed)} of {fmtInt(s.target)} promised pcs{d.period ? ` for ${d.period}` : ""}.{" "}
                    <span className={s.overdue_items ? "bad" : undefined}>
                      {s.overdue_items} item{s.overdue_items === 1 ? "" : "s"} overdue ({fmtInt(s.overdue_pcs)} pcs)
                    </span>
                    , {s.due_soon} due in the next 3 days.
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(x) => f.set("designer", x)} pretty={(x) => x} />
                <MultiSelect label="Team" options={d.options.team} value={f.values.team} onChange={(x) => f.set("team", x)} pretty={(x) => x} />
                <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(x) => f.set("status", x)} pretty={(x) => x} />
                <MultiSelect label="Due status" options={d.options.due} value={f.values.due} onChange={(x) => f.set("due", x)} pretty={(x) => x} />
              </FilterBar>
              <p className="stamp" style={{ whiteSpace: "normal", margin: "0 0 12px" }}>
                Today {d.today} · Pending = Qty Promised − Completed · Overdue = due date has passed and status is not 'Complete' · Days Left = Due Date − today
              </p>
              <Notices items={d.notices} />

              {d.no_match ? (
                <Empty title="No promised samples found for the selected filters" />
              ) : (
                <>
                  <KpiStrip kpis={kpiList(s)} cols={3} />

                  <Section title="Designer-wise target vs completed" sub="The Designer filter is not applied here so all designers can be compared; the other filters apply">
                    <Panel
                      title="Target vs completed"
                      sub={`Pcs · total ${fmtInt(done)} / ${fmtInt(target)} done (${(target ? (done / target) * 100 : 0).toFixed(1)}%) · full column = target · label = done % and done / target`}
                      right={<Legend items={DESIGNER_SERIES.map(([name, color]) => ({ name, color }))} />}
                    >
                      <DesignerColumns data={c.designers} />
                    </Panel>
                  </Section>

                  <Section title="Designer-wise table" sub="Done %: green ≥ 80%, amber 40–79%, red below 40%">
                    <Panel flush>
                      <DataTable table={d.tables.designers} name="flo_future_designer" maxRows={15} titleCaseFirst={false} />
                    </Panel>
                  </Section>

                  <Section title="Sample detail" sub="All items, most urgent first · every filter applies · pick one designer to see their full list">
                    <Panel flush>
                      <DataTable table={sampleTable(d.tables.items)} name="flo_future_samples" maxRows={15} titleCaseFirst={false} />
                    </Panel>
                  </Section>
                </>
              )}

              {visits}

              {!!d.checks?.length && (
                <Section title="Sheet checks" sub="Things in the sheet that look wrong or are missing. Fix them in the sheet; this list updates within a minute.">
                  <div data-reveal>
                    <Notices items={d.checks} />
                  </div>
                </Section>
              )}
            </>
          );
        }}
      </PageState>
    </div>
  );
}
