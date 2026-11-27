/* Welcome: the FLO front door, as on the web (/welcome). A needle stitches a thread through the FLO letters, then the
   headline, live figures from the sheets, the thread from design to delivery with a link to each page, the 22 labels
   and the house. "Enter the FLO world" opens the label hub; "Open dashboard" goes straight to the numbers. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, type Href } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { AccessibilityInfo, Animated, Easing, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { T } from "../components/ui";
import { fmtKpi } from "../lib/format";
import { useDashboard, useStatus } from "../lib/query";
import { font, useTheme } from "../lib/theme";
import type { Kpi, OverviewData } from "../lib/types";
import { DASHBOARD, LABELS, LOGO_RATIO, type Label } from "../world/brands";
import { NeedleFLO } from "../world/NeedleFLO";
import { LogoMark, openPage, syncLine } from "../world/parts";

const STAGES = [
  {
    name: "Design",
    line: "Designers sketch, clients choose, and the target shows who is ahead this month.",
    pages: [
      { to: "/designers", label: "Designers" },
      { to: "/target", label: "Designer order target" },
      { to: "/clients", label: "Clients order status" },
    ],
  },
  { name: "Sample", line: "Every sample is followed from cutting to approval, by designer and by date.", pages: [{ to: "/samples", label: "Samples" }] },
  {
    name: "Fabric",
    line: "Fabric is ordered, received and priced vendor by vendor, with every late PO in view.",
    pages: [
      { to: "/fabric-po", label: "Fabric PO" },
      { to: "/vendor-rate", label: "Vendor rate" },
    ],
  },
  {
    name: "Production",
    line: "Fabricators stitch; each piece is counted out, counted back and aged in stock.",
    pages: [
      { to: "/production", label: "Production" },
      { to: "/fabricators", label: "Fabricators" },
      { to: "/stock-ageing", label: "Stock ageing" },
    ],
  },
  {
    name: "Delivery",
    line: "Promises kept on time, sales in and out, and the day's work handed to the right person.",
    pages: [
      { to: "/flo-future", label: "FLO Future" },
      { to: "/in-out-sale", label: "In/Out sale" },
      { to: "/daily-delegation", label: "Daily delegation" },
    ],
  },
];

const FOOT = [
  {
    title: "Operations",
    links: [
      { to: "/", label: "Overview" },
      { to: "/production", label: "Production" },
      { to: "/fabricators", label: "Fabricators" },
      { to: "/fabric-po", label: "Fabric PO" },
      { to: "/stock-ageing", label: "Stock ageing" },
    ],
  },
  {
    title: "Design and sales",
    links: [
      { to: "/designers", label: "Designers" },
      { to: "/clients", label: "Clients order status" },
      { to: "/samples", label: "Samples" },
      { to: "/target", label: "Designer order target" },
      { to: "/flo-future", label: "FLO Future" },
    ],
  },
];

const ASK = ["Which fabric POs are overdue?", "How many orders are pending with fabricators?", "Aaj ka pending kaam"];

function pickCards(o: OverviewData | undefined): { kpi: Kpi; to: string; area: string }[] {
  if (!o) return [];
  const s = o.sections;
  const out: { kpi: Kpi; to: string; area: string }[] = [];
  const add = (k: Kpi | undefined, to: string, area: string) => k && out.push({ kpi: k, to, area });
  add(s.orders?.kpis[0], "/production", "Orders");
  add(s.orders?.kpis[1], "/production", "Orders");
  add(s.po?.kpis[0], "/fabric-po", "Fabric");
  add(s.samples?.kpis[0], "/samples", "Samples");
  add(s.stock?.kpis[0], "/fabricators", "Fabricators");
  add(s.flo_future?.kpis.find((k) => k.id === "done_pct"), "/flo-future", "FLO Future");
  return out;
}

/** One row of label logos drifting sideways forever (the set is drawn twice so the loop has no seam). */
function Marquee({ list, reverse, reduce }: { list: Label[]; reverse?: boolean; reduce: boolean }) {
  const c = useTheme();
  const w = 116;
  const gap = 14;
  const span = list.length * (w + gap);
  const [x] = useState(() => new Animated.Value(0));
  useEffect(() => {
    if (reduce) return;
    const loop = Animated.loop(Animated.timing(x, { toValue: 1, duration: list.length * 2600, easing: Easing.linear, useNativeDriver: true }));
    loop.start();
    return () => loop.stop();
  }, [x, list.length, reduce]);
  const translateX = x.interpolate({ inputRange: [0, 1], outputRange: reverse ? [-span, 0] : [0, -span] });
  return (
    <View style={{ overflow: "hidden", marginHorizontal: -16 }}>
      <Animated.View style={{ flexDirection: "row", gap, transform: [{ translateX }] }}>
        {[...list, ...list].map((l, i) => (
          <View key={l.slug + i} style={[st.mq, { width: w, height: w / LOGO_RATIO + 20, backgroundColor: c.sheet, borderColor: c.sheetEdge }]} importantForAccessibility={i >= list.length ? "no-hide-descendants" : "auto"}>
            <LogoMark label={l} width={w - 24} />
          </View>
        ))}
      </Animated.View>
    </View>
  );
}

