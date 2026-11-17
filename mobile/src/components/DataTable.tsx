/* Tables on a phone: the first column (designer, vendor, month…) stays put while the figures scroll sideways. Rows
   come in the server's order; tapping a column header sorts by it. TOTAL rows stay pinned at the bottom, rates are
   coloured green / amber / red like on the web, and the key column carries a thin bar. */
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { fmtCell, isNum, titleCase } from "../lib/format";
import { shareCsv } from "../lib/shareCsv";
import { font, useTheme } from "../lib/theme";
import type { Cell, Column, TableData } from "../lib/types";
import { T } from "./ui";

const ROW_H = 42;

function width(col: Column, rows: Cell[][], ci: number): number {
  let longest = Math.min(col.label.length * 7.6, 120);
  for (const r of rows.slice(0, 60)) longest = Math.max(longest, fmtCell(r[ci], col.format).length * 8);
  return Math.min(Math.max(longest + 24, 72), 190);
}

export function DataTable({ table, name, maxRows = 10, titleCaseFirst = true }: { table: TableData; name?: string; maxRows?: number; titleCaseFirst?: boolean }) {
  const c = useTheme();
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);
  const [all, setAll] = useState(false);
  const keyIdx = table.columns.findIndex((col) => col.key === table.key_col);

  const { body, pinned } = useMemo(() => {
    const rows = table.rows.map((r, i) => ({ r, m: table.meta[i] ?? { kind: null, muted: false } }));
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

  const widths = useMemo(() => table.columns.map((col, i) => (i === 0 ? 0 : width(col, table.rows, i))), [table]);
  const barMax = useMemo(
    () => (keyIdx < 0 ? 0 : Math.max(0, ...body.map((x) => (isNum(x.r[keyIdx]) ? Math.abs(x.r[keyIdx] as number) : 0)))),
    [body, keyIdx],
  );

  if (!table.columns.length || !table.rows.length) {
    return (
      <View style={{ padding: 16 }}>
        <T v="small">No data for the selected filters.</T>
      </View>
    );
  }

  const shown = [...(all ? body : body.slice(0, maxRows)), ...pinned];
  const hidden = body.length - Math.min(body.length, all ? body.length : maxRows);
  const first = table.columns[0];
  const toggle = (i: number) => setSort((s) => (s?.col === i ? (s.dir === -1 ? { col: i, dir: 1 } : null) : { col: i, dir: -1 }));
  const arrow = (i: number) => (sort?.col === i ? (sort.dir === -1 ? " ↓" : " ↑") : !sort && i === keyIdx && table.sorted ? " ↓" : "");
  const rowBg = (kind: string | null) => (kind === "total" ? c.well : "transparent");

  const rate = (v: Cell, col: Column, muted: boolean, kind: string | null) => {
    if (!col.rate || !isNum(v) || muted || kind === "ref") return null;
    return v >= col.rate.good ? [c.posSoft, c.posInk] : v >= col.rate.mid ? [c.warnSoft, c.warnInk] : [c.negSoft, c.negInk];
  };

  const headCell = (label: string, i: number, w?: number) => (
    <Pressable
      key={i}
      onPress={() => toggle(i)}
      accessibilityRole="button"
      accessibilityLabel={`Sort by ${label}`}
      style={[st.head, { width: w, borderColor: c.rule }, i === 0 ? { flex: 1 } : { alignItems: "flex-end" }]}
    >
      <Text numberOfLines={2} style={[st.headText, { color: i === keyIdx && !sort ? c.ink : c.muted, width: "100%", textAlign: i === 0 ? "left" : "right" }]}>
        {label}
        {arrow(i)}
      </Text>
    </Pressable>
  );

  return (
    <View>
      <View style={{ flexDirection: "row" }}>
        {/* fixed first column */}
        <View style={{ width: 132, borderRightWidth: StyleSheet.hairlineWidth, borderColor: c.ruleStrong }}>
          {headCell(first.label, 0)}
          {shown.map(({ r, m }, ri) => {
            const v = r[0];
            const text = titleCaseFirst && typeof v === "string" ? titleCase(v) : fmtCell(v, first.format);
            return (
              <View key={ri} style={[st.cell, { borderColor: c.rule, backgroundColor: rowBg(m.kind) }]}>
                <Text numberOfLines={2} style={[st.cellText, { color: m.muted ? c.faint : c.ink, fontFamily: m.kind ? font.uiBold : font.uiMedium, textAlign: "left" }]}>
                  {text}
                </Text>
              </View>
            );
          })}
        </View>
        {/* scrolling figures */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flex: 1 }}>
          <View>
            <View style={{ flexDirection: "row" }}>{table.columns.slice(1).map((col, j) => headCell(col.label, j + 1, widths[j + 1]))}</View>
            {shown.map(({ r, m }, ri) => (
              <View key={ri} style={{ flexDirection: "row", backgroundColor: rowBg(m.kind) }}>
                {table.columns.slice(1).map((col, j) => {
                  const ci = j + 1;
                  const v = r[ci];
                  const text = fmtCell(v, col.format);
                  const rc = rate(v, col, m.muted, m.kind);
                  const isKey = ci === keyIdx && !m.kind;
                  const zero = isNum(v) && v === 0;
                  const textual = col.format === "text" && typeof v === "string" && !/^[\d/.,: -]+$/.test(v);
                  return (
                    <View key={ci} style={[st.cell, { width: widths[ci], borderColor: c.rule, alignItems: textual ? "flex-start" : "flex-end" }]}>
                      {rc ? (
                        <View style={[st.rate, { backgroundColor: rc[0] }]}>
                          <Text style={[st.cellText, { color: rc[1], fontFamily: font.uiBold }]}>{text}</Text>
                        </View>
                      ) : (
                        <Text
                          numberOfLines={2}
                          style={[st.cellText, { width: "100%", textAlign: textual ? "left" : "right", color: zero || m.muted ? c.faint : c.ink, fontFamily: m.kind || isKey ? font.uiBold : font.ui }]}
                        >
                          {text}
                        </Text>
                      )}
                      {isKey && barMax > 0 && isNum(v) && v !== 0 && (
                        <View style={[st.bar, { backgroundColor: c.accent, width: `${(Math.abs(v) / barMax) * 70}%` }]} />
                      )}
                    </View>
                  );
                })}
              </View>
            ))}
          </View>
        </ScrollView>
      </View>
      <View style={[st.foot, { borderColor: c.rule }]}>
        <T v="small" style={{ flex: 1 }}>
          {table.note ?? `${body.length} row${body.length === 1 ? "" : "s"}`}
          {table.columns.length > 3 ? " · swipe for more" : ""}
        </T>
        {(hidden > 0 || (all && body.length > maxRows)) && (
          <Pressable onPress={() => setAll((x) => !x)} hitSlop={8} accessibilityRole="button">
            <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.accent }}>{all ? "Show fewer" : `Show all ${body.length}`}</Text>
          </Pressable>
        )}
        {name && (
          <Pressable onPress={() => shareCsv(name, table).catch(() => undefined)} hitSlop={8} accessibilityRole="button" accessibilityLabel={`Share ${name} as CSV`}>
            <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.accent }}>CSV</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  head: { height: 48, paddingHorizontal: 10, paddingVertical: 8, justifyContent: "flex-end", borderBottomWidth: StyleSheet.hairlineWidth },
  headText: { fontFamily: font.uiBold, fontSize: 12, lineHeight: 15 },
  cell: { height: ROW_H, paddingHorizontal: 10, justifyContent: "center", borderBottomWidth: StyleSheet.hairlineWidth },
  cellText: { fontSize: 13.5, lineHeight: 17, fontVariant: ["tabular-nums"], textAlign: "right" },
  rate: { borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  bar: { position: "absolute", right: 10, bottom: 5, height: 2.5, borderRadius: 2, opacity: 0.55 },
  foot: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 16, paddingVertical: 12 },
});
