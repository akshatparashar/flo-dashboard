/* Production: how much is still to come back, who has it, and what is late. */
import { View } from "react-native";
import { BarList, Bars, StackedList } from "../../components/charts";
import { DataTable } from "../../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../../components/Filters";
import { Em, Screen } from "../../components/Screen";
import { KpiGrid, Panel, Section } from "../../components/ui";
import { fmtInt } from "../../lib/format";
import { useDashboard } from "../../lib/query";
import type { ProductionData } from "../../lib/types";

const KEYS = ["month", "fabricator", "status", "category", "designer", "risk"];
const GROUPS = [
  { key: "fabricator", label: "Fabricator" },
  { key: "category", label: "Category" },
  { key: "designer", label: "Designer" },
  { key: "status", label: "Status", raw: true },
  { key: "risk", label: "Delay", single: true, raw: true },
];

export default function Production() {
  const f = useFilters(KEYS);
  const q = useDashboard<ProductionData>("/production", { ...f.values, risk: f.values.risk[0] ?? "" });
  return (
    <Screen
      title="Production"
      q={q}
      lede={(d) => {
        const k = Object.fromEntries(d.kpis.map((x) => [x.id, Number(x.value) || 0]));
        return (
          <>
            <Em>{fmtInt(k.pending)} pcs</Em> still to come back of {fmtInt(k.production)} in production
            {k.overdue_pcs > 0 ? (
              <>
                ; <Em bad>{fmtInt(k.overdue_pcs)} pcs</Em> across {d.summary.overdue_designs} designs are past their date.
              </>
            ) : (
              "; nothing is past its date."
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
          <KpiGrid kpis={d.kpis} lead={["pending"]} />
          <Section title="By category" sub="In production, received and pending pcs">
            <Panel title="Pcs by category" sub="Received and pending; together they make the pcs in production">
              <StackedList data={{ ...d.charts.by_category, series: d.charts.by_category.series.filter((s) => s.name !== "In production") }} unit="pcs" sortBy="Pending" />
            </Panel>
            <Panel title="Category table" flush>
              <DataTable table={d.tables.categories} name="production_categories" />
            </Panel>
          </Section>
          <Section title="Pending with fabricators" sub="Who holds the most pending pcs">
            <Panel title="Pending pcs by fabricator">
              <BarList items={d.charts.pending_share} unit="pcs" tone="neg" />
            </Panel>
            <Panel title="Pending share" flush>
              <DataTable table={d.tables.fabricators} name="production_fabricators" />
            </Panel>
          </Section>
          <Section title="Month by month" sub="By order month">
            <Panel title="Fulfilment by month" sub="Pcs · tap a month for figures">
              <Bars data={d.charts.monthly} unit="pcs" />
            </Panel>
            <Panel title="Monthly table" flush>
              <DataTable table={d.tables.monthly} name="production_monthly" maxRows={13} titleCaseFirst={false} />
            </Panel>
          </Section>
        </>
      )}
    </Screen>
  );
}
