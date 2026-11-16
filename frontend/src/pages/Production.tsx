import { useDashboard } from "../api/hooks";
import type { ProductionData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { colorFor, Legend } from "../components/charts/common";
import { BarList } from "../components/charts/Lists";
import { Lines } from "../components/charts/Lines";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { KpiStrip, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["month", "fabricator", "status", "category", "designer", "risk"];

export default function Production() {
  const f = useFilters(KEYS);
  const q = useDashboard<ProductionData>("/production", { ...f.values, risk: f.values.risk[0] ?? "" });
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x.value as number]));
          return (
            <>
              <PageHead
                title="Production"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(k.pending)} pcs</strong> still to come back of {fmtInt(k.production)} in production
                    {k.overdue_pcs > 0 ? (
                      <>
                        ; <span className="bad">{fmtInt(k.overdue_pcs)} pcs</span> across {d.summary.overdue_designs} designs are past their date.
                      </>
                    ) : (
                      "; nothing is past its date."
                    )}
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <MultiSelect label="Fabricator" options={d.options.fabricator} value={f.values.fabricator} onChange={(v) => f.set("fabricator", v)} />
                <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(v) => f.set("status", v)} />
                <MultiSelect label="Category" options={d.options.category} value={f.values.category} onChange={(v) => f.set("category", v)} />
                <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} />
                <MultiSelect label="Delay" options={d.options.risk} value={f.values.risk} onChange={(v) => f.set("risk", v)} single allLabel="Any" pretty={(s) => s} />
              </FilterBar>
              <KpiStrip kpis={d.kpis} cols={4} lead={["pending"]} />

              <Section title="By category" sub="In production, received and pending pcs">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Pcs by category" right={<Legend items={d.charts.by_category.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                      <Bars data={d.charts.by_category} names unit="pcs" label="In production, received and pending pcs by category" height={280} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Category table" flush>
                      <DataTable table={d.tables.categories} name="production_categories" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Pending with fabricators" sub="Who holds the most pending pcs">
                <div className="grid">
                  <div className="span-5">
                    <Panel title="Pending pcs by fabricator">
                      <BarList items={d.charts.pending_share} unit="pcs" tone="neg" label="Pending pcs by fabricator" />
                    </Panel>
                  </div>
                  <div className="span-7">
                    <Panel title="Pending share" flush>
                      <DataTable table={d.tables.fabricators} name="production_fabricator_pending" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Month by month" sub="By order month">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Fulfilment trend" sub="Pcs" right={<Legend items={d.charts.monthly.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i), kind: "line" as const }))} />}>
                      <Lines categories={d.charts.monthly.categories} series={d.charts.monthly.series.map((s) => ({ name: s.name, values: s.values, unit: "pcs", fill: s.name === "Received" }))} label="In production, received and pending pcs by month" height={300} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Monthly table" flush>
                      <DataTable table={d.tables.monthly} name="production_monthly" maxRows={13} titleCaseFirst={false} />
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
