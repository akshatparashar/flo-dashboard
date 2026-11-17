/* Tables as CSV, the same file the website downloads (frontend/src/lib/csv.ts): raw values so Excel sees real
   numbers, server row order, and a guard against formula injection. */
import type { TableData } from "./types";

function esc(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  // guard against formula injection when the file is opened in Excel / Sheets
  const safe = /^[=+\-@\t\r]/.test(s) && !/^-?\d+(\.\d+)?$/.test(s) ? `'${s}` : s;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function toCsv(t: TableData): string {
  const head = t.columns.map((c) => esc(c.label)).join(",");
  const body = t.rows.map((r) => r.map((v) => esc(typeof v === "number" ? Math.round(v * 100) / 100 : v)).join(","));
  return [head, ...body].join("\r\n");
}
