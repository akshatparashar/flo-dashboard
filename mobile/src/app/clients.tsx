/* Clients: how much clients ordered and how much has been fulfilled. */
import { View } from "react-native";
import { BarList, Bars, Split } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { KpiGrid, Panel, Section } from "../components/ui";
import { fmtInt } from "../lib/format";
import { useDashboard } from "../lib/query";
import type { ClientData } from "../lib/types";

const KEYS = ["month", "client", "order_type", "category"];
const GROUPS = [
  { key: "client", label: "Client" },
  { key: "order_type", label: "Order type", raw: true },
  { key: "category", label: "Category" },
];

export default function Clients() {
  const f = useFilters(KEYS);
  const q = useDashboard<ClientData>("/client", f.values);
  return (
    <Screen
      title="Clients"
      inStack
      q={q}
      lede={(d) => {
        const k = Object.fromEntries(d.kpis.map((x) => [x.id, Number(x.value) || 0]));
        const done = k.received + k.pending;
        const pct = done ? (k.received / done) * 100 : 0;
        return (
          <>
            <Em>{fmtInt(k.qty)} pcs</Em> ordered;{" "}
            {done ? (
              <>
                {pct.toFixed(1)}% of production received, <Em bad={k.pending > 0}>{fmtInt(k.pending)} pcs pending</Em>.
              </>
            ) : (
              "nothing in production yet."
            )}
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
          <Section title="Fulfilment" sub="Received and pending pcs">
            <Panel title="Where production stands" sub="Pcs">
              <Split items={d.charts.fulfilment} unit="pcs" />
            </Panel>
            <Panel title="Order pcs by month">
              <BarList items={d.charts.monthly_share} unit="pcs" max={12} />
            </Panel>
            <Panel title="Fulfilment by month" flush>
              <DataTable table={d.tables.monthly} name="clients_monthly" maxRows={13} titleCaseFirst={false} />
            </Panel>
          </Section>
          <Section title="Categories" sub="Pcs by category and month">
            <Panel title="Category mix by month" sub="Tap a month for figures">
              <Bars data={d.charts.category_by_month} unit="pcs" stacked />
            </Panel>
            <Panel title="Category table" flush>
              <DataTable table={d.tables.categories} name="clients_categories" maxRows={13} titleCaseFirst={false} />
            </Panel>
          </Section>
        </>
      )}
    </Screen>
  );
}
