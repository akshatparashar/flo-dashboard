import { useEffect, useState } from "react";
import { useDashboard } from "../api/hooks";
import type { VendorRateData } from "../api/types";
import { Legend } from "../components/charts/common";
import { RateBars } from "../components/charts/RateBars";
import { VendorDots } from "../components/charts/VendorDots";
import { DataTable } from "../components/DataTable";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

/* The Vendor Rate tab of the original Streamlit dashboard, rebuilt here: filters, KPIs, "Compare fabric category"
   with its vendor-wise cheapest-rate chart (★ = Best Price), vendor benchmark, one table per vendor and the master
   rate sheet. Every figure comes from GET /api/vendor-rate (backend/app/dashboards/vendor_rate.py), which reads the
   Rate_Data tab of FABRIC PO 11. */
const KEYS = ["vendor", "fabric", "width", "q"];
const WIDTH_COLORS = ["var(--accent)", "var(--series-ref)", "var(--series-pale)", "var(--warn)"];
/* one colour per vendor (11 on the sheet), distinguishable in light and dark */
const VENDOR_COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#475569", "#92400e", "#0d9488", "#a16207"];

/** Search box: the URL (and so the API) is only updated once typing pauses. */
function Search({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (text === value) return;
    const id = setTimeout(() => onChange(text), 350);
    return () => clearTimeout(id);
  }, [text, value, onChange]);
  return <input className="field vr-search" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search fabric / vendor, e.g. crepe, RV" aria-label="Search fabric or vendor" />;
}

