/* Charts sized for a phone. Colour follows meaning (see colorFor): blue = received / approved / achieved, navy = the
   reference (ordered, target), red = pending / overdue / rejected. Tapping a month shows its exact figures under the
   chart, so nothing depends on hover. */
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View, type LayoutChangeEvent } from "react-native";
import Svg, { G, Line, Rect, Text as SvgText } from "react-native-svg";
import { axisLabel, fmtInt, inrShort, isNum, shortMonth, titleCase } from "../lib/format";
import { colorFor, font, useTheme } from "../lib/theme";
import type { SeriesChart, Slice } from "../lib/types";
import { T } from "./ui";

type Unit = "pcs" | "mtr" | "POs" | "inr" | "pct" | "";

export function fmtValue(v: number, unit: Unit): string {
  if (unit === "inr") return inrShort(v);
  if (unit === "pct") return `${v.toFixed(1)}%`;
  return `${fmtInt(v)}${unit ? ` ${unit}` : ""}`;
}

function niceMax(max: number): { top: number; ticks: number[] } {
  if (!(max > 0)) return { top: 1, ticks: [0, 1] };
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const top = Math.ceil((max * 1.04) / step) * step;
  const ticks: number[] = [];
  for (let t = 0; t <= top + step / 2; t += step) ticks.push(t);
  return { top, ticks };
}

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  if (items.length < 2) return null;
  return (
    <View style={st.legend}>
      {items.map((it) => (
        <View key={it.name} style={st.legendItem}>
          <View style={[st.swatch, { backgroundColor: it.color }]} />
          <T v="small" style={{ fontSize: 12 }}>{it.name}</T>
        </View>
      ))}
    </View>
  );
}

/** Vertical bars by month (or any short category): grouped, or stacked when the series add up. */
export function Bars({ data, unit = "", stacked = false, height = 190 }: { data: SeriesChart; unit?: Unit; stacked?: boolean; height?: number }) {
  const c = useTheme();
  const [w, setW] = useState(0);
  const [sel, setSel] = useState<number | null>(null);
  const series = data.series.filter((s) => s.values.some((v) => isNum(v) && v !== 0));
  // trailing months with no data at all (the rest of the year) are not drawn
  let n = data.categories.length;
  while (n > 1 && series.every((s) => !isNum(s.values[n - 1]) || s.values[n - 1] === 0)) n--;
  const cats = data.categories.slice(0, n);
  const colors = series.map((s, i) => colorFor(s.name, i, c));
  const totals = cats.map((_, i) => series.reduce((a, s) => a + Math.max(0, s.values[i] ?? 0), 0));
  const max = stacked ? Math.max(0, ...totals) : Math.max(0, ...series.flatMap((s) => s.values.slice(0, n).filter(isNum)));
  const { top, ticks } = niceMax(max);
  const left = 40;
  const bottom = 22;
  const plotW = Math.max(0, w - left - 4);
  const plotH = height - bottom - 8;
  const band = cats.length ? plotW / cats.length : 0;
  const y = (v: number) => 8 + plotH - (v / top) * plotH;
  const step = Math.max(1, Math.ceil(cats.length / Math.max(1, Math.floor(plotW / 44))));
  const money = unit === "inr";

  if (!series.length) return <T v="small">Nothing to show for the selected filters.</T>;

  return (
    <View>
      <View onLayout={(e: LayoutChangeEvent) => setW(Math.floor(e.nativeEvent.layout.width))} style={{ height }}>
        {w > 0 && (
          <Svg width={w} height={height} accessibilityLabel={`${series.map((s) => s.name).join(", ")} by month`}>
            {ticks.map((t) => (
              <G key={t}>
                <Line x1={left} x2={w} y1={y(t)} y2={y(t)} stroke={c.grid} strokeWidth={1} />
                <SvgText x={left - 6} y={y(t) + 4} fontSize={10.5} fill={c.faint} textAnchor="end" fontFamily={font.ui}>
                  {axisLabel(t, money)}
                </SvgText>
              </G>
            ))}
            {cats.map((cat, i) => {
              const x0 = left + i * band;
              const pad = Math.min(band * 0.18, 8);
              const inner = band - pad * 2;
              const dim = sel !== null && sel !== i ? 0.35 : 1;
              let acc = 0;
              return (
                <G key={cat} opacity={dim}>
                  {series.map((s, si) => {
                    const v = Math.max(0, s.values[i] ?? 0);
                    if (!v) return null;
                    if (stacked) {
                      const yTop = y(acc + v);
                      const h = y(acc) - yTop;
                      acc += v;
                      return <Rect key={si} x={x0 + pad} y={yTop} width={inner} height={Math.max(h, 0.5)} fill={colors[si]} rx={si === series.length - 1 ? 2 : 0} />;
                    }
                    const bw = inner / series.length;
                    return <Rect key={si} x={x0 + pad + si * bw} y={y(v)} width={Math.max(bw - 1, 1)} height={Math.max(y(0) - y(v), 0.5)} fill={colors[si]} rx={1.5} />;
                  })}
                  {i % step === 0 && (
                    <SvgText x={x0 + band / 2} y={height - 6} fontSize={10.5} fill={sel === i ? c.ink : c.muted} textAnchor="middle" fontFamily={font.ui}>
                      {shortMonth(cat)}
                    </SvgText>
                  )}
                </G>
              );
            })}
          </Svg>
        )}
        {/* tap targets over each month */}
        <View style={[StyleSheet.absoluteFill, { flexDirection: "row", paddingLeft: left }]}>
          {cats.map((cat, i) => (
            <Pressable
              key={cat}
              style={{ flex: 1 }}
              onPress={() => setSel((s) => (s === i ? null : i))}
              accessibilityRole="button"
              accessibilityLabel={`${cat}: ${series.map((s) => `${s.name} ${fmtValue(s.values[i] ?? 0, unit)}`).join(", ")}`}
            />
          ))}
        </View>
      </View>
      {sel !== null ? (
        <View style={[st.readout, { backgroundColor: c.well }]}>
          <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.ink }}>{cats[sel]}</Text>
          {series.map((s, si) => (
            <View key={s.name} style={st.legendItem}>
              <View style={[st.swatch, { backgroundColor: colors[si] }]} />
              <T v="small" style={{ fontSize: 12.5 }}>
                {s.name} <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{fmtValue(s.values[sel] ?? 0, unit)}</Text>
              </T>
            </View>
          ))}
        </View>
      ) : (
        <Legend items={series.map((s, i) => ({ name: s.name, color: colors[i] }))} />
      )}
    </View>
  );
}

