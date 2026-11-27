/* Stock Ageing (FIFO): finished-goods pcs from EasyTrade, as on one day's closing. How old the stock is, what it is
   worth at inward cost, which design series hold the old stock, which designs to act on first, and how long stock
   has gone unsold. Same API as the web page (GET /api/stock-ageing). */
import { View } from "react-native";
import { Bars, Heatmap } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, SearchBox, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { UnsoldInsights } from "../components/UnsoldInsights";
import { Empty, Insights, KpiGrid, Notices, Panel, Section } from "../components/ui";
import { fmtInt, inrShort } from "../lib/format";
import { useDashboard } from "../lib/query";
import { useTheme } from "../lib/theme";
import type { Slice, StockAgeingData } from "../lib/types";

const KEYS = ["type", "age", "q"];
const GROUPS = [
  { key: "type", label: "Design series", raw: true },
  { key: "age", label: "Oldest age band", raw: true },
];
const short = (b: string) => b.replace(" days", "").replace("Over ", ">");
const bars = (name: string, slices: Slice[]) => ({ categories: slices.map((x) => short(x.label)), series: [{ name, values: slices.map((x) => x.value) }] });

export default function StockAgeing() {
  const c = useTheme();
  const f = useFilters(KEYS);
  const q = useDashboard<StockAgeingData>("/stock-ageing", f.values);
  return (
    <Screen
      title="Stock Ageing"
      inStack
      q={q}
      lede={(d) => {
        if (d.empty) return "No stock rows in the snapshot.";
        if (d.no_match) return "No design matches these filters.";
        const s = d.summary;
        return (
          <>
            <Em>{fmtInt(s.qty)} pcs</Em> worth <Em>{inrShort(s.value)}</Em> at inward cost; <Em bad>{inrShort(s.old_value)} ({s.old_value_pct.toFixed(0)}%)</Em> has been in stock over 180 days. As on {d.as_on} closing.
          </>
        );
      }}
      filters={(d) =>
        d.empty ? null : (
          <>
            <SearchBox value={f.values.q[0] ?? ""} onChange={(v) => f.set("q", v ? [v] : [])} placeholder="Search design code or description" />
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
              <Empty title="No stock rows" text="The snapshot has no items." />
            </>
          );
        if (d.no_match) return <Empty title="No design matches these filters" />;
        const heat = d.charts.type_age;
        return (
          <>
            <Notices items={d.notices} />
            <View style={{ marginTop: d.notices?.length ? 12 : 0 }}>
              <KpiGrid kpis={d.kpis} lead={["qty"]} />
            </View>

            <Section title="Highlights" sub={`${d.source} · pieces only · FIFO`}>
              <Insights items={d.insights} />
            </Section>

            {d.unsold && <UnsoldInsights u={d.unsold} asOn={d.as_on} />}

            <Section title="Time in warehouse" sub="How much stock sits in each age band">
              <Panel title="Value at cost by age" sub="Tap a band for figures">
                <Bars data={bars("Value", d.charts.value_by_age)} unit="inr" names colors={{ Value: c.accent }} />
              </Panel>
              <Panel title="Pieces by age">
                <Bars data={bars("Pcs", d.charts.qty_by_age)} unit="pcs" names colors={{ Pcs: c.seriesRef }} />
              </Panel>
              <Panel title="Age band summary" flush>
                <DataTable table={d.tables.ages} name="stock_ageing_bands" maxRows={10} titleCaseFirst={false} />
              </Panel>
            </Section>

            <Section title="By design series" sub="Series = the number at the start of the design code">
              <Panel title="Pieces by series and age" sub="Darker = more · tap a cell">
                <Heatmap rows={heat.rows} columns={heat.columns.map(short)} values={heat.values} raw />
              </Panel>
              <Panel title="Series summary" flush>
                <DataTable table={d.tables.types} name="stock_ageing_series" maxRows={16} titleCaseFirst={false} />
              </Panel>
            </Section>

            {!!d.tables.stuck.rows.length && (
              <Section title="Act on these first" sub="The 25 designs with the most value over 180 days old">
                <Panel flush>
                  <DataTable table={d.tables.stuck} name="stock_ageing_old_designs" maxRows={25} titleCaseFirst={false} />
                </Panel>
              </Section>
            )}

            <Section title="All designs" sub="Highest value first">
              <Panel flush>
                <DataTable table={d.tables.designs} name="stock_ageing_designs" maxRows={15} titleCaseFirst={false} />
              </Panel>
            </Section>
          </>
        );
      }}
    </Screen>
  );
}
