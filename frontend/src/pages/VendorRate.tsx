import { useEffect, useState } from "react";
import { useDashboard } from "../api/hooks";
import type { VendorRateData } from "../api/types";
import { Legend } from "../components/charts/common";
import { RateBars } from "../components/charts/RateBars";
import { DataTable } from "../components/DataTable";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, inr } from "../lib/format";
import { PageHead, PageState } from "./common";

/* The Vendor Rate tab of the original Streamlit dashboard, rebuilt here: filters, KPIs, "Compare fabric category"
   with its vendor-wise cheapest-rate chart (★ = Best Price), vendor benchmark, one table per vendor and the master
   rate sheet. Every figure comes from GET /api/vendor-rate (backend/app/dashboards/vendor_rate.py), which reads the
   Rate_Data tab of FABRIC PO 11. */
const KEYS = ["vendor", "fabric", "width", "q"];
const WIDTH_COLORS = ["var(--accent)", "var(--series-ref)", "var(--series-pale)", "var(--warn)"];

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
          const cards = d.vendor_cards ?? [];
          return (
            <>
              <PageHead
                title="Vendor Rate"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(k.vendors.value as number)} vendors</strong>, {fmtInt(k.offerings.value as number)} fabric offerings.
                    {typeof k.lowest44.value === "number" ? <> Lowest 44&quot; rate {inr(k.lowest44.value)} ({k.lowest44.hint}).</> : null}
                    {typeof k.lowest60.value === "number" ? <> Lowest 60&quot; rate {inr(k.lowest60.value)} ({k.lowest60.hint}).</> : null}
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
              <KpiStrip kpis={d.kpis} cols={5} lead={["lowest60"]} />

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

                  <Section title="Vendor benchmark summary" sub="Per-metre rates. Averages cover the 44″ and 60″ columns only; 0 / blank (pending) rates and per-piece items are left out of average, min and max.">
                    <Panel flush>
                      <DataTable table={d.tables.benchmark} name="vendor_rate_benchmark" maxRows={15} titleCaseFirst={false} />
                    </Panel>
                  </Section>

                  <Section title="Vendor rate tables" sub={`One table per vendor, like the blocks of the NEW RATE SHEET · ${cards.length} vendor${cards.length === 1 ? "" : "s"} · all filters apply`}>
                    <div className="grid">
                      {cards.map((c) => (
                        <div className="span-6" key={c.vendor}>
                          <Panel title={c.vendor} sub={`${c.items} item${c.items === 1 ? "" : "s"}${c.pending ? ` · ${c.pending} pending rate${c.pending === 1 ? "" : "s"}` : ""}`} flush>
                            <DataTable table={c.table} name={`vendor_rate_${c.vendor.replace(/\W+/g, "_")}`} maxRows={20} titleCaseFirst={false} />
                          </Panel>
                        </div>
                      ))}
                    </div>
                  </Section>

                  <Section title="Master rate sheet" sub={`${d.tables.master.rows.length} of the sheet's items match the filters`}>
                    <Panel flush>
                      <DataTable table={d.tables.master} name="vendor_rates_filtered" maxRows={20} titleCaseFirst={false} />
                    </Panel>
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
