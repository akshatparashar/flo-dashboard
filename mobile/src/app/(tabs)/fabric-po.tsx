/* Fabric PO: which fabric orders are overdue, and which vendors deliver on time. */
import { View } from "react-native";
import { BarList, Bars, Split } from "../../components/charts";
import { DataTable } from "../../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../../components/Filters";
import { Em, Screen } from "../../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section, T } from "../../components/ui";
import { fmtInt } from "../../lib/format";
import { useDashboard } from "../../lib/query";
import type { FabricPoData } from "../../lib/types";

const KEYS = ["month", "vendor", "order_type", "client", "designer", "item", "status"];
const GROUPS = [
  { key: "vendor", label: "Vendor" },
  { key: "order_type", label: "Order type", raw: true },
  { key: "client", label: "Client" },
  { key: "designer", label: "Designer" },
  { key: "item", label: "Item" },
  { key: "status", label: "Status", raw: true },
];

export default function FabricPO() {
  const f = useFilters(KEYS);
  const q = useDashboard<FabricPoData>("/fabric-po", f.values);
  return (
    <Screen
      title="Fabric PO"
      q={q}
      lede={(d) => {
        if (d.empty || d.empty_filtered) return null;
        const k = Object.fromEntries(d.kpis.map((x) => [x.id, x.value]));
        const overdue = Number(k.overdue) || 0;
        return (
          <>
            {overdue > 0 ? <Em bad>{fmtInt(overdue)} POs overdue</Em> : <Em>No PO overdue</Em>}, {fmtInt(Number(k.pending) || 0)} mtr of fabric still to arrive;{" "}
            {(Number(k.ontime_pct) || 0).toFixed(1)}% of received POs came on time.
          </>
        );
      }}
      filters={(d) =>
        d.empty ? null : (
          <>
            <MonthChips months={d.options.month ?? []} value={f.values.month} onChange={(v) => f.set("month", v)} />
            <View style={{ flexDirection: "row" }}>
              <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
            </View>
          </>
        )
      }
    >
      {(d) => {
        if (d.empty) return <><Notices items={d.notices} /><Empty title="No PO data" /></>;
        if (d.empty_filtered) return <><Notices items={d.notices} /><Empty title="No POs match these filters" text="Clear a filter to see more." /></>;
        return (
          <>
            <Notices items={d.notices} />
            <View style={{ marginTop: d.notices?.length ? 12 : 0 }}>
              <KpiGrid kpis={d.kpis.filter((x) => x.id !== "pcs")} lead={["overdue"]} />
            </View>
            {!!d.rule && <T v="small" style={{ marginTop: 10 }}>{d.rule}</T>}
            <Section title="Overdue and delivery" sub="POs not received by their due date">
              <Panel title="Delivery status" sub="Count of POs">
                <Split items={d.charts.timing} unit="POs" />
              </Panel>
              <Panel title="Overdue POs, not yet received" sub={d.overdue_total > 15 ? `Oldest 15 of ${d.overdue_total}` : `${d.overdue_total} POs`} flush>
                {d.overdue_total ? <DataTable table={d.tables.overdue} name="fabric_po_overdue" titleCaseFirst={false} /> : <T style={{ padding: 16 }}>No PO is overdue.</T>}
              </Panel>
            </Section>
            <Section title="Month by month" sub="By order date, in mtr">
              <Panel title="Ordered, received and pending" sub="mtr · tap a month for figures">
                <Bars data={d.charts.monthly} unit="mtr" />
              </Panel>
              <Panel title="Month-wise summary" flush>
                <DataTable table={d.tables.monthly} name="fabric_po_monthly" maxRows={13} titleCaseFirst={false} />
              </Panel>
            </Section>
            <Section title="Vendors" sub="Who delivers, who is late">
              <Panel title="Vendor scorecard" flush>
                <DataTable table={d.tables.vendors} name="fabric_po_vendors" />
              </Panel>
              <Panel title="Share of fabric ordered" sub="mtr">
                <BarList items={d.charts.vendor_share} unit="mtr" />
              </Panel>
            </Section>
            <Section title="All POs" sub="Every PO for the selected filters; tap a column to sort">
              <Panel flush>
                <DataTable table={d.tables.pos} name="fabric_po_pos" maxRows={15} titleCaseFirst={false} />
              </Panel>
            </Section>
          </>
        );
      }}
    </Screen>
  );
}
