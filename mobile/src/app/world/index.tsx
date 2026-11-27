/* FLO World: the label hub, as on the web (/world). The live Dashboard card sits on top; the 22 labels burst out of
   the centre, fly around and settle into a grid, each stitched to the label above it (the top row to the Dashboard).
   Then signals keep hopping up the stitches from an outer label, lighting each label they pass, until they reach the
   Dashboard, which flashes. The status line types itself through each sheet's real sync state. Tapping a card flies
   it to the middle and zooms through it. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { router, useFocusEffect, type Href } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Animated, Easing, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { T } from "../../components/ui";
import { ago } from "../../lib/format";
import { useStatus } from "../../lib/query";
import { font, useTheme } from "../../lib/theme";
import { DASHBOARD, LABELS, LOGO_RATIO } from "../../world/brands";
import { expoIn, expoOut, power2InOut, power3Out, Pulse, useReducedMotion } from "../../world/motion";
import { LogoMark, openPage } from "../../world/parts";

const NAVY = "#001938";
const SOURCE_NAMES: Record<string, string> = {
  tracker: "Master sheet",
  sample_summary: "Samples",
  overview_fabricators: "Fabricators",
  fabric_po: "Fabric PO",
  target_revenue: "Target",
  flo_future: "FLO Future",
  vendor_rate: "Vendor rates",
  in_out_sale: "In/Out sale",
  daily_delegation: "Delegation",
  stock_ageing: "Stock ageing",
};
const SIGNALS = 3;
const GAP = 16; // between labels (the stitches cross it)
const CORE_GAP = 22; // between the Dashboard card and the first row
const CORE_H = 230;

/** The status line: each new line scrambles in as 0s and 1s, then settles, like a terminal coming up. */
function useScramble(lines: string[], reduce: boolean | null): string {
  const [text, setText] = useState("");
  const key = lines.join("|");
  useEffect(() => {
    if (reduce === null) return;
    const all = key.split("|");
    if (reduce) {
      const id = setTimeout(() => setText(all[0]), 0);
      return () => clearTimeout(id);
    }
    let i = 0;
    let tick: ReturnType<typeof setInterval> | undefined;
    const next = () => {
      const target = all[i % all.length];
      i++;
      const t0 = Date.now();
      clearInterval(tick);
      tick = setInterval(() => {
        const t = Math.min(1, (Date.now() - t0) / 1100);
        const shown = Math.floor(target.length * Math.max(0, (t - 0.18) / 0.82));
        const noise = Array.from({ length: Math.min(target.length - shown, Math.ceil(target.length * Math.min(1, t * 3))) }, () => (Math.random() < 0.5 ? "0" : "1")).join("");
        setText(target.slice(0, shown) + noise);
        if (t >= 1) clearInterval(tick);
      }, 40);
    };
    next();
    const id = setInterval(next, 3600);
    return () => {
      clearInterval(id);
      clearInterval(tick);
    };
  }, [key, reduce]);
  return text;
}

