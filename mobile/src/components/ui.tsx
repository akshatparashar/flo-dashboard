/* Building blocks shared by every screen: type, cards, KPI tiles, notices, loading and error states. */
import { useEffect, useState, type ReactNode } from "react";
import { Animated, Platform, Pressable, StyleSheet, Text, View, type StyleProp, type TextProps, type TextStyle, type ViewStyle } from "react-native";
import { fmtKpi } from "../lib/format";
import { font, useTheme } from "../lib/theme";
import type { Kpi, Notice as NoticeT } from "../lib/types";

type Variant = "body" | "small" | "label" | "title" | "display" | "kpi" | "strong";

export function T({ v = "body", color, style, ...rest }: TextProps & { v?: Variant; color?: string }) {
  const c = useTheme();
  const styles: Record<Variant, TextStyle> = {
    body: { fontFamily: font.ui, fontSize: 15, lineHeight: 21, color: c.ink2 },
    small: { fontFamily: font.ui, fontSize: 13, lineHeight: 18, color: c.muted },
    label: { fontFamily: font.uiMedium, fontSize: 12.5, lineHeight: 16, color: c.muted, letterSpacing: 0.2 },
    strong: { fontFamily: font.uiBold, fontSize: 15, lineHeight: 21, color: c.ink },
    title: { fontFamily: font.uiBold, fontSize: 16, lineHeight: 21, color: c.ink },
    display: { fontFamily: font.display, fontSize: 32, lineHeight: 38, color: c.brand, letterSpacing: -0.3 },
    kpi: { fontFamily: font.uiBold, fontSize: 22, lineHeight: 27, color: c.ink, fontVariant: ["tabular-nums"] },
  };
  const base = styles[v];
  return <Text {...rest} style={[base, color ? { color } : null, style]} />;
}

export function Card({ children, style, flush }: { children: ReactNode; style?: StyleProp<ViewStyle>; flush?: boolean }) {
  const c = useTheme();
  return (
    <View style={[s.card, { backgroundColor: c.sheet, borderColor: c.sheetEdge }, flush ? { padding: 0, overflow: "hidden" } : null, style]}>
      {children}
    </View>
  );
}

export function Panel({ title, sub, right, children, flush }: { title?: string; sub?: string; right?: ReactNode; children: ReactNode; flush?: boolean }) {
  return (
    <Card flush={flush}>
      {(title || right) && (
        <View style={[s.panelHead, flush ? { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 10 } : null]}>
          <View style={{ flex: 1 }}>
            {title && <T v="title">{title}</T>}
            {sub && <T v="small">{sub}</T>}
          </View>
          {right}
        </View>
      )}
      {children}
    </Card>
  );
}

export function Section({ title, sub, action, children }: { title: string; sub?: string; action?: ReactNode; children: ReactNode }) {
  const c = useTheme();
  return (
    <View style={s.section}>
      <View style={s.sectionHead}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: font.display, fontSize: 22, lineHeight: 28, color: c.brand }}>{title}</Text>
          {sub && <T v="small">{sub}</T>}
        </View>
        {action}
      </View>
      <View style={{ gap: 12 }}>{children}</View>
    </View>
  );
}

function KpiTile({ k, lead }: { k: Kpi; lead?: boolean }) {
  const c = useTheme();
  const f = fmtKpi(k.value, k.format);
  const unit = f.unit || (k.unit && k.format !== "pct" && typeof k.value === "number" ? k.unit : "");
  const color = k.tone === "alert" && typeof k.value === "number" && k.value > 0 ? c.neg : k.tone === "good" ? c.pos : c.ink;
  const isText = typeof k.value === "string";
  return (
    <View
      style={[s.kpi, { backgroundColor: c.sheet, borderColor: lead ? c.ruleStrong : c.sheetEdge }, lead ? s.kpiLead : null]}
      accessible
      accessibilityLabel={`${k.label}: ${f.value} ${unit}`}
    >
      <T v="label" numberOfLines={2}>{k.label}</T>
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: 4, flexWrap: "wrap" }}>
        <T v="kpi" color={color} style={[lead ? { fontSize: 30, lineHeight: 36 } : null, isText ? { fontSize: 17, lineHeight: 22 } : null]} numberOfLines={isText ? 2 : 1} adjustsFontSizeToFit={!isText}>
          {f.value}
        </T>
        {!!unit && <T v="small" style={{ fontFamily: font.uiMedium }}>{unit}</T>}
      </View>
      {!!k.hint && !/^(sheet )?col(umn)?s? [A-Z]/i.test(k.hint) && (
        <T v="small" numberOfLines={2} style={{ fontSize: 12, lineHeight: 16 }}>{k.hint}</T>
      )}
    </View>
  );
}

