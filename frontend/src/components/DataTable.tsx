import { ArrowDown, ArrowUp, Download } from "lucide-react";
import { useMemo, useState } from "react";
import type { Cell, Column, TableData } from "../api/types";
import { toCsv, downloadCsv } from "../lib/csv";
import { fmtCell, isNum, titleCase } from "../lib/format";

interface Props {
  table: TableData;
  name: string;             // file name for CSV
  maxRows?: number;         // rows shown before "Show all"
  maxHeight?: number;
  titleCaseFirst?: boolean;
  csv?: boolean;
}

function rateClass(v: Cell, col: Column, muted: boolean, kind: string | null): string | null {
  if (!col.rate || !isNum(v) || muted || kind === "ref") return null;
  return v >= col.rate.good ? "good" : v >= col.rate.mid ? "mid" : "bad";
}

/** Sticky header, right-aligned tabular figures, TOTAL row pinned at the bottom, the key column marked with a thin
 *  bar. Rows arrive in the server's order (same as the original dashboards); clicking a header re-sorts locally. */
export function DataTable({ table, name, maxRows = 12, maxHeight, titleCaseFirst = true, csv = true }: Props) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);
  const [all, setAll] = useState(false);
  const keyIdx = table.columns.findIndex((c) => c.key === table.key_col);
  const leftCols = useMemo(
    () =>
      new Set(
        table.columns
          .map((c, i) => ({ c, i }))
          .filter(({ c, i }) => i > 0 && c.format === "text" && table.rows.some((r) => typeof r[i] === "string" && r[i] !== "" && !/^[\d/.,: -]+$/.test(String(r[i]))))
          .map(({ i }) => i),
      ),
    [table],
  );

  const { body, pinned } = useMemo(() => {
    const rows = table.rows.map((r, i) => ({ r, m: table.meta[i] }));
    const pinned = rows.filter((x) => x.m.kind);
    let body = rows.filter((x) => !x.m.kind);
    if (sort) {
      body = [...body].sort((a, b) => {
        const x = a.r[sort.col];
        const y = b.r[sort.col];
        if (isNum(x) && isNum(y)) return (x - y) * sort.dir;
        return String(x ?? "").localeCompare(String(y ?? "")) * sort.dir;
      });
    }
    return { body, pinned };
  }, [table, sort]);

  const barMax = useMemo(() => {
    if (keyIdx < 0) return 0;
    return Math.max(0, ...body.map((x) => (isNum(x.r[keyIdx]) ? Math.abs(x.r[keyIdx] as number) : 0)));
  }, [body, keyIdx]);

  if (!table.columns.length) return <div className="state">No data for the selected filters.</div>;
  const shown = all ? body : body.slice(0, maxRows);
  const hidden = body.length - shown.length;
  const label = (v: Cell, i: number) => (i === 0 && titleCaseFirst && typeof v === "string" ? titleCase(v) : v);

  return (
    <div>
      <div className="tbl-wrap" style={maxHeight ? ({ ["--max-h" as string]: `${maxHeight}px` } as React.CSSProperties) : undefined}>
        <table className="tbl">
          <thead>
            <tr>
              {table.columns.map((c, i) => {
                const active = sort?.col === i;
                const isKey = i === keyIdx;
                return (
                  <th key={c.key} className={isKey && !sort ? "is-key" : undefined} style={leftCols.has(i) ? { textAlign: "left" } : undefined} aria-sort={active ? (sort!.dir === 1 ? "ascending" : "descending") : undefined}>
                    <button
                      type="button"
                      onClick={() => setSort((s) => (s?.col === i ? (s.dir === -1 ? { col: i, dir: 1 } : null) : { col: i, dir: -1 }))}
                      title={isKey && table.sorted && !sort ? "Sorted by this column, highest first" : "Sort"}
                    >
                      {c.label}
                      {active ? sort!.dir === -1 ? <ArrowDown /> : <ArrowUp /> : isKey && table.sorted ? <ArrowDown /> : null}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {[...shown, ...pinned].map(({ r, m }, ri) => (
              <tr key={ri} className={[m.kind ?? "", m.muted ? "muted" : ""].join(" ").trim() || undefined}>
                {r.map((v, ci) => {
                  const col = table.columns[ci];
                  const text = fmtCell(label(v, ci), col.format);
                  const rc = rateClass(v, col, m.muted, m.kind);
                  const isKey = ci === keyIdx && !m.kind;
                  const zero = isNum(v) && v === 0 && ci > 0;
                  const cls = [isKey ? "key" : "", zero && !rc ? "zero" : ""].join(" ").trim() || undefined;
                  return (
                    <td key={ci} className={cls} title={ci === 0 && typeof v === "string" ? v : undefined} style={leftCols.has(ci) ? { textAlign: "left" } : undefined}>
                      {rc ? <span className={`rate ${rc}`}>{text}</span> : text}
                      {isKey && barMax > 0 && isNum(v) && v !== 0 && <span className="bar" style={{ width: `calc(${(Math.abs(v) / barMax) * 100}% * 0.7)` }} aria-hidden="true" />}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(hidden > 0 || all || csv || table.note) && (
        <div className="panel-foot">
          <span>
            {table.note ?? `${body.length.toLocaleString("en-US")} rows`}
            {hidden > 0 && (
              <button className="btn ghost sm" style={{ marginLeft: 8 }} onClick={() => setAll(true)}>
                Show all {body.length}
              </button>
            )}
            {all && body.length > maxRows && (
              <button className="btn ghost sm" style={{ marginLeft: 8 }} onClick={() => setAll(false)}>
                Show fewer
              </button>
            )}
          </span>
          {csv && (
            <button className="btn ghost sm" onClick={() => downloadCsv(`${name}.csv`, toCsv(table))} aria-label={`Download ${name} as CSV`}>
              <Download /> CSV
            </button>
          )}
        </div>
      )}
    </div>
  );
}
