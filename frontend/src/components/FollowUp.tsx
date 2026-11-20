import { useState } from "react";
import type { PromiseItem } from "../api/types";
import { fmtInt } from "../lib/format";

const SHOWN = 8;

/** Overdue, due today and due in 1-3 days: the top of the old "most urgent first" sample list. */
export function FollowUp({ items, empty, max = SHOWN }: { items: PromiseItem[]; empty: string; max?: number }) {
  const [all, setAll] = useState(false);
  if (!items.length) return <div className="state">{empty}</div>;
  const shown = all ? items : items.slice(0, max);
  return (
    <>
      <ul className="attn" aria-label="Promised samples to follow up">
        {shown.map((a, i) => (
          <li key={`${a.designer}-${a.item}-${i}`} className={`attn-row ${a.level}`}>
            <i aria-hidden="true" />
            <div className="attn-main">
              <b>{a.item}</b>
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
      {items.length > max && (
        <button className="btn ghost attn-more" onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}
