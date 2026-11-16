/* Target & revenue: are we on track for the yearly new-order target, and where does revenue come from? */
import { Image, StyleSheet, Text, View } from "react-native";
import { BarList, Bars, StackedList, TargetBar } from "../../components/charts";
import { DataTable } from "../../components/DataTable";
import { FilterButton, MonthChips, useFilters } from "../../components/Filters";
import { Em, Screen } from "../../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section, T } from "../../components/ui";
import { inr, inrShort, titleCase } from "../../lib/format";
import { useDashboard } from "../../lib/query";
import { font, useTheme } from "../../lib/theme";
import type { RepeatDesign, TargetData } from "../../lib/types";

const KEYS = ["month", "designer", "item", "order_by", "source"];
const GROUPS = [
  { key: "source", label: "Order type", raw: true },
  { key: "designer", label: "Designer" },
  { key: "item", label: "Item" },
  { key: "order_by", label: "Ordered by" },
];

function RepeatRow({ r }: { r: RepeatDesign }) {
  const c = useTheme();
  return (
    <View style={[st.repeat, { borderColor: c.rule }]}>
      {r.image ? (
        <Image source={{ uri: r.image }} style={[st.thumb, { backgroundColor: c.well }]} accessibilityLabel={`${r.item} ${r.barcode}`} />
      ) : (
        <View style={[st.thumb, { backgroundColor: c.well, alignItems: "center", justifyContent: "center" }]}>
          <Text style={{ fontFamily: font.display, fontSize: 20, color: c.faint }}>F</Text>
        </View>
      )}
      <View style={{ flex: 1, gap: 2 }}>
        <T v="strong" numberOfLines={1}>{r.barcode}</T>
        <T v="small" numberOfLines={1}>
          {titleCase(r.item)} · {titleCase(r.designer)}
        </T>
        <T v="small" numberOfLines={1}>Last repeat {r.last}</T>
      </View>
      <View style={{ alignItems: "flex-end", gap: 2 }}>
        <T v="strong">{r.orders}×</T>
        <T v="small">{r.pcs.toLocaleString("en-US")} pcs</T>
        <T v="small">{inr(r.revenue)}</T>
      </View>
    </View>
  );
}

export default function Target() {
  const f = useFilters(KEYS);
  const q = useDashboard<TargetData>("/target", f.values);
  return (
    <Screen
      title="Target & revenue"
      q={q}
      lede={(d) => {
        if (d.empty) return null;
        const t = d.tracker;
        const ahead = t.schedule.gap >= 0;
        return (
          <>
            <Em>{inrShort(t.gauge.achieved)}</Em> of the {inrShort(t.gauge.target)} new-order target ({t.gauge.value.toFixed(1)}%),{" "}
            {t.schedule.elapsed.length ? <Em bad={!ahead}>{ahead ? "ahead of" : "behind"} schedule by {inrShort(Math.abs(t.schedule.gap))}</Em> : "before the year starts"}.
          </>
        );
      }}
      filters={(d) => (d.empty ? null : <MonthChips months={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />)}
    >
      {(d) => {
        if (d.empty) return <><Notices items={d.notices} /><Empty title="No order data" /></>;
        const t = d.tracker;
        const fl = d.filtered;
        const fy = t.monthly.categories.slice(0, 12);
        const monthly = {
          categories: fy,
          series: [
            { name: "Achieved", values: t.monthly.achieved.slice(0, 12) },
            { name: "Target", values: t.monthly.target.slice(0, 12) },
          ],
        };
        return (
          <>
            <Notices items={d.notices} />
            <Section title="New-order target" sub={`${d.meta.fy} · yearly target ₹${d.annual_target_cr} Cr, split equally by month`}>
              <Panel title="Year so far">
                <TargetBar achieved={t.gauge.achieved} target={t.gauge.target} scheduled={t.schedule.scheduled} />
              </Panel>
              <KpiGrid kpis={t.kpis} lead={["achieved"]} />
              <Panel title="Achieved vs target by month" sub="₹ · tap a month for figures">
                <Bars data={monthly} unit="inr" />
              </Panel>
              <Notices items={t.notices} />
              <Panel title="Target vs achieved by month" sub="Achieved %: green 100%+, amber 75–99%, red under 75%" flush>
                <DataTable table={t.table} maxRows={13} titleCaseFirst={false} />
              </Panel>
            </Section>

            <Section title="Revenue" sub="New and repeat orders, pcs × rate">
              <View style={{ flexDirection: "row" }}>
                <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
              </View>
              {fl.empty ? (
                <Notices items={fl.notices} />
              ) : (
                <>
                  <KpiGrid kpis={fl.kpis} lead={["revenue"]} />
                  <Panel title="Revenue by month" sub="New and repeat · tap a month for figures">
                    <Bars data={fl.charts.monthly} unit="inr" stacked />
                  </Panel>
                  <Panel title="By designer" sub="New and repeat revenue">
                    <StackedList data={fl.charts.designers} unit="inr" />
                  </Panel>
                  <Panel title="Designer revenue" flush>
                    <DataTable table={fl.tables.designers} />
                  </Panel>
                  <Panel title="By item">
                    <BarList items={fl.charts.items} unit="inr" />
                  </Panel>
                  <Panel title="By who ordered">
                    <BarList items={fl.charts.order_by} unit="inr" />
                  </Panel>
                  <Panel title="Revenue by month" flush>
                    <DataTable table={fl.tables.monthly} maxRows={13} titleCaseFirst={false} />
                  </Panel>
                  <Panel title="Designs that sell again" sub="Top 15 by number of repeat orders" flush>
                    {fl.top_repeat.length ? (
                      fl.top_repeat.map((r) => <RepeatRow key={r.barcode} r={r} />)
                    ) : (
                      <T style={{ padding: 16 }}>No repeat orders in this selection.</T>
                    )}
                  </Panel>
                </>
              )}
            </Section>
          </>
        );
      }}
    </Screen>
  );
}

const st = StyleSheet.create({
  repeat: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth },
  thumb: { width: 48, height: 48, borderRadius: 10 },
});
