import { describe, expect, it, beforeEach } from "vitest";
import type { Meta, TableData } from "../api/types";
import { toQuery } from "../api/client";
import { toCsv } from "./csv";
import { describeMonths, monthRange } from "./filters";
import { ago, fmtCell, fmtInt, fmtKpi, inr, inrShort, shortMonth, titleCase } from "./format";
import { _resetLive, getLive, reportMeta } from "./live";

describe("format", () => {
  it("formats rupees like the original dashboard", () => {
    expect(inr(5020000)).toBe("₹50,20,000");
    expect(inr(-1234.4)).toBe("-₹1,234");
    expect(inr(999)).toBe("₹999");
    expect(inrShort(50.2e7)).toBe("₹50.20 Cr");
    expect(inrShort(329000)).toBe("₹3.29 L");
    expect(inrShort(4500)).toBe("₹4,500");
  });

  it("rounds counts half-to-even like Python", () => {
    expect(fmtInt(2.5)).toBe("2");
    expect(fmtInt(3.5)).toBe("4");
    expect(fmtInt(1234567)).toBe("1,234,567");
    expect(fmtInt(-0.2)).toBe("0");
  });

  it("formats table cells by column format", () => {
    expect(fmtCell(45.678, "pct")).toBe("45.7%");
    expect(fmtCell(1234.5, "dec")).toBe("1,234.50");
    expect(fmtCell(null, "int")).toBe("");
    expect(fmtCell("TOTAL", "text")).toBe("TOTAL");
    expect(fmtKpi(62.81, "pct")).toEqual({ value: "62.8", unit: "%" });
    expect(fmtKpi(31.51e7, "inr")).toEqual({ value: "₹31.51", unit: "Cr" });
    expect(fmtKpi(null, "int")).toEqual({ value: "—", unit: "" });
  });

  it("title-cases sheet names without breaking initialisms", () => {
    expect(titleCase("SHREE FAB")).toBe("Shree Fab");
    expect(titleCase("RK GARMENTS")).toBe("RK Garments");
    expect(titleCase("CO-ORD SET")).toBe("Co-ord Set");
    expect(titleCase("RFS")).toBe("RFS");
    expect(titleCase("TOP")).toBe("Top");
    expect(titleCase("(NOT ASSIGNED)")).toBe("(NOT ASSIGNED)");
    expect(titleCase("OPEN (WITHIN DEADLINE)")).toBe("Open (Within Deadline)");
  });

  it("shortens month labels and relative times", () => {
    expect(shortMonth("April-26")).toBe("Apr 26");
    expect(shortMonth("(NO DATE)")).toBe("(NO DATE)");
    const now = Date.parse("2026-11-16T10:00:00Z");
    expect(ago("2026-11-16T09:59:58Z", now)).toBe("just now");
    expect(ago("2026-11-16T09:59:30Z", now)).toBe("30s ago");
    expect(ago(null, now)).toBe("never");
  });
});

describe("filters", () => {
  const months = ["April-26", "May-26", "June-26", "July-26"];
  it("builds inclusive ranges in either direction", () => {
    expect(monthRange(months, "May-26", "July-26")).toEqual(["May-26", "June-26", "July-26"]);
    expect(monthRange(months, "July-26", "May-26")).toEqual(["May-26", "June-26", "July-26"]);
    expect(monthRange(months, "x", "May-26")).toEqual([]);
  });
  it("describes a selection", () => {
    expect(describeMonths([], months, shortMonth)).toBe("All months");
    expect(describeMonths(["May-26", "June-26", "July-26"], months, shortMonth)).toBe("May 26 – Jul 26");
    expect(describeMonths(["April-26", "July-26"], months, shortMonth)).toBe("Apr 26, Jul 26");
  });
  it("repeats list params in the query string", () => {
    expect(toQuery({ month: ["April-26", "May-26"], metric: "RCVD (Pcs)", empty: [], none: undefined })).toBe(
      "?month=April-26&month=May-26&metric=RCVD+%28Pcs%29",
    );
  });
});

describe("csv", () => {
  it("exports raw values, escapes quotes and blocks formula injection", () => {
    const t: TableData = {
      title: null,
      note: null,
      key_col: null,
      sorted: false,
      columns: [
        { key: "Name", label: "Name", format: "text" },
        { key: "Qty", label: "Qty", format: "int" },
      ],
      rows: [
        ['Mehr & Co, "A"', 1234.567],
        ["=HYPERLINK()", -5],
      ],
      meta: [
        { kind: null, muted: false },
        { kind: null, muted: false },
      ],
    };
    expect(toCsv(t)).toBe('Name,Qty\r\n"Mehr & Co, ""A""",1234.57\r\n\'=HYPERLINK(),-5');
  });
});

describe("live pulses", () => {
  beforeEach(() => _resetLive());
  const meta = (v: string): Meta => ({
    fy: "FY 2026-27",
    fy_months: [],
    source: "demo",
    ttl: 60,
    server_time: "",
    synced_at: null,
    version: v,
    stale: false,
    sources: [{ source: "tracker", synced_at: null, version: v, stale: false, error: null }],
  });
  it("fires only when a data version really changes", () => {
    reportMeta(meta("a"));
    expect(getLive().pulses).toBe(0);
    reportMeta(meta("a"));
    expect(getLive().pulses).toBe(0);
    reportMeta(meta("b"));
    expect(getLive().pulses).toBe(1);
    expect(getLive().changedSources).toEqual(["tracker"]);
    reportMeta(meta("b"));
    expect(getLive().pulses).toBe(1);
  });
});
