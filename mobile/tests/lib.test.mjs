// Unit tests for the app's pure helpers. Run: npm test (Node 22+ loads the .ts sources directly).
import assert from "node:assert/strict";
import { test } from "node:test";
import { ago, clockIST, fmtCell, fmtInt, fmtKpi, inr, inrShort, shortMonth, titleCase } from "../src/lib/format.ts";
import { normalizeServer, toQuery } from "../src/lib/api.ts";

test("numbers read the same as on the web dashboard", () => {
  assert.equal(fmtInt(1234567), "1,234,567");
  assert.equal(fmtInt(2.5), "2"); // half-even, like the server
  assert.equal(fmtInt(3.5), "4");
  assert.equal(fmtInt(-1200), "-1,200");
  assert.equal(inr(5020000), "₹50,20,000");
  assert.equal(inr(-1234.4), "-₹1,234");
  assert.equal(inrShort(50.2e7), "₹50.20 Cr");
  assert.equal(inrShort(329000), "₹3.29 L");
  assert.equal(inrShort(4500), "₹4,500");
  assert.equal(inrShort(123456789012), "₹12,345.68 Cr");
  assert.equal(fmtCell(49.06, "pct"), "49.1%");
  assert.equal(fmtCell(34807.72, "dec"), "34,807.72");
  assert.equal(fmtCell(null, "int"), "");
  assert.equal(fmtCell("RCVD", "text"), "RCVD");
  assert.deepEqual(fmtKpi(217800000, "inr"), { value: "₹21.78", unit: "Cr" });
  assert.deepEqual(fmtKpi(68.66, "pct"), { value: "68.7", unit: "%" });
  assert.deepEqual(fmtKpi(null, "int"), { value: "—", unit: "" });
});

test("labels", () => {
  assert.equal(shortMonth("November-26"), "Nov 26");
  assert.equal(titleCase("SHREE FAB"), "Shree Fab");
  assert.equal(titleCase("AS STITCHCRAFT"), "AS Stitchcraft");
  assert.equal(titleCase("(BLANK)"), "(BLANK)");
  assert.equal(clockIST("2026-11-16T11:34:09+00:00"), "5:04 pm");
  assert.equal(clockIST("2026-11-16T18:40:00+00:00"), "12:10 am");
  const now = Date.parse("2026-11-16T12:00:00Z");
  assert.equal(ago("2026-11-16T11:59:58Z", now), "just now");
  assert.equal(ago("2026-11-16T11:58:00Z", now), "2 min ago");
});

test("server address and query string", () => {
  assert.equal(normalizeServer("flo-dashboard.vercel.app/"), "https://flo-dashboard.vercel.app");
  assert.equal(normalizeServer(" https://x.example.com/api "), "https://x.example.com");
  assert.equal(normalizeServer("http://192.168.1.5:8000"), "http://192.168.1.5:8000");
  assert.equal(toQuery({ month: ["April-26", "May-26"], risk: "", designer: [] }), "?month=April-26&month=May-26");
  assert.equal(toQuery({ q: "A & B" }), "?q=A%20%26%20B");
});

test("CSV export matches the website's file", async () => {
  const { toCsv } = await import("../src/lib/csv.ts");
  const table = {
    columns: [{ label: "Vendor" }, { label: "Value, ₹" }, { label: "Note" }],
    rows: [["SHREE FAB", 1234.567, "=SUM(A1)"], ["A \"B\"", -5, null]],
  };
  assert.equal(toCsv(table), 'Vendor,"Value, ₹",Note\r\nSHREE FAB,1234.57,\'=SUM(A1)\r\n"A ""B""",-5,');
});