export default function VendorRate() {
  const f = useFilters(KEYS);
  const q = useDashboard<VendorRateData>("/vendor-rate", f.values);
  const [picked, setPicked] = useState<string | null>(null);
  const [width, setWidth] = useState<string>('60"');
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty || !d.tables || !d.compare)
            return (
              <>
                <PageHead title="Vendor Rate" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No vendor rates">The FABRIC PO 11 sheet's Rate_Data tab has no rates yet.</Empty>
              </>
            );
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x]));
          const cmpCat = picked && d.compare.data[picked] ? picked : d.compare.default;
          const cmp = d.compare.data[cmpCat];
          const vf = d.vendor_fabric;
          const vfWidth = vf && vf.data[width] ? width : vf?.widths.includes('60"') ? '60"' : (vf?.widths[0] ?? '60"');
          const vfData = vf?.data[vfWidth] ?? { categories: [], series: [] };
          const tables = d.sheet_tables?.length ? d.sheet_tables : (d.vendor_cards ?? []).map((c) => ({ vendor: c.vendor, items: c.items, table: c.table }));
          return (
            <>
              <PageHead
                title="Vendor Rate"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(k.vendors.value as number)} vendors</strong>, {fmtInt(k.offerings.value as number)} fabric offerings.
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MultiSelect label="Vendor" options={d.options.vendor} value={f.values.vendor} onChange={(v) => f.set("vendor", v)} pretty={(x) => x} />
                <MultiSelect label="Fabric category" options={d.options.fabric} value={f.values.fabric} onChange={(v) => f.set("fabric", v)} pretty={(x) => x} />
                <MultiSelect label="Width" options={d.options.width} value={f.values.width} onChange={(v) => f.set("width", v.slice(-1))} pretty={(x) => x} single />
                <Search value={f.values.q[0] ?? ""} onChange={(v) => f.set("q", v ? [v] : [])} />
              </FilterBar>
              <Notices items={d.notices} />

              {d.no_match ? (
                <Empty title="No fabric matches the selected filters" />
              ) : (
                <>
                  <Section title="Side-by-side fabric price comparison" sub="Always across every vendor; the Vendor filter above does not apply here">
                    <div className="vr-pick">
                      <label htmlFor="vr-cmp">Compare fabric category</label>
                      <select id="vr-cmp" className="field" value={cmpCat} onChange={(e) => setPicked(e.target.value)}>
                        {d.compare.categories.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                    {cmp.tiles.length > 0 && (
                      <KpiStrip
                        cols={cmp.tiles.length + 1}
                        kpis={[
                          ...cmp.tiles.map((t) => ({ id: `c${t.width}`, label: `Cheapest ${t.width}`, value: t.rate, unit: "", format: "inr_full" as const, hint: `${t.vendor} · ${t.fabric}`.slice(0, 60) })),
                          { id: "cv", label: "Vendors offering", value: cmp.vendors, unit: "", format: "int" as const },
                        ]}
                      />
                    )}
                    <div className="grid" style={{ marginTop: 16 }}>
                      {cmp.chart && (
                        <div className="span-12">
                          <Panel
                            title={`${cmpCat}: vendor-wise cheapest rate (★ = Best Price)`}
                            sub="₹ per mtr · each vendor's cheapest fabric at every width"
                            right={<Legend items={cmp.chart.series.map((s, i) => ({ name: s.name, color: WIDTH_COLORS[i % WIDTH_COLORS.length] }))} />}
                          >
                            <RateBars vendors={cmp.chart.vendors} series={cmp.chart.series} colors={WIDTH_COLORS} label={`${cmpCat}: cheapest rate per vendor and width`} />
                          </Panel>
                        </div>
                      )}
                      {cmp.table && (
                        <div className="span-12">
                          <Panel title={`${cmpCat}: cheapest fabric per vendor`} flush>
                            <DataTable table={cmp.table} name={`vendor_rate_compare_${cmpCat}`} titleCaseFirst={false} />
                          </Panel>
                        </div>
                      )}
                      {cmp.pieces && (
                        <div className="span-12">
                          <Panel title={`${cmpCat}: per piece rates`} sub="Shown apart: never mixed with per-metre rates" flush>
                            <DataTable table={cmp.pieces} name={`vendor_rate_pieces_${cmpCat}`} titleCaseFirst={false} />
                          </Panel>
                        </div>
                      )}
                      {!cmp.chart && !cmp.pieces && <div className="span-12 state">No rate is available for this category yet.</div>}
                    </div>
                  </Section>

                  {vf && vf.widths.length > 0 && (
                    <Section title="Vendor vs fabric price" sub="Each dot is one vendor's cheapest rate for that fabric · the ringed ★ dot is the best price · hover a dot for the exact rate, or a vendor name to follow it · the Vendor and Fabric filters apply">
                      <Panel
                        title={`${vfWidth}: vendor-wise rate by fabric (★ = Best Price)`}
                        sub="₹ per mtr · the band spans the cheapest to the dearest vendor"
                        right={
                          <div className="seg" role="group" aria-label="Width">
                            {vf.widths.map((w) => (
                              <button key={w} type="button" aria-pressed={vfWidth === w} onClick={() => setWidth(w)}>
                                {w}
                              </button>
                            ))}
                          </div>
                        }
                      >
                        <VendorDots categories={vfData.categories} series={vfData.series} colors={VENDOR_COLORS} label={`${vfWidth} rate by fabric category and vendor`} />
                      </Panel>
                    </Section>
                  )}

                  <Section
                    title="NEW RATE SHEET: vendor tables"
                    sub={`The rate cards exactly as in the sheet, one table per vendor · ${tables.length} vendor${tables.length === 1 ? "" : "s"} · the Vendor filter applies`}
                  >
                    <div className="grid">
                      {tables.map((c) => (
                        <div className="span-6" key={c.vendor}>
                          <Panel title={c.vendor} sub={`${c.items} item${c.items === 1 ? "" : "s"}`} flush>
                            <DataTable table={c.table} name={`new_rate_sheet_${c.vendor.replace(/\W+/g, "_")}`} maxRows={20} titleCaseFirst={false} csv />
                          </Panel>
                        </div>
                      ))}
                    </div>
                  </Section>
                </>
              )}

              {!!d.checks?.length && (
                <Section title="Sheet checks" sub="Things in the rate sheet that look wrong or are missing. Fix them in the sheet; this list updates within a minute.">
                  <div data-reveal>
                    <Notices items={d.checks} />
                  </div>
                </Section>
              )}
            </>
          );
        }}
      </PageState>
    </div>
  );
}
