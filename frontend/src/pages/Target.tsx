import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useDashboard } from "../api/hooks";
import type { TargetData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { colorFor, Legend } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { BarList, Progress } from "../components/charts/Lists";
import { Lines } from "../components/charts/Lines";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { inr, inrShort, titleCase } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["month", "designer", "item", "order_by", "source"];
const DEFAULT_CR = 50.2;

function TargetInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  const commit = () => {
    const v = parseFloat(text);
    if (Number.isFinite(v) && v >= 0 && v <= 100000) onChange(Math.round(v * 100) / 100);
    else setText(String(value));
  };
  return (
    <label className="fbtn" style={{ paddingRight: 4 }} title="Yearly NEW-order target in crore. Monthly target = yearly ÷ 12.">
      <span className="k">Yearly target ₹</span>
      <input
        className="num"
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        aria-label="Yearly new-order target in crore"
        style={{ width: 54, border: 0, background: "transparent", fontWeight: 600, color: "var(--ink)", outline: "none", textAlign: "right" }}
      />
      <span className="k">Cr</span>
    </label>
  );
}

export default function Target() {
  const f = useFilters(KEYS);
  const [sp, setSp] = useSearchParams();
  const cr = Number(sp.get("target") ?? DEFAULT_CR) || 0;
  const setCr = (v: number) =>
    setSp(
      (p) => {
        const n = new URLSearchParams(p);
        if (v === DEFAULT_CR) n.delete("target");
        else n.set("target", String(v));
        return n;
      },
      { replace: true },
    );
  const q = useDashboard<TargetData>("/target", { ...f.values, annual_target_cr: cr });
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty) return <><PageHead title="Designer Order Target" meta={d.meta} /><Notices items={d.notices} /><Empty title="No order data" /></>;
          const t = d.tracker;
          const ahead = t.schedule.gap >= 0;
          const monthlyTarget = t.monthly.target[0] ?? 0;
          const fl = d.filtered;
          const fy = t.monthly.categories.slice(0, 12);
          return (
            <>
              <PageHead
                title="Designer Order Target"
                meta={d.meta}
                lede={
                  <>
                    <strong>{inrShort(t.gauge.achieved)}</strong> of the {inrShort(t.gauge.target)} new-order target ({t.gauge.value.toFixed(1)}%),{" "}
                    {t.schedule.elapsed.length ? <span className={ahead ? undefined : "bad"}>{ahead ? "ahead of" : "behind"} schedule by {inrShort(Math.abs(t.schedule.gap))}</span> : "before the year starts"}.
                  </>
                }
              />
              <Notices items={d.notices} />

              <Section title="New-order target" sub="Always the whole year; the filters further down do not change this part" right={<TargetInput value={d.annual_target_cr} onChange={setCr} />}>
                <KpiStrip kpis={t.kpis} cols={4} lead={["achieved"]} />
                <div className="grid" style={{ marginTop: 16 }}>
                  <div className="span-12">
                    <Panel title="Year so far" sub="The tick marks where the schedule says we should be today">
                      <Progress value={t.gauge.achieved} max={t.gauge.target} marker={t.schedule.scheduled} leftLabel={`Achieved ${inrShort(t.gauge.achieved)} · ${t.gauge.value.toFixed(1)}%`} rightLabel={`Target ${inrShort(t.gauge.target)}`} />
                    </Panel>
                  </div>
                  <div className="span-7">
                    <Panel title="New-order revenue by month" sub="Bars = achieved, dashed line = monthly target">
                      <Bars
                        data={{ categories: fy, series: [{ name: "Achieved", values: t.monthly.achieved.slice(0, 12) }] }}
                        months
                        money
                        reference={{ value: monthlyTarget, label: `Target ${inrShort(monthlyTarget)}` }}
                        label="New-order revenue achieved per month against the monthly target"
                        height={290}
                      />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Cumulative against target" right={<Legend items={[{ name: "Achieved", color: "var(--accent)", kind: "line" }, { name: "Target", color: "var(--series-ref)", kind: "dash" }]} />}>
                      <Lines
                        categories={fy}
                        series={[
                          { name: "Cumulative target", values: t.monthly.cum_target.slice(0, 12), dashed: true },
                          { name: "Cumulative achieved", values: t.monthly.cum_achieved.slice(0, 12), fill: true },
                        ]}
                        money
                        label="Cumulative new-order revenue against cumulative target"
                        height={290}
                      />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Notices items={t.notices} />
                    <Panel title="Target vs achieved by month" sub="Achieved %: green 100% or more, amber 75–99%, red under 75%. Months not started stay blank." flush>
                      <DataTable table={t.table} name="target_monthly" maxRows={13} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Revenue breakdown" sub="New and repeat orders; the filters apply from here down">
                <FilterBar active={f.active} onReset={f.reset}>
                  <MonthFilter label="Order month" options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                  <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} />
                  <MultiSelect label="Item" options={d.options.item} value={f.values.item} onChange={(v) => f.set("item", v)} />
                  <MultiSelect label="Order by" options={d.options.order_by} value={f.values.order_by} onChange={(v) => f.set("order_by", v)} />
                  <MultiSelect label="Order type" options={d.options.source} value={f.values.source} onChange={(v) => f.set("source", v)} />
                </FilterBar>
                {fl.empty ? (
                  <Notices items={fl.notices} />
                ) : (
                  <>
                    <KpiStrip kpis={fl.kpis} cols={5} lead={["revenue"]} />
                    <div className="grid" style={{ marginTop: 16 }}>
                      <div className="span-7">
                        <Panel title="Revenue by month" sub="New and repeat" right={<Legend items={fl.charts.monthly.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                          <Bars data={fl.charts.monthly} stacked months money label="New and repeat revenue by month" height={290} />
                        </Panel>
                      </div>
                      <div className="span-5">
                        <Panel title="By designer" right={<Legend items={fl.charts.designers.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                          <HBars data={fl.charts.designers} money label="New and repeat revenue per designer" max={10} />
                        </Panel>
                      </div>
                      <div className="span-12">
                        <Panel title="Revenue by month" flush>
                          <DataTable table={fl.tables.monthly} name="target_month_revenue" maxRows={13} titleCaseFirst={false} />
                        </Panel>
                      </div>
                      <div className="span-12">
                        <Panel title="Designer revenue" flush>
                          <DataTable table={fl.tables.designers} name="target_designer" />
                        </Panel>
                      </div>
                      <div className="span-5">
                        <Panel title="By item">
                          <BarList items={fl.charts.items} money label="Revenue per item" />
                        </Panel>
                      </div>
                      <div className="span-7">
                        <Panel title="Item revenue" flush>
                          <DataTable table={fl.tables.items} name="target_item" maxRows={8} />
                        </Panel>
                      </div>
                      <div className="span-5">
                        <Panel title="By who ordered">
                          <BarList items={fl.charts.order_by} money label="Revenue per orderer" />
                        </Panel>
                      </div>
                      <div className="span-7">
                        <Panel title="Order-by revenue" flush>
                          <DataTable table={fl.tables.order_by} name="target_orderby" maxRows={8} />
                        </Panel>
                      </div>
                    </div>

                    <Section title="Designs that sell again" sub="Top 15 by number of repeat orders">
                      <Panel flush>
                        {fl.top_repeat.length ? (
                          <div className="tbl-wrap">
                            <table className="tbl">
                              <thead>
                                <tr>
                                  <th>Design</th>
                                  <th style={{ textAlign: "left" }}>Item</th>
                                  <th style={{ textAlign: "left" }}>Designer</th>
                                  <th className="is-key">Repeat orders</th>
                                  <th>Repeat pcs</th>
                                  <th>Repeat revenue</th>
                                  <th>Last repeat</th>
                                </tr>
                              </thead>
                              <tbody>
                                {fl.top_repeat.map((r) => (
                                  <tr key={r.barcode}>
                                    <td style={{ height: 64 }}>
                                      <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                        {r.image ? <img className="thumb" src={r.image} alt={`${r.item} ${r.barcode}`} loading="lazy" referrerPolicy="no-referrer" /> : <span className="thumb empty" aria-hidden="true">F</span>}
                                        {r.barcode}
                                      </span>
                                    </td>
                                    <td style={{ textAlign: "left" }}>{titleCase(r.item)}</td>
                                    <td style={{ textAlign: "left" }}>{titleCase(r.designer)}</td>
                                    <td className="key">{r.orders}</td>
                                    <td>{r.pcs.toLocaleString("en-US")}</td>
                                    <td>{inr(r.revenue)}</td>
                                    <td>{r.last}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div className="state">No repeat orders in this selection.</div>
                        )}
                      </Panel>
                    </Section>

                    <Section title="Order lines" sub={fl.lines_truncated ? `First ${fl.tables.lines.rows.length.toLocaleString("en-US")} of ${fl.lines_total.toLocaleString("en-US")} lines` : `${fl.lines_total.toLocaleString("en-US")} lines`}>
                      <Panel flush>
                        <DataTable table={fl.tables.lines} name="target_order_lines" maxRows={10} titleCaseFirst={false} />
                      </Panel>
                    </Section>
                  </>
                )}
              </Section>

              <Section title="Data check" sub="Pcs × rate against the sheet's TOTAL AMOUNT, over all orders">
                <Notices items={d.quality.notices} />
                {d.quality.rows && (
                  <Panel title="Rows to check" flush>
                    <DataTable table={d.quality.rows} name="target_rows_to_check" maxRows={8} titleCaseFirst={false} />
                  </Panel>
                )}
              </Section>
            </>
          );
        }}
      </PageState>
    </div>
  );
}
