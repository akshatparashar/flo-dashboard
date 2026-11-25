import { useEffect, useState } from "react";
import { useDashboard } from "../api/hooks";
import type { DailyDelegationData, TodoItem } from "../api/types";
import { Bars } from "../components/charts/Bars";
import { Legend } from "../components/charts/common";
import { BarList } from "../components/charts/Lists";
import { Pie } from "../components/charts/Pie";
import { DataTable } from "../components/DataTable";
import { FilterBar, MultiSelect } from "../components/Filters";
import { Empty, KpiStrip, Notices, Panel, Section } from "../components/ui";
import { useFilters } from "../lib/filters";
import { fmtInt } from "../lib/format";
import { PageHead, PageState } from "./common";

/* Daily Delegation: Sir's day from the "Daily Schedule" tab of Sir_Daily_Delegation_Tracker. Who holds which task,
   what is done, what is waiting for approval and how long open tasks have been waiting. Every figure comes from
   GET /api/daily-delegation (backend/app/dashboards/daily_delegation.py). */
const KEYS = ["date", "person", "status", "q"];
const STATUS_COLORS: Record<string, string> = {
  Completed: "var(--pos)",
  "In Progress": "var(--accent)",
  "Awaiting Approval": "var(--warn)",
  Pending: "var(--neg)",
  "On Hold": "var(--series-grey)",
  "Status Not Set": "var(--series-pale)",
};

/** Search box: the URL (and so the API) is only updated once typing pauses. */
function Search({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (text === value) return;
    const id = setTimeout(() => onChange(text), 350);
    return () => clearTimeout(id);
  }, [text, value, onChange]);
  return <input className="field vr-search" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search task, person or remark" aria-label="Search tasks" />;
}

