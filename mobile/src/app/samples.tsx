/* Samples: how many samples are approved, and per designer and vendor. */
import { View } from "react-native";
import { Bars, Split, StackedList } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section } from "../components/ui";
import { fmtInt } from "../lib/format";
import { useDashboard } from "../lib/query";
import type { SamplesData } from "../lib/types";

const KEYS = ["month", "designer", "status", "vendor"];
const GROUPS = [
  { key: "designer", label: "Designer" },
  { key: "vendor", label: "Vendor" },
  { key: "status", label: "Status", raw: true },
];

export default function Samples() {
  const f = useFilters(KEYS);
  const q = useDashboard<SamplesData>("/samples", f.values);
  return (
    <Screen
      title="Samples"
      inStack
      q={q}
      lede={(d) => {
        if (d.empty) return null;
        const k = Object.fromEntries(d.kpis.map((x) => [x.id, Number(x.value) || 0]));
        return (
          <>
            <Em>{k.approval_pct.toFixed(1)}% approved</Em> of {fmtInt(k.total)} samples; <Em bad={k.rejected > 0}>{fmtInt(k.rejected)} rejected</Em>, {fmtInt(k.open)} still on hold or in
            process.
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
        if (d.empty) return <><Notices items={d.notices} /><Empty title="No sample data" /></>;
        return (
          <>
            <Notices items={d.notices} />
            <View style={{ marginTop: d.notices?.length ? 12 : 0 }}>
              <KpiGrid kpis={d.kpis} lead={["approval_pct"]} />
            </View>
            <Section title="Status" sub="By process month">
              <Panel title="Overall status" sub="Pcs">
                <Split items={d.charts.status_share} unit="pcs" />
              </Panel>
              <Panel title="Status by month" sub="Pcs · tap a month for figures">
                <Bars data={d.charts.monthly_status} unit="pcs" stacked />
              </Panel>
              <Panel title="Monthly table" flush>
                <DataTable table={d.tables.monthly} name="samples_monthly" maxRows={13} titleCaseFirst={false} />
              </Panel>
            </Section>
            <Section title="Designers" sub="Samples per designer">
              <Panel title="Status per designer" sub="Pcs">
                <StackedList data={d.charts.designers} unit="pcs" max={12} />
              </Panel>
              <Panel title="Designer table" flush>
                <DataTable table={d.tables.designers} name="samples_designers" maxRows={12} />
              </Panel>
            </Section>
            <Section title="Vendors" sub="Samples per sampling vendor">
              <Panel title="Status per vendor" sub="Pcs">
                <StackedList data={d.charts.vendors} unit="pcs" max={12} />
              </Panel>
              <Panel title="Vendor table" flush>
                <DataTable table={d.tables.vendors} name="samples_vendors" maxRows={12} />
              </Panel>
            </Section>
          </>
        );
      }}
    </Screen>
  );
}
