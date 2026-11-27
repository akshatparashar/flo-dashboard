/* Clients: how much clients ordered and how much has been fulfilled. */
import { View } from "react-native";
import { BarList, Bars, Split } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { KpiGrid, Notices, Panel, Section } from "../components/ui";
import { useTheme } from "../lib/theme";
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
  const c = useTheme();
  const f = useFilters(KEYS);
  const q = useDashboard<ClientData>("/client", f.values);
  return (
    <Screen
      title="Clients Order Status"
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
          {!!d.charts.client_share?.length && (
            <Section title="Clients" sub="Share of ordered pcs by client">
              <Panel title="Order pcs by client">
                <BarList items={d.charts.client_share} unit="pcs" max={10} />
              </Panel>
            </Section>
          )}
          {d.delivery60 && (
            <Section title="Expected deliveries" sub={`Pending pcs by the 60-day delivery date · red = date already passed (${d.delivery60.today})`}>
              <KpiGrid kpis={d.delivery60.kpis} lead={["total"]} />
              <Panel title="Pcs due to arrive, by month" sub="Tap a month for figures">
                <Bars data={d.delivery60.chart} unit="pcs" stacked colors={{ Overdue: c.neg, "Not yet due": c.seriesRef }} />
              </Panel>
              <Panel title="Month-wise pcs expected" flush>
                <DataTable table={d.delivery60.tables.months} name="clients_delivery60_months" maxRows={14} titleCaseFirst={false} />
              </Panel>
              <Panel title="Client-wise pending and delivery dates" flush>
                <DataTable table={d.delivery60.tables.clients} name="clients_delivery60_clients" maxRows={14} titleCaseFirst={false} />
              </Panel>
            </Section>
          )}
          {(d.fw_orders || d.fw_orders_error) && (
            <Section title="FW ORDER'S" sub="Order, dispatched and pending pcs by month · DASHBOARD tab">
              {d.fw_orders ? (
                <>
                  <Notices items={d.fw_orders.checks} />
                  <Panel
                    title="Orders vs dispatched"
                    sub={`${fmtInt(d.fw_orders.totals.dispatched)} of ${fmtInt(d.fw_orders.totals.order)} pcs dispatched (${d.fw_orders.totals.dispatched_pct.toFixed(1)}%)`}
                  >
                    <Bars data={d.fw_orders.chart} unit="pcs" colors={{ "Order pcs": c.seriesRef, "Dispatched pcs": c.accent, "Pending pcs": c.neg }} />
                  </Panel>
                  <Panel title="FW ORDER'S" flush>
                    <DataTable table={d.fw_orders.table} name="fw_orders" maxRows={13} titleCaseFirst={false} />
                  </Panel>
                </>
              ) : (
                <Notices items={[{ kind: "warning", text: `FW ORDER'S could not be read: ${d.fw_orders_error}` }]} />
              )}
            </Section>
          )}
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
