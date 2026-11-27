/* The opening, as on the website: FLO's open bracket draws itself like a wire, the wordmark appears inside it, the
   sheets light up as they really load, then the bracket stretches out to the edges of the screen and the landing
   page is underneath (frontend/src/components/Preloader.tsx, exit "page"). */
import { useEffect, useRef, useState } from "react";
import { Animated, Image, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import Svg, { Path } from "react-native-svg";
import { font, useTheme } from "../lib/theme";
import type { StatusData } from "../lib/types";
import { expoOut, power2InOut, power3Out, useReducedMotion } from "./motion";

const AnimatedPath = Animated.createAnimatedComponent(Path);

const SOURCES: [string, string][] = [
  ["tracker", "Master sheet"],
  ["sample_summary", "Samples"],
  ["overview_fabricators", "Fabricators"],
  ["fabric_po", "Fabric PO"],
  ["target_revenue", "Target"],
  ["flo_future", "FLO Future"],
  ["vendor_rate", "Vendor rates"],
  ["in_out_sale", "In/Out sale"],
  ["daily_delegation", "Delegation"],
];
const MIN_MS = 1900; // long enough for the bracket and the wordmark to finish drawing
const MAX_MS = 3200; // never hold the app for slow sheets
// the logo's open bracket in its 1600 x 1131 artwork: top-right end, top-right corner, top-left, bottom-left, bottom end
const BRACKET: [number, number][] = [
  [1474, 264],
  [1474, 136],
  [125, 136],
  [125, 956],
  [295, 956],
];
const ART = { w: 1600, h: 1131, stroke: 9 };

const pathOf = (p: number[][]) => `M${p[0][0]},${p[0][1]} L${p[1][0]},${p[1][1]} L${p[2][0]},${p[2][1]} L${p[3][0]},${p[3][1]} L${p[4][0]},${p[4][1]}`;
const easeExpoInOut = (t: number) => (t === 0 ? 0 : t === 1 ? 1 : t < 0.5 ? 2 ** (20 * t - 10) / 2 : (2 - 2 ** (-20 * t + 10)) / 2);

export function Preloader({ status, onDone }: { status: StatusData | undefined; onDone: () => void }) {
  const c = useTheme();
  const { width: vw, height: vh } = useWindowDimensions();
  const reduce = useReducedMotion();
  const [t0] = useState(() => Date.now());
  const [ready, setReady] = useState(false);
  const [k, setK] = useState(0); // 0 = bracket around the logo, 1 = bracket at the screen edges
  const [draw] = useState(() => new Animated.Value(0));
  const [mark] = useState(() => new Animated.Value(0));
  const [chips] = useState(() => new Animated.Value(0));
  const [fade] = useState(() => new Animated.Value(1));
  const exiting = useRef(false);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  const w = Math.min(420, vw * 0.74);
  const h = (w * ART.h) / ART.w;
  const s = w / ART.w;
  const box = { x: (vw - w) / 2, y: (vh - h) / 2 - 36 };
  const start = BRACKET.map(([x, y]) => [box.x + x * s, box.y + y * s]);
  const sb = { l: 14, t: 14, r: vw - 14, b: vh - 14 };
  const end = [
    [sb.r, sb.t + Math.min(160, (sb.b - sb.t) * 0.25)],
    [sb.r, sb.t],
    [sb.l, sb.t],
    [sb.l, sb.b],
    [sb.l + Math.min(260, (sb.r - sb.l) * 0.3), sb.b],
  ];
  const cur = start.map((p, i) => [p[0] + (end[i][0] - p[0]) * k, p[1] + (end[i][1] - p[1]) * k]);
  const len = (BRACKET[0][1] - BRACKET[1][1] + BRACKET[1][0] - BRACKET[2][0] + BRACKET[3][1] - BRACKET[2][1] + BRACKET[4][0] - BRACKET[3][0]) * s;

  // intro: draw the bracket, then reveal the wordmark and the sheets
  useEffect(() => {
    if (reduce === null) return;
    if (reduce) {
      draw.setValue(1);
      mark.setValue(1);
      chips.setValue(1);
      return;
    }
    Animated.sequence([
      Animated.timing(draw, { toValue: 1, duration: 1050, easing: power2InOut, useNativeDriver: false }),
      Animated.parallel([
        Animated.timing(mark, { toValue: 1, duration: 750, easing: power3Out, useNativeDriver: true }),
        Animated.timing(chips, { toValue: 1, duration: 700, delay: 350, easing: power3Out, useNativeDriver: true }),
      ]),
    ]).start();
  }, [reduce, draw, mark, chips]);

  // hold until the sheets answer (or 3.2 s at most)
  useEffect(() => {
    const wait = Math.max(0, MIN_MS - (Date.now() - t0));
    const timer = setTimeout(() => setReady(true), status ? wait : Math.max(0, MAX_MS - (Date.now() - t0)));
    return () => clearTimeout(timer);
  }, [status, t0]);

  // exit: the bracket stretches out to the screen's edges, everything else fades
  useEffect(() => {
    if (!ready || exiting.current) return;
    exiting.current = true;
    if (reduce) {
      Animated.timing(fade, { toValue: 0, duration: 250, useNativeDriver: true }).start(() => done.current());
      return;
    }
    Animated.parallel([
      Animated.timing(mark, { toValue: 0, duration: 350, useNativeDriver: true }),
      Animated.timing(chips, { toValue: 0, duration: 350, useNativeDriver: true }),
    ]).start(() => {
      const t1 = Date.now();
      let raf = 0;
      const tick = () => {
        const t = Math.min(1, (Date.now() - t1) / 850);
        setK(easeExpoInOut(t));
        if (t < 1) raf = requestAnimationFrame(tick);
        else Animated.timing(fade, { toValue: 0, duration: 450, easing: expoOut, useNativeDriver: true }).start(() => done.current());
      };
      raf = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(raf);
    });
  }, [ready, reduce, mark, chips, fade]);

  const sources = status?.sources ?? {};
  return (
    <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: c.frame, opacity: fade, zIndex: 10 }]} accessibilityLabel="Loading FLO" accessibilityState={{ busy: true }}>
      <Svg width={vw} height={vh} style={StyleSheet.absoluteFill}>
        <AnimatedPath
          d={pathOf(cur)}
          fill="none"
          stroke={c.brand}
          strokeWidth={ART.stroke * s + (1.5 - ART.stroke * s) * k}
          strokeDasharray={`${len} ${len * 3}`}
          strokeDashoffset={k > 0 ? 0 : draw.interpolate({ inputRange: [0, 1], outputRange: [len, 0] })}
        />
      </Svg>
      <Animated.View style={{ position: "absolute", left: box.x, top: box.y, width: w, height: h, opacity: mark, transform: [{ translateX: mark.interpolate({ inputRange: [0, 1], outputRange: [-14, 0] }) }] }}>
        <Image source={require("../../assets/brand/flo-wordmark-navy.png")} style={{ width: "100%", height: "100%", tintColor: c.brand }} resizeMode="contain" />
      </Animated.View>
      <Animated.View style={[st.sources, { top: box.y + h + 28, opacity: chips, transform: [{ translateY: chips.interpolate({ inputRange: [0, 1], outputRange: [6, 0] }) }] }]}>
        {SOURCES.map(([key, name]) => {
          const src = sources[key];
          const color = !src ? c.seriesGrey : src.ok || src.stale ? c.pos : c.neg;
          return (
            <View key={key} style={st.src}>
              <View style={[st.dot, { backgroundColor: color }]} />
              <Text style={{ fontFamily: font.uiMedium, fontSize: 11.5, color: src ? c.ink2 : c.faint }}>{name}</Text>
            </View>
          );
        })}
      </Animated.View>
    </Animated.View>
  );
}

const st = StyleSheet.create({
  sources: { position: "absolute", left: 24, right: 24, flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: 12, rowGap: 8 },
  src: { flexDirection: "row", alignItems: "center", gap: 5 },
  dot: { width: 6, height: 6, borderRadius: 3 },
});