/** A ranked list with bars: best for names (fabricators, vendors, designers) on a narrow screen. */
export function BarList({ items, unit = "", tone = "accent", max = 8 }: { items: Slice[]; unit?: Unit; tone?: "accent" | "neg"; max?: number }) {
  const c = useTheme();
  const [all, setAll] = useState(false);
  const rows = useMemo(() => [...items].filter((x) => isNum(x.value)).sort((a, b) => b.value - a.value), [items]);
  const top = Math.max(0, ...rows.map((r) => r.value));
  const shown = all ? rows : rows.slice(0, max);
  if (!rows.length) return <T v="small">Nothing to show.</T>;
  return (
    <View style={{ gap: 12 }}>
      {shown.map((r) => (
        <View key={r.label} style={{ gap: 5 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
            <T v="body" numberOfLines={1} style={{ flex: 1, fontSize: 14, color: c.ink }}>{titleCase(r.label)}</T>
            <T v="strong" style={{ fontSize: 14, fontVariant: ["tabular-nums"] }}>{fmtValue(r.value, unit)}</T>
          </View>
          <View style={[st.track, { backgroundColor: c.well }]}>
            <View style={{ width: `${top ? (r.value / top) * 100 : 0}%`, height: "100%", borderRadius: 4, backgroundColor: tone === "neg" ? c.neg : c.accent }} />
          </View>
        </View>
      ))}
      {rows.length > max && (
        <Pressable onPress={() => setAll((x) => !x)} hitSlop={8} accessibilityRole="button">
          <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.accent }}>{all ? "Show fewer" : `Show all ${rows.length}`}</Text>
        </Pressable>
      )}
    </View>
  );
}

