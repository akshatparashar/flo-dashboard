import { useDashboard } from "../api/hooks";
import type { FabricPoData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { colorFor, Legend, TIMING_COLORS } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { BarList, Split } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notice, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["month", "vendor", "order_type", "client", "designer", "item", "status"];

export default function FabricPO() {
  const f = useFilters(KEYS);
  const q = useDashboard<FabricPoData>("/fabric-po", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const filters = (
            <FilterBar active={f.active} onReset={f.reset}>
              <MonthFilter label="Order month" options={d.options.month ?? []} value={f.values.month} onChange={(v) => f.set("month", v)} />
              <MultiSelect label="Vendor" options={d.options.vendor ?? []} value={f.values.vendor} onChange={(v) => f.set("vendor", v)} />
              <MultiSelect label="Order type" options={d.options.order_type ?? []} value={f.values.order_type} onChange={(v) => f.set("order_type", v)} />
              <MultiSelect label="Client" options={d.options.client ?? []} value={f.values.client} onChange={(v) => f.set("client", v)} />
              <MultiSelect label="Designer" options={d.options.designer ?? []} value={f.values.designer} onChange={(v) => f.set("designer", v)} />
              <MultiSelect label="Item" options={d.options.item ?? []} value={f.values.item} onChange={(v) => f.set("item", v)} />
              <MultiSelect label="Status" options={d.options.status ?? []} value={f.values.status} onChange={(v) => f.set("status", v)} pretty={(s) => s} />
            </FilterBar>
          );
          if (d.empty) return <><PageHead title="Fabric PO" meta={d.meta} /><Notices items={d.notices} /><Empty title="No PO data" /></>;
          if (d.empty_filtered) return <><PageHead title="Fabric PO" meta={d.meta} />{filters}<Empty title="No POs match these filters">Clear a filter to see more.</Empty></>;
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x]));
          return (
            <>
              <PageHead
                title="Fabric PO"
                meta={d.meta}
                lede={
                  <>
                    {(k.overdue.value as number) > 0 ? <span className="bad">{fmtInt(k.overdue.value as number)} POs overdue</span> : <strong>No PO overdue</strong>}, {fmtInt(k.pending.value as number)} mtr of fabric still to arrive; {(k.ontime_pct.value as number).toFixed(1)}% of received POs came on time.
                  </>
                }
              />
              {filters}
              <Notice n={{ kind: "info", text: d.rule }} />
              <KpiStrip kpis={d.kpis.filter((x) => x.id !== "pcs")} cols={5} lead={["overdue"]} />

              <Section title="Overdue, not yet received" sub={d.overdue_total > 15 ? `Oldest 15 of ${d.overdue_total}` : undefined}>
                <div className="grid">
                  <div className="span-8">
                    <Panel flush>
                      {d.overdue_total ? <DataTable table={d.tables.overdue} name="fabric_po_overdue" maxRows={15} titleCaseFirst={false} /> : <div className="state">No PO is overdue.</div>}
                    </Panel>
                  </div>
                  <div className="span-4">
                    <Panel title="Delivery status" sub="Count of POs">
                      <Split items={d.charts.timing} unit="POs" colors={TIMING_COLORS} label="POs by delivery status" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Month by month" sub="By order month, metres of fabric">
                <div className="grid">
                  <div className="span-8">
                    <Panel title="Ordered, received and pending" sub="mtr" right={<Legend items={d.charts.monthly.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                      <Bars data={d.charts.monthly} months unit="mtr" label="Fabric ordered, received and pending by month" height={290} />
                    </Panel>
                  </div>
                  <div className="span-4">
                    <Panel title="Order type" sub="Count of POs">
                      <Split items={d.charts.order_type} unit="POs" colors={{ NEW: "var(--accent)", REPEAT: "var(--series-ref)" }} label="POs by order type" />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Month-wise summary" flush>
                      <DataTable table={d.tables.monthly} name="fabric_po_monthly" maxRows={13} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Vendors" sub="Fabric ordered, received and delays per vendor">
                <div className="grid">
                  <div className="span-12">
                    <Panel title="Vendor scorecard" flush>
                      <DataTable table={d.tables.vendors} name="fabric_po_vendor" />
                    </Panel>
                  </div>
                  <div className="span-7">
                    <Panel title="Received and pending" sub="mtr" right={<Legend items={d.charts.vendors.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                      <HBars data={d.charts.vendors} unit="mtr" label="Fabric received and pending per vendor" />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Share of fabric ordered" sub="mtr">
                      <BarList items={d.charts.vendor_share} unit="mtr" label="Share of fabric ordered per vendor" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Every PO" sub="Most days late first">
                <Panel flush>
                  <DataTable table={d.tables.pos} name="fabric_po_all" maxRows={12} titleCaseFirst={false} />
                </Panel>
              </Section>
            </>
          );
        }}
      </PageState>
    </div>
  );
}
