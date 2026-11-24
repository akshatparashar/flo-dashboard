import { useDashboard } from "../api/hooks";
import type { InOutSaleData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Legend } from "../components/charts/common";
import { Heatmap } from "../components/charts/Lists";
import { RunningTotal } from "../components/charts/RunningTotal";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, inrShort, shortMonth } from "../lib/format";
import { PageHead, PageState } from "./common";

/* In / Out Sale: the "2026-27" tab of the IN/OUT/SALE sheet. This year against last year (sale pcs, sale amount,
   net sale), the flow order -> production -> incoming -> sale per month, and fabricator-wise incoming pieces with
   the incoming pcs per fabricator. Every figure comes from GET /api/in-out-sale (backend/app/dashboards/in_out_sale.py). */
const KEYS = ["month", "fabricator", "type"];
const THIS = "var(--accent)";
const LAST = "var(--series-pale)";
const FLOW_COLORS = { "Order pcs": "var(--series-pale)", "Sent to production": "var(--series-ref)", "Incoming pcs": "var(--accent)", "Sale pcs": "var(--pos)" };
const STACK = ["var(--accent)", "var(--series-ref)", "var(--series-pale)", "var(--pos)", "var(--warn)", "var(--series-grey)", "var(--neg)", "var(--accent-strong)"];

export default function InOutSale() {
  const f = useFilters(KEYS);
  const q = useDashboard<InOutSaleData>("/in-out-sale", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty || !d.years)
            return (
              <>
                <PageHead title="In/Out Sale" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No sale data yet">The 2026-27 tab of the IN/OUT/SALE sheet has no month table.</Empty>
              </>
            );
          const { this: ty, last: ly } = d.years;
          const sale = d.charts.sale_pcs.series;
          const net = d.charts.net_sale.series;
          const yc = { [sale[0].name]: THIS, [sale[1].name]: LAST };
          const nc = { [net[0].name]: THIS, [net[1].name]: LAST };
          const ch = d.summary.sale_change_pct;
          const fab = d.fabricators;
          const heat = d.charts.fab_heat;
          const stackColors = Object.fromEntries((d.charts.fab_months?.series ?? []).map((s, i) => [s.name, STACK[i % STACK.length]]));
          return (
            <>
              <PageHead
                title="In/Out Sale"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(d.summary.sale_pcs)} pcs</strong> sold, <strong>{inrShort(d.summary.net_sale)}</strong> net sale in {d.summary.months} month{d.summary.months === 1 ? "" : "s"}
                    {ch === null ? (
                      "."
                    ) : (
                      <>
                        ; <span className={ch >= 0 ? "good" : "bad"}>{ch >= 0 ? "up" : "down"} {Math.abs(ch).toFixed(1)}%</span> on {ly} pcs for the same months.
                      </>
                    )}
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <MultiSelect label="Fabricator" options={d.options.fabricator} value={f.values.fabricator} onChange={(v) => f.set("fabricator", v)} />
                <MultiSelect label="Type" options={d.options.type} value={f.values.type} onChange={(v) => f.set("type", v)} pretty={(x) => x} />
              </FilterBar>
              <KpiStrip kpis={d.kpis} cols={4} lead={["sale_pcs"]} />

              <Section title={`${ty} against ${ly}`} sub="Same months of both years · the Fabricator and Type filters do not apply here">
                <div className="grid">
                  <div className="span-6">
                    <Panel title="Sale pcs by month" right={<Legend items={[{ name: ty, color: THIS }, { name: ly, color: LAST }]} />}>
                      <Bars data={d.charts.sale_pcs} months unit="pcs" label={`Sale pcs by month, ${ty} against ${ly}`} colors={yc} height={290} />
                    </Panel>
                  </div>
                  <div className="span-6">
                    <Panel title="Net sale by month" right={<Legend items={[{ name: ty, color: THIS }, { name: ly, color: LAST }]} />}>
                      <Bars data={d.charts.net_sale} months money label={`Net sale by month, ${ty} against ${ly}`} colors={nc} height={290} />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Net sale, running total" sub="Month by month, added up · hover a month to compare the two years">
                      <RunningTotal
                        categories={d.charts.cumulative_net.categories}
                        thisYear={{ name: ty, values: d.charts.cumulative_net.series[0].values }}
                        lastYear={{ name: ly, values: d.charts.cumulative_net.series[1].values }}
                        label="Running net sale, this year against last year"
                        height={320}
                      />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Month by month" sub="Sale pcs and net sale, with the change on last year" flush>
                      <DataTable table={d.tables.compare} name="in_out_sale_compare" maxRows={14} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="In and out" sub="Orders, pieces sent to production, pieces coming in and pieces sold, per month">
                <div className="grid">
                  <div className="span-12">
                    <Panel title="Order, production, incoming and sale" sub="Pcs" right={<Legend items={d.charts.flow.series.map((s) => ({ name: s.name, color: FLOW_COLORS[s.name as keyof typeof FLOW_COLORS] }))} />}>
                      <Bars data={d.charts.flow} months unit="pcs" label="Order, production, incoming and sale pcs by month" colors={FLOW_COLORS} height={300} />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Flow table" sub="Net per pc = net sale ÷ sale pcs · Deducted = what the sheet takes off the sale amount" flush>
                      <DataTable table={d.tables.flow} name="in_out_sale_flow" maxRows={14} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section
                title="Fabricator-wise incoming"
                sub={fab.count ? `${fab.count} fabricators · ${fmtInt(fab.incoming ?? 0)} pcs came in · the month, Fabricator and Type filters apply` : "The month, Fabricator and Type filters apply"}
              >
                {fab.count && heat && d.tables.fabricators ? (
                  <div className="grid">
                    {d.charts.fab_months && (
                      <div className="span-12">
                        <Panel title="Incoming by month" sub="Top fabricators, stacked" right={<Legend items={d.charts.fab_months.series.map((s) => ({ name: s.name, color: stackColors[s.name] }))} />}>
                          <Bars data={d.charts.fab_months} stacked months unit="pcs" label="Incoming pcs by month and fabricator" colors={stackColors} height={270} />
                        </Panel>
                      </div>
                    )}
                    <div className="span-12">
                      <Panel title="Incoming pcs, fabricator by month" sub="Darker = more">
                        <Heatmap rows={heat.rows} columns={heat.columns.map(shortMonth)} values={heat.values} label="Incoming pcs per fabricator per month" full />
                      </Panel>
                    </div>
                    <div className="span-12">
                      <Panel title="Fabricator table" flush>
                        <DataTable table={d.tables.fabricators} name="in_out_sale_fabricators" maxRows={16} titleCaseFirst={false} />
                      </Panel>
                    </div>
                  </div>
                ) : (
                  <Empty title="No fabricator rows match these filters" />
                )}
              </Section>

              {!!d.checks.length && (
                <Section title="Sheet checks" sub="Places where two tables of the sheet disagree. Fix them in the sheet; this list updates within a minute.">
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
