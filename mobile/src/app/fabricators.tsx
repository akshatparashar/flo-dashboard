/* Fabricators: how much stock sits with each fabricator, month by month. */
import { View } from "react-native";
import { BarList, Bars, StackedList } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section } from "../components/ui";
import { fmtInt, titleCase } from "../lib/format";
import { useDashboard } from "../lib/query";
import type { FabricatorData } from "../lib/types";

const KEYS = ["fabricator", "month", "metric"];
const GROUPS = [
  { key: "fabricator", label: "Fabricator" },
  { key: "metric", label: "Matrix shows", single: true, raw: true },
];

export default function Fabricators() {
  const f = useFilters(KEYS);
  const q = useDashboard<FabricatorData>("/fabricator", { fabricator: f.values.fabricator, month: f.values.month, metric: f.values.metric[0] });
  return (
    <Screen
      title="Fabricators"
      inStack
      q={q}
      lede={(d) => {
        if (d.empty) return null;
        const k = Object.fromEntries(d.kpis.map((x) => [x.id, x]));
        const most = k.most_pending;
        return (
          <>
            <Em bad>{fmtInt(Number(k.remaining?.value) || 0)} pcs</Em> still with fabricators, {(Number(k.received_pct?.value) || 0).toFixed(1)}% of production received
            {most && most.value !== "—" && most.value !== null ? (
              <>
                ; <Em>{titleCase(String(most.value))}</Em> holds the most ({most.hint}).
              </>
            ) : (
              "."
            )}
          </>
        );
      }}
      filters={(d) =>
        d.empty ? null : (
          <>
            <MonthChips months={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
            <View style={{ flexDirection: "row" }}>
              <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
            </View>
          </>
        )
      }
    >
      {(d) => {
        if (d.empty) return <><Notices items={d.notices} /><Empty title="No stock tables found" /></>;
        return (
          <>
            <Notices items={d.notices} />
            <View style={{ marginTop: d.notices?.length ? 12 : 0 }}>
              <KpiGrid kpis={d.kpis} lead={["remaining"]} />
            </View>
            <Section title="Month by month" sub="Pcs under production, received and remaining">
              <Panel title="Production, received and remaining" sub="Pcs · tap a month for figures">
                <Bars data={d.charts.monthly} unit="pcs" />
              </Panel>
              <Panel title="Monthly position of stock" flush>
                <DataTable table={d.tables.monthly} name="fabricators_monthly" maxRows={13} titleCaseFirst={false} />
              </Panel>
            </Section>
            <Section title="By fabricator" sub="Who holds the stock">
              <Panel title="Received and remaining" sub="Pcs, most remaining first">
                <StackedList data={d.charts.rcvd_vs_remaining} unit="pcs" sortBy="Remaining" max={12} />
              </Panel>
              <Panel title="Received rate" sub="Received ÷ pcs under production, %">
                <BarList items={d.charts.received_pct} unit="pct" max={12} />
              </Panel>
              <Panel title="Fabricator scorecard" flush>
                <DataTable table={d.tables.scorecard} name="fabricators_scorecard" maxRows={12} />
              </Panel>
            </Section>
            {d.matrix && (
              <Section title="Matrix" sub={`${d.metric} per fabricator and month`}>
                <Panel flush>
                  <DataTable table={d.matrix.table} name="fabricators_matrix" maxRows={12} />
                </Panel>
              </Section>
            )}
          </>
        );
      }}
    </Screen>
  );
}
