import { useState } from "react";
import { useDashboard } from "../api/hooks";
import type { VendorRateData } from "../api/types";
import { BarList, Heatmap } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, inr } from "../lib/format";
import { PageHead, PageState } from "./common";

/* Fabric rates per vendor from FABRIC PO 11 (Rate_Data, cross-checked against the NEW RATE SHEET). Every figure
   comes from GET /api/vendor-rate (backend/app/dashboards/vendor_rate.py). */
const KEYS = ["vendor", "fabric"];

export default function VendorRate() {
  const f = useFilters(KEYS);
  const q = useDashboard<VendorRateData>("/vendor-rate", f.values);
  const [width, setWidth] = useState<"60" | "44">("60");
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty || !d.tables || !d.charts)
            return (
              <>
                <PageHead title="Vendor Rate" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No vendor rates">The FABRIC PO 11 sheet's Rate_Data tab has no rates yet.</Empty>
              </>
            );
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x]));
          const t = d.tables;
          const c = d.charts;
          const m = width === "60" ? c.matrix60 : c.matrix44;
          const avg60 = k.avg60?.value as number | null;
          const avg44 = k.avg44?.value as number | null;
          return (
            <>
              <PageHead
                title="Vendor Rate"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(k.vendors?.value as number)} vendors</strong>, {fmtInt(k.offerings?.value as number)} fabric offerings.
                    {avg60 ? <> Average {inr(avg60)} per mtr at 60"</> : null}
                    {avg44 ? <> and {inr(avg44)} at 44"</> : null}.
                    {k.cheapest_vendor && k.cheapest_vendor.value !== "—" ? <> Lowest 60" average: <strong>{k.cheapest_vendor.value}</strong>.</> : null}
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MultiSelect label="Vendor" options={d.options.vendor} value={f.values.vendor} onChange={(v) => f.set("vendor", v)} pretty={(x) => x} />
                <MultiSelect label="Fabric" options={d.options.fabric} value={f.values.fabric} onChange={(v) => f.set("fabric", v)} pretty={(x) => x} />
              </FilterBar>
              <Notices items={d.notices} />
              <KpiStrip kpis={d.kpis} cols={4} lead={["avg60"]} />

              <Section title="Cheapest vendor for each fabric" sub="Lowest 60&quot; and 44&quot; rate per fabric category, and how far apart the vendors are. Every vendor is compared; the fabric filter applies.">
                <Panel flush>
                  <DataTable table={t.categories} name="vendor_rate_by_fabric" maxRows={15} titleCaseFirst={false} />
                </Panel>
              </Section>

              <Section
                title="Price map"
                sub="Average rate per fabric category and vendor, ₹ per mtr · darker = dearer · 0 = not quoted at this width"
                right={
                  <div className="seg" role="group" aria-label="Width">
                    {(["60", "44"] as const).map((w) => (
                      <button key={w} type="button" aria-pressed={width === w} onClick={() => setWidth(w)}>
                        {w}" width
                      </button>
                    ))}
                  </div>
                }
              >
                <div className="grid">
                  <div className="span-8">
                    <Panel title={`${width}" rate by fabric and vendor`}>
                      {m.rows.length ? (
                        <div className="vr-heat">
                          <Heatmap rows={m.rows} columns={m.columns} values={m.values} label={`Average ${width} inch rate by fabric category and vendor`} rowLabel={(s) => s} />
                        </div>
                      ) : (
                        <div className="state">No {width}" rates for these filters.</div>
                      )}
                    </Panel>
                  </div>
                  <div className="span-4">
                    <Panel title='Average 60" rate by vendor' sub="₹ per mtr, dearest first">
                      <BarList items={c.vendor_avg} money max={12} share={false} label="Average 60 inch rate per vendor" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Vendor benchmark" sub="Same as the sheet's Vendor Benchmark Summary; 0 and blank rates are left out of the averages">
                <Panel flush>
                  <DataTable table={t.vendors} name="vendor_rate_benchmark" maxRows={15} titleCaseFirst={false} />
                </Panel>
              </Section>

              <Section title="Full rate list" sub="Every fabric each vendor quotes, in sheet order. vs Best % = how much dearer than the cheapest rate for the same fabric and width.">
                <Panel flush>
                  <DataTable table={t.rates} name="vendor_rate_list" maxRows={20} titleCaseFirst={false} />
                </Panel>
              </Section>

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
