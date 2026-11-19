import { useState } from "react";
import { useDashboard } from "../api/hooks";
import type { FloFutureData, Kpi, PromiseItem } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Legend, colorFor } from "../components/charts/common";
import { HBars } from "../components/charts/HBars";
import { BarList, Progress, Split } from "../components/charts/Lists";
import { DataTable } from "../components/DataTable";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

const KEYS = ["team", "designer", "vendor", "status", "season", "month"];
const STAGE_COLORS: Record<string, string> = {
  Complete: "var(--accent)",
  "In work": "var(--series-ref)",
  "Not started": "var(--series-pale)",
  "Not updated": "var(--neg)",
};
const TIMELINE_COLORS: Record<string, string> = { Overdue: "var(--neg)", Pending: "var(--series-ref)" };
const SAMPLE_KPIS = ["promised", "completed", "pending", "done_pct", "overdue", "due_soon", "not_updated", "top"];
const OUT_KPIS = ["out_promised", "out_pending"];
const VISIT_KPIS = ["visits_done", "unplanned"];
const ATTENTION_SHOWN = 8;

const pick = (kpis: Kpi[], ids: string[]) => ids.map((id) => kpis.find((k) => k.id === id)).filter((k): k is Kpi => !!k);
const plural = (n: number, word: string) => `${fmtInt(n)} ${word}${n === 1 ? "" : "s"}`;

