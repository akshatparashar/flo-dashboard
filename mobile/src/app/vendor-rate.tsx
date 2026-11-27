/* Vendor Rate: fabric rates from the Rate_Data tab of FABRIC PO 11. Pick a fabric category to see the cheapest rate at
   each width and every vendor's cheapest fabric; the master price table puts fabrics against vendors (★ = best price);
   one vendor's own rate card on request. Same API as the web page (GET /api/vendor-rate). */
import { useState } from "react";
import { View } from "react-native";
import { Bars } from "../components/charts";
import { DataTable } from "../components/DataTable";
import { FilterButton, SearchBox, useFilters } from "../components/Filters";
import { Em, Screen } from "../components/Screen";
import { Empty, KpiGrid, Notices, Panel, Section, Segmented, T } from "../components/ui";
import { fmtInt, inr } from "../lib/format";
import { useDashboard } from "../lib/query";
import { useTheme } from "../lib/theme";
import type { TableData, VendorRateData } from "../lib/types";

const KEYS = ["vendor", "fabric", "width", "q"];
const GROUPS = [
  { key: "vendor", label: "Vendor", raw: true },
  { key: "fabric", label: "Fabric category", raw: true },
  { key: "width", label: "Width", raw: true, single: true },
];

type Grid = { categories: string[]; series: { name: string; values: (number | null)[]; best: boolean[] }[] };

/** Fabric down the side, vendors across, ₹ per mtr; ★ marks the cheapest vendor for that fabric, · = not quoted. */
function masterTable(g: Grid): TableData {
  const vendors = g.series.filter((s) => s.values.some((v) => v !== null));
  return {
    title: null,
    note: `${g.categories.length} fabrics · ${vendors.length} vendors · ★ = best price`,
    columns: [{ key: "fabric", label: "Fabric", format: "text" }, ...vendors.map((s) => ({ key: s.name, label: s.name, format: "text" as const }))],
    rows: g.categories.map((cat, i) => [cat, ...vendors.map((s) => (s.values[i] === null ? "·" : `${s.best[i] ? "★ " : ""}${inr(s.values[i] as number)}`))]),
    meta: g.categories.map(() => ({ kind: null, muted: false })),
    key_col: null,
    sorted: false,
  };
}

