/* The FLO letters with a needle that stitches a thread through them, as on the web landing page
   (frontend/src/world/NeedleFLO.tsx): behind the F, over the L, behind the left of the O, through its counter and out
   over its right side. The thread is drawn twice, under the letters and over them clipped to the "over" stretches,
   so it really weaves; the needle too. The path is sampled once here so the needle can ride it frame by frame. */
import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, Easing, Image, View } from "react-native";
import Svg, { ClipPath, Defs, Ellipse, G, Path, Rect } from "react-native-svg";
import { useTheme } from "../lib/theme";

/** seconds the needle takes to stitch through the letters */
export const STITCH = 5.2;

const THREAD =
  "M -875 30 C -560 30, -240 150, 0 128 C 60 122, 100 132, 128 112 C 150 98, 160 70, 186 56 C 215 40, 245 70, 262 100 " +
  "C 280 130, 300 118, 330 104 C 370 86, 405 80, 432 74 C 520 56, 640 0, 860 -6 C 1040 -12, 1200 30, 1325 20";

// stretches where the thread runs over the letters (letter units)
const FRONT = [
  [132, 258],
  [398, 1400],
];

// what a phone shows of the thread: a little either side of the 450 x 165 letters
const VB = { x: -30, y: -22, w: 510, h: 208 };
const NEEDLE_LEN = 86 * 1.3;

type Pt = { x: number; y: number; s: number };

/** Points along the thread with the running length, so a fraction of the length maps to a place and a direction. */
function sample(): { pts: Pt[]; len: number } {
  const n = THREAD.match(/-?\d+(\.\d+)?/g)!.map(Number);
  let [x0, y0] = [n[0], n[1]];
  const pts: Pt[] = [{ x: x0, y: y0, s: 0 }];
  let s = 0;
  for (let i = 2; i + 5 < n.length; i += 6) {
    const [x1, y1, x2, y2, x3, y3] = n.slice(i, i + 6);
    for (let k = 1; k <= 60; k++) {
      const t = k / 60;
      const u = 1 - t;
      const x = u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3;
      const y = u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3;
      const p = pts[pts.length - 1];
      s += Math.hypot(x - p.x, y - p.y);
      pts.push({ x, y, s });
    }
    [x0, y0] = [x3, y3];
  }
  return { pts, len: s };
}

function at(pts: Pt[], s: number): { x: number; y: number; deg: number } {
  let lo = 0;
  let hi = pts.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (pts[mid].s < s) lo = mid;
    else hi = mid;
  }
  const a = pts[lo];
  const b = pts[hi];
  const f = b.s > a.s ? (s - a.s) / (b.s - a.s) : 0;
  return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, deg: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI };
}

const { pts, len } = sample();
// start where the visible part begins, so the needle is in view from the first frame
const from = pts.find((p) => p.x >= VB.x - 8)?.s ?? 0;
// where the thread leaves the right edge: the glint only needs to run across what is on screen
const to = pts.find((p) => p.x >= VB.x + VB.w + 8)?.s ?? len;
const GLINT = 34;

const AnimatedPath = Animated.createAnimatedComponent(Path);

const ease = (t: number) => -(Math.cos(Math.PI * t) - 1) / 2; // sine.inOut, as on the web

function Needle({ x, y, deg, body, eye }: { x: number; y: number; deg: number; body: string; eye: string }) {
  // tip on the thread, the eye trailing behind
  return (
    <G transform={`translate(${x} ${y}) rotate(${deg}) translate(${-NEEDLE_LEN} 0) scale(1.3)`}>
      <Path d="M 86 0 L 14 -2.1 Q 0 -2.6 0 0 Q 0 2.6 14 2.1 Z" fill={body} />
      <Ellipse cx={9} cy={0} rx={5} ry={0.85} fill={eye} />
    </G>
  );
}

/** `onDone` fires as the needle leaves the O, which is when the headline should come in. */
export function NeedleFLO({ width, onDone, play = true }: { width: number; onDone?: () => void; play?: boolean }) {
  const c = useTheme();
  const [p, setP] = useState(0);
  const [fade] = useState(() => new Animated.Value(0));
  const [glint] = useState(() => new Animated.Value(from - GLINT));
  const [stitched, setStitched] = useState(false);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  useEffect(() => {
    if (!play) return;
    let raf = 0;
    let cancelled = false;
    let fired = false;
    Animated.timing(fade, { toValue: 1, duration: 1400, useNativeDriver: true }).start();
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (cancelled) return;
      if (reduce) {
        setP(1);
        done.current?.();
        return;
      }
      const t0 = Date.now() + 100;
      const tick = () => {
        const t = Math.min(1, Math.max(0, (Date.now() - t0) / (STITCH * 1000)));
        setP(t);
        if (!fired && t >= 0.72) {
          fired = true;
          done.current?.();
        }
        if (t < 1) raf = requestAnimationFrame(tick);
        else setStitched(true);
      };
      raf = requestAnimationFrame(tick);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [play, fade]);

  // afterwards a short glint keeps running along the thread, like a signal through a wire
  useEffect(() => {
    if (!stitched) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(glint, { toValue: to, duration: 2600, easing: Easing.inOut(Easing.sin), useNativeDriver: false }),
        Animated.delay(2400),
        Animated.timing(glint, { toValue: from - GLINT, duration: 0, useNativeDriver: false }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [stitched, glint]);

  const s = from + (len - from) * ease(p);
  const n = at(pts, s);
  const showNeedle = p > 0.01 && p < 0.985 && n.x < VB.x + VB.w + NEEDLE_LEN;
  const k = width / VB.w;
  const height = VB.h * k;
  const thread = { d: THREAD, fill: "none", stroke: c.accent, strokeWidth: 2.4, strokeLinecap: "round" as const, strokeDasharray: `${len} ${len}`, strokeDashoffset: len - s };
  const needle = { ...n, body: c.ink2, eye: c.frame };
  const shine = stitched && (
    <AnimatedPath
      d={THREAD}
      fill="none"
      stroke={c.dark ? "#ffffff" : c.sheet}
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeDasharray={`${GLINT} ${len * 2}`}
      strokeDashoffset={glint.interpolate({ inputRange: [0, len], outputRange: [0, -len] })}
    />
  );
  const viewBox = `${VB.x} ${VB.y} ${VB.w} ${VB.h}`;

  return (
    <View style={{ width, height }} accessible accessibilityRole="image" accessibilityLabel="FLO">
      <Svg width={width} height={height} viewBox={viewBox} style={{ position: "absolute" }}>
        <Path {...thread} />
        {shine}
        {showNeedle && <Needle {...needle} />}
      </Svg>
      <Animated.View style={{ position: "absolute", left: -VB.x * k, top: -VB.y * k, width: 450 * k, height: 165 * k, opacity: fade }}>
        <Image source={require("../../assets/world/flo-letters.png")} style={{ width: "100%", height: "100%", tintColor: c.brand }} resizeMode="stretch" />
      </Animated.View>
      <Svg width={width} height={height} viewBox={viewBox} style={{ position: "absolute" }}>
        <Defs>
          <ClipPath id="flo-front">
            {FRONT.map(([a, b]) => (
              <Rect key={a} x={a} y={-200} width={b - a} height={600} />
            ))}
          </ClipPath>
        </Defs>
        <G clipPath="url(#flo-front)">
          <Path {...thread} />
          {shine}
          {showNeedle && <Needle {...needle} />}
        </G>
      </Svg>
    </View>
  );
}
