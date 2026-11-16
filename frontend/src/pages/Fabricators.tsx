import { useDashboard } from "../api/hooks";
import type { FabricatorData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { colorFor, Legend } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { BarList, Heatmap } from "../components/charts/Lists";
import { Lines } from "../components/charts/Lines";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notice, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt, titleCase } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["fabricator", "month", "metric"];

export default function Fabricators() {
  const f = useFilters(KEYS);
  const q = useDashboard<FabricatorData>("/fabricator", { fabricator: f.values.fabricator, month: f.values.month, metric: f.values.metric[0] });
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty) return <><PageHead title="Fabricators" meta={d.meta} /><Notices items={d.notices} /><Empty title="No stock tables found" /></>;
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x]));
          const rate = k.received_pct.value as number;
          return (
            <>
              <PageHead
                title="Fabricators"
                meta={d.meta}
                lede={
                  <>
                    <span className="bad">{fmtInt(k.remaining.value as number)} pcs</span> still with fabricators, {rate.toFixed(1)}% of production received
                    {k.most_pending.value !== "—" ? <>; <strong>{titleCase(String(k.most_pending.value))}</strong> holds the most ({k.most_pending.hint}).</> : "."}
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MultiSelect label="Fabricator" options={d.options.fabricator} value={f.values.fabricator} onChange={(v) => f.set("fabricator", v)} />
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <MultiSelect label="Matrix shows" options={d.options.metric} value={f.values.metric.length ? [d.metric] : []} onChange={(v) => f.set("metric", v)} single pretty={(s) => s} allLabel={d.metric} />
              </FilterBar>
              <Notices items={d.notices} />
              <KpiStrip kpis={d.kpis} cols={4} lead={["remaining"]} />

              <Section title="Month by month" sub="The full year; the month filter does not apply here">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Production, received and remaining" sub="Pcs" right={<Legend items={d.charts.monthly.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                      <Bars data={d.charts.monthly} months unit="pcs" label="Pcs under production, received and remaining by month" height={290} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Fabric issued and pcs coming in" right={<Legend items={[{ name: "Fabric (mtr)", color: "var(--series-ref)", kind: "line" }, { name: "Incoming (pcs)", color: "var(--accent)", kind: "line" }]} />}>
                      <Lines
                        categories={d.charts.issue_incoming.categories}
                        series={[
                          { name: "Fabric issue (mtr)", values: d.charts.issue_incoming.series[0].values, unit: "mtr", color: "var(--series-ref)" },
                          { name: "Monthly incoming (pcs)", values: d.charts.issue_incoming.series[1].values, unit: "pcs", axis: "right", color: "var(--accent)" },
                        ]}
                        leftUnit="mtr"
                        rightUnit="pcs"
                        label="Fabric issued in metres and incoming pcs by month"
                        height={290}
                      />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Monthly position of stock" flush>
                      <DataTable table={d.tables.monthly} name="fabricator_monthly" maxRows={13} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Scorecard" sub="All fabricators side by side; the month filter applies">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Received and remaining" sub="Pcs" right={<Legend items={d.charts.rcvd_vs_remaining.series.map((s, i) => ({ name: s.name, color: colorFor(s.name, i) }))} />}>
                      <HBars data={d.charts.rcvd_vs_remaining} unit="pcs" label="Received and remaining pcs per fabricator" />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Received rate" sub="Received ÷ pcs under production">
                      <BarList items={d.charts.received_pct} unit="%" decimals={1} share={false} label="Received rate per fabricator" max={10} />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Notice n={d.check} />
                    <Panel title="Fabricator scorecard" flush>
                      <DataTable table={d.tables.scorecard} name="fabricator_scorecard" />
                    </Panel>
                  </div>
                </div>
              </Section>

              {d.matrix && (
                <Section title={`${d.metric} by fabricator and month`} sub="Darker = more. Change the measure with “Matrix shows”.">
                  <div style={{ display: "grid", gap: 16 }}>
                    <Panel>
                      <Heatmap rows={d.matrix.heatmap.rows} columns={d.matrix.heatmap.columns} values={d.matrix.heatmap.values} decimals={0} label={`${d.metric} per fabricator per month`} />
                    </Panel>
                    <Panel title="Matrix table" flush>
                      <DataTable table={d.matrix.table} name="fabricator_matrix" />
                    </Panel>
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
