/* In/Out Sale: the 2026-27 tab of the IN/OUT/SALE sheet. This year against last year (sale pcs, net sale and its
   running total), the flow order -> production -> incoming -> sale per month, and incoming pcs per fabricator.
   Same API as the web page (GET /api/in-out-sale). */
import { View } from "react-native";
import { Bars, Heatmap } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section } from "../components/ui";
import { fmtInt, inrShort, shortMonth } from "../lib/format";
import { useDashboard } from "../lib/query";
import { useTheme } from "../lib/theme";
import type { InOutSaleData } from "../lib/types";

const KEYS = ["month", "fabricator", "type"];
const GROUPS = [
  { key: "fabricator", label: "Fabricator" },
  { key: "type", label: "Type", raw: true },
];

export default function InOutSale() {
  const c = useTheme();
  const f = useFilters(KEYS);
  const q = useDashboard<InOutSaleData>("/in-out-sale", f.values);
  const flowColors = { "Order pcs": c.seriesPale, "Sent to production": c.seriesRef, "Incoming pcs": c.accent, "Sale pcs": c.pos };
  const stack = [c.accent, c.seriesRef, c.seriesPale, c.pos, c.warn, c.seriesGrey, c.neg];
  return (
    <Screen
      title="In/Out Sale"
      inStack
      q={q}
      lede={(d) => {
        if (d.empty || !d.years) return "No sale data in the sheet yet.";
        const ch = d.summary.sale_change_pct;
        return (
          <>
            <Em>{fmtInt(d.summary.sale_pcs)} pcs</Em> sold, <Em>{inrShort(d.summary.net_sale)}</Em> net sale in {d.summary.months} month{d.summary.months === 1 ? "" : "s"}
            {ch === null ? "." : (
              <>
                ; <Em bad={ch < 0}>{ch >= 0 ? "up" : "down"} {Math.abs(ch).toFixed(1)}%</Em> on {d.years.last} pcs for the same months.
              </>
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
        if (d.empty || !d.years)
          return (
            <>
              <Notices items={d.notices} />
              <Empty title="No sale data yet" text="The 2026-27 tab of the IN/OUT/SALE sheet has no month table." />
            </>
          );
        const { this: ty, last: ly } = d.years;
        const yc = (names: string[]) => ({ [names[0]]: c.accent, [names[1]]: c.seriesPale });
        const fab = d.fabricators;
        const heat = d.charts.fab_heat;
        const months = d.charts.fab_months;
        return (
          <>
            <Notices items={d.notices} />
            <KpiGrid kpis={d.kpis} lead={["sale_pcs"]} />

            <Section title={`${ty} against ${ly}`} sub="Same months of both years · Fabricator and Type filters do not apply">
              <Panel title="Sale pcs by month" sub="Tap a month for figures">
                <Bars data={d.charts.sale_pcs} unit="pcs" colors={yc(d.charts.sale_pcs.series.map((s) => s.name))} />
              </Panel>
              <Panel title="Net sale by month">
                <Bars data={d.charts.net_sale} unit="inr" colors={yc(d.charts.net_sale.series.map((s) => s.name))} />
              </Panel>
              <Panel title="Net sale, running total" sub="Month by month, added up">
                <Bars data={d.charts.cumulative_net} unit="inr" colors={yc(d.charts.cumulative_net.series.map((s) => s.name))} />
              </Panel>
              <Panel title="Month by month" sub="With the change on last year" flush>
                <DataTable table={d.tables.compare} name="in_out_sale_compare" maxRows={14} titleCaseFirst={false} />
              </Panel>
            </Section>

            <Section title="In and out" sub="Orders, sent to production, incoming and sold, per month">
              <Panel title="Order, production, incoming and sale" sub="Pcs · tap a month for figures">
                <Bars data={d.charts.flow} unit="pcs" colors={flowColors} />
              </Panel>
              <Panel title="Flow table" sub="Net per pc = net sale ÷ sale pcs" flush>
                <DataTable table={d.tables.flow} name="in_out_sale_flow" maxRows={14} titleCaseFirst={false} />
              </Panel>
            </Section>

            <Section title="Fabricator-wise incoming" sub={fab.count ? `${fab.count} fabricators · ${fmtInt(fab.incoming ?? 0)} pcs came in` : "Month, Fabricator and Type filters apply"}>
              {fab.count && heat && d.tables.fabricators ? (
                <>
                  {months && (
                    <Panel title="Incoming by month" sub="Top fabricators, stacked">
                      <Bars data={months} unit="pcs" stacked colors={Object.fromEntries(months.series.map((s, i) => [s.name, stack[i % stack.length]]))} />
                    </Panel>
                  )}
                  <Panel title="Incoming pcs, fabricator by month" sub="Darker = more · tap a cell">
                    <Heatmap rows={heat.rows} columns={heat.columns.map(shortMonth)} values={heat.values} />
                  </Panel>
                  <Panel title="Fabricator table" flush>
                    <DataTable table={d.tables.fabricators} name="in_out_sale_fabricators" maxRows={16} />
                  </Panel>
                </>
              ) : (
                <Empty title="No fabricator rows match these filters" />
              )}
            </Section>

            {!!d.checks.length && (
              <Section title="Sheet checks" sub="Places where two tables of the sheet disagree">
                <Notices items={d.checks} />
              </Section>
            )}
          </>
        );
      }}
    </Screen>
  );
}
