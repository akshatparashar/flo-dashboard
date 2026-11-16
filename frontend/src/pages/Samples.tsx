import { useDashboard } from "../api/hooks";
import type { SamplesData } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { colorFor, Legend } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { Lines } from "../components/charts/Lines";
import { Split } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FilterBar, MonthFilter, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["month", "designer", "status", "vendor"];
const STATUS_COLORS: Record<string, string> = {
  Approved: "var(--accent)",
  Rejected: "var(--neg)",
  "On Hold": "var(--series-ref)",
  "In Process": "var(--series-pale)",
  Other: "var(--series-grey)",
};

export default function Samples() {
  const f = useFilters(KEYS);
  const q = useDashboard<SamplesData>("/samples", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty) return <><PageHead title="Samples" meta={d.meta} /><Notices items={d.notices} /><Empty title="No sample data" /></>;
          const k = Object.fromEntries(d.kpis.map((x) => [x.id, x.value]));
          const legend = (names: string[]) => <Legend items={names.map((n) => ({ name: n, color: STATUS_COLORS[n] ?? colorFor(n) }))} />;
          const used = d.charts.monthly_status.series.filter((s) => s.values.some(Boolean)).map((s) => s.name);
          return (
            <>
              <PageHead
                title="Samples"
                meta={d.meta}
                lede={
                  <>
                    <strong>{(k.approval_pct as number).toFixed(1)}% approved</strong> of {fmtInt(k.total as number)} samples; <span className={(k.rejected as number) > 0 ? "bad" : undefined}>{fmtInt(k.rejected as number)} rejected</span>, {fmtInt(k.open as number)} still on hold or in process.
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MonthFilter options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} />
                <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} />
                <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(v) => f.set("status", v)} pretty={(s) => s} />
                <MultiSelect label="Vendor" options={d.options.vendor} value={f.values.vendor} onChange={(v) => f.set("vendor", v)} />
              </FilterBar>
              <Notices items={d.notices} />
              <KpiStrip kpis={d.kpis} cols={5} lead={["approval_pct"]} />

              <Section title="Month by month" sub="By process date">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Status by month" sub="Pcs" right={legend(used)}>
                      <Bars data={d.charts.monthly_status} stacked months unit="pcs" colors={STATUS_COLORS} label="Sample status by month" height={290} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Overall status">
                      <Split items={d.charts.status_share} unit="pcs" colors={STATUS_COLORS} label="Share of samples by status" />
                    </Panel>
                  </div>
                  <div className="span-7">
                    <Panel title="Volume trend" sub="Total, approved and rejected pcs" right={<Legend items={d.charts.monthly_trend.series.map((s) => ({ name: s.name, color: colorFor(s.name), kind: "line" as const }))} />}>
                      <Lines categories={d.charts.monthly_trend.categories} series={d.charts.monthly_trend.series.map((s) => ({ name: s.name, values: s.values, unit: "pcs" }))} label="Total, approved and rejected samples by month" />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Monthly table" flush>
                      <DataTable table={d.tables.monthly} name="sample_monthly" maxRows={13} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Designer scorecard" sub="Every designer, compared on month, status and vendor filters">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Designer table" flush>
                      <DataTable table={d.tables.designers} name="sample_designer" />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Status per designer" sub="Pcs" right={legend(used)}>
                      <HBars data={d.charts.designers} unit="pcs" label="Sample status per designer" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Vendor scorecard" sub="Every vendor, compared on month, status and designer filters">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Vendor table" flush>
                      <DataTable table={d.tables.vendors} name="sample_vendor" />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Status per vendor" sub="Pcs" right={legend(used)}>
                      <HBars data={d.charts.vendors} unit="pcs" label="Sample status per vendor" />
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
