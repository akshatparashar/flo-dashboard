import { useEffect, useState } from "react";
import { useDashboard } from "../api/hooks";
import type { StockAgeingData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Heatmap } from "../components/charts/Lists";
import { DataTable, DayLegend } from "../components/DataTable";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, inrShort } from "../lib/format";
import { PageHead, PageState } from "./common";
import { UnsoldInsights } from "../components/UnsoldInsights";

/* Stock Ageing (FIFO): finished-goods pcs from EasyTrade, as on one day's closing. How old the stock is, what it is
   worth at inward cost, which design series hold the old stock and which designs to act on first. Every figure comes
   from GET /api/stock-ageing (backend/app/dashboards/stock_ageing.py). */
const KEYS = ["type", "age", "q"];

function Search({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (text === value) return;
    const id = setTimeout(() => onChange(text), 350);
    return () => clearTimeout(id);
  }, [text, value, onChange]);
  return <input className="field vr-search" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search design code or description" aria-label="Search designs" />;
}

const SHORT = (b: string) => b.replace(" days", "").replace("Over ", ">");

export default function StockAgeing() {
  const f = useFilters(KEYS);
  const q = useDashboard<StockAgeingData>("/stock-ageing", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty)
            return (
              <>
                <PageHead title="Stock Ageing" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No stock rows">The snapshot has no items.</Empty>
              </>
            );
          const filters = (
            <FilterBar active={f.active} onReset={f.reset}>
              <MultiSelect label="Design series" options={d.options.type} value={f.values.type} onChange={(v) => f.set("type", v)} pretty={(x) => x} />
              <MultiSelect label="Oldest age band" options={d.options.age} value={f.values.age} onChange={(v) => f.set("age", v)} pretty={(x) => x} />
              <Search value={f.values.q[0] ?? ""} onChange={(v) => f.set("q", v ? [v] : [])} />
            </FilterBar>
          );
          if (d.no_match)
            return (
              <>
                <PageHead title="Stock Ageing" meta={d.meta} />
                {filters}
                <Empty title="No design matches these filters" />
              </>
            );
          const s = d.summary;
          const bars = (name: string, slices: { label: string; value: number }[]) => ({ categories: slices.map((x) => SHORT(x.label)), series: [{ name, values: slices.map((x) => x.value) }] });
          const heat = d.charts.type_age;
          return (
            <>
              <PageHead
                title="Stock Ageing"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(s.qty)} pcs</strong> worth <strong>{inrShort(s.value)}</strong> at inward cost; <span className="bad">{inrShort(s.old_value)} ({s.old_value_pct.toFixed(0)}%)</span> has been in stock over 180 days. As on {d.as_on} closing.
                  </>
                }
              />
              {filters}
              <Notices items={d.notices} />
              <KpiStrip kpis={d.kpis} cols={4} lead={["qty"]} />

              <Section title="Highlights" sub={`${d.source} · pieces only · FIFO · as on ${d.as_on}`}>
                <Panel>
                  <ul className="insights">
                    {d.insights.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </Panel>
              </Section>

              {d.unsold && <UnsoldInsights u={d.unsold} asOn={d.as_on} />}

              <Section title="Stock by time in warehouse" sub="How much stock sits in each age band">
                <div className="grid">
                  <div className="span-6">
                    <Panel title="Value at cost by age">
                      <Bars data={bars("Value", d.charts.value_by_age)} money label="Stock value by age band" colors={{ Value: "var(--accent)" }} height={260} />
                    </Panel>
                  </div>
                  <div className="span-6">
                    <Panel title="Pieces by age">
                      <Bars data={bars("Pcs", d.charts.qty_by_age)} unit="pcs" label="Stock pieces by age band" colors={{ Pcs: "var(--series-ref)" }} height={260} />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Age band summary" flush>
                      <DataTable table={d.tables.ages} name="stock_ageing_bands" maxRows={10} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="By design series" sub="Series = the number at the start of the design code">
                <div className="grid">
                  <div className="span-12">
                    <Panel title="Pieces by series and age" sub="Darker = more">
                      <Heatmap rows={heat.rows} columns={heat.columns.map(SHORT)} values={heat.values} label="Pieces per design series and age band" rowLabel={(x) => x} full />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Series summary" flush>
                      <DataTable table={d.tables.types} name="stock_ageing_series" maxRows={16} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              {!!d.tables.stuck.rows.length && (
                <Section title="Act on these first" sub="The 25 designs with the most value over 180 days old">
                  <Panel flush>
                    <DayLegend />
                    <DataTable table={d.tables.stuck} name="stock_ageing_old_designs" maxRows={25} titleCaseFirst={false} csv dayHeat={["Avg age (days)"]} />
                  </Panel>
                </Section>
              )}

              <Section title="All designs" sub="Highest value first">
                <Panel flush>
                  <DayLegend />
                  <DataTable table={d.tables.designs} name="stock_ageing_designs" maxRows={15} titleCaseFirst={false} csv dayHeat={["Avg age (days)"]} />
                </Panel>
              </Section>
            </>
          );
        }}
      </PageState>
    </div>
  );
}
