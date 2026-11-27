/* Motion helpers for the FLO World screens: the reduce-motion setting, the "live" ping dot, scroll reveals and the
   count-up of live numbers. They follow the web page's GSAP timings (frontend/src/world/). */
import { Children, createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AccessibilityInfo, Animated, Easing, Text, View, type StyleProp, type TextStyle, type ViewStyle } from "react-native";
import { fmtKpi } from "../lib/format";
import type { Fmt } from "../lib/types";

/** True when the phone asks for less motion: every animation then shows its end state at once. */
export function useReducedMotion(): boolean | null {
  const [r, setR] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((v) => alive && setR(v));
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setR);
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return r;
}

export const expoOut = Easing.bezier(0.16, 1, 0.3, 1);
export const power3Out = Easing.bezier(0.215, 0.61, 0.355, 1);
export const power2InOut = Easing.bezier(0.455, 0.03, 0.515, 0.955);
export const expoIn = Easing.bezier(0.7, 0, 0.84, 0);

/** A status dot with a ring that keeps rippling out from it (the web's w-ping). */
export function Pulse({ color, size = 8, style }: { color: string; size?: number; style?: StyleProp<ViewStyle> }) {
  const [v] = useState(() => new Animated.Value(0));
  const reduce = useReducedMotion();
  useEffect(() => {
    if (reduce !== false) return;
    const loop = Animated.loop(Animated.timing(v, { toValue: 1, duration: 2000, easing: expoOut, useNativeDriver: true }));
    loop.start();
    return () => loop.stop();
  }, [v, reduce]);
  return (
    <View style={[{ width: size, height: size }, style]}>
      <Animated.View
        style={{
          position: "absolute",
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: color,
          opacity: v.interpolate({ inputRange: [0, 1], outputRange: [0.6, 0] }),
          transform: [{ scale: v.interpolate({ inputRange: [0, 1], outputRange: [1, 3.2] }) }],
        }}
      />
      <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }} />
    </View>
  );
}

/* Scroll reveals: the screen shares its scroll position; a block rises in the first time it comes into view. */
interface ScrollCtx {
  y: Animated.Value;
  height: number;
}
const Ctx = createContext<ScrollCtx | null>(null);
export const ScrollProvider = ({ value, children }: { value: ScrollCtx; children: ReactNode }) => <Ctx.Provider value={value}>{children}</Ctx.Provider>;

/** Calls `onShow` once, when the block's top passes `at` (0..1) of the screen height. Returns the onLayout to attach. */
function useOnShow(onShow: () => void, at = 0.85) {
  const ctx = useContext(Ctx);
  const top = useRef<number | null>(null);
  const shown = useRef(false);
  const fire = useRef(onShow);
  useEffect(() => {
    fire.current = onShow;
  }, [onShow]);
  useEffect(() => {
    if (!ctx) return;
    const check = (y: number) => {
      if (shown.current || top.current === null) return;
      if (top.current < y + ctx.height * at) {
        shown.current = true;
        fire.current();
      }
    };
    const id = ctx.y.addListener(({ value }) => check(value));
    return () => ctx.y.removeListener(id);
  }, [ctx, at]);
  return (yInContent: number) => {
    top.current = yInContent;
    if (!ctx || shown.current) return;
    // already on screen when laid out
    const now = (ctx.y as unknown as { __getValue: () => number }).__getValue();
    if (yInContent < now + ctx.height * at) {
      shown.current = true;
      fire.current();
    }
  };
}

/** Blocks that rise and fade in one after another (stagger, seconds) the first time they scroll into view. Each direct
 *  child is one block. `offset` is where this group's parent sits in the scrolling content. */
export function Reveal({ children, offset = 0, stagger = 0.08, style, distance = 28, gap, onShow }: { children: ReactNode; offset?: number; stagger?: number; style?: StyleProp<ViewStyle>; distance?: number; gap?: number; onShow?: () => void }) {
  const items = Children.toArray(children);
  const [vals] = useState(() => items.map(() => new Animated.Value(0)));
  const reduce = useReducedMotion();
  const place = useOnShow(() => {
    onShow?.();
    if (reduce) return vals.forEach((v) => v.setValue(1));
    Animated.stagger(
      stagger * 1000,
      vals.map((v) => Animated.timing(v, { toValue: 1, duration: 900, easing: power3Out, useNativeDriver: true })),
    ).start();
  });
  useEffect(() => {
    if (reduce) vals.forEach((v) => v.setValue(1));
  }, [reduce, vals]);
  return (
    <View onLayout={(e) => place(offset + e.nativeEvent.layout.y)} style={[{ gap }, style]}>
      {items.map((child, i) => {
        const v = vals[i];
        if (!v) return child;
        return (
          <Animated.View key={i} style={{ opacity: v, transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [distance, 0] }) }] }}>
            {child}
          </Animated.View>
        );
      })}
    </View>
  );
}

/** A live figure that counts up from zero the first time it is shown (expo out, 1.6 s). */
export function CountUp({ value, format, style, run }: { value: number | string | null; format: Fmt; style?: StyleProp<TextStyle>; run: boolean }) {
  const reduce = useReducedMotion();
  const target = typeof value === "number" ? value : null;
  const [shown, setShown] = useState<number | null>(target === null ? null : 0);
  const started = useRef(false);
  useEffect(() => {
    if (target === null || !run || started.current || reduce === null) return;
    started.current = true;
    const t0 = Date.now();
    let raf = 0;
    if (reduce) {
      raf = requestAnimationFrame(() => setShown(target));
      return () => cancelAnimationFrame(raf);
    }
    const tick = () => {
      const t = Math.min(1, (Date.now() - t0) / 1600);
      const k = t === 1 ? 1 : 1 - 2 ** (-10 * t);
      setShown(target * k);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run, reduce]);
  const v = target === null ? value : format === "int" || format === "inr" ? Math.round(shown ?? 0) : (shown ?? 0);
  return <Text style={style}>{fmtKpi(v as number | string | null, format).value}</Text>;
}

export { useOnShow };