/** Two tiles per row; the KPIs named in `lead` get a full-width tile so the figure that matters reads first. */
export function KpiGrid({ kpis, lead = [] }: { kpis: Kpi[]; lead?: string[] }) {
  const first = kpis.filter((k) => lead.includes(k.id));
  const rest = kpis.filter((k) => !lead.includes(k.id));
  return (
    <View style={{ gap: 10 }}>
      {first.map((k) => (
        <KpiTile key={k.id} k={k} lead />
      ))}
      <View style={s.kpiGrid}>
        {rest.map((k) => (
          <View key={k.id} style={s.kpiCell}>
            <KpiTile k={k} />
          </View>
        ))}
      </View>
    </View>
  );
}

export function Notices({ items }: { items?: NoticeT[] }) {
  const c = useTheme();
  if (!items?.length) return null;
  const tone = { error: [c.negSoft, c.negInk], warning: [c.warnSoft, c.warnInk], success: [c.posSoft, c.posInk], info: [c.accentSoft, c.ink2] };
  return (
    <View style={{ gap: 8 }}>
      {items.map((n, i) => (
        <View key={i} style={[s.notice, { backgroundColor: tone[n.kind][0] }]}>
          <T v="small" color={tone[n.kind][1]}>{n.text}</T>
        </View>
      ))}
    </View>
  );
}

export function Button({ label, onPress, kind = "default", disabled, icon }: { label: string; onPress: () => void; kind?: "default" | "primary" | "ghost"; disabled?: boolean; icon?: ReactNode }) {
  const c = useTheme();
  const bg = kind === "primary" ? c.brand : kind === "ghost" ? "transparent" : c.control;
  const fg = kind === "primary" ? c.onBrand : c.ink;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      style={({ pressed }) => [
        s.btn,
        { backgroundColor: bg, borderColor: kind === "default" ? c.controlEdge : "transparent", opacity: disabled ? 0.45 : pressed ? 0.8 : 1 },
      ]}
    >
      {icon}
      <Text style={{ fontFamily: font.uiBold, fontSize: 15, color: fg }}>{label}</Text>
    </Pressable>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card style={{ alignItems: "flex-start", gap: 10, marginTop: 8 }}>
      <T v="title">Couldn’t load this page</T>
      <T>{message}</T>
      <Button label="Try again" onPress={onRetry} />
    </Card>
  );
}

export function Empty({ title, text }: { title: string; text?: string }) {
  return (
    <Card style={{ gap: 6 }}>
      <T v="title">{title}</T>
      {text && <T>{text}</T>}
    </Card>
  );
}

/** Grey placeholder blocks with a soft pulse while the first data arrives. */
export function Skeleton() {
  const c = useTheme();
  const [a] = useState(() => new Animated.Value(0.5));
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(a, { toValue: 1, duration: 700, useNativeDriver: Platform.OS !== "web" }),
        Animated.timing(a, { toValue: 0.5, duration: 700, useNativeDriver: Platform.OS !== "web" }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [a]);
  const block = (h: number, w: number | `${number}%` = "100%") => <View style={{ height: h, width: w, borderRadius: 12, backgroundColor: c.sheetEdge }} />;
  return (
    <Animated.View style={{ opacity: a, gap: 12 }} accessibilityLabel="Loading">
      {block(18, "70%")}
      {block(96)}
      <View style={{ flexDirection: "row", gap: 10 }}>
        <View style={{ flex: 1 }}>{block(84)}</View>
        <View style={{ flex: 1 }}>{block(84)}</View>
      </View>
      <View style={{ flexDirection: "row", gap: 10 }}>
        <View style={{ flex: 1 }}>{block(84)}</View>
        <View style={{ flex: 1 }}>{block(84)}</View>
      </View>
      {block(220)}
    </Animated.View>
  );
}

const s = StyleSheet.create({
  card: { borderRadius: 16, borderWidth: StyleSheet.hairlineWidth, padding: 16 },
  panelHead: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginBottom: 12 },
  section: { marginTop: 28, gap: 12 },
  sectionHead: { flexDirection: "row", alignItems: "flex-end", gap: 8 },
  kpiGrid: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -5, rowGap: 10 },
  kpiCell: { width: "50%", paddingHorizontal: 5 },
  kpi: { borderRadius: 14, borderWidth: StyleSheet.hairlineWidth, padding: 14, gap: 6, flexGrow: 1, minHeight: 92 },
  kpiLead: { paddingVertical: 16 },
  notice: { borderRadius: 12, paddingVertical: 10, paddingHorizontal: 12 },
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, minHeight: 44, paddingHorizontal: 16, borderRadius: 12, borderWidth: 1 },
});
