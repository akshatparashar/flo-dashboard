import type { TableData } from "../api/types";

function esc(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  // guard against formula injection when the file is opened in Excel / Sheets
  const safe = /^[=+\-@\t\r]/.test(s) && !/^-?\d+(\.\d+)?$/.test(s) ? `'${s}` : s;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/** Raw values (not display strings) so the file opens with real numbers. Rows keep the server order. */
export function toCsv(t: TableData): string {
  const head = t.columns.map((c) => esc(c.label)).join(",");
  const body = t.rows.map((r) => r.map((v) => esc(typeof v === "number" ? Math.round(v * 100) / 100 : v)).join(","));
  return [head, ...body].join("\r\n");
}

export function downloadCsv(filename: string, csv: string) {
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
