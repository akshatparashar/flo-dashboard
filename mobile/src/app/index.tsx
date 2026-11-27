/* Welcome: the FLO front door, as on the web (/welcome). A needle stitches a thread through the FLO letters, then the
   headline, live figures from the sheets, the thread from design to delivery with a link to each page, the 22 labels
   and the house. "Enter the FLO world" opens the label hub; "Open dashboard" goes straight to the numbers. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect, type Href } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Animated, Easing, Image, Pressable, StyleSheet, Text, useWindowDimensions, View, type ScrollViewInstance } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { T } from "../components/ui";
import { fmtKpi } from "../lib/format";
import { useDashboard, useStatus } from "../lib/query";
import { font, useTheme } from "../lib/theme";
import type { Kpi, OverviewData } from "../lib/types";
import { DASHBOARD, LABELS, LOGO_RATIO, type Label } from "../world/brands";
import { NeedleFLO } from "../world/NeedleFLO";
import { CountUp, expoIn, expoOut, power3Out, Pulse, Reveal, ScrollProvider, useReducedMotion } from "../world/motion";
import { LogoMark, openPage, syncLine } from "../world/parts";
import { Preloader } from "../world/Preloader";

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
      { to: "/overview", label: "Overview" },
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
    const loop = Animated.loop(Animated.timing(x, { toValue: 1, duration: 60000, easing: Easing.linear, useNativeDriver: true }));
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

/** Breathing grey block while the live figures load. */
function SkeletonCard({ full }: { full?: boolean }) {
  const c = useTheme();
  const [v] = useState(() => new Animated.Value(1));
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([Animated.timing(v, { toValue: 0.55, duration: 800, useNativeDriver: true }), Animated.timing(v, { toValue: 1, duration: 800, useNativeDriver: true })]));
    loop.start();
    return () => loop.stop();
  }, [v]);
  return <Animated.View style={[st.card, full ? st.full : st.half, { backgroundColor: c.sheet, borderColor: c.sheetEdge, opacity: v }]} />;
}

