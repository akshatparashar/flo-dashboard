import { useDashboard } from "../api/hooks";
import type { FloFutureData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Legend } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { BarList, Split } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FollowUp } from "../components/FollowUp";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

/* Same filters, KPIs, tables and colour meanings as the original Streamlit "FLO Future" tab; every number comes
   from GET /api/flo-future (backend/app/dashboards/flo_future.py). */
const KEYS = ["designer", "team", "status", "due"];
export const DUE_COLORS: Record<string, string> = {
  Overdue: "var(--neg)",
  "Due Today": "var(--warn)",
  "Due in 1-3 Days": "color-mix(in srgb, var(--warn) 62%, var(--sheet))",
  "Due in 4-7 Days": "var(--series-pale)",
  "Due Later (> 7 Days)": "var(--series-ref)",
  "No Due Date": "var(--series-grey)",
  Completed: "var(--accent)",
};
const DESIGNER_COLORS: Record<string, string> = {
  Completed: "var(--accent)",
  "Pending · Overdue": "var(--neg)",
  "Pending · Due in 0-3 Days": "var(--warn)",
  "Pending · Due later / No date": "var(--series-pale)",
};
const VISIT_COLORS: Record<string, string> = {
  Required: "var(--series-grey)",
  Done: "var(--accent)",
  "Missed / Not Marked": "var(--neg)",
  Upcoming: "var(--series-ref)",
};
const plural = (n: number, word: string) => `${fmtInt(n)} ${word}${n === 1 ? "" : "s"}`;

function Visits({ d }: { d: FloFutureData }) {
  const v = d.visits;
  if (!v.chart.categories.length) return null;
  const flagged = v.chart.categories.map((c, i) => [c, v.chart.flags[i]]).filter(([, f]) => f);
  return (
    <Section title="Visits and meetings" sub={`${v.totals.done} / ${v.totals.required} done this month · Done = 'X' or STATUS 'Done' in the sheet · Missed = date passed but not marked done`}>
      <div className="grid">
        <div className="span-7">
          <Panel title="Required vs done" sub="Count per activity" right={<Legend items={Object.entries(VISIT_COLORS).map(([name, color]) => ({ name, color }))} />}>
            <Bars data={v.chart} colors={VISIT_COLORS} label="Visits and meetings: required, done, missed and upcoming per activity" height={250} />
            {flagged.length > 0 && (
              <div className="ff-flags">
                {flagged.map(([c, f]) => (
                  <span key={c}>
                    <b>{c}</b>: {f}
                  </span>
                ))}
              </div>
            )}
          </Panel>
        </div>
        <div className="span-5">
          <Panel title="Activity summary" flush>
            <DataTable table={v.summary} name="flo_future_visits_summary" titleCaseFirst={false} csv={false} />
          </Panel>
        </div>
        {v.detail.rows.length > 0 && (
          <div className="span-12">
            <Panel title="Every planned visit and meeting" flush>
              <DataTable table={v.detail} name="flo_future_visits" titleCaseFirst={false} />
            </Panel>
          </div>
        )}
      </div>
    </Section>
  );
}

