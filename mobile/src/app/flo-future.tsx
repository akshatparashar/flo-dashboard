/* FLO Future: designers' promised samples for the season. How much is done, what is overdue or due in the next three
   days, each designer's target against completed, and this month's visits and meetings. Same API as the web page
   (GET /api/flo-future). */
import { View } from "react-native";
import { StackedList } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, useFilters } from "../components/Filters";
import { FollowUp } from "../components/FollowUp";
import { Em, Screen } from "../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section, T } from "../components/ui";
import { fmtInt } from "../lib/format";
import { useDashboard } from "../lib/query";
import { useTheme } from "../lib/theme";
import type { FloFutureData, Kpi, TableData } from "../lib/types";

const KEYS = ["designer", "team", "status", "due"];
const GROUPS = [
  { key: "designer", label: "Designer", raw: true },
  { key: "team", label: "Team", raw: true },
  { key: "status", label: "Status", raw: true },
  { key: "due", label: "Due status", raw: true },
];
const SAMPLE_COLS = ["Collection / Sample", "Designer", "Vendor", "Qty", "Completed", "Pending", "Status", "Due Date", "Days Left", "Promised To", "Remark"];

const text = (id: string, label: string, value: string, hint?: string, tone?: Kpi["tone"]): Kpi => ({ id, label, value, unit: "", format: "text", hint, tone });

function kpiList(s: NonNullable<FloFutureData["summary"]>): Kpi[] {
  const mp = s.most_pending;
  const lo = s.longest_overdue;
  const out: Kpi[] = [
    text("target", "Target qty (promised)", `${fmtInt(s.target)} pcs`, `${s.items} items`),
    text("completed", "Completed", `${fmtInt(s.completed)} pcs`, `${s.items_done} of ${s.items} items done`),
    text("pending", "Pending", `${fmtInt(s.pending)} pcs`),
    text("overdue", "Overdue", `${s.overdue_items} items · ${fmtInt(s.overdue_pcs)} pcs`, "Due date passed", s.overdue_items ? "alert" : undefined),
    text("due_soon", "Due in next 3 days", `${s.due_soon} items · ${fmtInt(s.due_soon_pcs)} pcs`),
    text("most_pending", "Most pending", mp ? `${mp.designer} (${fmtInt(mp.pending)} pcs)` : "None"),
    text("longest", "Longest overdue", lo ? `${lo.days} days · ${lo.designer}` : "None", lo?.item),
  ];
  if (s.visits.required) out.push(text("visits", "Visits & meetings done", `${s.visits.done} / ${s.visits.required}`));
  return out;
}

/** The sample list with the columns the owner reads (the API also sends team, season, due status). */
function sampleTable(t: TableData): TableData {
  const keep = SAMPLE_COLS.map((c) => t.columns.findIndex((x) => x.label === c)).filter((i) => i >= 0);
  return { ...t, columns: keep.map((i) => t.columns[i]), rows: t.rows.map((r) => keep.map((i) => r[i])) };
}

export default function FloFuture() {
  const c = useTheme();
  const f = useFilters(KEYS);
  const q = useDashboard<FloFutureData>("/flo-future", f.values);
  return (
    <Screen
      title="FLO Future"
      inStack
      q={q}
      lede={(d) => {
        const s = d.summary;
        if (d.empty || !s) return "No promised samples in the sheet yet.";
        return (
          <>
            <Em>{s.done_pct.toFixed(1)}% done</Em>: {fmtInt(s.completed)} of {fmtInt(s.target)} promised pcs{d.period ? ` for ${d.period}` : ""}.{" "}
            <Em bad={s.overdue_items > 0}>
              {s.overdue_items} item{s.overdue_items === 1 ? "" : "s"} overdue
            </Em>
            , {s.due_soon} due in the next 3 days.
          </>
        );
      }}
      filters={(d) =>
        d.empty ? null : (
          <View style={{ flexDirection: "row" }}>
            <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
          </View>
        )
      }
    >
      {(d) => {
        const v = d.visits;
        const visits = v.chart.categories.length > 0 && (
          <Section title="Visits and meetings" sub="This month · required against done">
            <Panel title="Required vs done" sub={`${v.totals.done} / ${v.totals.required} done${v.totals.missed ? ` · ${v.totals.missed} missed or not marked` : ""}`} flush>
              <DataTable table={v.summary} name="flo_future_visits" maxRows={12} titleCaseFirst={false} />
            </Panel>
          </Section>
        );
        if (d.empty || !d.summary || !d.tables || !d.charts)
          return (
            <>
              <Notices items={d.notices} />
              <Empty title="No promised samples" text="The FLO Future sheet's Samples tab has no rows yet." />
              {visits}
            </>
          );
        if (d.no_match) return <Empty title="No promised samples match these filters" />;
        const ch = d.charts.designers;
        const target = ch.labels.reduce((a, l) => a + l.target, 0);
        const done = ch.labels.reduce((a, l) => a + l.completed, 0);
        return (
          <>
            <Notices items={d.notices} />
            <View style={{ marginTop: d.notices?.length ? 12 : 0 }}>
              <KpiGrid kpis={[text("done_pct", "Completion", `${d.summary.done_pct.toFixed(1)}%`, `Today ${d.today}`), ...kpiList(d.summary)]} lead={["done_pct"]} />
            </View>

            {!!d.follow_up?.length && (
              <Section title="Follow up first" sub="Overdue, then due in the next 3 days">
                <Panel flush>
                  <FollowUp items={d.follow_up} max={6} empty="Nothing is overdue or due soon." />
                </Panel>
              </Section>
            )}

            <Section title="Designer-wise" sub="Target against completed · the Designer filter does not apply here">
              <Panel title="Completed and pending" sub={`Pcs · ${fmtInt(done)} / ${fmtInt(target)} done (${(target ? (done / target) * 100 : 0).toFixed(1)}%)`}>
                <StackedList data={ch} unit="pcs" max={14} raw colors={{ Completed: c.accent, "Pending · Overdue": c.neg, "Pending · Due in 0-3 Days": c.warn, "Pending · Due later / No date": c.seriesPale }} />
              </Panel>
              <Panel title="Designer table" sub="Done %: green ≥ 80%, amber 40–79%, red below 40%" flush>
                <DataTable table={d.tables.designers} name="flo_future_designer" maxRows={15} titleCaseFirst={false} />
              </Panel>
            </Section>

            <Section title="Sample detail" sub="Most urgent first · every filter applies">
              <Panel flush>
                <DataTable table={sampleTable(d.tables.items)} name="flo_future_samples" maxRows={15} titleCaseFirst={false} />
              </Panel>
            </Section>

            {visits}

            {!!d.checks?.length && (
              <Section title="Sheet checks" sub="Fix these in the sheet; this list updates within a minute">
                <Notices items={d.checks} />
              </Section>
            )}
            <T v="small" style={{ marginTop: 16 }}>
              Pending = qty promised − completed · Overdue = due date passed and status not Complete · Days left = due date − today
            </T>
          </>
        );
      }}
    </Screen>
  );
}
