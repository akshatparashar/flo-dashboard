import { useMemo, useState } from "react";
import type { TableData, UnsoldData } from "../api/types";
import { fmtInt, inrShort } from "../lib/format";
import { Bars } from "./charts/Bars";
import { Legend } from "./charts/common";
import { Heatmap, Split } from "./charts/Lists";
import { DataTable, DayLegend } from "./DataTable";
import { Panel, Section } from "./ui";

/* Unsold Inventory Insights (Stock Ageing page). Two measures kept visibly apart: how long each remaining piece has
   been in stock (piece age) and how long a design's stock has sat without a sale. Figures come from the `unsold`
   block of GET /api/stock-ageing (backend/app/dashboards/unsold.py), which follows the page's filters. */

type Measure = "sale" | "age";
type Pick = 0 | 30 | 90 | 180 | 365 | "never";

const BAND_COLORS: Record<string, string> = {
  "0-30 days": "var(--pos)",
  "31-90 days": "var(--accent)",
  "91-180 days": "var(--series-ref)",
  "181-365 days": "var(--warn)",
  "Over 365 days": "var(--neg)",
  Unknown: "var(--series-grey)",
};
const COMPARE_COLORS = { "Pieces older than": "var(--series-ref)", "Designs with no sale for": "var(--neg)" };

/** The rows of the product list that match the chosen measure and threshold. */
function pickRows(table: TableData, measure: Measure, pick: Pick) {
  const at = (name: string) => table.columns.findIndex((c) => c.label === name);
  const days = at("Days without sale");
  const last = at("Last sale");
  const older = typeof pick === "number" && pick > 0 ? at(`Pcs over ${pick}d`) : -1;
  const keep = table.rows
    .map((_, i) => i)
    .filter((i) => {
      const r = table.rows[i];
      if (pick === 0) return true;
      if (pick === "never") return last >= 0 && !r[last];
      if (measure === "sale") return Number(r[days]) > pick;
      return Number(r[older]) > 0;
    });
  const sum = (col: number) => keep.reduce((a, i) => a + (Number(table.rows[i][col]) || 0), 0);
  return {
    table: { ...table, rows: keep.map((i) => table.rows[i]), meta: keep.map((i) => table.meta[i]) } as TableData,
    designs: keep.length,
    pcs: measure === "age" && older >= 0 ? sum(older) : sum(at("Pcs")),
    value: measure === "age" && older >= 0 ? null : sum(at("Value")),
  };
}

