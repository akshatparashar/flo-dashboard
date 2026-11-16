import { useDashboard } from "../api/hooks";
import type { DesignerData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { colorFor, Legend } from "../components/charts/common";
import { Heatmap } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { KpiStrip, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, shortMonth, titleCase } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["month", "designer", "order_type"];

export default function Designers() {
  const f = useFilters(KEYS);
  const q = useDashboard<DesignerData>("/designer", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const top = d.kpis.find((k) => k.id === "top");
          const qty = d.kpis.find((k) => k.id === "qty")?.value as number;
          const trend = d.charts.monthly_trend;
          return (
            <>
              <PageHead
                title="Designers"
                meta={d.meta}
                lede={
                  top && top.value !== "—" ? (
                    <>
                      <strong>{titleCase(String(top.value))}</strong> leads with {top.hint} of {fmtInt(qty)} pcs ordered.
                    </>
                  ) : (
                    "No orders for the selected filters."
                  )
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} />
                <MultiSelect label="Order type" options={d.options.order_type} value={f.values.order_type} onChange={(v) => f.set("order_type", v)} />
              </FilterBar>
              <KpiStrip kpis={d.kpis} cols={5} lead={["qty"]} />

              <Section title="Volume and share" sub="New and repeat order pcs per designer">
                <div className="grid">
                  <div className="span-6">
                    <Panel title="Designer table" flush>
                      <DataTable table={d.tables.designers} name="designer_volume" />
                    </Panel>
                  </div>
                  <div className="span-6">
                    <Panel title="New and repeat pcs" right={<Legend items={d.charts.new_vs_repeat.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                      <Bars data={d.charts.new_vs_repeat} stacked names unit="pcs" label="New and repeat order pcs per designer" height={340} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Month by month" sub="Pcs ordered per designer, darker = more">
                <Panel>
                  {trend.series.length ? (
                    <Heatmap rows={trend.series.map((s) => s.name)} columns={trend.categories.map(shortMonth)} values={trend.series.map((s) => s.values)} label="Pcs per designer per month" />
                  ) : (
                    <div className="state">No monthly data for these filters.</div>
                  )}
                </Panel>
              </Section>

              <Section title="Categories" sub="Pcs per designer and category">
                <Panel flush>
                  <DataTable table={d.tables.categories} name="designer_categories" />
                </Panel>
              </Section>
            </>
          );
        }}
      </PageState>
    </div>
  );
}
