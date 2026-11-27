/* Daily Delegation: Sir's day from the "Daily Schedule" tab of Sir_Daily_Delegation_Tracker. Today's open work with the
   person responsible first, then what is carried over, who holds what and how long open tasks have waited.
   Same API as the web page (GET /api/daily-delegation). */
import { StyleSheet, Text, View } from "react-native";
import { BarList, Split, StackedList } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, SearchBox, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { Card, Empty, Insights, KpiGrid, Notices, Panel, Section, T } from "../components/ui";
import { fmtInt } from "../lib/format";
import { useDashboard } from "../lib/query";
import { font, useTheme, type Palette } from "../lib/theme";
import type { DailyDelegationData, TodoItem } from "../lib/types";

const KEYS = ["date", "person", "status", "q"];
const GROUPS = [
  { key: "date", label: "Date", raw: true },
  { key: "person", label: "Responsible", raw: true },
  { key: "status", label: "Status", raw: true },
];

function statusColors(c: Palette): Record<string, string> {
  return {
    Completed: c.pos,
    "In Progress": c.accent,
    "Awaiting Approval": c.warn,
    Pending: c.neg,
    "On Hold": c.seriesGrey,
    "Status Not Set": c.seriesPale,
  };
}

/** Open work as red-edged lines: the task, who is responsible, its status (and how long it has waited). */
function TodoLines({ items, aged }: { items: TodoItem[]; aged?: boolean }) {
  const c = useTheme();
  const sc = statusColors(c);
  return (
    <View>
      {items.map((t, i) => (
        <View key={`${t.task}-${i}`} style={[st.todo, { borderLeftColor: c.neg, borderColor: c.rule, borderTopWidth: i ? StyleSheet.hairlineWidth : 0 }]}>
          <T v="strong" style={{ fontSize: 14.5 }}>{t.task}</T>
          <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
            <T v="small" style={{ color: c.ink }}>{t.person}</T>
            <View style={[st.pill, { borderColor: sc[t.status] ?? c.seriesGrey }]}>
              <Text style={{ fontFamily: font.uiBold, fontSize: 11.5, color: sc[t.status] ?? c.muted }}>{t.status}</Text>
            </View>
            {aged && t.age !== null && (
              <T v="small">
                {t.date} · {t.age} day{t.age === 1 ? "" : "s"}
              </T>
            )}
          </View>
        </View>
      ))}
    </View>
  );
}

export default function DailyDelegation() {
  const c = useTheme();
  const f = useFilters(KEYS);
  const q = useDashboard<DailyDelegationData>("/daily-delegation", f.values);
  const sc = statusColors(c);
  return (
    <Screen
      title="Daily Delegation"
      inStack
      q={q}
      lede={(d) => {
        if (d.empty) return "No tasks in the Daily Schedule tab yet.";
        if (d.no_match) return "No task matches these filters.";
        const s = d.summary;
        return (
          <>
            <Em>{fmtInt(s.tasks)} tasks</Em> over {s.days} day{s.days === 1 ? "" : "s"}: {fmtInt(s.completed)} done ({s.done_pct.toFixed(0)}%), <Em bad={s.open > 0}>{fmtInt(s.open)} still open</Em>
            {s.awaiting ? <>, {fmtInt(s.awaiting)} waiting for {"Sir's"} approval</> : null}.
          </>
        );
      }}
      filters={(d) =>
        d.empty ? null : (
          <>
            <SearchBox value={f.values.q[0] ?? ""} onChange={(v) => f.set("q", v ? [v] : [])} placeholder="Search task, person or remark" />
            <View style={{ flexDirection: "row" }}>
              <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
            </View>
          </>
        )
      }
    >
      {(d) => {
        if (d.empty)
          return (
            <>
              <Notices items={d.notices} />
              <Empty title="No tasks yet" text="The Daily Schedule tab has no task rows." />
            </>
          );
        if (d.no_match) return <Empty title="No task matches these filters" />;
        const tp = d.today_pending;
        return (
          <>
            <KpiGrid kpis={d.kpis} lead={["total"]} />

            <Section title="Today's pending work" sub={`${tp.date} · open tasks dated today`}>
              <Card flush>
                {tp.today.length ? (
                  <TodoLines items={tp.today} />
                ) : (
                  <T style={{ padding: 16 }}>{tp.today_total ? "Everything dated today is completed." : `No task is dated today (${tp.date}) yet.`}</T>
                )}
              </Card>
              {!!tp.carried.length && (
                <Panel title={`Carried over · ${tp.carried.length}`} sub="Still open from earlier days, oldest first" flush>
                  <TodoLines items={tp.carried.slice(0, 10)} aged />
                  {tp.carried.length > 10 && <T v="small" style={{ padding: 16 }}>+{tp.carried.length - 10} more · see Needs attention below</T>}
                </Panel>
              )}
            </Section>

            <Section title="Highlights" sub={`From the sheet as on ${d.today}`}>
              <Insights items={d.insights} />
            </Section>

            <Section title="Where things stand" sub="Status of every task">
              <Panel title="Status">
                <Split items={d.charts.status} unit="tasks" colors={sc} raw />
              </Panel>
              <Panel title="Open tasks by age" sub="Days since the task's date">
                <BarList items={d.charts.ageing} unit="tasks" tone="neg" max={6} raw keepOrder />
              </Panel>
            </Section>

            <Section title="Who has what" sub="Tasks per responsible person, by status">
              <Panel title="Tasks by person">
                <StackedList data={d.charts.by_person} unit="tasks" max={14} colors={sc} raw />
              </Panel>
              <Panel title="Person summary" flush>
                <DataTable table={d.tables.persons} name="delegation_persons" maxRows={14} titleCaseFirst={false} />
              </Panel>
              <Panel title="Date summary" flush>
                <DataTable table={d.tables.dates} name="delegation_dates" maxRows={14} titleCaseFirst={false} />
              </Panel>
            </Section>

            {!!d.tables.attention.rows.length && (
              <Section title="Needs attention" sub="Open from earlier days, and waiting for approval · oldest first">
                <Panel flush>
                  <DataTable table={d.tables.attention} name="delegation_attention" maxRows={12} titleCaseFirst={false} />
                </Panel>
              </Section>
            )}

            <Section title="All tasks" sub="Open first, oldest on top; completed follow">
              <Panel flush>
                <DataTable table={d.tables.tasks} name="delegation_tasks" maxRows={15} titleCaseFirst={false} />
              </Panel>
            </Section>

            {!!d.checks.length && (
              <Section title="Sheet checks" sub="Rows that look incomplete">
                <Notices items={d.checks} />
              </Section>
            )}
          </>
        );
      }}
    </Screen>
  );
}

const st = StyleSheet.create({
  todo: { borderLeftWidth: 4, paddingHorizontal: 14, paddingVertical: 12, gap: 6 },
  pill: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
});