/** Horizontal stacked bars per name (e.g. received + pending per fabricator), largest `sortBy` first. */
export function StackedList({ data, unit = "", sortBy, max = 8 }: { data: SeriesChart; unit?: Unit; sortBy?: string; max?: number }) {
  const c = useTheme();
  const series = data.series;
  const key = series.findIndex((s) => s.name === sortBy);
  const rows = data.categories
    .map((name, i) => ({ name, vals: series.map((s) => Math.max(0, s.values[i] ?? 0)) }))
    .sort((a, b) => (key >= 0 ? b.vals[key] - a.vals[key] : b.vals.reduce((x, y) => x + y, 0) - a.vals.reduce((x, y) => x + y, 0)))
    .slice(0, max);
  const top = Math.max(0, ...rows.map((r) => r.vals.reduce((x, y) => x + y, 0)));
  const colors = series.map((s, i) => colorFor(s.name, i, c));
  return (
    <View style={{ gap: 12 }}>
      {rows.map((r) => (
        <View key={r.name} style={{ gap: 5 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
            <T numberOfLines={1} style={{ flex: 1, fontSize: 14, color: c.ink }}>{titleCase(r.name)}</T>
            <T v="small" style={{ fontVariant: ["tabular-nums"] }}>
              {r.vals.map((v, i) => fmtValue(v, unit === "inr" || i === r.vals.length - 1 ? unit : "")).join(" · ")}
            </T>
          </View>
          <View style={[st.track, { backgroundColor: c.well, flexDirection: "row", overflow: "hidden" }]}>
            {r.vals.map((v, i) => (
              <View key={i} style={{ width: `${top ? (v / top) * 100 : 0}%`, backgroundColor: colors[i] }} />
            ))}
          </View>
        </View>
      ))}
      <Legend items={series.map((s, i) => ({ name: s.name, color: colors[i] }))} />
    </View>
  );
}

const SPLIT: Record<string, "accent" | "neg" | "ref" | "pale" | "grey" | "warn"> = {
  "On Time": "accent", Delayed: "warn", "Overdue (Pending)": "neg", "Open (Within Deadline)": "pale", "No Date": "grey", Cancelled: "grey",
};

/** Shares of one whole as a single segmented bar with a labelled list (e.g. POs by delivery status). */
export function Split({ items, unit = "" }: { items: Slice[]; unit?: Unit }) {
  const c = useTheme();
  const rows = items.filter((x) => isNum(x.value) && x.value > 0);
  const total = rows.reduce((a, x) => a + x.value, 0);
  const tone = { accent: c.accent, neg: c.neg, ref: c.seriesRef, pale: c.seriesPale, grey: c.seriesGrey, warn: c.warn };
  const color = (label: string, i: number) => (SPLIT[label] ? tone[SPLIT[label]] : colorFor(label, i, c));
  if (!total) return <T v="small">Nothing to show.</T>;
  return (
    <View style={{ gap: 12 }}>
      <View style={[st.split, { backgroundColor: c.well }]}>
        {rows.map((x, i) => (
          <View key={x.label} style={{ flex: x.value, backgroundColor: color(x.label, i) }} />
        ))}
      </View>
      {rows.map((x, i) => (
        <View key={x.label} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <View style={[st.swatch, { backgroundColor: color(x.label, i) }]} />
          <T style={{ flex: 1, fontSize: 14, color: c.ink }} numberOfLines={1}>{titleCase(x.label)}</T>
          <T v="strong" style={{ fontSize: 14, fontVariant: ["tabular-nums"] }}>{fmtValue(x.value, unit)}</T>
          <T v="small" style={{ width: 52, textAlign: "right", fontVariant: ["tabular-nums"] }}>{((x.value / total) * 100).toFixed(1)}%</T>
        </View>
      ))}
    </View>
  );
}

/** Progress toward the yearly target, with a tick where the schedule says we should be today. */
export function TargetBar({ achieved, target, scheduled }: { achieved: number; target: number; scheduled?: number }) {
  const c = useTheme();
  const pct = target > 0 ? Math.min(achieved / target, 1) : 0;
  const tick = target > 0 && scheduled ? Math.min(scheduled / target, 1) : null;
  return (
    <View style={{ gap: 8 }}>
      <View style={[st.target, { backgroundColor: c.well }]}>
        <View style={{ width: `${pct * 100}%`, height: "100%", borderRadius: 8, backgroundColor: c.accent }} />
        {tick !== null && <View style={[st.tick, { left: `${tick * 100}%`, backgroundColor: c.ink }]} />}
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <T v="small">
          Achieved <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{inrShort(achieved)}</Text>
        </T>
        <T v="small">
          Target <Text style={{ fontFamily: font.uiBold, color: c.ink }}>{inrShort(target)}</Text>
        </T>
      </View>
      {tick !== null && <T v="small" style={{ fontSize: 12 }}>The black tick marks where the schedule says we should be today ({inrShort(scheduled ?? 0)}).</T>}
    </View>
  );
}

const st = StyleSheet.create({
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 10 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  swatch: { width: 10, height: 10, borderRadius: 3 },
  readout: { marginTop: 10, borderRadius: 10, padding: 10, gap: 4 },
  track: { height: 8, borderRadius: 4 },
  split: { flexDirection: "row", height: 14, borderRadius: 7, overflow: "hidden", gap: 2 },
  target: { height: 16, borderRadius: 8, overflow: "visible", justifyContent: "center" },
  tick: { position: "absolute", width: 2.5, height: 26, top: -5, borderRadius: 1 },
});