export default function FloFuture() {
  const f = useFilters(KEYS);
  const q = useDashboard<FloFutureData>("/flo-future", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const head = (lede?: React.ReactNode) => <PageHead title="FLO Future" meta={d.meta} lede={lede} />;
          if (d.empty || !d.summary || !d.tables || !d.charts)
            return (
              <>
                {head()}
                <Notices items={d.notices} />
                <Empty title="No promised samples">The FLO Future sheet's Samples tab has no rows yet.</Empty>
                <Visits d={d} />
              </>
            );
          const s = d.summary;
          const t = d.tables;
          const c = d.charts;
          const period = d.period ? ` for ${d.period}` : "";
          const labels = Object.fromEntries(c.designers.labels.map((l) => [l.designer, l]));
          const filters = (
            <FilterBar active={f.active} onReset={f.reset}>
              <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} pretty={(x) => x} />
              <MultiSelect label="Team" options={d.options.team} value={f.values.team} onChange={(v) => f.set("team", v)} pretty={(x) => x} />
              <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(v) => f.set("status", v)} pretty={(x) => x} />
              <MultiSelect label="Due Status" options={d.options.due} value={f.values.due} onChange={(v) => f.set("due", v)} pretty={(x) => x} />
            </FilterBar>
          );
          return (
            <>
              {head(
                <>
                  <strong>{s.done_pct.toFixed(1)}% done</strong>: {fmtInt(s.completed)} of {fmtInt(s.target)} promised pcs{period}.{" "}
                  <span className={s.overdue_items ? "bad" : undefined}>
                    {plural(s.overdue_items, "item")} overdue ({fmtInt(s.overdue_pcs)} pcs)
                  </span>
                  , {plural(s.due_soon, "item")} due in the next 3 days.
                </>,
              )}
              {filters}
              <p className="stamp ff-rule">
                Today {d.today} · Pending = Qty Promised − Completed · Overdue = due date has passed and the item is not complete · Days Left = Due Date − today
              </p>
              <Notices items={d.notices} />
              {d.no_match ? (
                <Empty title="No promised samples found for the selected filters" />
              ) : (
                <>
                  <KpiStrip kpis={d.kpis} cols={d.kpis.length === 9 ? 3 : 4} lead={["done_pct"]} />

                  <Section title="Follow up now" sub="Overdue first, then due today and in the next 3 days">
                    <div className="grid">
                      <div className="span-7">
                        <Panel title="Urgent samples" sub={plural(d.follow_up?.length ?? 0, "item")} flush>
                          <FollowUp items={d.follow_up ?? []} empty="Nothing is overdue or due in the next 3 days for these filters." />
                        </Panel>
                      </div>
                      <div className="span-5">
                        <Panel title="Open pcs by due status" sub="Pending pcs of items not complete">
                          <Split items={c.due_status} unit="pcs" colors={DUE_COLORS} label="Pending pcs by due status" />
                        </Panel>
                        <Panel title="Open pcs by status">
                          <BarList items={c.status} unit="pcs" max={10} label="Pending pcs by sample status" />
                        </Panel>
                      </div>
                    </div>
                  </Section>

                  <Section title="Designer-wise target vs completed" sub="The Designer filter is not applied here so all designers can be compared; the other filters apply">
                    <div className="grid">
                      <div className="span-5">
                        <Panel
                          title="Target vs completed"
                          sub="Full bar = target pcs · label = done % and done / target"
                          right={<Legend items={Object.entries(DESIGNER_COLORS).map(([name, color]) => ({ name, color }))} />}
                        >
                          <HBars
                            data={c.designers}
                            colors={DESIGNER_COLORS}
                            unit="pcs"
                            max={20}
                            label="Designer-wise target qty split into completed and pending pcs"
                            endLabel={(name) => {
                              const l = labels[name];
                              return l ? `${l.done_pct.toFixed(0)}% · ${fmtInt(l.completed)}/${fmtInt(l.target)}` : "";
                            }}
                          />
                        </Panel>
                      </div>
                      <div className="span-7">
                        <Panel title="Designer table" sub="Done %: green ≥ 80%, amber 40–79%, red below 40%" flush>
                          <DataTable table={t.designers} name="flo_future_designer" maxRows={15} titleCaseFirst={false} />
                        </Panel>
                        {t.teams.rows.length > 0 && (
                          <Panel title="Team table" flush>
                            <DataTable table={t.teams} name="flo_future_team" titleCaseFirst={false} />
                          </Panel>
                        )}
                      </div>
                    </div>
                  </Section>

                  <Section title="Sample detail" sub="All items, most urgent first; every filter applies. Pick one designer to see their full list.">
                    <Panel flush>
                      <DataTable table={t.items} name="flo_future_samples" maxRows={15} titleCaseFirst={false} />
                    </Panel>
                  </Section>
                </>
              )}

              <Visits d={d} />

              {t.outsource.rows.length > 0 && (
                <Section title="Outsource projects" sub="From the sheet's Outsource Projects tab, same rules; not part of the sample numbers above">
                  <Panel flush>
                    <DataTable table={t.outsource} name="flo_future_outsource" titleCaseFirst={false} />
                  </Panel>
                </Section>
              )}

              {!!d.checks?.length && (
                <Section title="Sheet checks" sub="Things in the sheet that look wrong or are missing. They never change a number; fix them in the sheet.">
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
