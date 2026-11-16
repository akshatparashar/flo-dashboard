import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TableData } from "../api/types";
import { DataTable } from "./DataTable";

const table: TableData = {
  title: null,
  note: null,
  key_col: "Pending",
  sorted: true,
  columns: [
    { key: "Fabricator", label: "Fabricator", format: "text" },
    { key: "Pending", label: "Pending", format: "int" },
    { key: "RCVD %", label: "RCVD %", format: "pct", rate: { good: 50, mid: 25 } },
  ],
  rows: [
    ["SHREE FAB", 2320, 72.5],
    ["NAVKAR TEX", 1430, 30],
    ["PRIME CRAFT", 0, 10],
    ["TOTAL", 3750, 41.2],
  ],
  meta: [
    { kind: null, muted: false },
    { kind: null, muted: false },
    { kind: null, muted: false },
    { kind: "total", muted: false },
  ],
};

describe("DataTable", () => {
  it("keeps server order, title-cases names, colours rates and pins TOTAL last", () => {
    render(<DataTable table={table} name="t" />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual(["Shree Fab", "Navkar Tex", "Prime Craft", "TOTAL"]);
    expect(within(rows[0]).getByText("72.5%")).toHaveClass("rate", "good");
    expect(within(rows[1]).getByText("30.0%")).toHaveClass("rate", "mid");
    expect(within(rows[2]).getByText("10.0%")).toHaveClass("rate", "bad");
    expect(rows[3]).toHaveClass("total");
    expect(within(rows[0]).getByText("2,320")).toBeInTheDocument();
  });

  it("re-sorts on header click and never moves the TOTAL row", () => {
    render(<DataTable table={table} name="t" />);
    fireEvent.click(screen.getByRole("button", { name: /Fabricator/ }));
    const names = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
    expect(names).toEqual(["Shree Fab", "Prime Craft", "Navkar Tex", "TOTAL"]);
  });

  it("collapses long tables behind Show all", () => {
    render(<DataTable table={table} name="t" maxRows={2} />);
    expect(screen.getAllByRole("row")).toHaveLength(1 + 2 + 1);
    fireEvent.click(screen.getByRole("button", { name: "Show all 3" }));
    expect(screen.getAllByRole("row")).toHaveLength(1 + 3 + 1);
  });

  it("shows an empty state without columns", () => {
    render(<DataTable table={{ ...table, columns: [], rows: [], meta: [] }} name="t" />);
    expect(screen.getByText("No data for the selected filters.")).toBeInTheDocument();
  });
});
