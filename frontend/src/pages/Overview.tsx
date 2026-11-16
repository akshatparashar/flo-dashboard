import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDashboard, useStatus } from "../api/hooks";
import type { Alert, OverviewData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Legend, TIMING_COLORS, colorFor } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { Split } from "../components/charts/Lists";
import { DataFlow, type FlowOut } from "../components/DataFlow";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter } from "../components/Filters";
import { KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { PageHead, PageState } from "./common";

const KEYS = ["month"];
const AREA_LINK: Record<string, string> = { orders: "/production", overdue: "/production?risk=Overdue", stock: "/fabricators", po: "/fabric-po", samples: "/samples" };
const AREA_NAME: Record<string, string> = { orders: "Production", overdue: "Delivery", stock: "Fabricator stock", po: "Fabric PO", samples: "Samples", none: "Data" };
const SEVERITY: Record<string, number> = { error: 0, warning: 1, info: 2, success: 3 };

function AlertCard({ a }: { a: Alert }) {
  const to = AREA_LINK[a.area];
  const body = (
    <>
      <span className="tag">
        <i />
        {AREA_NAME[a.area] ?? a.area}
      </span>
      <h3>{a.title}</h3>
      <p>{a.text}</p>
      {a.top && (
        <div className="tops">
          {a.top.map((t) => (
            <span key={t.dimension}>
              Most pending {t.dimension.toLowerCase()}: <b>{t.name}</b> ({t.value.toLocaleString("en-US")})
            </span>
          ))}
        </div>
      )}
    </>
  );
  return to ? (
    <Link className={`alert ${a.kind}`} to={to}>
      {body}
    </Link>
  ) : (
    <div className={`alert ${a.kind}`}>{body}</div>
  );
}

export default function Overview() {
  const f = useFilters(KEYS);
  const q = useDashboard<OverviewData>("/overview", { month: f.values.month });
  const status = useStatus();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const alerts = [...d.alerts].sort((a, b) => SEVERITY[a.kind] - SEVERITY[b.kind]);
          const worst = alerts.filter((a) => a.kind === "error" || a.kind === "warning");
          const s = d.sections;
          const outputs: FlowOut[] = d.alerts
            .filter((a) => a.area !== "none")
            .map((a) => ({ label: AREA_NAME[a.area] ?? a.area, value: a.title, to: AREA_LINK[a.area] ?? "/", hot: a.kind === "error" }));
          return (
            <>
              <PageHead
                title="Overview"
                meta={d.meta}
                lede={
                  worst.length ? (
                    <>
                      <span className="bad">{worst[0].title}</span>
                      {worst[1] ? <> and <strong>{worst[1].title}</strong></> : null}
                      {" "}need attention{f.values.month.length ? " in the selected months" : " this year"}.
                    </>
                  ) : (
                    "Nothing needs attention right now."
                  )
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <span className="applied">Orders by order date · samples by process date · stock by month · POs by order date</span>
              </FilterBar>
              <Notices items={d.errors} />

              <div style={{ display: "grid", gap: 16 }}>
                <DataFlow sources={status.data?.sources} outputs={outputs} now={now} />
                <div className="alerts" data-n={alerts.length} data-reveal>
                  {alerts.map((a) => (
                    <AlertCard key={a.area + a.title} a={a} />
                  ))}
                </div>
              </div>

              {s.orders && (
                <Section title="Orders and production" sub="Master sheet · every order line, its production and receipts" right={<Link className="btn sm" to="/production">Open production</Link>}>
                  <KpiStrip kpis={s.orders.kpis.filter((k) => k.id !== "designs")} cols={4} lead={["pending"]} />
                  <div className="grid" style={{ marginTop: 16 }}>
                    <div className="span-7">
                      <Panel title="Received and pending by order month" sub="Pcs" right={<Legend items={s.orders.charts.monthly.series.map((x, i) => ({ name: x.name, color: colorFor(x.name, i) }))} />}>
                        <Bars data={s.orders.charts.monthly} stacked months unit="pcs" label="Received and pending pcs by order month" />
                      </Panel>
                    </div>
                    <div className="span-5">
                      <Panel title="Pending by fabricator" sub="Pcs, most pending first" right={<Legend items={s.orders.charts.fabricators.series.map((x, i) => ({ name: x.name, color: colorFor(x.name, i) }))} />}>
                        <HBars data={{ categories: s.orders.charts.fabricators.categories, series: [...s.orders.charts.fabricators.series].reverse() }} unit="pcs" label="Received and pending pcs per fabricator" max={8} sortBy="Pending" />
                      </Panel>
                    </div>
                    <div className="span-12">
                      <Panel title="Pending and overdue by fabricator" sub="Overdue = in production with delay days above 0" flush>
                        <DataTable table={s.orders.tables.fabricators} name="overview_fabricator_pending" maxRows={10} />
                      </Panel>
                    </div>
                    <div className="span-6">
                      <Panel title="Pending by category" flush>
                        <DataTable table={s.orders.tables.categories} name="overview_category_pending" maxRows={8} />
                      </Panel>
                    </div>
                    <div className="span-6">
                      <Panel title="Pending by client" flush>
                        <DataTable table={s.orders.tables.clients} name="overview_client_pending" maxRows={8} />
                      </Panel>
                    </div>
                  </div>
                </Section>
              )}

              {s.po && (
                <Section title="Fabric POs" sub="Fabric ordering and receiving" right={<Link className="btn sm" to="/fabric-po">Open fabric PO</Link>}>
                  <KpiStrip kpis={s.po.kpis} cols={4} lead={["overdue"]} />
                  <div className="grid" style={{ marginTop: 16 }}>
                    <div className="span-7">
                      <Panel title="Overdue POs, not yet received" sub={s.po.overdue_total > 15 ? `Oldest 15 of ${s.po.overdue_total}` : `${s.po.overdue_total} POs`} flush>
                        {s.po.overdue_total ? <DataTable table={s.po.tables.overdue} name="overview_po_overdue" maxRows={8} titleCaseFirst={false} /> : <div className="state">No PO is overdue.</div>}
                      </Panel>
                    </div>
                    <div className="span-5">
                      <Panel title="Delivery status" sub="Count of POs">
                        <Split items={s.po.timing} unit="POs" colors={TIMING_COLORS} label="POs by delivery status" />
                      </Panel>
                    </div>
                    <div className="span-12">
                      <Panel title="Vendors: pending and delays" flush>
                        <DataTable table={s.po.tables.vendors} name="overview_po_vendor" maxRows={8} />
                      </Panel>
                    </div>
                  </div>
                </Section>
              )}

              {s.stock && (
                <Section title="Fabricator stock" sub="Fabricator report · position of stock" right={<Link className="btn sm" to="/fabricators">Open fabricators</Link>}>
                  <KpiStrip kpis={s.stock.kpis} cols={3} lead={["remaining"]} />
                  <div className="grid" style={{ marginTop: 16 }}>
                    <div className="span-7">
                      <Panel title="Stock by fabricator" flush>
                        <DataTable table={s.stock.table} name="overview_fabricator_stock" />
                      </Panel>
                    </div>
                    <div className="span-5">
                      <Panel title="Received and remaining" sub="Pcs" right={<Legend items={s.stock.chart.series.map((x, i) => ({ name: x.name, color: colorFor(x.name, i) }))} />}>
                        <HBars data={{ categories: s.stock.chart.categories, series: [...s.stock.chart.series].reverse() }} unit="pcs" label="Received and remaining pcs per fabricator" sortBy="Remaining" />
                      </Panel>
                    </div>
                  </div>
                </Section>
              )}

              {s.samples && (
                <Section title="Samples" sub="Sample summary · by process date" right={<Link className="btn sm" to="/samples">Open samples</Link>}>
                  <KpiStrip kpis={s.samples.kpis} cols={3} lead={["approval_pct"]} />
                  <div className="grid" style={{ marginTop: 16 }}>
                    <div className="span-6">
                      <Panel title="Samples by vendor" flush>
                        <DataTable table={s.samples.table} name="overview_sample_vendor" />
                      </Panel>
                    </div>
                    <div className="span-6">
                      <Panel title="Sample status by month" sub="Pcs" right={<Legend items={s.samples.chart.series.filter((x) => x.values.some(Boolean)).map((x, i) => ({ name: x.name, color: colorFor(x.name, i) }))} />}>
                        <Bars data={s.samples.chart} stacked months unit="pcs" label="Sample status by month" />
                      </Panel>
                    </div>
                  </div>
                </Section>
              )}

              {s.designers && (
                <Section title="Designers" sub="Orders from the master sheet with samples from the sample sheet" right={<Link className="btn sm" to="/designers">Open designers</Link>}>
                  <Panel flush>
                    <DataTable table={s.designers.table} name="overview_designer" maxRows={12} />
                  </Panel>
                </Section>
              )}
            </>
          );
        }}
      </PageState>
    </div>
  );
}
