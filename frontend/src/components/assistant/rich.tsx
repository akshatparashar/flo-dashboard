/* Renders the assistant's plain-text answers: **bold**, line breaks, "• " bullets, "1. " numbered lines and
   simple "| a | b |" tables (a "|---|" line under the header).
   Builds React elements only (no innerHTML), so nothing in an answer can inject markup. */
import { Fragment, type ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
  );
}

export function RichText({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((it, i) => <li key={i}>{inline(it)}</li>);
    out.push(list.ordered ? <ol key={out.length}>{items}</ol> : <ul key={out.length}>{items}</ul>);
    list = null;
  };
  let table: string[][] | null = null;
  const flushTable = () => {
    if (!table) return;
    const [head, ...body] = table;
    out.push(
      <div className="fa-table" key={out.length}>
        <table>
          <thead>
            <tr>{head.map((c, i) => <th key={i}>{inline(c)}</th>)}</tr>
          </thead>
          <tbody>
            {body.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
    table = null;
  };
  for (const line of lines) {
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flush();
      if (/^\s*\|[\s|:-]+\|\s*$/.test(line)) continue; // the |---| divider
      const cells = line.trim().slice(1, -1).split("|").map((c) => c.trim());
      (table ??= []).push(cells);
      continue;
    }
    flushTable();
    const bullet = line.match(/^\s*•\s+(.*)$/);
    const num = line.match(/^\s*\d+\.\s+(.*)$/);
    if (bullet || num) {
      const ordered = !!num;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? num)![1]);
      continue;
    }
    flush();
    if (line.trim()) out.push(<p key={out.length}>{inline(line)}</p>);
  }
  flush();
  flushTable();
  return <>{out}</>;
}