export default function Welcome() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const status = useStatus();
  const overview = useDashboard<OverviewData>("/overview", {});
  const cards = useMemo(() => pickCards(overview.data), [overview.data]);
  const sync = syncLine(status.data);
  const [reduce, setReduce] = useState(false);
  const [copy] = useState(() => new Animated.Value(0));

  useEffect(() => {
    void AccessibilityInfo.isReduceMotionEnabled().then(setReduce);
  }, []);

  const showCopy = () => Animated.timing(copy, { toValue: 1, duration: 900, easing: Easing.out(Easing.exp), useNativeDriver: true }).start();
  const rise = (d: number) => ({
    opacity: copy.interpolate({ inputRange: [d, Math.min(1, d + 0.5)], outputRange: [0, 1], extrapolate: "clamp" }),
    transform: [{ translateY: copy.interpolate({ inputRange: [d, Math.min(1, d + 0.5)], outputRange: [18, 0], extrapolate: "clamp" }) }],
  });
  const enterWorld = () => router.push("/world" as Href);
  const flo = Math.min(width - 32, 520);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: c.frame }} contentContainerStyle={{ paddingTop: insets.top + 10, paddingBottom: 0 }}>
      <View style={st.nav}>
        <Text style={{ fontFamily: font.uiBold, fontSize: 11.5, letterSpacing: 1.6, color: c.muted }}>FLO INDIA</Text>
        <Pressable onPress={() => openPage("/")} accessibilityRole="button" style={({ pressed }) => [st.ghost, { borderColor: c.controlEdge, opacity: pressed ? 0.7 : 1 }]}>
          <Text style={{ fontFamily: font.uiBold, fontSize: 13.5, color: c.ink }}>Open dashboard</Text>
        </Pressable>
      </View>

      {/* hero */}
      <View style={st.hero}>
        <NeedleFLO width={flo} onDone={showCopy} />
        <Animated.Text style={[st.line, { color: c.brand }, rise(0)]} accessibilityRole="header">
          Let the fashion flo.
        </Animated.Text>
        <Animated.View style={rise(0.25)}>
          <T style={{ textAlign: "center", fontSize: 16, lineHeight: 23, maxWidth: 420 }}>
            FLO India&apos;s own intelligence. Every order, sample, fabric roll and delivery, read live from the sheets and answered in one place.
          </T>
        </Animated.View>
        <Animated.View style={rise(0.45)}>
          <Pressable onPress={enterWorld} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: c.brand, opacity: pressed ? 0.85 : 1 }]}>
            <Text style={{ fontFamily: font.uiBold, fontSize: 16, color: c.onBrand }}>Enter the FLO world</Text>
            <Ionicons name="arrow-forward" size={18} color={c.onBrand} />
          </Pressable>
        </Animated.View>
        <Animated.View style={[st.corners, rise(0.6)]}>
          <T v="small" style={{ fontSize: 12 }}>
            Fashion, lifestyle, outfit{"\n"}Jaipur, India
          </T>
          <View style={{ flexDirection: "row", gap: 7, alignItems: "flex-start" }}>
            <View style={[st.pulse, { backgroundColor: sync && sync.ok < sync.total ? c.warn : c.pos }]} />
            <T v="small" style={{ fontSize: 12, textAlign: "right" }} accessibilityLiveRegion="polite">
              {sync ? `${sync.ok} of ${sync.total} sheets in sync\nupdated ${sync.when}` : "Connecting to the sheets\none moment"}
            </T>
          </View>
        </Animated.View>
      </View>

      <View style={st.body}>
        {/* live figures */}
        <View style={st.sec}>
          <Text style={[st.h2, { color: c.brand }]}>The whole house, live.</Text>
          <T>These numbers are read from the FLO sheets right now. When a sheet changes, this changes within a minute.</T>
          <View style={st.bento}>
            {cards.length === 0 &&
              Array.from({ length: 4 }, (_, i) => <View key={i} style={[st.card, st.half, { backgroundColor: c.sheetEdge, borderColor: c.sheetEdge, height: 110 }]} />)}
            {cards.map((x, i) => {
              const f = fmtKpi(x.kpi.value, x.kpi.format);
              return (
                <Pressable
                  key={x.kpi.id + i}
                  onPress={() => openPage(x.to)}
                  accessibilityRole="link"
                  style={({ pressed }) => [st.card, i === 0 ? st.full : st.half, { backgroundColor: i === 0 ? c.brand : c.sheet, borderColor: c.sheetEdge, opacity: pressed ? 0.85 : 1 }]}
                >
                  <Text style={[st.area, { color: i === 0 ? c.onBrand : c.muted }]}>{x.area}</Text>
                  <Text style={{ fontFamily: font.uiBold, fontSize: i === 0 ? 40 : 26, color: i === 0 ? c.onBrand : c.ink, fontVariant: ["tabular-nums"] }} numberOfLines={1} adjustsFontSizeToFit>
                    {f.value}
                    {!!f.unit && <Text style={{ fontSize: 15, fontFamily: font.uiMedium }}> {f.unit}</Text>}
                  </Text>
                  <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: i === 0 ? c.onBrand : c.ink2 }} numberOfLines={2}>
                    {x.kpi.label}
                  </Text>
                  <Ionicons name="arrow-up-outline" size={16} color={i === 0 ? c.onBrand : c.faint} style={st.go} />
                </Pressable>
              );
            })}
          </View>
          <View style={[st.card, { backgroundColor: c.sheet, borderColor: c.sheetEdge, gap: 8 }]}>
            <Text style={{ fontFamily: font.display, fontSize: 22, color: c.brand }}>Ask in plain words.</Text>
            <T>FLO Assistant reads the same sheets. Ask it anything, the way you would ask a colleague.</T>
            {ASK.map((q) => (
              <Pressable key={q} onPress={() => router.push("/assistant")} accessibilityRole="button" style={({ pressed }) => [st.ask, { borderColor: c.controlEdge, backgroundColor: pressed ? c.pressed : c.control }]}>
                <Text style={{ fontFamily: font.uiMedium, fontSize: 14, color: c.ink }}>{q}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        {/* the thread */}
        <View style={st.sec}>
          <Text style={[st.h2, { color: c.brand }]}>One thread, design to delivery.</Text>
          <T>Each stage of a garment has its own page. Follow the thread to the one you need.</T>
          <View style={{ paddingLeft: 26 }}>
            <View style={[st.threadLine, { backgroundColor: c.accent }]} />
            {STAGES.map((s) => (
              <View key={s.name} style={{ marginBottom: 14 }}>
                <View style={[st.knot, { borderColor: c.accent, backgroundColor: c.frame }]} />
                <View style={[st.card, { backgroundColor: c.sheet, borderColor: c.sheetEdge, gap: 6 }]}>
                  <T v="title" style={{ fontSize: 17 }}>{s.name}</T>
                  <T style={{ fontSize: 14.5 }}>{s.line}</T>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
                    {s.pages.map((p) => (
                      <Pressable key={p.to} onPress={() => openPage(p.to)} accessibilityRole="link" style={({ pressed }) => [st.link, { backgroundColor: c.accentSoft, opacity: pressed ? 0.75 : 1 }]}>
                        <Text style={{ fontFamily: font.uiBold, fontSize: 13, color: c.accent }}>{p.label}</Text>
                        <Ionicons name="arrow-forward" size={13} color={c.accent} />
                      </Pressable>
                    ))}
                  </View>
                </View>
              </View>
            ))}
          </View>
        </View>

        {/* labels */}
        <View style={st.sec}>
          <Text style={[st.h2, { color: c.brand }]}>Twenty-two labels. One world.</Text>
          <T>Every FLO label gets its own room in the system. The dashboard is open today; the others are being stitched in, one by one.</T>
          <View style={{ gap: 12 }}>
            <Marquee list={[DASHBOARD, ...LABELS.slice(0, 11)]} reduce={reduce} />
            <Marquee list={LABELS.slice(11)} reverse reduce={reduce} />
          </View>
          <Pressable onPress={enterWorld} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: c.brand, alignSelf: "flex-start", opacity: pressed ? 0.85 : 1 }]}>
            <Text style={{ fontFamily: font.uiBold, fontSize: 16, color: c.onBrand }}>Enter the FLO world</Text>
            <Ionicons name="arrow-forward" size={18} color={c.onBrand} />
          </Pressable>
        </View>

        {/* the house */}
        <View style={st.sec}>
          <Text style={{ fontFamily: font.display, fontSize: 30, lineHeight: 36, color: c.brand }}>Where modern style embraces timeless tradition.</Text>
          <View style={[st.card, { backgroundColor: c.sheet, borderColor: c.sheetEdge, gap: 12 }]}>
            <Text style={{ fontFamily: font.display, fontSize: 22, color: c.brand }}>FLO India</Text>
            {[
              ["Founder", "Arihant Jain"],
              ["What we make", "Indian wear, indo-western and ethnic clothing for men, women and children"],
              ["Where", "S-4, Kartarpura Industrial Area, Bais Godam, Jaipur 302006"],
            ].map(([k, v]) => (
              <View key={k} style={{ gap: 2 }}>
                <T v="label">{k}</T>
                <T style={{ color: c.ink }} selectable>{v}</T>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* footer */}
      <View style={[st.foot, { backgroundColor: c.dark ? "#0b1424" : "#001938", paddingBottom: 28 + insets.bottom }]}>
        <Text style={{ fontFamily: font.display, fontSize: 30, color: "#fae8de" }}>Let the fashion flo.</Text>
        <Text style={{ fontFamily: font.ui, fontSize: 14.5, lineHeight: 21, color: "#c9d2e3" }}>FLO India&apos;s own intelligence: every order, sample, fabric roll and delivery, read live from the sheets.</Text>
        <Pressable onPress={enterWorld} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: "#fae8de", alignSelf: "flex-start", opacity: pressed ? 0.85 : 1 }]}>
          <Text style={{ fontFamily: font.uiBold, fontSize: 15, color: "#001938" }}>Enter the FLO world</Text>
          <Ionicons name="arrow-forward" size={17} color="#001938" />
        </Pressable>
        <View style={{ flexDirection: "row", gap: 20, marginTop: 8 }}>
          {FOOT.map((col) => (
            <View key={col.title} style={{ flex: 1, gap: 8 }}>
              <Text style={{ fontFamily: font.uiBold, fontSize: 11.5, letterSpacing: 1.2, color: "#93a0b3", textTransform: "uppercase" }}>{col.title}</Text>
              {col.links.map((l) => (
                <Pressable key={l.to} onPress={() => openPage(l.to)} accessibilityRole="link" hitSlop={4}>
                  <Text style={{ fontFamily: font.uiMedium, fontSize: 14, color: "#eef1f7" }}>{l.label}</Text>
                </Pressable>
              ))}
            </View>
          ))}
        </View>
        <Text style={{ fontFamily: font.ui, fontSize: 12.5, color: "#93a0b3", marginTop: 12 }}>
          S-4, Kartarpura Industrial Area, Bais Godam, Jaipur 302006 · © {new Date().getFullYear()} FLO India
        </Text>
      </View>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  nav: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 16 },
  ghost: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, minHeight: 36, justifyContent: "center" },
  hero: { alignItems: "center", paddingHorizontal: 16, paddingTop: 36, paddingBottom: 20, gap: 18 },
  line: { fontFamily: font.display, fontSize: 40, lineHeight: 46, textAlign: "center", letterSpacing: -0.5 },
  cta: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 50, paddingHorizontal: 22, borderRadius: 999 },
  corners: { flexDirection: "row", justifyContent: "space-between", alignSelf: "stretch", marginTop: 16 },
  pulse: { width: 8, height: 8, borderRadius: 4, marginTop: 4 },
  body: { paddingHorizontal: 16, gap: 44, paddingTop: 20, paddingBottom: 44 },
  sec: { gap: 12 },
  h2: { fontFamily: font.display, fontSize: 30, lineHeight: 36, letterSpacing: -0.3 },
  bento: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 10, marginTop: 4 },
  card: { borderRadius: 18, borderWidth: StyleSheet.hairlineWidth, padding: 16 },
  full: { width: "100%", gap: 4, minHeight: 140 },
  half: { width: "48.5%", gap: 4, minHeight: 120 },
  area: { fontFamily: font.uiBold, fontSize: 11, letterSpacing: 1.1, textTransform: "uppercase" },
  go: { position: "absolute", top: 14, right: 14, transform: [{ rotate: "45deg" }] },
  ask: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 9, alignSelf: "flex-start" },
  threadLine: { position: "absolute", left: 8, top: 18, bottom: 30, width: 2, borderRadius: 1, opacity: 0.6 },
  knot: { position: "absolute", left: -24, top: 18, width: 14, height: 14, borderRadius: 7, borderWidth: 3 },
  link: { flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 },
  mq: { borderRadius: 14, borderWidth: StyleSheet.hairlineWidth, alignItems: "center", justifyContent: "center" },
  foot: { paddingHorizontal: 20, paddingTop: 36, gap: 14, borderTopLeftRadius: 28, borderTopRightRadius: 28 },
});
