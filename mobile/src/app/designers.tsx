/* Designers: who designs the most volume, new vs repeat, in which categories. */
import { View } from "react-native";
import { Bars, StackedList } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { KpiGrid, Panel, Section } from "../components/ui";
import { fmtInt, titleCase } from "../lib/format";
import { useDashboard } from "../lib/query";
import type { DesignerData } from "../lib/types";

const KEYS = ["month", "designer", "order_type"];
const GROUPS = [
  { key: "designer", label: "Designer" },
  { key: "order_type", label: "Order type", raw: true },
];

export default function Designers() {
  const f = useFilters(KEYS);
  const q = useDashboard<DesignerData>("/designer", f.values);
  return (
    <Screen
      title="Designers"
      inStack
      q={q}
      lede={(d) => {
        const top = d.kpis.find((k) => k.id === "top");
        const qty = Number(d.kpis.find((k) => k.id === "qty")?.value) || 0;
        if (!top || top.value === "—" || top.value === null) return "No orders for the selected filters.";
        return (
          <>
            <Em>{titleCase(String(top.value))}</Em> leads with {top.hint} of {fmtInt(qty)} pcs ordered.
          </>
        );
      }}
      filters={(d) => (
        <>
          <MonthChips months={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
          <View style={{ flexDirection: "row" }}>
            <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
          </View>
        </>
      )}
    >
      {(d) => (
        <>
          <KpiGrid kpis={d.kpis} lead={["qty"]} />
          <Section title="Volume by designer" sub="New and repeat pcs">
            <Panel title="New and repeat pcs">
              <StackedList data={d.charts.new_vs_repeat} unit="pcs" max={12} />
            </Panel>
            <Panel title="Designer table" flush>
              <DataTable table={d.tables.designers} name="designers_designers" maxRows={12} />
            </Panel>
          </Section>
          <Section title="Month by month" sub="Pcs ordered">
            <Panel title="Order pcs by month" sub="Tap a month for figures">
              <Bars data={d.charts.monthly_trend} unit="pcs" />
            </Panel>
          </Section>
          <Section title="Categories" sub="Pcs per designer and category">
            <Panel flush>
              <DataTable table={d.tables.categories} name="designers_categories" maxRows={12} />
            </Panel>
          </Section>
        </>
      )}
    </Screen>
  );
}