/** Open work as red-edged lines: the task, who is responsible, its status (and how long it has waited). */
function TodoLines({ items, aged }: { items: TodoItem[]; aged?: boolean }) {
  return (
    <ul className="todo">
      {items.map((t, i) => (
        <li key={`${t.task}-${i}`}>
          <span className="todo-task">{t.task}</span>
          <span className="todo-who">{t.person}</span>
          <span className="todo-status" style={{ ["--c" as string]: STATUS_COLORS[t.status] ?? "var(--series-grey)" }}>
            {t.status}
          </span>
          {aged && t.age !== null && (
            <span className="todo-age">
              {t.date} · {t.age} day{t.age === 1 ? "" : "s"}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function DailyDelegation() {
  const f = useFilters(KEYS);
  const q = useDashboard<DailyDelegationData>("/daily-delegation", f.values);
  return (
    <div className="page">
      <PageState q={q}>
        {(d) => {
          if (d.empty)
            return (
              <>
                <PageHead title="Daily Delegation" meta={d.meta} />
                <Notices items={d.notices} />
                <Empty title="No tasks yet">The Daily Schedule tab has no task rows.</Empty>
              </>
            );
          const filters = (
            <FilterBar active={f.active} onReset={f.reset}>
              <MultiSelect label="Date" options={d.options.date} value={f.values.date} onChange={(v) => f.set("date", v)} pretty={(x) => x} />
              <MultiSelect label="Responsible" options={d.options.person} value={f.values.person} onChange={(v) => f.set("person", v)} pretty={(x) => x} />
              <MultiSelect label="Status" options={d.options.status} value={f.values.status} onChange={(v) => f.set("status", v)} pretty={(x) => x} />
              <Search value={f.values.q[0] ?? ""} onChange={(v) => f.set("q", v ? [v] : [])} />
            </FilterBar>
          );
          if (d.no_match)
            return (
              <>
                <PageHead title="Daily Delegation" meta={d.meta} />
                {filters}
                <Empty title="No task matches these filters" />
              </>
            );
          const s = d.summary;
          const stat = d.charts.status;
          const byP = d.charts.by_person;
          const byD = d.charts.by_date;
          const colors = (names: string[]) => Object.fromEntries(names.map((n) => [n, STATUS_COLORS[n] ?? "var(--series-grey)"]));
          return (
            <>
              <PageHead
                title="Daily Delegation"
                meta={d.meta}
                lede={
                  <>
                    <strong>{fmtInt(s.tasks)} tasks</strong> over {s.days} day{s.days === 1 ? "" : "s"}: {fmtInt(s.completed)} done ({s.done_pct.toFixed(0)}%),{" "}
                    <span className={s.open ? "bad" : undefined}>{fmtInt(s.open)} still open</span>
                    {s.awaiting ? <>, {fmtInt(s.awaiting)} waiting for Sir's approval</> : null}.
                  </>
                }
              />
              {filters}
              <KpiStrip kpis={d.kpis} cols={4} lead={["total"]} />

              <Section title="Today's pending work" sub={`${d.today_pending.date} · open tasks dated today, with the person responsible`}>
                <Panel>
                  {d.today_pending.today.length ? (
                    <TodoLines items={d.today_pending.today} />
                  ) : (
                    <div className="todo-none">
                      {d.today_pending.today_total ? "Everything dated today is completed." : `No task is dated today (${d.today_pending.date}) in the Daily Schedule tab yet.`}
                    </div>
                  )}
                  {!!d.today_pending.carried.length && (
                    <>
                      <div className="todo-sub">
                        Carried over from earlier days <b>{d.today_pending.carried.length}</b> · still open, oldest first
                      </div>
                      <TodoLines items={d.today_pending.carried.slice(0, 10)} aged />
                      {d.today_pending.carried.length > 10 && <div className="stamp">+{d.today_pending.carried.length - 10} more · see Needs attention below</div>}
                    </>
                  )}
                </Panel>
              </Section>

              <Section title="Highlights" sub={`Worked out from the sheet as on ${d.today}`}>
                <Panel>
                  <ul className="insights">
                    {d.insights.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </Panel>
              </Section>

              <Section title="Where things stand" sub="Status of every task, and how long the open ones have been waiting">
                <div className="grid">
                  <div className="span-6">
                    <Panel title="Status">
                      <Pie items={stat} unit="tasks" label="Tasks by status" colors={STATUS_COLORS} />
                    </Panel>
                  </div>
                  <div className="span-6">
                    <Panel title="Open tasks by age" sub="Days since the task's date, completed tasks left out">
                      <BarList items={d.charts.ageing} unit="tasks" max={6} tone="neg" label="Open tasks by age" share={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Who has what" sub="Tasks per responsible person, by status">
                <div className="grid">
                  <div className="span-12">
                    <Panel title="Tasks by person" right={<Legend items={byP.series.map((x) => ({ name: x.name, color: STATUS_COLORS[x.name] ?? "var(--series-grey)" }))} />}>
                      <Bars data={byP} stacked names unit="tasks" label="Tasks by person and status" colors={colors(byP.series.map((x) => x.name))} height={300} />
                    </Panel>
                  </div>
                  <div className="span-12">
                    <Panel title="Person summary" flush>
                      <DataTable table={d.tables.persons} name="delegation_persons" maxRows={14} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              <Section title="Day by day" sub="Tasks per date, by status">
                <div className="grid">
                  <div className="span-7">
                    <Panel title="Tasks by date" right={<Legend items={byD.series.map((x) => ({ name: x.name, color: STATUS_COLORS[x.name] ?? "var(--series-grey)" }))} />}>
                      <Bars data={byD} stacked unit="tasks" label="Tasks by date and status" colors={colors(byD.series.map((x) => x.name))} height={280} />
                    </Panel>
                  </div>
                  <div className="span-5">
                    <Panel title="Date summary" flush>
                      <DataTable table={d.tables.dates} name="delegation_dates" maxRows={14} titleCaseFirst={false} />
                    </Panel>
                  </div>
                </div>
              </Section>

              {!!d.tables.attention.rows.length && (
                <Section title="Needs attention" sub="Open tasks from earlier days, and everything waiting for Sir's approval · oldest first">
                  <Panel flush>
                    <DataTable table={d.tables.attention} name="delegation_attention" maxRows={12} titleCaseFirst={false} csv />
                  </Panel>
                </Section>
              )}

              <Section title="All tasks" sub="Open tasks first, oldest on top; completed tasks follow">
                <Panel flush>
                  <DataTable table={d.tables.tasks} name="delegation_tasks" maxRows={15} titleCaseFirst={false} csv />
                </Panel>
              </Section>

              {!!d.checks.length && (
                <Section title="Sheet checks" sub="Rows in the Daily Schedule tab that look incomplete. Fix them in the sheet; this list updates within a minute.">
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