/** The thread from design to delivery: the stages come in one after another and the thread draws itself as you scroll. */
function Stages({ top, scrollY, height }: { top: number; scrollY: Animated.Value; height: number }) {
  const c = useTheme();
  const [y, setY] = useState<number | null>(null);
  const at = top + (y ?? 0);
  const draw = y === null ? 0 : scrollY.interpolate({ inputRange: [at - height * 0.8, at - height * 0.25], outputRange: [0, 1], extrapolate: "clamp" });
  return (
    <View style={{ paddingLeft: 26 }} onLayout={(e) => setY(e.nativeEvent.layout.y)}>
      <View style={[st.threadLine, { backgroundColor: c.rule }]} />
      <Animated.View style={[st.threadLine, { backgroundColor: c.accent, opacity: 1, transformOrigin: "top", transform: [{ scaleY: draw }] }]} />
      <Reveal offset={at} stagger={0.12} distance={36} gap={14}>
        {STAGES.map((s) => (
          <View key={s.name}>
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
      </Reveal>
    </View>
  );
}

let introPlayed = false;

export default function Welcome() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const status = useStatus();
  const overview = useDashboard<OverviewData>("/overview", {});
  const cards = useMemo(() => pickCards(overview.data), [overview.data]);
  const sync = syncLine(status.data);
  const reduce = useReducedMotion();
  // the opening plays once each time the app starts
  const [ready, setReady] = useState(introPlayed);
  const [copy] = useState(() => new Animated.Value(0));
  const [nav] = useState(() => new Animated.Value(0));
  const [navAway] = useState(() => new Animated.Value(0));
  const [dive] = useState(() => new Animated.Value(0));
  const [scrollY] = useState(() => new Animated.Value(0));
  const [counted, setCounted] = useState(false);
  const [footY, setFootY] = useState<number | null>(null);
  const scroller = useRef<ScrollViewInstance>(null);
  const lastY = useRef(0);
  const away = useRef(false);
  const leaving = useRef(false);

  useEffect(() => {
    if (!ready) return;
    Animated.timing(nav, { toValue: 1, duration: 700, delay: 400, easing: power3Out, useNativeDriver: false }).start();
  }, [ready, nav]);

  // coming back from FLO World: the letters are back in place
  useFocusEffect(
    useCallback(() => {
      leaving.current = false;
      dive.setValue(0);
      if (introPlayed) nav.setValue(1);
    }, [dive, nav]),
  );

  const finishIntro = useCallback(() => {
    introPlayed = true;
    setReady(true);
  }, []);
  const showCopy = useCallback(() => {
    Animated.timing(copy, { toValue: 1, duration: 1300, easing: expoOut, useNativeDriver: true }).start();
  }, [copy]);

  const rise = (d: number) => ({
    opacity: copy.interpolate({ inputRange: [d, Math.min(1, d + 0.45)], outputRange: [0, 1], extrapolate: "clamp" }),
    transform: [{ translateY: copy.interpolate({ inputRange: [d, Math.min(1, d + 0.45)], outputRange: [22, 0], extrapolate: "clamp" }) }],
  });
  const heroOut = { opacity: dive.interpolate({ inputRange: [0, 0.25], outputRange: [1, 0], extrapolate: "clamp" }) };

  // "Enter the FLO world": the copy lifts away and the camera dives into the O of FLO
  const enterWorld = () => {
    if (leaving.current) return;
    leaving.current = true;
    const go = () => router.push("/world" as Href);
    if (reduce) return go();
    scroller.current?.scrollTo({ y: 0, animated: true });
    Animated.timing(nav, { toValue: 0, duration: 300, useNativeDriver: false }).start();
    Animated.timing(dive, { toValue: 1, duration: 1300, delay: lastY.current > 40 ? 450 : 0, easing: expoIn, useNativeDriver: true }).start(go);
  };

  // the bar slips away while reading down, and comes back on the way up
  const onScroll = (e: { nativeEvent: { contentOffset: { y: number } } }) => {
    const y = e.nativeEvent.contentOffset.y;
    scrollY.setValue(y);
    const dy = y - lastY.current;
    if (Math.abs(dy) < 6 && y > 0) return; // ignore jitter and the last event of a fling
    lastY.current = y;
    const next = dy > 0 && y > 400;
    if (next !== away.current) {
      away.current = next;
      Animated.timing(navAway, { toValue: next ? 1 : 0, duration: 300, easing: power3Out, useNativeDriver: false }).start();
    }
  };

  const flo = Math.min(width - 32, 520);
  const k = flo / 510;
  // the centre of the O's counter inside the letters' box (83.2% x 49.8% of the 450 x 165 letters)
  const ox = (30 + 0.832 * 450) * k;
  const oy = (22 + 0.498 * 165) * k;
  const heroH = height;
  const body = heroH; // where the sections start in the scrolling content

  return (
    <View style={{ flex: 1, backgroundColor: c.frame }}>
      <ScrollProvider value={{ y: scrollY, height }}>
        <Animated.ScrollView ref={scroller} onScroll={onScroll} scrollEventThrottle={16} scrollEnabled={ready} style={{ flex: 1 }}>
          {/* hero: the whole first screen */}
          <View style={[st.hero, { height: heroH, paddingTop: insets.top + 64, paddingBottom: insets.bottom + 18 }]}>
            <View style={{ flex: 1, justifyContent: "center", alignItems: "center", gap: 22, alignSelf: "stretch" }}>
              <Animated.View
                style={{
                  transformOrigin: `${ox}px ${oy}px`,
                  opacity: dive.interpolate({ inputRange: [0, 0.75, 1], outputRange: [1, 1, 0] }),
                  transform: [{ scale: dive.interpolate({ inputRange: [0.15, 1], outputRange: [1, 18], extrapolate: "clamp" }) }],
                }}
              >
                <NeedleFLO width={flo} onDone={showCopy} play={ready} />
              </Animated.View>
              <Animated.View style={[heroOut, { alignItems: "center", gap: 18 }]}>
                <Animated.Text style={[st.line, { color: c.brand }, rise(0)]} accessibilityRole="header">
                  Let the fashion flo.
                </Animated.Text>
                <Animated.View style={rise(0.2)}>
                  <T style={{ textAlign: "center", fontSize: 16, lineHeight: 23, maxWidth: 420 }}>
                    FLO India&apos;s own intelligence. Every order, sample, fabric roll and delivery, read live from the sheets and answered in one place.
                  </T>
                </Animated.View>
                <Animated.View style={[rise(0.35), { transform: [...rise(0.35).transform, { scale: copy.interpolate({ inputRange: [0.35, 0.8], outputRange: [0.96, 1], extrapolate: "clamp" }) }] }]}>
                  <Pressable onPress={enterWorld} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: c.brand, transform: [{ scale: pressed ? 0.97 : 1 }] }]}>
                    <Text style={{ fontFamily: font.uiBold, fontSize: 16, color: c.onBrand }}>Enter the FLO world</Text>
                    <Ionicons name="arrow-forward" size={18} color={c.onBrand} />
                  </Pressable>
                </Animated.View>
              </Animated.View>
            </View>
            <Animated.View style={[st.corners, heroOut, { opacity: Animated.multiply(copy.interpolate({ inputRange: [0.5, 1], outputRange: [0, 1], extrapolate: "clamp" }), heroOut.opacity) }]}>
              <T v="small" style={{ fontSize: 12 }}>
                Fashion, lifestyle, outfit{"\n"}Jaipur, India
              </T>
              <ScrollCue />
              <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-start" }}>
                <Pulse color={sync && sync.ok < sync.total ? c.warn : c.pos} style={{ marginTop: 4 }} />
                <T v="small" style={{ fontSize: 12, textAlign: "right" }} accessibilityLiveRegion="polite">
                  {sync ? `${sync.ok} of ${sync.total} sheets in sync\nupdated ${sync.when}` : "Connecting to the sheets\none moment"}
                </T>
              </View>
            </Animated.View>
          </View>

          <View style={st.body}>
            <Reveal offset={body} gap={12} onShow={() => setCounted(true)}>
              <Text style={[st.h2, { color: c.brand }]}>The whole house, live.</Text>
              <T>These numbers are read from the FLO sheets right now. Nobody typed them in; when a sheet changes, this changes within a minute.</T>
              <View style={st.bento}>
                {cards.length === 0 && [0, 1, 2, 3, 4].map((i) => <SkeletonCard key={i} full={i === 0} />)}
                {cards.map((x, i) => {
                  const f = fmtKpi(x.kpi.value, x.kpi.format);
                  const big = i === 0;
                  return (
                    <Pressable
                      key={x.kpi.id + i}
                      onPress={() => openPage(x.to)}
                      accessibilityRole="link"
                      accessibilityLabel={`${x.kpi.label}: ${f.value} ${f.unit}`}
                      style={({ pressed }) => [st.card, big ? st.full : st.half, { backgroundColor: big ? NAVY : c.sheet, borderColor: c.sheetEdge, transform: [{ scale: pressed ? 0.97 : 1 }, { translateY: pressed ? -2 : 0 }] }]}
                    >
                      <Text style={[st.area, { color: big ? "#9ae6bd" : c.pos }]}>{x.area}</Text>
                      <Text style={{ fontFamily: font.uiBold, fontSize: big ? 44 : 27, color: big ? "#fae8de" : c.ink, fontVariant: ["tabular-nums"] }} numberOfLines={1} adjustsFontSizeToFit>
                        <CountUp value={x.kpi.value} format={x.kpi.format} run={counted} />
                        {!!f.unit && <Text style={{ fontSize: 15, fontFamily: font.uiMedium }}> {f.unit}</Text>}
                      </Text>
                      <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: big ? "#eef1f7" : c.ink2 }} numberOfLines={2}>
                        {x.kpi.label}
                      </Text>
                      {!!x.kpi.hint && big && <Text style={{ fontFamily: font.ui, fontSize: 12.5, color: "#c9d2e3" }} numberOfLines={1}>{x.kpi.hint}</Text>}
                      <Ionicons name="arrow-up-outline" size={16} color={big ? "#fae8de" : c.faint} style={st.go} />
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
            </Reveal>

            <Reveal offset={body} gap={12} style={st.secTop}>
              <Text style={[st.h2, { color: c.brand }]}>One thread, design to delivery.</Text>
              <T>Each stage of a garment has its own page in the system. Follow the thread to the one you need.</T>
            </Reveal>
            <Stages top={body} scrollY={scrollY} height={height} />

            <Reveal offset={body} gap={12} style={st.secTop}>
              <Text style={[st.h2, { color: c.brand }]}>Twenty-two labels. One world.</Text>
              <T>Every FLO label gets its own room in the system. The dashboard is open today; the others are being stitched in, one by one.</T>
              <View style={{ gap: 12 }}>
                <Marquee list={[DASHBOARD, ...LABELS.slice(0, 11)]} reduce={!!reduce} />
                <Marquee list={LABELS.slice(11)} reverse reduce={!!reduce} />
              </View>
              <Pressable onPress={enterWorld} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: c.brand, alignSelf: "flex-start", transform: [{ scale: pressed ? 0.97 : 1 }] }]}>
                <Text style={{ fontFamily: font.uiBold, fontSize: 16, color: c.onBrand }}>Enter the FLO world</Text>
                <Ionicons name="arrow-forward" size={18} color={c.onBrand} />
              </Pressable>
            </Reveal>

            <Reveal offset={body} gap={14} style={st.secTop}>
              <Text style={{ fontFamily: font.display, fontSize: 32, lineHeight: 38, color: c.brand }}>Where modern style embraces timeless tradition.</Text>
              <View style={[st.card, { backgroundColor: c.sheet, borderColor: c.sheetEdge, gap: 12 }]}>
                <Text style={{ fontFamily: font.display, fontSize: 22, color: c.brand }}>FLO India</Text>
                {[
                  ["Founder", "Arihant Jain"],
                  ["What we make", "Indian wear, indo-western and ethnic clothing for men, women and children"],
                  ["Where", "S-4, Kartarpura Industrial Area, Bais Godam, Jaipur 302006"],
                ].map(([key, v]) => (
                  <View key={key} style={{ gap: 2 }}>
                    <T v="label">{key}</T>
                    <T style={{ color: c.ink }} selectable>{v}</T>
                  </View>
                ))}
              </View>
            </Reveal>
          </View>

          {/* footer */}
          <View style={[st.foot, { backgroundColor: NAVY, paddingBottom: 28 + insets.bottom }]} onLayout={(e) => setFootY(e.nativeEvent.layout.y)}>
            {footY !== null && (
            <Reveal offset={footY} gap={14} stagger={0.07} distance={24}>
              <Text style={{ fontFamily: font.display, fontSize: 32, color: "#fae8de" }}>Let the fashion flo.</Text>
              <Text style={{ fontFamily: font.ui, fontSize: 14.5, lineHeight: 21, color: "#c9d2e3" }}>FLO India&apos;s own intelligence: every order, sample, fabric roll and delivery, read live from the sheets.</Text>
              <Pressable onPress={enterWorld} accessibilityRole="button" style={({ pressed }) => [st.cta, { backgroundColor: "#fae8de", alignSelf: "flex-start", transform: [{ scale: pressed ? 0.97 : 1 }] }]}>
                <Text style={{ fontFamily: font.uiBold, fontSize: 15, color: NAVY }}>Enter the FLO world</Text>
                <Ionicons name="arrow-forward" size={17} color={NAVY} />
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
            </Reveal>
            )}
          </View>
        </Animated.ScrollView>
      </ScrollProvider>

      {/* top bar: comes in after the opening, slips away while reading down */}
      <Animated.View
        pointerEvents={ready ? "box-none" : "none"}
        style={[
          st.nav,
          {
            paddingTop: insets.top + 10,
            backgroundColor: scrollY.interpolate({ inputRange: [heroH * 0.6, heroH * 0.9], outputRange: [c.dark ? "rgba(17,26,43,0)" : "rgba(238,241,246,0)", c.dark ? "rgba(17,26,43,0.94)" : "rgba(238,241,246,0.94)"], extrapolate: "clamp" }),
            opacity: nav,
            transform: [{ translateY: Animated.add(nav.interpolate({ inputRange: [0, 1], outputRange: [-10, 0] }), navAway.interpolate({ inputRange: [0, 1], outputRange: [0, -(insets.top + 70)] })) }],
          },
        ]}
      >
        <Image source={require("../../assets/brand/flo-letters-navy.png")} style={{ width: 54, height: 20, tintColor: c.brand }} resizeMode="contain" accessibilityLabel="FLO" />
        <Pressable onPress={() => openPage("/overview")} accessibilityRole="button" style={({ pressed }) => [st.ghost, { borderColor: c.controlEdge, backgroundColor: c.frame, opacity: pressed ? 0.7 : 1 }]}>
          <Text style={{ fontFamily: font.uiBold, fontSize: 13.5, color: c.ink }}>Open dashboard</Text>
        </Pressable>
      </Animated.View>

      {!introPlayed && !ready && <Preloader status={status.data ?? (status.error ? ({ sources: {} } as never) : undefined)} onDone={finishIntro} />}
    </View>
  );
}

