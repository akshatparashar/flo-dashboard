import { useDashboard } from "../api/hooks";
import type { ClientData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Pie } from "../components/charts/Pie";
import { Legend } from "../components/charts/common";
import { Heatmap, Progress } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, shortMonth } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["month", "client", "order_type", "category"];

const FW_COLORS = { "Order pcs": "var(--series-ref)", "Dispatched pcs": "var(--accent)", "Pending pcs": "var(--neg)" };

function FwOrders({ fw }: { fw: NonNullable<ClientData["fw_orders"]> }) {
  const t = fw.totals;
  return (
    <>
      <Notices items={fw.checks} />
      <div className="grid">
        <div className="span-12">
          <Panel
            title="Orders vs dispatched"
            sub={`${fmtInt(t.dispatched)} of ${fmtInt(t.order)} pcs dispatched (${t.dispatched_pct.toFixed(1)}% of the orders that are dispatched or pending)`}
            right={<Legend items={fw.chart.series.map((s) => ({ name: s.name, color: FW_COLORS[s.name as keyof typeof FW_COLORS] }))} />}
          >
            <Bars data={fw.chart} months unit="pcs" label="FW orders: order, dispatched and pending pcs by month" colors={FW_COLORS} height={300} />
          </Panel>
        </div>
        <div className="span-12">
          <Panel title="FW ORDER'S" flush>
            <DataTable table={fw.table} name="fw_orders" maxRows={13} titleCaseFirst={false} />
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function Clients() {
  const f = useFilters(KEYS);
  const q = useDashboard<ClientData>("/client", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x.value as number]));
          const done = k.received + k.pending;
          const pct = done ? (k.received / done) * 100 : 0;
          const monthly = d.tables.monthly;
          const bodyRows = monthly.rows.filter((_, i) => !monthly.meta[i].kind);
          const cat = d.charts.category_by_month;
          return (
            <>
              <PageHead
                title="Clients Order Status"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(k.qty)} pcs</strong> ordered; {done ? <>{pct.toFixed(1)}% of production received, <span className={k.pending ? "bad" : undefined}>{fmtInt(k.pending)} pcs pending</span>.</> : "nothing in production yet."}
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <MultiSelect label="Client" options={d.options.client} value={f.values.client} onChange={(v) => f.set("client", v)} />
                <MultiSelect label="Order type" options={d.options.order_type} value={f.values.order_type} onChange={(v) => f.set("order_type", v)} />
                <MultiSelect label="Category" options={d.options.category} value={f.values.category} onChange={(v) => f.set("category", v)} />
              </FilterBar>
              <KpiStrip kpis={d.kpis} cols={4} lead={["qty"]} />

              <Section title="Fulfilment" sub="Received against everything sent to production">
                <Panel>
                  <Progress value={k.received} max={done} leftLabel={`Received ${fmtInt(k.received)} pcs`} rightLabel={`In production ${fmtInt(done)} pcs`} />
                </Panel>
              </Section>

              <Section title="Clients" sub="Share of ordered pcs by client">
                <div className="grid">
                  <div className="span-12">
                    <Panel title="Order pcs by client">
                      <Pie items={d.charts.client_share} unit="pcs" label="Order pcs by client" />
                    </Panel>
                  </div>
                </div>
              </Section>

              {d.delivery60 && (
                <Section title="Expected deliveries by month" sub={`Pending pcs (column AU) by the 60 DAYS DELIVERY DATE (column AG): how many pcs are due to arrive in each month · red = date already passed (${d.delivery60.today})`}>
                  <KpiStrip kpis={d.delivery60.kpis} cols={6} lead={["total"]} />
                  <div className="grid" style={{ marginTop: 16 }}>
                    <div className="span-7">
                      <Panel
                        title="Pcs due to arrive, by month"
                        sub="Pending pcs per delivery month"
                        right={<Legend items={[{ name: "Date passed", color: "var(--neg)" }, { name: "Not yet due", color: "var(--series-ref)" }]} />}
                      >
                        <Bars data={d.delivery60.chart} stacked months unit="pcs" label="Pending pcs by 60-day delivery month" colors={{ Overdue: "var(--neg)", "Not yet due": "var(--series-ref)" }} height={320} />
                      </Panel>
                    </div>
                    <div className="span-5">
                      <Panel title="Month-wise pcs expected" flush>
                        <DataTable table={d.delivery60.tables.months} name="client_delivery60_months" maxRows={14} titleCaseFirst={false} />
                      </Panel>
                    </div>
                    <div className="span-12">
                      <Panel title="Client-wise pending and delivery dates" flush>
                        <DataTable table={d.delivery60.tables.clients} name="client_delivery60_clients" maxRows={14} titleCaseFirst={false} />
                      </Panel>
                    </div>
                  </div>
                </Section>
              )}

              {(d.fw_orders || d.fw_orders_error) && (
                <Section title="FW ORDER'S" sub="Order, dispatched and pending pcs by month · from the DASHBOARD tab of the master sheet">
                  {d.fw_orders ? (
                    <FwOrders fw={d.fw_orders} />
                  ) : (
                    <Notices items={[{ kind: "warning", text: `FW ORDER'S could not be read: ${d.fw_orders_error}` }]} />
                  )}
                </Section>
              )}

              <Section title="Month by month" sub="By order month">
                <div className="grid">
                  <div className="span-6">
                    <Panel title="Order pcs by month">
                      <Bars data={{ categories: bodyRows.map((r) => String(r[0])), series: [{ name: "Order qty", values: bodyRows.map((r) => Number(r[1]) || 0) }] }} months unit="pcs" label="Order pcs by month" colors={{ "Order qty": "var(--accent)" }} height={300} />
                    </Panel>
                  </div>
                  <div className="span-6">
                    <Panel title="Fulfilment by month" flush>
                      <DataTable table={monthly} name="client_monthly" maxRows={13} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Categories by month" sub="Order pcs, darker = more">
                <div className="grid">
                  <div className="span-12">
                    <Panel>
                      {cat.series.length ? (
                        <Heatmap rows={cat.series.map((s) => s.name)} columns={cat.categories.map(shortMonth)} values={cat.series.map((s) => s.values)} label="Order pcs per category per month" full />
                      ) : (
                        <div className="state">No category data for these filters.</div>
                      )}
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Category table" flush>
                      <DataTable table={d.tables.categories} name="client_categories" maxRows={13} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>
            </>
          );
        }}
      </PageState>
    </div>
  );
}