export function UnsoldInsights({ u, asOn }: { u: UnsoldData; asOn: string }) {
  const [measure, setMeasure] = useState<Measure>("sale");
  const [pick, setPick] = useState<Pick>(90);
  const m: Measure = u.has_sales ? measure : "age";
  const p: Pick = pick === "never" && m !== "sale" ? 0 : pick;
  const list = useMemo(() => pickRows(u.table, m, p), [u.table, m, p]);
  const picks: Pick[] = m === "sale" ? [0, 30, 90, 180, 365, "never"] : [0, 30, 90, 180, 365];
  const pickLabel = (x: Pick) => (x === 0 ? "All" : x === "never" ? "Never sold" : `Over ${x} days`);
  const adjusted = u.dated_from.adjustments;
  const returned = u.dated_from.returns;

  return (
    <Section title="Unsold Inventory Insights" sub={`How long stock has been waiting, as on ${asOn} · follows the filters above`}>
      <div className="unsold-cards" role="group" aria-label="Unsold for more than">
        {u.cards.map((c, i) => (
          <button key={c.days} type="button" className={`unsold-card step${i}`} aria-pressed={p === c.days} onClick={() => setPick(p === c.days ? 0 : (c.days as Pick))}>
            <span className="uc-title">Over {c.days} days</span>
            <span className="uc-label">Pieces in stock that long</span>
            <span className="uc-big num">
              {fmtInt(c.pcs)}
              <em>pcs</em>
            </span>
            <span className="uc-line num">
              {inrShort(c.value)} at cost · {c.pcs_pct.toFixed(1)}% of pieces
            </span>
            <span className="uc-meter" aria-hidden="true">
              <i style={{ width: `${Math.min(100, c.pcs_pct)}%` }} />
            </span>
            {c.no_sale ? (
              <span className="uc-sale">
                <b className="num">{fmtInt(c.no_sale.designs)}</b> designs with no sale that long
                <span className="num">
                  {fmtInt(c.no_sale.pcs)} pcs · {inrShort(c.no_sale.value)}
                </span>
              </span>
            ) : (
              <span className="uc-sale">Sales history is not in this snapshot</span>
            )}
          </button>
        ))}
      </div>
      <p className="unsold-note">
        Each “over” figure includes the longer ones (over 365 days is also over 90), so do not add the cards together.
        {u.never && u.never.designs > 0 && (
          <>
            {" "}
            <button type="button" className="unsold-link" onClick={() => { setMeasure("sale"); setPick("never"); }}>
              {fmtInt(u.never.designs)} designs have no sale on record
            </button>{" "}
            ({fmtInt(u.never.pcs)} pcs, {inrShort(u.never.value)}).
          </>
        )}
      </p>

      <div className="grid">
        <div className="span-12">
          <Panel>
            <ul className="insights">
              {u.insights.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </Panel>
        </div>
        <div className={u.has_sales ? "span-6" : "span-12"}>
          <Panel title="Value waiting, by threshold" sub="Cost of pieces older than, and of designs not sold for" right={<Legend items={u.compare.series.map((s) => ({ name: s.name, color: COMPARE_COLORS[s.name as keyof typeof COMPARE_COLORS] }))} />}>
            <Bars data={{ ...u.compare, categories: u.cards.map((c) => `>${c.days} days`) }} money label="Stock value by how long it has been unsold" colors={COMPARE_COLORS} height={270} />
          </Panel>
        </div>
        {u.has_sales && (
          <div className="span-6">
            <Panel title="Stock value by time without a sale" sub="Every design counted once · since its last sale, or since the stock arrived if later">
              <Split items={u.bands.map((b) => ({ label: b.label, value: b.value }))} money label="Stock value by time without a sale" colors={BAND_COLORS} />
            </Panel>
          </div>
        )}
        {u.heat && (
          <div className="span-12">
            <Panel title="Pieces by design series and time without a sale" sub="Darker = more pieces">
              <Heatmap rows={u.heat.rows} columns={u.heat.columns.map((c) => c.replace(" days", "").replace("Over ", ">"))} values={u.heat.values} label="Pieces per design series and time without a sale" rowLabel={(x) => x} full />
            </Panel>
          </div>
        )}
        <div className="span-12">
          <Panel title="Explore the products" sub={u.has_sales ? "One row per design, longest without a sale first · a blank Last sale means no sale on record since April 2023" : "One row per design, oldest stock first"} flush>
            <div className="unsold-tools">
              {u.has_sales && (
                <div className="seg" role="group" aria-label="Measure">
                  <button type="button" aria-pressed={m === "sale"} onClick={() => setMeasure("sale")}>
                    No sale for
                  </button>
                  <button type="button" aria-pressed={m === "age"} onClick={() => setMeasure("age")}>
                    Piece age
                  </button>
                </div>
              )}
              <div className="seg" role="group" aria-label="Threshold">
                {picks.map((x) => (
                  <button key={String(x)} type="button" aria-pressed={p === x} onClick={() => setPick(x)}>
                    {pickLabel(x)}
                  </button>
                ))}
              </div>
              <span className="unsold-count num" role="status">
                <b>{fmtInt(list.designs)}</b> designs · <b>{fmtInt(list.pcs)}</b> {m === "age" && p !== 0 ? `pcs ${pickLabel(p).toLowerCase()}` : "pcs"}
                {list.value !== null && <> · <b>{inrShort(list.value)}</b></>}
              </span>
            </div>
            <DayLegend />
            {list.designs ? (
              <DataTable table={list.table} name="unsold_inventory" maxRows={15} titleCaseFirst={false} csv dayHeat={["Days without sale", "Oldest piece (days)"]} />
            ) : (
              <div className="state">No design matches this choice.</div>
            )}
          </Panel>
        </div>
      </div>
      {u.has_sales && <p className="unsold-note">A sale counts as the last sale even if the piece was later returned. Sales are read from April 2023.</p>}
      {(adjusted > 0 || returned > 0) && (
        <p className="unsold-note">
          How age is dated: {adjusted > 0 && <>{fmtInt(adjusted)} pcs of the current stock are dated from a stock count or journal entry, not a purchase, so they may be older than shown. </>}
          {returned > 0 && <>{fmtInt(returned)} pcs are sales returns, dated from the day they came back.</>}
        </p>
      )}
    </Section>
  );
}