export default function VendorRate() {
  const c = useTheme();
  const f = useFilters(KEYS);
  const q = useDashboard<VendorRateData>("/vendor-rate", f.values);
  const [picked, setPicked] = useState<string | null>(null);
  const [width, setWidth] = useState('60"');
  const [vendor, setVendor] = useState("");
  const widthColors = [c.accent, c.seriesRef, c.seriesPale, c.warn];
  return (
    <Screen
      title="Vendor Rate"
      inStack
      q={q}
      lede={(d) => {
        const k = Object.fromEntries(d.kpis.map((x) => [x.id, Number(x.value) || 0]));
        if (d.empty) return "No vendor rates in the sheet yet.";
        return (
          <>
            <Em>{fmtInt(k.vendors)} vendors</Em>, {fmtInt(k.offerings)} fabric offerings.
          </>
        );
      }}
      filters={(d) =>
        d.empty ? null : (
          <>
            <SearchBox value={f.values.q[0] ?? ""} onChange={(v) => f.set("q", v ? [v] : [])} placeholder="Search fabric or vendor, e.g. crepe" />
            <View style={{ flexDirection: "row" }}>
              <FilterButton groups={GROUPS} options={d.options} values={f.values} onApply={f.setAll} />
            </View>
          </>
        )
      }
    >
      {(d) => {
        if (d.empty || !d.compare)
          return (
            <>
              <Notices items={d.notices} />
              <Empty title="No vendor rates" text="The FABRIC PO 11 sheet's Rate_Data tab has no rates yet." />
            </>
          );
        if (d.no_match) return <Empty title="No fabric matches these filters" />;
        const cat = picked && d.compare.data[picked] ? picked : d.compare.default;
        const cmp = d.compare.data[cat];
        const vf = d.vendor_fabric;
        const vfWidth = vf && vf.data[width] ? width : vf?.widths.includes('60"') ? '60"' : (vf?.widths[0] ?? '60"');
        const vfData = vf?.data[vfWidth];
        const tables = d.sheet_tables?.length ? d.sheet_tables : (d.vendor_cards ?? []).map((x) => ({ vendor: x.vendor, items: x.items, table: x.table }));
        const chosen = tables.find((x) => x.vendor === vendor) ?? null;
        const chart = cmp.chart && {
          categories: cmp.chart.vendors,
          series: cmp.chart.series.map((s) => ({ name: s.name, values: s.values.map((v) => v ?? 0) })),
        };
        return (
          <>
            <Notices items={d.notices} />
            <Section title="Compare a fabric" sub="Across every vendor · the Vendor filter does not apply here">
              <Segmented items={d.compare.categories.map((x) => ({ value: x, label: x }))} value={cat} onChange={setPicked} label="Fabric category" />
              {cmp.tiles.length > 0 && (
                <KpiGrid
                  kpis={[
                    ...cmp.tiles.map((t) => ({ id: `c${t.width}`, label: `Cheapest ${t.width}`, value: t.rate, unit: "", format: "inr_full" as const, hint: `${t.vendor} · ${t.fabric}`.slice(0, 60) })),
                    { id: "cv", label: "Vendors offering", value: cmp.vendors, unit: "", format: "int" as const },
                  ]}
                />
              )}
              {chart && (
                <Panel title={`${cat}: cheapest rate per vendor`} sub="₹ per mtr, at every width · tap a vendor for figures">
                  <Bars data={chart} unit="inr" names colors={Object.fromEntries(chart.series.map((s, i) => [s.name, widthColors[i % widthColors.length]]))} />
                </Panel>
              )}
              {cmp.table && (
                <Panel title={`${cat}: cheapest fabric per vendor`} flush>
                  <DataTable table={cmp.table} name={`vendor_rate_compare_${cat.replace(/\W+/g, "_")}`} titleCaseFirst={false} />
                </Panel>
              )}
              {cmp.pieces && (
                <Panel title={`${cat}: per piece rates`} sub="Never mixed with per-metre rates" flush>
                  <DataTable table={cmp.pieces} name={`vendor_rate_pieces_${cat.replace(/\W+/g, "_")}`} titleCaseFirst={false} />
                </Panel>
              )}
              {!cmp.chart && !cmp.pieces && <T v="small">No rate is available for this category yet.</T>}
            </Section>

            {vf && vfData && vf.widths.length > 0 && (
              <Section title="Vendor vs fabric price" sub="Each vendor's cheapest rate for every fabric · Vendor and Fabric filters apply">
                <Segmented items={vf.widths.map((w) => ({ value: w, label: `${w} width` }))} value={vfWidth} onChange={setWidth} label="Width" />
                <Panel title={`${vfWidth}: master price table`} sub="₹ per mtr · ★ = best price · · = not quoted" flush>
                  <DataTable table={masterTable(vfData)} name={`vendor_fabric_prices_${vfWidth.replace(/\W+/g, "")}`} maxRows={20} titleCaseFirst={false} />
                </Panel>
              </Section>
            )}

            {tables.length > 0 && (
              <Section title="Vendor rate cards" sub="NEW RATE SHEET · one vendor's table, exactly as in the sheet">
                <Segmented items={[{ value: "", label: "Choose a vendor" }, ...tables.map((t) => ({ value: t.vendor, label: t.vendor }))]} value={chosen?.vendor ?? ""} onChange={setVendor} label="Vendor" />
                {chosen ? (
                  <Panel title={chosen.vendor} sub={`${chosen.items} item${chosen.items === 1 ? "" : "s"}`} flush>
                    <DataTable table={chosen.table} name={`new_rate_sheet_${chosen.vendor.replace(/\W+/g, "_")}`} maxRows={25} titleCaseFirst={false} />
                  </Panel>
                ) : (
                  <T v="small">Choose a vendor above to see its rate table.</T>
                )}
              </Section>
            )}

            {!!d.checks?.length && (
              <Section title="Sheet checks" sub="Fix these in the rate sheet; this list updates within a minute">
                <Notices items={d.checks} />
              </Section>
            )}
          </>
        );
      }}
    </Screen>
  );
}
