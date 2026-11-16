/* Number formatting, matched to the original dashboard: counts use 1,234 grouping, rupees use Indian grouping
   (₹50,20,000) and compact rupees use crore / lakh (₹50.20 Cr, ₹3.29 L). */
import type { Cell, Fmt } from "../api/types";

const int0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const dec2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dec1 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** Python's round-half-even, so rounded figures match the server's ("{:,.0f}") exactly. */
function roundHalfEven(v: number): number {
  const r = Math.round(v);
  return Math.abs(v % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

export function fmtInt(v: number): string {
  return int0.format(roundHalfEven(v)).replace("-0", "0");
}

export function inr(v: number): string {
  if (!isNum(v)) return "";
  const n = Math.round(Math.abs(v));
  let s = String(n);
  if (s.length > 3) {
    const head = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    s = `${head},${s.slice(-3)}`;
  }
  return `${v < 0 && n ? "-" : ""}₹${s}`;
}

export function inrShort(v: number): string {
  if (!isNum(v)) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e7) return `${sign}₹${dec2.format(a / 1e7)} Cr`;
  if (a >= 1e5) return `${sign}₹${dec2.format(a / 1e5)} L`;
  return `${sign}₹${int0.format(Math.round(a))}`;
}

/** Splits a compact rupee figure into number and unit so the unit can be set smaller. */
export function inrParts(v: number): { value: string; unit: string } {
  const s = inrShort(v);
  const m = s.match(/^(-?₹[\d,.]+)\s?(Cr|L)?$/);
  return m ? { value: m[1], unit: m[2] ?? "" } : { value: s, unit: "" };
}

export function fmtCell(v: Cell, fmt: Fmt): string {
  if (v === null || v === undefined || v === "") return "";
  if (typeof v !== "number") return String(v);
  switch (fmt) {
    case "pct":
      return `${dec1.format(v)}%`;
    case "dec":
      return dec2.format(v);
    case "dec1":
      return dec1.format(v);
    case "inr":
    case "inr_full":
      return inr(v);
    case "text":
      return String(v);
    default:
      return fmtInt(v);
  }
}

export function fmtKpi(value: number | string | null, fmt: Fmt): { value: string; unit: string } {
  if (value === null || value === undefined) return { value: "—", unit: "" };
  if (typeof value === "string") return { value, unit: "" };
  switch (fmt) {
    case "pct":
      return { value: dec1.format(value), unit: "%" };
    case "dec1":
      return { value: dec1.format(value), unit: "" };
    case "dec":
      return { value: dec2.format(value), unit: "" };
    case "inr":
      return inrParts(value);
    case "inr_full":
      return { value: inr(value), unit: "" };
    default:
      return { value: fmtInt(value), unit: "" };
  }
}

/** Compact axis label: 12,400 -> 12.4k, 3,20,00,000 rupees -> 3.2 Cr */
export function axisLabel(v: number, money = false): string {
  const a = Math.abs(v);
  if (money) {
    if (a >= 1e7) return `${+(v / 1e7).toFixed(a >= 1e8 ? 0 : 1)} Cr`;
    if (a >= 1e5) return `${+(v / 1e5).toFixed(a >= 1e6 ? 0 : 1)} L`;
    if (a >= 1e3) return `${+(v / 1e3).toFixed(0)}k`;
    return String(v);
  }
  if (a >= 1e6) return `${+(v / 1e6).toFixed(1)}M`;
  if (a >= 1e4) return `${+(v / 1e3).toFixed(0)}k`;
  if (a >= 1e3) return `${+(v / 1e3).toFixed(1)}k`;
  return String(+v.toFixed(2));
}

export function shortMonth(m: string): string {
  const mm = m.match(/^([A-Za-z]+)-(\d{2})$/);
  return mm ? `${mm[1].slice(0, 3)} ${mm[2]}` : m;
}

/** "SHREE FAB" -> "Shree Fab"; short initialisms ("RK", "AS") stay upper case; "(BLANK)" style labels stay as is. */
export function titleCase(s: string): string {
  if (!s || s.startsWith("(") || s === "TOTAL") return s;
  return s
    .split(/(\s+|\/)/)
    .map((w) => ((/^[A-Za-z]{1,2}$/.test(w) || /^[B-DF-HJ-NP-TV-Z]{3,4}$/.test(w)) && w === w.toUpperCase() ? w : w.toLowerCase().replace(/[a-z]/, (c) => c.toUpperCase())))
    .join("");
}

const rel = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
export function ago(iso: string | null, now = Date.now()): string {
  if (!iso) return "never";
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return rel.format(-Math.round(s / 60), "minute");
  return rel.format(-Math.round(s / 3600), "hour");
}

export function clockIST(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", second: "2-digit" });
}