/** A small "scroll" hint under the hero that bobs up and down. */
function ScrollCue() {
  const c = useTheme();
  const [v] = useState(() => new Animated.Value(0));
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([Animated.timing(v, { toValue: 1, duration: 900, easing: Easing.inOut(Easing.sin), useNativeDriver: true }), Animated.timing(v, { toValue: 0, duration: 900, easing: Easing.inOut(Easing.sin), useNativeDriver: true })]));
    loop.start();
    return () => loop.stop();
  }, [v]);
  return (
    <Animated.View style={{ alignItems: "center", transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [0, 5] }) }] }} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Text style={{ fontFamily: font.uiMedium, fontSize: 10.5, letterSpacing: 1.4, color: c.faint }}>SCROLL</Text>
      <Ionicons name="chevron-down" size={14} color={c.faint} />
    </Animated.View>
  );
}

const NAVY = "#001938";

const st = StyleSheet.create({
  nav: { position: "absolute", top: 0, left: 0, right: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 16, paddingBottom: 10 },
  ghost: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, minHeight: 36, justifyContent: "center" },
  hero: { alignItems: "center", paddingHorizontal: 16 },
  line: { fontFamily: font.display, fontSize: 42, lineHeight: 48, textAlign: "center", letterSpacing: -0.5 },
  cta: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 52, paddingHorizontal: 24, borderRadius: 999 },
  corners: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", alignSelf: "stretch" },
  body: { paddingHorizontal: 16, gap: 14, paddingTop: 36, paddingBottom: 56 },
  secTop: { marginTop: 52 },
  h2: { fontFamily: font.display, fontSize: 32, lineHeight: 38, letterSpacing: -0.3 },
  bento: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 10, marginTop: 4 },
  card: { borderRadius: 18, borderWidth: StyleSheet.hairlineWidth, padding: 16 },
  full: { width: "100%", gap: 4, minHeight: 150, paddingTop: 44 },
  half: { width: "48.5%", gap: 4, minHeight: 128, paddingTop: 40 },
  area: { position: "absolute", top: 16, left: 16, fontFamily: font.uiBold, fontSize: 11, letterSpacing: 1.1, textTransform: "uppercase" },
  go: { position: "absolute", top: 14, right: 14, transform: [{ rotate: "45deg" }] },
  ask: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 9, alignSelf: "flex-start" },
  threadLine: { position: "absolute", left: 8, top: 18, bottom: 30, width: 2, borderRadius: 1 },
  knot: { position: "absolute", left: -24, top: 18, width: 14, height: 14, borderRadius: 7, borderWidth: 3 },
  link: { flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 },
  mq: { borderRadius: 14, borderWidth: StyleSheet.hairlineWidth, alignItems: "center", justifyContent: "center" },
  foot: { paddingHorizontal: 20, paddingTop: 40, borderTopLeftRadius: 28, borderTopRightRadius: 28 },
});