export default function World() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const status = useStatus();
  const reduce = useReducedMotion();

  // the grid: two columns on a phone, more on a tablet
  const W = Math.min(width, 900) - 32;
  const cols = W >= 660 ? 4 : W >= 440 ? 3 : 2;
  const TW = (W - (cols - 1) * GAP) / cols;
  const logoW = TW - 30;
  const TH = logoW / LOGO_RATIO + 50;
  const spot = (i: number) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    return { x: col * (TW + GAP), y: CORE_H + CORE_GAP + row * (TH + GAP), row };
  };
  const rows = Math.ceil(LABELS.length / cols);
  const stageH = CORE_H + CORE_GAP + rows * TH + (rows - 1) * GAP;
  // each label's stitch: from its top edge up to the label above it, or to the Dashboard card
  const links = LABELS.map((_, i) => {
    const s = spot(i);
    const x = s.x + TW / 2;
    return { x, y1: s.y, y2: s.y - (s.row === 0 ? CORE_GAP : GAP), parent: s.row === 0 ? -1 : i - cols };
  });

  // ---------------------------------------------------------------- entrance: burst out of the centre
  const [core] = useState(() => new Animated.Value(0));
  const [head] = useState(() => new Animated.Value(0));
  const [fly] = useState(() => LABELS.map(() => new Animated.Value(0)));
  const [grow] = useState(() => LABELS.map(() => new Animated.Value(0)));
  const [stitch] = useState(() => LABELS.map(() => new Animated.Value(0)));
  const [arrived, setArrived] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  // where each label starts (screen centre) and the random point it swings through, in its own coordinates
  const [paths] = useState(() =>
    LABELS.map(() => ({ rx: (Math.random() - 0.5) * 0.84, ry: (Math.random() - 0.5) * 0.76, rot: (Math.random() - 0.5) * 100 })),
  );

  useEffect(() => {
    if (reduce === null) return;
    const all = [core, head, ...fly, ...grow];
    if (reduce) {
      all.forEach((v) => v.setValue(1));
      stitch.forEach((v) => v.setValue(1));
      const id = setTimeout(() => setArrived(true), 0);
      return () => clearTimeout(id);
    }
    const anim = Animated.parallel([
      Animated.timing(core, { toValue: 1, duration: 1200, easing: expoOut, useNativeDriver: true }),
      Animated.timing(head, { toValue: 1, duration: 700, delay: 200, easing: power3Out, useNativeDriver: true }),
      ...LABELS.map((_, i) =>
        Animated.parallel([
          Animated.timing(fly[i], { toValue: 1, duration: 1900, delay: 150 + i * 45, easing: power2InOut, useNativeDriver: true }),
          Animated.timing(grow[i], { toValue: 1, duration: 1300, delay: 150 + i * 45, easing: expoOut, useNativeDriver: true }),
        ]),
      ),
    ]);
    anim.start(({ finished }) => {
      if (!finished) return;
      setArrived(true);
      // the stitches draw in
      Animated.parallel(stitch.map((v) => Animated.timing(v, { toValue: 1, duration: 600, delay: Math.random() * 600, easing: power3Out, useNativeDriver: true }))).start();
    });
    return () => anim.stop();
  }, [reduce, core, head, fly, grow, stitch]);

  // ---------------------------------------------------------------- signals hop up the stitches to the Dashboard
  const [ping, setPing] = useState<Set<number>>(() => new Set());
  const [hit] = useState(() => new Animated.Value(0));
  const [dots] = useState(() => Array.from({ length: SIGNALS }, () => ({ x: new Animated.Value(0), y: new Animated.Value(0), o: new Animated.Value(0) })));
  const live = useRef(false);
  useEffect(() => {
    if (!arrived || reduce) return;
    live.current = true;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const later = (ms: number, fn: () => void) => timers.push(setTimeout(() => live.current && fn(), ms));
    const hop = (d: (typeof dots)[number], i: number) => {
      const k = links[i];
      setPing((s) => new Set(s).add(i));
      d.x.setValue(k.x);
      d.y.setValue(k.y1);
      Animated.sequence([
        Animated.delay(250),
        Animated.parallel([
          Animated.timing(d.y, { toValue: k.y2, duration: 450, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
          Animated.sequence([
            Animated.timing(d.o, { toValue: 1, duration: 120, useNativeDriver: true }),
            Animated.delay(210),
            Animated.timing(d.o, { toValue: 0, duration: 120, useNativeDriver: true }),
          ]),
        ]),
      ]).start(({ finished }) => {
        setPing((s) => {
          const n = new Set(s);
          n.delete(i);
          return n;
        });
        if (!finished || !live.current) return;
        if (k.parent >= 0) return hop(d, k.parent);
        hit.setValue(1);
        Animated.timing(hit, { toValue: 0, duration: 800, easing: power3Out, useNativeDriver: true }).start();
        later(400 + Math.random() * 1400, () => send(d));
      });
    };
    // start two to five rows down, so the signal crosses several labels on its way to the Dashboard and stays on screen
    const send = (d: (typeof dots)[number]) => {
      const from = cols * 2;
      const to = Math.min(LABELS.length, cols * 5);
      hop(d, from + Math.floor(Math.random() * (to - from)));
    };
    dots.forEach((d, k) => later(800 + k * 700, () => send(d)));
    return () => {
      live.current = false;
      timers.forEach(clearTimeout);
      dots.forEach((d) => d.o.setValue(0));
    };
    // links follow cols, which follows the screen width
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arrived, reduce, cols, dots, hit]);

  // ---------------------------------------------------------------- status line
  const lines = useMemo(() => {
    const out = ["FLO intelligence online."];
    for (const [k, s] of Object.entries(status.data?.sources ?? {})) out.push(`${SOURCE_NAMES[k] ?? s.name}: ${s.ok ? "in sync" : "needs a look"}, ${s.synced_at ? ago(s.synced_at) : "waiting"}.`);
    return out;
  }, [status.data]);
  const typed = useScramble(lines, reduce);
  const sources = Object.values(status.data?.sources ?? {});
  const okCount = sources.filter((s) => s.ok).length;

  // ---------------------------------------------------------------- tap: fly to the middle and zoom through
  const [leave] = useState(() => new Animated.Value(0));
  const [zoom] = useState(() => new Animated.Value(0));
  const [picked, setPicked] = useState<number | null>(null); // -1 = the Dashboard card
  const busy = useRef(false);
  useFocusEffect(
    useCallback(() => {
      busy.current = false;
      leave.setValue(0);
      zoom.setValue(0);
      setPicked(null);
    }, [leave, zoom]),
  );
  const go = (i: number, to: () => void) => {
    if (busy.current) return;
    busy.current = true;
    if (reduce) return to();
    setPicked(i);
    Animated.parallel([
      Animated.timing(leave, { toValue: 1, duration: 450, easing: Easing.in(Easing.quad), useNativeDriver: true }),
      Animated.timing(zoom, { toValue: 1, duration: 1150, delay: 100, easing: power2InOut, useNativeDriver: true }),
    ]).start(({ finished }) => finished && to());
  };
  const stageTop = insets.top + 76; // where the stage starts on screen, before scrolling
  const toCentre = (cx: number, cy: number) => ({
    dx: width / 2 - (16 + (width - 32 - W) / 2 + cx),
    dy: height / 2 - (stageTop - scrollTop + cy),
  });
  const zoomStyle = (cx: number, cy: number, w: number, h: number) => {
    const { dx, dy } = toCentre(cx, cy);
    const s = Math.max(width / w, height / h) * 1.2;
    return {
      opacity: zoom.interpolate({ inputRange: [0, 0.6, 1], outputRange: [1, 1, 0] }),
      transform: [
        { translateX: zoom.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, dx, dx] }) },
        { translateY: zoom.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, dy, dy] }) },
        { scale: zoom.interpolate({ inputRange: [0, 0.5, 1], outputRange: [1, 1, s], easing: expoIn }) },
      ],
      zIndex: 20,
    };
  };
  const fadeOthers = { opacity: leave.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }), transform: [{ scale: leave.interpolate({ inputRange: [0, 1], outputRange: [1, 0.96] }) }] };

  const label = (i: number) => {
    const s = spot(i);
    const { dx, dy } = toCentre(s.x + TW / 2, s.y + TH / 2);
    const p = paths[i];
    const sx = dx + p.rx * width;
    const sy = dy + p.ry * height;
    const on = ping.has(i);
    const style =
      picked === i
        ? zoomStyle(s.x + TW / 2, s.y + TH / 2, TW, TH)
        : {
            opacity: Animated.multiply(grow[i].interpolate({ inputRange: [0, 0.23, 1], outputRange: [0, 1, 1] }), picked === null ? 1 : fadeOthers.opacity),
            transform: [
              { translateX: fly[i].interpolate({ inputRange: [0, 0.5, 1], outputRange: [dx, sx, 0] }) },
              { translateY: fly[i].interpolate({ inputRange: [0, 0.5, 1], outputRange: [dy, sy, 0] }) },
              { rotate: fly[i].interpolate({ inputRange: [0, 1], outputRange: [`${p.rot}deg`, "0deg"] }) },
              { scale: grow[i].interpolate({ inputRange: [0, 1], outputRange: [0.2, 1] }) },
            ],
          };
    return (
      <Animated.View key={LABELS[i].slug} style={[{ position: "absolute", left: s.x, top: s.y, width: TW, height: TH }, style]}>
        <Pressable
          onPress={() => go(i, () => router.push(`/world/${LABELS[i].slug}` as Href))}
          accessibilityRole="link"
          accessibilityLabel={`FLO ${LABELS[i].name}, coming soon`}
          style={({ pressed }) => [st.tile, { backgroundColor: c.sheet, borderColor: on ? c.accent : c.sheetEdge, borderWidth: on ? 1.5 : StyleSheet.hairlineWidth, transform: [{ scale: pressed ? 0.96 : 1 }] }]}
        >
          <LogoMark label={LABELS[i]} width={logoW} color={on ? c.accent : c.brand} />
          <Text style={{ fontFamily: font.uiMedium, fontSize: 10.5, color: on ? c.accent : c.faint, letterSpacing: 0.9 }}>COMING SOON</Text>
        </Pressable>
      </Animated.View>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.frame }}>
      <Animated.View style={[st.head, { paddingTop: insets.top + 8, opacity: Animated.multiply(head, fadeOthers.opacity), transform: [{ translateY: head.interpolate({ inputRange: [0, 1], outputRange: [-12, 0] }) }] }]}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} accessibilityRole="button" accessibilityLabel="Back to the FLO welcome screen" hitSlop={10} style={st.back}>
          <Ionicons name="arrow-back" size={22} color={c.ink} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={{ fontFamily: font.display, fontSize: 26, color: c.brand }} accessibilityRole="header">FLO World</Text>
          <Text style={{ fontFamily: font.uiMedium, fontSize: 12.5, color: c.muted, letterSpacing: 0.3, fontVariant: ["tabular-nums"] }} numberOfLines={1}>
            {typed || " "}
          </Text>
        </View>
        <View style={st.back} />
      </Animated.View>

      <ScrollView
        scrollEnabled={picked === null}
        onScroll={(e) => setScrollTop(e.nativeEvent.contentOffset.y)}
        scrollEventThrottle={32}
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 32 + insets.bottom, alignItems: "center" }}
      >
        <View style={{ width: W, height: stageH }}>
          {/* the stitches, and the signals travelling up them */}
          {links.map((k, i) => (
            <Animated.View
              key={i}
              style={[
                st.stitch,
                {
                  left: k.x - 1,
                  top: k.y2,
                  height: k.y1 - k.y2,
                  borderColor: ping.has(i) ? c.accent : c.ruleStrong,
                  opacity: picked === null ? 1 : fadeOthers.opacity,
                  transformOrigin: "bottom",
                  transform: [{ scaleY: stitch[i] }],
                },
              ]}
            />
          ))}
          {dots.map((d, k) => (
            <Animated.View key={k} style={[st.signal, { backgroundColor: c.accent, opacity: d.o, transform: [{ translateX: Animated.add(d.x, -5) }, { translateY: Animated.add(d.y, -5) }] }]} />
          ))}

          {/* the Dashboard: live, in the middle of it all */}
          <Animated.View
            style={[
              { position: "absolute", left: 0, top: 0, width: W, height: CORE_H },
              picked === -1
                ? zoomStyle(W / 2, CORE_H / 2, W, CORE_H)
                : { opacity: Animated.multiply(core, picked === null ? 1 : fadeOthers.opacity), transform: [{ scale: core.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] }) }] },
            ]}
          >
            <Animated.View style={[StyleSheet.absoluteFill, st.coreGlow, { borderColor: c.accent, opacity: hit, transform: [{ scale: hit.interpolate({ inputRange: [0, 1], outputRange: [1, 1.03] }) }] }]} />
            <Pressable onPress={() => go(-1, () => openPage("/overview"))} accessibilityRole="link" accessibilityLabel="FLO Dashboard, live. Open it." style={({ pressed }) => [st.core, { backgroundColor: c.dark ? "#0b1424" : NAVY, transform: [{ scale: pressed ? 0.98 : 1 }] }]}>
              <View style={st.live}>
                <Pulse color="#4fc98a" />
                <Text style={{ fontFamily: font.uiBold, fontSize: 12, color: "#9ae6bd", letterSpacing: 1 }}>LIVE</Text>
              </View>
              <LogoMark label={DASHBOARD} width={Math.min(300, W * 0.66)} color="#fae8de" />
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Text style={{ fontFamily: font.uiMedium, fontSize: 13.5, color: "#c9d2e3" }}>
                  {sources.length ? `${okCount} of ${sources.length} sheets in sync` : "Connecting to the sheets"}
                </Text>
                <Ionicons name="arrow-forward" size={15} color="#c9d2e3" />
              </View>
            </Pressable>
          </Animated.View>

          {LABELS.map((_, i) => label(i))}
        </View>
        <Animated.View style={{ opacity: Animated.multiply(head, fadeOthers.opacity), marginTop: 18 }}>
          <T v="small">Choose a label to open it.</T>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

const st = StyleSheet.create({
  head: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingBottom: 8, zIndex: 2 },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  core: { flex: 1, borderRadius: 24, paddingVertical: 24, paddingHorizontal: 20, alignItems: "center", justifyContent: "center", gap: 16 },
  coreGlow: { borderRadius: 28, borderWidth: 6, margin: -6 },
  live: { position: "absolute", top: 18, left: 20, flexDirection: "row", alignItems: "center", gap: 8 },
  tile: { flex: 1, borderRadius: 16, alignItems: "center", justifyContent: "center", gap: 8 },
  stitch: { position: "absolute", width: 0, borderLeftWidth: 2, borderStyle: "dashed" },
  signal: { position: "absolute", left: 0, top: 0, width: 10, height: 10, borderRadius: 5 },
});