/** Promises that need someone to act: overdue first, then due in the next days, then no status / no date. */
function Attention({ items }: { items: PromiseItem[] }) {
  const [all, setAll] = useState(false);
  if (!items.length) return <div className="state">Nothing needs attention: no promise is late, due in the next 3 days or missing a status.</div>;
  const shown = all ? items : items.slice(0, ATTENTION_SHOWN);
  return (
    <>
      <ul className="attn" aria-label="Promised items that need attention">
        {shown.map((a, i) => (
          <li key={`${a.designer}-${a.item}-${i}`} className={`attn-row ${a.level}`}>
            <i aria-hidden="true" />
            <div className="attn-main">
              <b>{a.item}</b>
              {a.kind === "Outsource" && <span className="attn-kind">Outsource</span>}
              <span className="attn-who">
                {a.designer}
                {a.team && !a.team.startsWith("(") ? ` · ${a.team}` : ""}
                {a.vendor ? ` · ${a.vendor}` : ""} · {a.status}
              </span>
            </div>
            <div className="attn-side">
              <span className="attn-reason">{a.reason}</span>
              <span className="attn-pcs num">
                {fmtInt(a.pending)} pcs pending{a.due ? ` · due ${a.due}` : ""}
              </span>
            </div>
          </li>
        ))}
      </ul>
      {items.length > ATTENTION_SHOWN && (
        <button className="btn ghost attn-more" onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}

export default function FloFuture() {
  const f = useFilters(KEYS);
  const q = useDashboard<FloFutureData>("/flo-future", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty || !d.tables || !d.charts || !d.summary)
            return (
              <>
                <PageHead title="FLO Future" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No promises found">The FLO Future sheet has no rows in its Samples or Outsource Projects tab yet.</Empty>
              </>
            );
          const s = d.summary;
          const t = d.tables;
          const c = d.charts;
          const period = d.period || "this month";
          const lateTone = s.overdue > 0 ? "bad" : undefined;
          return (
            <>
              <PageHead
                title="FLO Future"
                meta={d.meta}
                lede={
                  <>
                    <strong>{s.done_pct.toFixed(0)}% done</strong> of {fmtInt(s.qty)} sample pcs promised for {period}.{" "}
                    <span className={lateTone}>{plural(s.overdue, "item")} overdue</span>, {plural(s.due_soon, "item")} due in the next 7 days
                    {s.not_updated ? <>, {plural(s.not_updated, "item")} still “Not Updated”</> : null}.
                  </>
                }
              />
              <FilterBar active={f.active} onReset={f.reset}>
                <MultiSelect label="Team" options={d.options.team} value={f.values.team} onChange={(v) => f.set("team", v)} pretty={(x) => x} />
                <MultiSelect label="Designer" options={d.options.designer} value={f.values.designer} onChange={(v) => f.set("designer", v)} />
                <MultiSelect label="Vendor" options={d.options.vendor} value={f.values.vendor} onChange={(v) => f.set("vendor", v)} pretty={(x) => x} />
                <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(v) => f.set("status", v)} pretty={(x) => x} />
                {d.options.season.length > 0 && <MultiSelect label="Season" options={d.options.season} value={f.values.season} onChange={(v) => f.set("season", v)} />}
                {d.options.month.length > 1 && <MultiSelect label="Due month" options={d.options.month} value={f.values.month} onChange={(v) => f.set("month", v)} pretty={(x) => x} />}
              </FilterBar>
              <Notices items={d.notices} />
              <KpiStrip kpis={pick(d.kpis, SAMPLE_KPIS)} cols={4} lead={["done_pct"]} />

              <Section title="Needs attention" sub="Late promises first, then what is due in the next 3 days and items with no status or no date">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Follow up" sub={`${plural(d.attention?.length ?? 0, "item")} · samples and outsource`} flush>
                      <Attention items={d.attention ?? []} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Month progress" sub="Completed pcs against everything promised">
                      <Progress
                        value={s.completed}
                        max={s.qty}
                        marker={d.pace && d.pace.due_by_today > 0 ? d.pace.due_by_today : undefined}
                        leftLabel={`${fmtInt(s.completed)} done`}
                        rightLabel={`${fmtInt(s.qty)} promised`}
                      />
                      {d.pace && d.pace.due_by_today > 0 && (
                        <p className="stamp" style={{ marginTop: 8, whiteSpace: "normal" }}>
                          The tick marks {fmtInt(d.pace.due_by_today)} pcs whose due date has already passed.
                          {s.completed >= d.pace.due_by_today ? " Completed work is ahead of it." : " Completed work is behind it."}
                        </p>
                      )}
                    </Panel>
                    <Panel title="Where the pcs stand" sub="Done, and pending pcs by how far along their item is">
                      <Split items={c.stage_share} unit="pcs" colors={STAGE_COLORS} label="Promised sample pcs by stage" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Designer scorecard" sub="Every designer's promises for the month; the designer filter is not applied here so all can be compared">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Designer table" flush>
                      <DataTable table={t.designers} name="flo_future_designers" maxRows={14} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Done and pending per designer" sub="Sample pcs" right={<Legend items={["Completed", "Pending"].map((n) => ({ name: n, color: colorFor(n) }))} />}>
                      <HBars data={c.designers} unit="pcs" label="Completed and pending promised pcs per designer" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Due dates and status" sub="Pending pcs by promised date, and where open items are in the sampling pipeline">
                <div className="grid">
                  <div className="span-7">
                    <Panel
                      title="Pending pcs by due date"
                      sub={c.timeline.no_date ? `${fmtInt(c.timeline.no_date)} pending pcs have no due date and are not shown` : "Red = date already passed"}
                      right={<Legend items={c.timeline.series.filter((x) => x.values.some(Boolean)).map((x) => ({ name: x.name, color: TIMELINE_COLORS[x.name] }))} />}
                    >
                      {c.timeline.categories.length ? <Bars data={c.timeline} stacked unit="pcs" colors={TIMELINE_COLORS} label="Pending promised pcs by due date" height={260} /> : <div className="state">No open item has a due date.</div>}
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Pending pcs by status" sub="Open items only">
                      <BarList items={c.status} unit="pcs" max={10} label="Pending promised pcs by status" />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Teams and vendors" sub="Who the samples are with">
                <div className="grid">
                  <div className="span-6">
                    <Panel title="Teams" flush>
                      <DataTable table={t.teams} name="flo_future_teams" titleCaseFirst={false} />
                    </Panel>
                  </div>
                  <div className="span-6">
                    <Panel title="Sampling vendors" flush>
                      <DataTable table={t.vendors} name="flo_future_vendors" titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Every promised sample" sub="Late first, then by due date; finished items last">
                <Panel flush>
                  <DataTable table={t.items} name="flo_future_samples" maxRows={15} titleCaseFirst={false} />
                </Panel>
              </Section>

              <Section title="Outsource projects" sub="Work given to outside sampling houses">
                <KpiStrip kpis={pick(d.kpis, OUT_KPIS)} cols={2} />
                <div className="grid" style={{ marginTop: "var(--gap)" }}>
                  <div className="span-8">
                    <Panel title="Projects" flush>
                      <DataTable table={t.outsource} name="flo_future_outsource" titleCaseFirst={false} />
                    </Panel>
                  </div>
                  <div className="span-4">
                    <Panel title="Outsource vendors" flush>
                      <DataTable table={t.outsource_vendors} name="flo_future_outsource_vendors" titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Visits and meetings" sub="Market, store, Surat and factory visits, and the Saturday meetings">
                <KpiStrip kpis={pick(d.kpis, VISIT_KPIS)} cols={2} />
                <div style={{ marginTop: "var(--gap)" }}>
                  <Panel flush>
                    {t.visits.rows.length ? <DataTable table={t.visits} name="flo_future_visits" titleCaseFirst={false} /> : <div className="state">No visits or meetings on the sheet yet.</div>}
                  </Panel>
                </div>
              </Section>

              {!!d.checks?.length && (
                <Section title="Sheet checks" sub="Things in the FLO Future sheet that look wrong or are missing. Fix them in the sheet; this list updates within a minute.">
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
