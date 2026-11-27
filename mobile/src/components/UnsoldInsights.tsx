/* Unsold Inventory Insights (Stock Ageing screen). Two measures kept apart: how long each remaining piece has been in
   stock (piece age) and how long a design's stock has sat without a sale. Tap a card to list those designs. Figures
   come from the `unsold` block of GET /api/stock-ageing, which follows the screen's filters. */
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { fmtInt, inrShort } from "../lib/format";
import { font, useTheme } from "../lib/theme";
import type { TableData, UnsoldData } from "../lib/types";
import { Bars, Heatmap, Split } from "./charts";
import { DataTable } from "./DataTable";
import { Insights, Panel, Section, Segmented, T } from "./ui";

type Measure = "sale" | "age";
type Pick = 0 | 30 | 90 | 180 | 365 | "never";

/** The rows of the product list that match the chosen measure and threshold. */
function pickRows(table: TableData, measure: Measure, pick: Pick) {
  const at = (name: string) => table.columns.findIndex((c) => c.label === name);
  const days = at("Days without sale");
  const last = at("Last sale");
  const older = typeof pick === "number" && pick > 0 ? at(`Pcs over ${pick}d`) : -1;
  const keep = table.rows
    .map((_, i) => i)
    .filter((i) => {
      const r = table.rows[i];
      if (pick === 0) return true;
      if (pick === "never") return last >= 0 && !r[last];
      if (measure === "sale") return Number(r[days]) > pick;
      return Number(r[older]) > 0;
    });
  const sum = (col: number) => keep.reduce((a, i) => a + (Number(table.rows[i][col]) || 0), 0);
  return {
    table: { ...table, rows: keep.map((i) => table.rows[i]), meta: keep.map((i) => table.meta[i]) } as TableData,
    designs: keep.length,
    pcs: measure === "age" && older >= 0 ? sum(older) : sum(at("Pcs")),
    value: measure === "age" && older >= 0 ? null : sum(at("Value")),
  };
}

const short = (b: string) => b.replace(" days", "").replace("Over ", ">");

export function UnsoldInsights({ u, asOn }: { u: UnsoldData; asOn: string }) {
  const c = useTheme();
  const [measure, setMeasure] = useState<Measure>("sale");
  const [pick, setPick] = useState<Pick>(90);
  const m: Measure = u.has_sales ? measure : "age";
  const p: Pick = pick === "never" && m !== "sale" ? 0 : pick;
  const list = useMemo(() => pickRows(u.table, m, p), [u.table, m, p]);
  const picks: Pick[] = m === "sale" ? [0, 30, 90, 180, 365, "never"] : [0, 30, 90, 180, 365];
  const pickLabel = (x: Pick) => (x === 0 ? "All" : x === "never" ? "Never sold" : `Over ${x} days`);
  const steps = [c.pos, c.accent, c.seriesRef, c.warn, c.neg];
  const bandColors: Record<string, string> = {
    "0-30 days": c.pos,
    "31-90 days": c.accent,
    "91-180 days": c.seriesRef,
    "181-365 days": c.warn,
    "Over 365 days": c.neg,
    Unknown: c.seriesGrey,
  };

  return (
    <Section title="Unsold inventory" sub={`How long stock has been waiting, as on ${asOn} · follows the filters`}>
      <View style={{ gap: 10 }}>
        {u.cards.map((card, i) => {
          const on = p === card.days;
          return (
            <Pressable
              key={card.days}
              onPress={() => setPick(on ? 0 : (card.days as Pick))}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={({ pressed }) => [st.card, { backgroundColor: c.sheet, borderColor: on ? c.ink : c.sheetEdge, borderLeftColor: steps[i % steps.length], opacity: pressed ? 0.85 : 1 }]}
            >
              <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8 }}>
                <T v="title" style={{ flex: 1 }}>Over {card.days} days</T>
                <Text style={{ fontFamily: font.uiBold, fontSize: 20, color: c.ink, fontVariant: ["tabular-nums"] }}>
                  {fmtInt(card.pcs)} <Text style={{ fontFamily: font.ui, fontSize: 13, color: c.muted }}>pcs</Text>
                </Text>
              </View>
              <T v="small">
                {inrShort(card.value)} at cost · {card.pcs_pct.toFixed(1)}% of pieces in stock that long
              </T>
              <View style={[st.meter, { backgroundColor: c.well }]}>
                <View style={{ width: `${Math.min(100, card.pcs_pct)}%`, height: "100%", borderRadius: 3, backgroundColor: steps[i % steps.length] }} />
              </View>
              {card.no_sale ? (
                <T v="small" style={{ color: c.ink2 }}>
                  <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{fmtInt(card.no_sale.designs)}</Text> designs with no sale that long · {fmtInt(card.no_sale.pcs)} pcs · {inrShort(card.no_sale.value)}
                </T>
              ) : (
                <T v="small">Sales history is not in this snapshot</T>
              )}
            </Pressable>
          );
        })}
        <T v="small">Each “over” figure includes the longer ones, so do not add the cards together.</T>
        {u.never && u.never.designs > 0 && (
          <Pressable onPress={() => { setMeasure("sale"); setPick("never"); }} accessibilityRole="button" hitSlop={6}>
            <Text style={{ fontFamily: font.uiBold, fontSize: 13.5, color: c.accent }}>
              {fmtInt(u.never.designs)} designs have no sale on record ({fmtInt(u.never.pcs)} pcs, {inrShort(u.never.value)}) →
            </Text>
          </Pressable>
        )}
      </View>

      <Insights items={u.insights} />

      <Panel title="Value waiting, by threshold" sub="Cost of pieces older than, and of designs not sold for">
        <Bars data={{ ...u.compare, categories: u.cards.map((x) => `>${x.days}d`) }} unit="inr" names colors={{ "Pieces older than": c.seriesRef, "Designs with no sale for": c.neg }} />
      </Panel>
      {u.has_sales && (
        <Panel title="Stock value by time without a sale" sub="Every design counted once">
          <Split items={u.bands.map((b) => ({ label: b.label, value: b.value }))} unit="inr" colors={bandColors} raw />
        </Panel>
      )}
      {u.heat && (
        <Panel title="Pieces by series and time without a sale" sub="Darker = more · tap a cell">
          <Heatmap rows={u.heat.rows} columns={u.heat.columns.map(short)} values={u.heat.values} raw />
        </Panel>
      )}

      <Panel title="Explore the products" sub={u.has_sales ? "Longest without a sale first · blank last sale = none since April 2023" : "Oldest stock first"} flush>
        <View style={{ gap: 8, paddingHorizontal: 16, paddingBottom: 10 }}>
          {u.has_sales && (
            <Segmented items={[{ value: "sale" as Measure, label: "No sale for" }, { value: "age" as Measure, label: "Piece age" }]} value={m} onChange={setMeasure} label="Measure" />
          )}
          <Segmented items={picks.map((x) => ({ value: x, label: pickLabel(x) }))} value={p} onChange={setPick} label="Threshold" />
          <T v="small" accessibilityLiveRegion="polite">
            <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{fmtInt(list.designs)}</Text> designs · <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{fmtInt(list.pcs)}</Text> pcs
            {list.value !== null && <> · <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{inrShort(list.value)}</Text></>}
          </T>
        </View>
        {list.designs ? (
          <DataTable table={list.table} name="unsold_inventory" maxRows={15} titleCaseFirst={false} />
        ) : (
          <T style={{ padding: 16 }}>No design matches this choice.</T>
        )}
      </Panel>
    </Section>
  );
}

const st = StyleSheet.create({
  card: { borderRadius: 14, borderWidth: 1, borderLeftWidth: 4, padding: 14, gap: 6 },
  meter: { height: 6, borderRadius: 3, overflow: "hidden" },
});
